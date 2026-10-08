import { describe, expect, it } from "vitest";

import { SyntheticCaptureAdapter } from "./capture";

describe("SyntheticCaptureAdapter", () => {
  it("preserves interruption gaps and idempotent acknowledgements", () => {
    const adapter = new SyntheticCaptureAdapter();
    adapter.dispatch("start");
    adapter.acknowledgeChunk(1);
    adapter.dispatch("interrupt", 1200);
    adapter.acknowledgeChunk(1);
    adapter.dispatch("recover", 1800);
    adapter.acknowledgeChunk(2);
    adapter.dispatch("stop");
    adapter.dispatch("upload");
    const completed = adapter.dispatch("complete");
    expect(completed.state).toBe("complete");
    expect(completed.acknowledgedChunks).toBe(2);
    expect(completed.gaps).toEqual([
      { startMs: 1200, endMs: 1800, reason: "synthetic_interruption" },
    ]);
  });

  it("rejects silent chunk loss", () => {
    const adapter = new SyntheticCaptureAdapter();
    adapter.dispatch("start");
    expect(() => adapter.acknowledgeChunk(2)).toThrow("chunk_sequence_gap");
  });
});
