import { describe, expect, it, vi } from "vitest";

import { CaptureApiClient } from "./capture-api";

describe("CaptureApiClient", () => {
  it("recovers database state without exposing provider credentials", async () => {
    const request = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          capture_session_id: "capture-1",
          state: "interrupted",
          acknowledged_chunks: 2,
          gaps: [{ start_ms: 10, end_ms: null, reason: "device" }],
        }),
        { status: 200 },
      ),
    );
    const client = new CaptureApiClient(
      {
        baseUrl: "http://127.0.0.1:8000",
        csrfToken: "synthetic-token",
        origin: "http://127.0.0.1:5173",
        adapter: "synthetic",
      },
      request,
    );
    const recovered = await client.recover("capture-1");
    expect(recovered.acknowledgedChunks).toBe(2);
    expect(request).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/capture-sessions/capture-1",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("creates, uploads, and finalizes through the authenticated persistence boundary", async () => {
    const response = () =>
      new Response(
        JSON.stringify({
          capture_session_id: "capture-2",
          state: "recording",
          acknowledged_chunks: 1,
          gaps: [],
          source_asset_id: "source-1",
          ingestion_id: "ingestion-1",
        }),
        { status: 200 },
      );
    const transport = vi.fn().mockImplementation(response);
    const client = new CaptureApiClient(
      {
        baseUrl: "http://127.0.0.1:8000",
        csrfToken: "synthetic-csrf",
        origin: "http://127.0.0.1:5173",
        adapter: "synthetic",
      },
      transport,
    );

    await client.create("document-1");
    await client.putChunk("capture-2", 1, "YWJj", "digest");
    const finalized = await client.finalize(
      "capture-2",
      "meeting.webm",
      1000,
      "audio/webm",
    );

    expect(finalized.ingestionId).toBe("ingestion-1");
    expect(transport.mock.calls[0][1].headers).not.toHaveProperty("Cookie");
    expect(transport).toHaveBeenNthCalledWith(
      1,
      "http://127.0.0.1:8000/api/v1/capture-sessions",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          "X-CSRF-Token": "synthetic-csrf",
        }),
      }),
    );
    expect(transport).toHaveBeenNthCalledWith(
      2,
      "http://127.0.0.1:8000/api/v1/capture-sessions/capture-2/chunks/1",
      expect.objectContaining({ method: "PUT" }),
    );
    expect(transport).toHaveBeenNthCalledWith(
      3,
      "http://127.0.0.1:8000/api/v1/capture-sessions/capture-2/finalize",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
