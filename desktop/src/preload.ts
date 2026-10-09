import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("vereloDesktop", {
  platform: process.platform,
  auth: {
    onExpired: (callback: () => void) =>
      ipcRenderer.on("auth:expired", callback),
    onSignedIn: (callback: () => void) =>
      ipcRenderer.on("auth:signed-in", callback),
    mode: () => ipcRenderer.invoke("auth:mode"),
    status: () => ipcRenderer.invoke("auth:status"),
    open: () => ipcRenderer.invoke("auth:open"),
    complete: (link: string) => ipcRenderer.invoke("auth:complete", link),
    logout: () => ipcRenderer.invoke("auth:logout"),
  },
  meetings: {
    projects: () => ipcRenderer.invoke("meetings:projects"),
    createProject: (name: string) =>
      ipcRenderer.invoke("meetings:create-project", name),
    clear: () => ipcRenderer.invoke("meetings:clear"),
    list: (projectId: string) => ipcRenderer.invoke("meetings:list", projectId),
    create: (projectId: string, title: string) =>
      ipcRenderer.invoke("meetings:create", projectId, title),
    select: (documentId: string) =>
      ipcRenderer.invoke("meetings:select", documentId),
    history: () => ipcRenderer.invoke("meetings:history"),
    review: (ingestionId: string) =>
      ipcRenderer.invoke("meetings:review", ingestionId),
    audio: (ingestionId: string) =>
      ipcRenderer.invoke("meetings:audio", ingestionId),
    waveform: (ingestionId: string) =>
      ipcRenderer.invoke("meetings:waveform", ingestionId),
    retry: (ingestionId: string) =>
      ipcRenderer.invoke("meetings:retry", ingestionId),
  },
  capture: {
    connection: () => ipcRenderer.invoke("recorder:connection"),
    onRemoteState: (
      callback: (value: { action: string; documentId: string | null }) => void,
    ) =>
      ipcRenderer.on("capture:remote-state", (_event, value) =>
        callback(value),
      ),
    mode: () => ipcRenderer.invoke("capture:mode"),
    current: () => ipcRenderer.invoke("capture:current"),
    progress: () => ipcRenderer.invoke("capture:progress"),
    create: () => ipcRenderer.invoke("capture:create"),
    dispatch: (action: string, atMs?: number) =>
      ipcRenderer.invoke("capture:dispatch", action, atMs),
    uploadChunk: (contentBase64: string) =>
      ipcRenderer.invoke("capture:chunk", contentBase64),
    finalize: (durationMs: number) =>
      ipcRenderer.invoke("capture:finalize", durationMs),
  },
});
