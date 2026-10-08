import { randomUUID } from "node:crypto";

export type CaptureState =
  | "idle"
  | "recording"
  | "paused"
  | "interrupted"
  | "finalizing"
  | "uploading"
  | "complete"
  | "failed";

export interface RecordingGap {
  startMs: number;
  endMs: number | null;
  reason: string;
}

export interface CaptureSnapshot {
  captureSessionId: string;
  state: CaptureState;
  acknowledgedChunks: number;
  gaps: RecordingGap[];
  adapter: "synthetic" | "recall_desktop";
  sourceAssetId?: string;
  ingestionId?: string;
}

export class SyntheticCaptureAdapter {
  private snapshot: CaptureSnapshot = {
    captureSessionId: randomUUID(),
    state: "idle",
    acknowledgedChunks: 0,
    gaps: [],
    adapter: "synthetic",
  };

  current(): CaptureSnapshot {
    return structuredClone(this.snapshot);
  }

  dispatch(event: string, atMs = 0): CaptureSnapshot {
    const transitions: Record<string, CaptureState> = {
      "idle:start": "recording",
      "recording:pause": "paused",
      "paused:resume": "recording",
      "recording:interrupt": "interrupted",
      "paused:interrupt": "interrupted",
      "interrupted:recover": "recording",
      "recording:stop": "finalizing",
      "paused:stop": "finalizing",
      "interrupted:stop": "finalizing",
      "finalizing:upload": "uploading",
      "uploading:complete": "complete",
    };
    const target = transitions[`${this.snapshot.state}:${event}`];
    if (!target) throw new Error("invalid_capture_transition");
    if (event === "interrupt") {
      this.snapshot.gaps.push({
        startMs: atMs,
        endMs: null,
        reason: "synthetic_interruption",
      });
    }
    if (event === "recover") {
      const gap = this.snapshot.gaps.at(-1);
      if (!gap || gap.endMs !== null || atMs < gap.startMs)
        throw new Error("invalid_gap_recovery");
      gap.endMs = atMs;
    }
    this.snapshot.state = target;
    return this.current();
  }

  acknowledgeChunk(sequence: number): CaptureSnapshot {
    if (sequence <= this.snapshot.acknowledgedChunks) return this.current();
    if (sequence !== this.snapshot.acknowledgedChunks + 1)
      throw new Error("chunk_sequence_gap");
    this.snapshot.acknowledgedChunks = sequence;
    return this.current();
  }
}
