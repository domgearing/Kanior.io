import type { CaptureSnapshot } from "./capture";

export interface CaptureApiConfiguration {
  baseUrl: string;
  csrfToken: string;
  origin: string;
  adapter: "synthetic" | "recall_desktop";
}

export interface FinalizedCapture extends CaptureSnapshot {
  sourceAssetId?: string;
  ingestionId?: string;
}

export interface RecallUploadGrant {
  uploadToken: string;
  sdkUploadId: string;
  captureMode: "audio_only";
}

export interface TranscriptionProgress {
  state: string;
  stage: string;
  safeErrorCode: string | null;
}

/** Authenticated persistence boundary; enabled after the desktop session flow is connected. */
export class CaptureApiClient {
  constructor(
    private readonly configuration: CaptureApiConfiguration,
    private readonly request: typeof fetch = fetch,
  ) {}

  async create(documentId: string): Promise<CaptureSnapshot> {
    return this.send("/api/v1/capture-sessions", "POST", {
      document_id: documentId,
    });
  }

  async recover(captureSessionId: string): Promise<CaptureSnapshot> {
    return this.send(`/api/v1/capture-sessions/${captureSessionId}`, "GET");
  }

  async transcriptionProgress(ingestionId: string): Promise<TranscriptionProgress> {
    const value = await this.raw(`/api/v1/ingestions/${ingestionId}`, "GET");
    return {
      state: value.state as string,
      stage: value.stage as string,
      safeErrorCode: (value.safe_error_code as string | null) ?? null,
    };
  }

  async createRecallUpload(
    captureSessionId: string,
  ): Promise<RecallUploadGrant> {
    const response = await this.raw(
      `/api/v1/capture-sessions/${captureSessionId}/recall-upload`,
      "POST",
      { operation_key: `recall-upload:${captureSessionId}` },
    );
    return {
      uploadToken: response.upload_token as string,
      sdkUploadId: response.sdk_upload_id as string,
      captureMode: response.capture_mode as "audio_only",
    };
  }

  async transition(
    captureSessionId: string,
    event: string,
    atMs = 0,
  ): Promise<CaptureSnapshot> {
    return this.send(
      `/api/v1/capture-sessions/${captureSessionId}/transitions`,
      "POST",
      { event, at_ms: atMs },
    );
  }

  async putChunk(
    captureSessionId: string,
    sequence: number,
    contentBase64: string,
    sha256: string,
  ): Promise<CaptureSnapshot> {
    return this.send(
      `/api/v1/capture-sessions/${captureSessionId}/chunks/${sequence}`,
      "PUT",
      { sequence, content_base64: contentBase64, sha256 },
    );
  }

  async finalize(
    captureSessionId: string,
    filename: string,
    durationMs: number,
    detectedMime: "audio/wav" | "audio/mpeg" | "audio/mp4" | "audio/webm",
  ): Promise<FinalizedCapture> {
    const result = await this.send(
      `/api/v1/capture-sessions/${captureSessionId}/finalize`,
      "POST",
      { filename, duration_ms: durationMs, detected_mime: detectedMime },
    );
    return result;
  }

  private async send(
    path: string,
    method: "GET" | "POST" | "PUT",
    body?: object,
  ): Promise<CaptureSnapshot> {
    const value = await this.raw(path, method, body);
    return {
      captureSessionId: value.capture_session_id as string,
      state: value.state as CaptureSnapshot["state"],
      acknowledgedChunks: value.acknowledged_chunks as number,
      gaps: (value.gaps as Array<Record<string, unknown>>).map((gap) => ({
        startMs: gap.start_ms as number,
        endMs: gap.end_ms as number | null,
        reason: gap.reason as string,
      })),
      adapter: this.configuration.adapter,
      ...(value.source_asset_id
        ? { sourceAssetId: value.source_asset_id as string }
        : {}),
      ...(value.ingestion_id
        ? { ingestionId: value.ingestion_id as string }
        : {}),
    };
  }

  private async raw(
    path: string,
    method: "GET" | "POST" | "PUT",
    body?: object,
  ): Promise<Record<string, unknown>> {
    const response = await this.request(
      `${this.configuration.baseUrl}${path}`,
      {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": this.configuration.csrfToken,
          Origin: this.configuration.origin,
        },
        body: body ? JSON.stringify(body) : undefined,
      },
    );
    if (!response.ok) throw new Error(`capture_api_${response.status}`);
    return (await response.json()) as Record<string, unknown>;
  }
}
