import { describe, expect, it } from "vitest";

import { navigationGroups } from "./navigation";

describe("Business navigation", () => {
  it("places commercial inventory and intelligence in the Business workflow", () => {
    const content = navigationGroups.find((group) => group.label === "Content Creation");
    const business = navigationGroups.find((group) => group.label === "Business");
    expect(content?.label).toBe("Content Creation");
    expect(business?.label).toBe("Business");
    expect(business?.items.map((item) => [item.label, item.path])).toEqual([
      ["Commercial Administration", "/commercial-administration"],
      ["Commerce", "/commerce"],
      ["Commerce Library", "/business/commerce-library"],
      ["Available Inventory", "/inventory/available"],
      ["Customers", "/business/customers"],
      ["Sales", "/business/sales"],
      ["Operations", "/business/operations"],
      ["Intelligence Center", "/home"],
    ]);
    expect(content?.items.some((item) => item.label === "Available Inventory")).toBe(false);
    expect(navigationGroups.some((group) => group.label === "Intelligence")).toBe(false);
  });
});

describe("Creator navigation", () => {
  it("keeps personality and social creative direction separate", () => {
    const creator = navigationGroups.find((group) => group.label === "Creator");
    expect(creator?.items.map((item) => [item.label, item.path])).toEqual([
      ["Personality", "/creator/personality"],
      ["Social Creative Direction", "/creator/social-creative-direction"],
      ["Lifestyle", "/creator/lifestyle"],
      ["World Model", "/creator/world-model"],
    ]);
  });
});

describe("Administration navigation", () => {
  it("appears between Developer Tools and System", () => {
    const labels = navigationGroups.map((group) => group.label);
    const index = labels.indexOf("Administration");
    expect(labels[index - 1]).toBe("Developer Tools");
    expect(labels[index + 1]).toBe("System");
    expect(navigationGroups[index]?.items.map((item) => [item.label, item.path])).toEqual([
      ["Administration", "/administration"],
    ]);
  });
});

describe("Developer Tools navigation", () => {
  it("includes the read-only Customer Commerce workspace", () => {
    const developer = navigationGroups.find(
      (group) => group.label === "Developer Tools",
    );
    expect(developer?.items.map((item) => [item.label, item.path]))
      .toContainEqual([
        "Customer Commerce",
        "/developer/customer-commerce",
      ]);
    expect(developer?.items.map((item) => [item.label, item.path]))
      .toContainEqual(["Purchase Intents", "/developer/purchase-intents"]);
    expect(developer?.items.map((item) => [item.label, item.path]))
      .toContainEqual([
        "Customer Sales Brain", "/developer/customer-sales-brain",
      ]);
    expect(developer?.items.map((item) => [item.label, item.path]))
      .toContainEqual([
        "Commercial Offering Selector", "/developer/offering-selector",
      ]);
  });
});

describe("AI navigation", () => {
  it("activates Ava Coach as the conversation coaching workspace", () => {
    const ai = navigationGroups.find((group) => group.label === "AI");
    expect(ai?.items[0]).toMatchObject({
      label: "Ava Coach",
      path: "/agents/ava-coach",
      description: "Evidence-based conversation coaching for operator review.",
    });
  });
});
