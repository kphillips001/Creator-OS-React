import { beforeEach, describe, expect, it, vi } from "vitest";

import { getContentStudioContext } from "./contentStudioApi";

describe("getContentStudioContext", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("rejects a successful non-JSON response without parsing it", async () => {
    const json = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      headers: new Headers({ "content-type": "text/html" }),
      json,
      ok: true,
      status: 200,
    }));

    await expect(getContentStudioContext()).rejects.toThrow("non-JSON response");
    expect(json).not.toHaveBeenCalled();
  });

  it("handles an empty error response without exposing a parse exception", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      headers: new Headers({ "content-type": "text/plain" }),
      ok: false,
      status: 502,
      text: () => Promise.resolve(""),
    }));

    await expect(getContentStudioContext()).rejects.toThrow("HTTP 502");
  });

  it("handles malformed JSON on a successful response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      headers: new Headers({ "content-type": "application/json" }),
      json: () => Promise.reject(new SyntaxError("unexpected end of data")),
      ok: true,
      status: 200,
    }));

    await expect(getContentStudioContext()).rejects.toThrow("returned invalid JSON");
  });
});
