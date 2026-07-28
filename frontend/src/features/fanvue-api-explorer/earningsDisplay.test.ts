import { describe, expect, it } from "vitest";

import { sortEarningsForDisplay } from "./earningsDisplay";

describe("sortEarningsForDisplay", () => {
  it("sorts earnings data by descending ISO-8601 date without mutation", () => {
    const body = {
      data: [
        { id: "old", date: "2026-07-20T12:00:00Z" },
        { id: "new", date: "2026-07-24T09:30:00Z" },
        { id: "middle", date: "2026-07-22T18:00:00+00:00" },
      ],
      pagination: { cursor: "unchanged" },
    };
    const originalOrder = [...body.data];
    const result = sortEarningsForDisplay("/insights/earnings", body);

    expect(result.sortingApplied).toBe(true);
    expect((result.body as typeof body).data.map((item) => item.id)).toEqual([
      "new", "middle", "old",
    ]);
    expect(body.data).toEqual(originalOrder);
    expect((result.body as typeof body).pagination).toBe(body.pagination);
  });

  it("preserves original order when any date is invalid", () => {
    const body = {
      data: [
        { id: "first", date: "not-a-date" },
        { id: "second", date: "2026-07-24T09:30:00Z" },
      ],
    };
    const result = sortEarningsForDisplay("/insights/earnings", body);
    expect(result).toEqual({ body, sortingApplied: false });
    expect(result.body).toBe(body);
  });

  it.each([
    ["empty", []],
    ["single item", [{ id: "only", date: "2026-07-24T09:30:00Z" }]],
  ])("leaves %s earnings arrays unchanged", (_label, data) => {
    const body = { data };
    const result = sortEarningsForDisplay("/insights/earnings", body);
    expect(result).toEqual({ body, sortingApplied: false });
    expect(result.body).toBe(body);
  });

  it("does not reorder non-earnings responses", () => {
    const body = {
      data: [
        { id: "old", date: "2026-07-20T12:00:00Z" },
        { id: "new", date: "2026-07-24T09:30:00Z" },
      ],
    };
    const result = sortEarningsForDisplay("/media-links", body);
    expect(result).toEqual({ body, sortingApplied: false });
    expect(result.body).toBe(body);
  });
});
