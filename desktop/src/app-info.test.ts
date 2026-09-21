import { describe, expect, it } from "vitest";

import { desktopApplicationName } from "./app-info";

describe("desktopApplicationName", () => {
  it("identifies the capture client", () => {
    expect(desktopApplicationName).toBe("KaniorAI Capture");
  });
});
