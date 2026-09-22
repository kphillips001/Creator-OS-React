import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearOverviewQueryCache, overviewQuery, peekOverviewQuery,
} from "./overviewQueryCache";

afterEach(() => { vi.useRealTimers(); clearOverviewQueryCache(); });

describe("Overview display query cache", () => {
  it("deduplicates in-flight requests and retains recent display data", async () => {
    let resolve: (value: { value: number }) => void = () => undefined;
    const loader = vi.fn(() => new Promise<{ value: number }>((done) => { resolve = done; }));
    const first = overviewQuery("key", loader);
    const second = overviewQuery("key", loader);
    expect(loader).toHaveBeenCalledTimes(1);
    resolve({ value: 7 });
    await expect(first).resolves.toEqual({ value: 7 });
    await expect(second).resolves.toEqual({ value: 7 });
    expect(peekOverviewQuery("key", 10_000)).toEqual({ value: 7 });
  });

  it("expires display data after its freshness window", async () => {
    vi.useFakeTimers();
    await overviewQuery("key", async () => ({ value: 7 }));
    expect(peekOverviewQuery("key", 10_000)).toEqual({ value: 7 });
    vi.advanceTimersByTime(10_001);
    expect(peekOverviewQuery("key", 10_000)).toBeNull();
  });
});
