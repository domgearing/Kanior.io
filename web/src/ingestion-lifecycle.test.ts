import { describe, expect, it } from "vitest";
import {
  lifecyclePosition,
  lifecycleSteps,
  safeProcessingMessage,
} from "./ingestion-lifecycle";

describe("ingestion lifecycle", () => {
  it("orders processing through review and publication without inventing percentage progress", () => {
    expect(lifecycleSteps).toHaveLength(7);
    expect(lifecyclePosition("source_pending")).toBe(1);
    expect(lifecyclePosition("transcription_processing")).toBe(3);
    expect(lifecyclePosition("draft_ready")).toBe(4);
    expect(lifecyclePosition("approved")).toBe(5);
    expect(lifecyclePosition("published")).toBe(6);
    expect(lifecyclePosition("failed_retryable")).toBe(-1);
    expect(lifecyclePosition("failed_retryable", "transcription")).toBe(3);
  });

  it("gives a safe action and retains the diagnostic code", () => {
    expect(safeProcessingMessage("transcription_timeout")).toContain(
      "transcription timeout",
    );
    expect(safeProcessingMessage(null)).toBeNull();
  });
});
