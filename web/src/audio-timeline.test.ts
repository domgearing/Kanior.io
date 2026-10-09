import { describe, expect, it } from "vitest";
import { activeTimedIndex, wordParts } from "./audio-timeline";

describe("audio timeline", () => {
  it("selects only a word with exact provider timing", () => {
    expect(activeTimedIndex([{ start_ms: 100, end_ms: 300 }], 200)).toBe(0);
    expect(activeTimedIndex([{ start_ms: 100, end_ms: 300 }], 300)).toBe(-1);
    expect(activeTimedIndex([{ start_ms: null, end_ms: null }], 200)).toBe(-1);
  });

  it("preserves spaces and rejects mismatched word offsets", () => {
    const words = [
      {
        text: "Hello",
        start_ms: 0,
        end_ms: 200,
        start_character: 0,
        end_character: 5,
      },
      {
        text: "world!",
        start_ms: 250,
        end_ms: 500,
        start_character: 6,
        end_character: 12,
      },
    ];
    expect(
      wordParts("Hello world!", words)
        .map((part) => part.text)
        .join(""),
    ).toBe("Hello world!");
    expect(wordParts("Hello edited", words)).toEqual([
      { text: "Hello edited", wordIndex: null },
    ]);
  });
});
