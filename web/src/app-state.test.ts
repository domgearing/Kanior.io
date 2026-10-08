import { describe, expect, it } from "vitest";

import { initialApplicationStatus, resolvePreviewLocation } from "./app-state";

describe("initialApplicationStatus", () => {
  it("describes the runnable foundation", () => {
    expect(initialApplicationStatus).toBe("Synthetic preview ready");
  });
});

describe("resolvePreviewLocation", () => {
  it("resolves direct links without accepting arbitrary routes", () => {
    expect(resolvePreviewLocation("#home")).toEqual({ page: "home" });
    expect(resolvePreviewLocation("#projects/dovetail")).toEqual({
      page: "project",
      projectId: "dovetail",
    });
    expect(resolvePreviewLocation("#projects/../../secret")).toEqual({
      page: "home",
    });
  });
});
