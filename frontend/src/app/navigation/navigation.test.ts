import { describe, expect, it } from "vitest";

import { navigationGroups } from "./navigation";

describe("Business navigation", () => {
  it("presents only primary operator workflows and moves administration to Advanced", () => {
    const studios = navigationGroups.find((group) => group.label === "Studios");
    const libraries = navigationGroups.find((group) => group.label === "Libraries");
    const business = navigationGroups.find((group) => group.label === "Business");
    const advanced = navigationGroups.find((group) => group.label === "Advanced");
    expect(studios?.items.map((item) => [item.label,item.path])).toEqual([
      ["Content Studio","/studio/content"],
      ["Photoshoot Studio","/content/photoshoot"],
      ["Video Studio","/studio/video"],
      ["Edit Studio","/content/edit"],
      ["Regeneration Studio","/studio/regeneration"],
    ]);
    expect(libraries?.items.map((item) => [item.label,item.path])).toEqual([
      ["Generation Library","/library/generations"],
      ["Photoshoot Gallery","/library/photoshoots"],
      ["Video Gallery","/gallery/videos"],
      ["Reference Library","/library/references"],
      ["Asset Library","/library/assets"],
    ]);
    expect(navigationGroups.some((group)=>group.label==="Content Creation")).toBe(false);
    expect(navigationGroups.flatMap((group)=>group.items).some((item)=>item.label==="Story Studio")).toBe(false);
    expect(business?.label).toBe("Business");
    expect(business?.items.map((item) => [item.label, item.path])).toEqual([
      ["Overview", "/home"],
      ["Commerce", "/commerce"],
      ["Customers", "/business/customers"],
      ["Sales", "/business/sales"],
    ]);
    expect(advanced?.items.map((item) => [item.label, item.path])).toEqual([
      ["Operations", "/business/operations"],
      ["Commercial Administration", "/commercial-administration"],
    ]);
    expect(navigationGroups.flatMap((group) => group.items).some((item) =>
      ["Commerce Library", "Available Inventory", "Intelligence Center"].includes(item.label))).toBe(false);
    expect(navigationGroups.some((group) => group.label === "Intelligence")).toBe(false);
  });
});

describe("Video Gallery navigation", () => {
  it("pairs the completed-video gallery with Video Studio", () => {
    const libraries=navigationGroups.find((group)=>group.label==="Libraries");
    const studios=navigationGroups.find((group)=>group.label==="Studios");
    expect(libraries?.items.map((item)=>[item.label,item.path])).toContainEqual(["Video Gallery","/gallery/videos"]);
    expect(studios?.items.map((item)=>item.label)).toContain("Video Studio");
  });
});

describe("Creator navigation", () => {
  it("moves creator configuration into Administration without duplication", () => {
    const administration = navigationGroups.find((group) => group.label === "Administration");
    expect(navigationGroups.some((group) => group.label === "Creator")).toBe(false);
    expect(administration?.items.slice(1,5).map((item) => [item.label, item.path])).toEqual([
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
      ["Personality", "/creator/personality"],
      ["Social Creative Direction", "/creator/social-creative-direction"],
      ["Lifestyle", "/creator/lifestyle"],
      ["World Model", "/creator/world-model"],
      ["Developer Notes", "/administration/developer-notes"],
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
