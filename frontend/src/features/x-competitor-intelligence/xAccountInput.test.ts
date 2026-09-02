import { describe, expect, it } from "vitest";
import { normalizeXAccount, parseXAccountBatch } from "./xAccountInput";

describe("X account input normalization", () => {
  it.each([
    ["AshleyReed", "AshleyReed"],
    ["@AshleyReed", "AshleyReed"],
    ["https://x.com/AshleyReed", "AshleyReed"],
    ["https://twitter.com/AshleyReed/", "AshleyReed"],
    ["[https://x.com/AshleyReed](https://x.com/AshleyReed)", "AshleyReed"],
  ])("normalizes %s", (input, expected) => expect(normalizeXAccount(input)).toEqual({ username: expected, error: null }));

  it.each(["not valid!", "https://example.com/AshleyReed", "https://x.com/AshleyReed/status/1", "@abcdefghijklmnop"])("rejects %s", (input) => {
    const result = normalizeXAccount(input);
    expect(result.username).toBeNull();
    expect(result.error).toBeTruthy();
  });

  it("preserves order, ignores blanks, deduplicates case-insensitively, and reports invalid lines", () => {
    const result = parseXAccountBatch("@AshleyReed\n\nashleyreed\nhttps://x.com/SummerHayes123\nbad value");
    expect(result.usernames).toEqual(["AshleyReed", "SummerHayes123"]);
    expect(result.invalid).toMatchObject([{ line: 5, value: "bad value" }]);
  });
});
