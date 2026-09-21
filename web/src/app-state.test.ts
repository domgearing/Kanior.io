import { describe, expect, it } from "vitest";

import { initialApplicationStatus } from "./app-state";

describe("initialApplicationStatus", () => {
  it("describes the runnable foundation", () => {
    expect(initialApplicationStatus).toBe("Foundation ready");
  });
});
