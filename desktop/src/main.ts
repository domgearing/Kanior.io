import { createHash, randomUUID } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import RecallAiSdk, {
  type MeetingDetectedEvent,
  type NetworkStatusEvent,
} from "@recallai/desktop-sdk";

import {
  app,
  BrowserWindow,
  desktopCapturer,
  ipcMain,
  session,
} from "electron";

import { desktopApplicationName } from "./app-info";
import { CaptureApiClient, type FinalizedCapture } from "./capture-api";
import { SyntheticCaptureAdapter, type CaptureSnapshot } from "./capture";

const synthetic = new SyntheticCaptureAdapter();
const apiBase = (process.env.VERELO_DESKTOP_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const publicOrigin = new URL(process.env.VERELO_PUBLIC_ORIGIN ?? "http://127.0.0.1:5173").origin;
const captureProvider = process.env.VERELO_DESKTOP_CAPTURE_PROVIDER;
const recallApiUrl = process.env.VERELO_RECALL_API_BASE_URL;
const recallEnabled = captureProvider === "recall_desktop" && Boolean(recallApiUrl);
let client: CaptureApiClient | null = null;
let selectedDocumentId: string | null = null;
let loginWindow: BrowserWindow | null = null;

function expireSession(): void {
  client = null;
  selectedDocumentId = null;
  for (const window of BrowserWindow.getAllWindows()) {
    window.webContents.send("auth:expired");
  }
}

async function apiRequest(pathname: string, method = "GET", body?: object): Promise<Record<string, unknown>> {
  const response = await session.defaultSession.fetch(`${apiBase}${pathname}`, {
    method,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Origin: publicOrigin,
      ...(method === "GET" ? {} : { "X-CSRF-Token": await csrf() }),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401) expireSession();
  if (!response.ok) throw new Error(`verelo_api_${response.status}`);
  return (await response.json()) as Record<string, unknown>;
}

async function csrf(): Promise<string> {
  const me = await session.defaultSession.fetch(`${apiBase}/api/v1/me`, { credentials: "include" });
  if (!me.ok) {
    expireSession();
    throw new Error("sign_in_required");
  }
  const identity = (await me.json()) as Record<string, unknown>;
  return identity.csrf_token as string;
}

async function authenticationStatus(): Promise<{ signedIn: boolean; displayName?: string; canCreateProject?: boolean }> {
  try {
    const response = await session.defaultSession.fetch(`${apiBase}/api/v1/me`, { credentials: "include" });
    if (!response.ok) {
      client = null;
      return { signedIn: false };
    }
    const me = (await response.json()) as Record<string, unknown>;
    client = new CaptureApiClient(
      { baseUrl: apiBase, csrfToken: me.csrf_token as string, origin: publicOrigin,
        adapter: recallEnabled ? "recall_desktop" : "synthetic" },
      async (input, init) => {
        const response = await session.defaultSession.fetch(
          input instanceof URL ? input.toString() : input, init,
        );
        if (response.status === 401) expireSession();
        return response;
      },
    );
    const capabilities = Array.isArray(me.capabilities) ? me.capabilities : [];
    return {
      signedIn: true,
      displayName: me.display_name as string,
      canCreateProject: capabilities.includes("projects:create"),
    };
  } catch {
    client = null;
    return { signedIn: false };
  }
}

ipcMain.handle("auth:status", () => authenticationStatus());
ipcMain.handle("auth:mode", () => apiRequest("/api/v1/auth/mode"));
ipcMain.handle("auth:open", async () => {
  if (loginWindow && !loginWindow.isDestroyed()) {
    loginWindow.focus();
    return;
  }
  loginWindow = new BrowserWindow({ width: 850, height: 700, title: "Sign in to Verelo",
    webPreferences: { contextIsolation: true, nodeIntegration: false } });
  loginWindow.on("closed", () => { loginWindow = null; });
  loginWindow.webContents.on("did-navigate", (_event, url) => {
    if (new URL(url).origin !== publicOrigin) return;
    void authenticationStatus().then((result) => {
      if (!result.signedIn) return;
      for (const window of BrowserWindow.getAllWindows()) {
        if (window !== loginWindow) window.webContents.send("auth:signed-in");
      }
      loginWindow?.close();
    });
  });
  await loginWindow.loadURL(publicOrigin);
});
ipcMain.handle("auth:complete", async (_event, link: unknown) => {
  if (typeof link !== "string") throw new Error("invalid_sign_in_link");
  const url = new URL(link);
  if (url.origin !== publicOrigin || url.pathname !== "/auth/verify" || !url.hash.startsWith("#token=")) {
    throw new Error("invalid_sign_in_link");
  }
  if (!loginWindow || loginWindow.isDestroyed()) throw new Error("open_sign_in_first");
  await loginWindow.loadURL(url.toString());
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const status = await authenticationStatus();
    if (status.signedIn) {
      loginWindow.close();
      return status;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("sign_in_link_not_accepted");
});
ipcMain.handle("auth:logout", async () => {
  await apiRequest("/api/v1/auth/logout", "POST");
  client = null;
  selectedDocumentId = null;
  return { signedIn: false };
});
ipcMain.handle("meetings:projects", async () => {
  const response = await apiRequest("/api/v1/projects");
  return response.items;
});
ipcMain.handle("meetings:create-project", async (_event, name: unknown) => {
  if (typeof name !== "string" || !name.trim() || name.trim().length > 200) {
    throw new Error("invalid_project_name");
  }
  return apiRequest("/api/v1/projects", "POST", { name: name.trim() });
});
ipcMain.handle("meetings:clear", () => {
  selectedDocumentId = null;
});
ipcMain.handle("meetings:list", async (_event, projectId: unknown) => {
  if (typeof projectId !== "string" || !/^[0-9a-f-]{36}$/i.test(projectId)) throw new Error("invalid_project_id");
  const response = await apiRequest(`/api/v1/projects/${projectId}/documents`);
  return response.items;
});
ipcMain.handle("meetings:create", async (_event, projectId: unknown, title: unknown) => {
  if (typeof projectId !== "string" || !/^[0-9a-f-]{36}$/i.test(projectId) ||
      typeof title !== "string" || !title.trim() || title.length > 200) throw new Error("invalid_meeting");
  return apiRequest(`/api/v1/projects/${projectId}/documents`, "POST", {
    title: title.trim(), meeting_date: new Date().toISOString(), language: "en-US",
    consent_acknowledged: true, consent_policy_version: "synthetic-consent-v1",
  });
});
ipcMain.handle("meetings:select", async (_event, documentId: unknown) => {
  if (typeof documentId !== "string" || !/^[0-9a-f-]{36}$/i.test(documentId)) throw new Error("invalid_document_id");
  const document = await apiRequest(`/api/v1/documents/${documentId}`);
  selectedDocumentId = document.document_id as string;
  return document;
});
ipcMain.handle("meetings:history", async () => {
  if (!selectedDocumentId) return [];
  const response = await apiRequest(`/api/v1/documents/${selectedDocumentId}/ingestions`);
  return response.items;
});
ipcMain.handle("meetings:retry", async (_event, ingestionId: unknown) => {
  if (!selectedDocumentId || typeof ingestionId !== "string" ||
      !/^[0-9a-f-]{36}$/i.test(ingestionId)) throw new Error("invalid_ingestion_id");
  const response = await apiRequest(`/api/v1/documents/${selectedDocumentId}/ingestions`);
  const items = response.items as Array<Record<string, unknown>>;
  if (!items.some((item) => item.ingestion_id === ingestionId && item.can_retry === true)) {
    throw new Error("ingestion_not_retryable_in_selected_meeting");
  }
  return apiRequest(`/api/v1/ingestions/${ingestionId}/retry`, "POST", {
    operation_key: `desktop-retry-${randomUUID()}`,
  });
});

let captureSessionId: string | null = null;
let nextSequence = 1;
let recallWindowId: string | null = null;
let recallInitialized = false;

async function initializeRecall(): Promise<void> {
  if (!recallEnabled || !recallApiUrl || recallInitialized) return;
  RecallAiSdk.addEventListener("meeting-detected", (event: MeetingDetectedEvent) => {
    recallWindowId = event.window.id;
  });
  RecallAiSdk.addEventListener("network-status", (event: NetworkStatusEvent) => {
    if (!client || !captureSessionId) return;
    const action = event.status === "disconnected" ? "interrupt" : "recover";
    void client.transition(captureSessionId, action, Date.now()).catch(() => undefined);
  });
  RecallAiSdk.addEventListener("shutdown", () => {
    if (client && captureSessionId) {
      void client.transition(captureSessionId, "interrupt", Date.now()).catch(() => undefined);
    }
  });
  await RecallAiSdk.init({ apiUrl: recallApiUrl });
  recallInitialized = true;
}

function recoveryPath(): string {
  return path.join(app.getPath("userData"), "active-capture.json");
}

function persistRecovery(): void {
  writeFileSync(
    recoveryPath(),
    JSON.stringify({ captureSessionId, nextSequence }),
    {
      encoding: "utf8",
      mode: 0o600,
    },
  );
}

function loadRecovery(): void {
  const location = recoveryPath();
  if (!existsSync(location)) return;
  try {
    const value = JSON.parse(readFileSync(location, "utf8")) as Record<
      string,
      unknown
    >;
    if (typeof value.captureSessionId === "string")
      captureSessionId = value.captureSessionId;
    if (
      Number.isSafeInteger(value.nextSequence) &&
      Number(value.nextSequence) > 0
    ) {
      nextSequence = Number(value.nextSequence);
    }
  } catch {
    captureSessionId = null;
    nextSequence = 1;
  }
}

async function current(): Promise<CaptureSnapshot> {
  if (!client || !captureSessionId) return synthetic.current();
  try {
    const state = await client.recover(captureSessionId);
    nextSequence = state.acknowledgedChunks + 1;
    persistRecovery();
    return state;
  } catch {
    captureSessionId = null;
    nextSequence = 1;
    return synthetic.current();
  }
}

ipcMain.handle("capture:mode", () => ({
  connected: Boolean(client && selectedDocumentId),
  configuredDocumentId: selectedDocumentId,
  adapter: recallEnabled ? "recall_desktop" : "synthetic",
}));
ipcMain.handle("capture:current", () => current());
ipcMain.handle("capture:progress", async () => {
  if (!client || !captureSessionId) return null;
  const capture = await current();
  if (!capture.ingestionId) return { state: capture.state, stage: "recall_upload", safeErrorCode: null };
  return client.transcriptionProgress(capture.ingestionId);
});
ipcMain.handle("capture:create", async () => {
  if (!client || !selectedDocumentId) throw new Error("sign_in_and_select_meeting_first");
  const state = await client.create(selectedDocumentId);
  captureSessionId = state.captureSessionId;
  nextSequence = 1;
  persistRecovery();
  return state;
});
ipcMain.handle(
  "capture:dispatch",
  async (_event, action: unknown, atMs: unknown) => {
    if (
      typeof action !== "string" ||
      (atMs !== undefined && typeof atMs !== "number")
    ) {
      throw new Error("invalid_capture_request");
    }
    if (!client) throw new Error("sign_in_required");
    if (!captureSessionId) throw new Error("capture_session_required");
    if (recallEnabled) {
      await initializeRecall();
      if (action === "start") {
        recallWindowId ??= await RecallAiSdk.prepareDesktopAudioRecording();
        const grant = await client.createRecallUpload(captureSessionId);
        await RecallAiSdk.startRecording({
          windowId: recallWindowId,
          uploadToken: grant.uploadToken,
          disableRawMedia: true,
        });
      } else if (action === "pause" && recallWindowId) {
        await RecallAiSdk.pauseRecording({ windowId: recallWindowId });
      } else if (action === "resume" && recallWindowId) {
        await RecallAiSdk.resumeRecording({ windowId: recallWindowId });
      } else if (action === "stop" && recallWindowId) {
        await RecallAiSdk.stopRecording({ windowId: recallWindowId });
      }
    }
    const event = action === "complete" ? "upload" : action;
    return client.transition(captureSessionId, event, atMs ?? 0);
  },
);
ipcMain.handle("capture:chunk", async (_event, contentBase64: unknown) => {
  if (typeof contentBase64 !== "string" || contentBase64.length === 0) {
    throw new Error("invalid_capture_chunk");
  }
  if (!client || !captureSessionId) throw new Error("capture_session_required");
  if (recallEnabled) throw new Error("recall_upload_managed_by_sdk");
  const bytes = Buffer.from(contentBase64, "base64");
  if (bytes.byteLength === 0 || bytes.byteLength > 5 * 1024 * 1024) {
    throw new Error("invalid_capture_chunk");
  }
  const sequence = nextSequence;
  const state = await client.putChunk(
    captureSessionId,
    sequence,
    contentBase64,
    createHash("sha256").update(bytes).digest("hex"),
  );
  nextSequence = state.acknowledgedChunks + 1;
  persistRecovery();
  return state;
});
ipcMain.handle("capture:finalize", async (_event, durationMs: unknown) => {
  if (!Number.isSafeInteger(durationMs) || Number(durationMs) < 0) {
    throw new Error("invalid_capture_duration");
  }
  if (!client || !captureSessionId) throw new Error("capture_session_required");
  if (recallEnabled) return current();
  const result: FinalizedCapture = await client.finalize(
    captureSessionId,
    `meeting-${captureSessionId}.webm`,
    Number(durationMs),
    "audio/webm",
  );
  return result;
});

const createWindow = () => {
  const window = new BrowserWindow({
    width: 960,
    height: 720,
    minWidth: 720,
    minHeight: 540,
    title: desktopApplicationName,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });

  void window.loadFile(path.join(__dirname, "renderer", "index.html"));
};

app.whenReady().then(() => {
  app.setName(desktopApplicationName);
  loadRecovery();
  void initializeRecall().catch(() => undefined);
  session.defaultSession.setDisplayMediaRequestHandler(
    (_request, callback) => {
      void desktopCapturer
        .getSources({
          types: ["screen", "window"],
          thumbnailSize: { width: 0, height: 0 },
        })
        .then((sources) => {
          const source = sources[0];
          if (!source) return callback({});
          callback({
            video: source,
            ...(process.platform === "win32"
              ? { audio: "loopback" as const }
              : {}),
          });
        })
        .catch(() => callback({}));
    },
    { useSystemPicker: true },
  );
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
