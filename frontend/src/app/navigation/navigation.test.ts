import { describe, expect, it } from "vitest";

import { navigationGroups } from "./navigation";

describe("Business navigation", () => {
  it("appears immediately after Content Creation with all five workspaces", () => {
    const content = navigationGroups[0];
    const business = navigationGroups[1];
    expect(content?.label).toBe("Content Creation");
    expect(business?.label).toBe("Business");
    expect(business?.items.map((item) => [item.label, item.path])).toEqual([
      ["Commerce Library", "/business/commerce-library"],
      ["Products", "/business/products"],
      ["Customers", "/business/customers"],
      ["Sales", "/business/sales"],
      ["Operations", "/business/operations"],
    ]);
  });
});
