import { describe, expect, it } from "vitest";

import { navigationGroups } from "./navigation";

describe("Business navigation", () => {
  it("presents only primary operator workflows", () => {
    const studios = navigationGroups.find((group) => group.label === "Studios");
    const libraries = navigationGroups.find(
      (group) => group.label === "Libraries",
    );
    const business = navigationGroups.find(
      (group) => group.label === "Business",
    );
    expect(studios?.items.map((item) => [item.label, item.path])).toEqual([
      ["Content Studio", "/studio/content"],
      ["Photoshoot Studio", "/content/photoshoot"],
      ["Video Studio", "/studio/video"],
      ["Edit Studio", "/content/edit"],
      ["Regeneration Studio", "/studio/regeneration"],
    ]);
    expect(libraries?.items.map((item) => [item.label, item.path])).toEqual([
      ["Generation Library", "/library/generations"],
      ["Photoshoot Gallery", "/library/photoshoots"],
      ["Video Gallery", "/gallery/videos"],
      ["Reference Library", "/library/references"],
      ["Asset Library", "/library/assets"],
    ]);
    expect(
      navigationGroups.some((group) => group.label === "Content Creation"),
    ).toBe(false);
    expect(
      navigationGroups
        .flatMap((group) => group.items)
        .some((item) => item.label === "Story Studio"),
    ).toBe(false);
    expect(business?.label).toBe("Business");
    expect(business?.items.map((item) => [item.label, item.path])).toEqual([
      ["Overview", "/home"],
      ["Chat", "/business/relationships"],
      ["Controls", "/business/controls"],
      ["Ask Creator_OS", "/business/ask"],
      ["Queue", "/business/queue"],
      ["Archive", "/system/archive"],
      ["API Balances", "/business/api-balances"],
    ]);
    expect(business?.items.some((item) => item.label === "Relationships")).toBe(false);
    expect(navigationGroups.some((group) => group.label === "Advanced")).toBe(false);
    expect(
      navigationGroups
        .flatMap((group) => group.items)
        .some((item) => item.path === "/commercial-administration"),
    ).toBe(false);
    expect(
      navigationGroups
        .flatMap((group) => group.items)
        .some((item) =>
          [
            "Commerce Library",
            "Available Inventory",
            "Intelligence Center",
          ].includes(item.label),
        ),
    ).toBe(false);
    expect(
      navigationGroups.some((group) => group.label === "Intelligence"),
    ).toBe(false);
    expect(
      navigationGroups.some((group) => group.label === "Publishing"),
    ).toBe(false);
    expect(
      navigationGroups
        .flatMap((group) => group.items)
        .some((item) => item.path === "/publishing"),
    ).toBe(false);
  });
});

describe("Video Gallery navigation", () => {
  it("pairs the completed-video gallery with Video Studio", () => {
    const libraries = navigationGroups.find(
      (group) => group.label === "Libraries",
    );
    const studios = navigationGroups.find((group) => group.label === "Studios");
    expect(
      libraries?.items.map((item) => [item.label, item.path]),
    ).toContainEqual(["Video Gallery", "/gallery/videos"]);
    expect(studios?.items.map((item) => item.label)).toContain("Video Studio");
  });
});

describe("Creator navigation", () => {
  it("consolidates creator configuration into one Administration workspace", () => {
    const administration = navigationGroups.find(
      (group) => group.label === "Administration",
    );
    expect(navigationGroups.some((group) => group.label === "Creator")).toBe(
      false,
    );
    expect(
      administration?.items.map((item) => [item.label, item.path]),
    ).toEqual([
      ["Ava Configuration", "/administration/ava"],
      ["Ava Rules", "/agents/ai-training"],
      ["Provider Connections", "/administration/providers"],
      ["Developer Notes", "/administration/developer-notes"],
    ]);
    const labels = navigationGroups.flatMap((group) => group.items.map((item) => item.label));
    expect(labels).not.toEqual(expect.arrayContaining(["Administration", "Personality", "Social Creative Direction", "Lifestyle", "World Model"]));
  });
});

describe("Administration navigation", () => {
  it("appears after Training and immediately before Developer Tools", () => {
    const labels = navigationGroups.map((group) => group.label);
    const index = labels.indexOf("Administration");
    expect(labels[index - 1]).toBe("Training");
    expect(labels[index + 1]).toBe("Developer Tools");
    expect(
      navigationGroups[index]?.items.map((item) => [item.label, item.path]),
    ).toEqual([
      ["Ava Configuration", "/administration/ava"],
      ["Ava Rules", "/agents/ai-training"],
      ["Provider Connections", "/administration/providers"],
      ["Developer Notes", "/administration/developer-notes"],
    ]);
  });
});

describe("Tools navigation", () => {
  it("places competitor intelligence under Tools and retires AI Developer Notes", () => {
    const labels = navigationGroups.map((group) => group.label);
    const index = labels.indexOf("Tools");
    expect(labels[index - 1]).toBe("Business");
    expect(labels[index + 1]).toBe("Training");
    expect(
      navigationGroups[index]?.items.map((item) => [item.label, item.path]),
    ).toEqual([
      ["X Competitor Intelligence", "/tools/x-intelligence"],
    ]);
    expect(navigationGroups.some((group) => group.label === "System")).toBe(false);
    expect(navigationGroups.flatMap((group) => group.items).map((item) => item.label))
      .not.toEqual(expect.arrayContaining(["Settings", "Diagnostics", "IG Competitor Intelligence"]));
  });
});

describe("Developer Tools navigation", () => {
  it("retains its complete navigation inventory unchanged", () => {
    const developer = navigationGroups.find(
      (group) => group.label === "Developer Tools",
    );
    expect(developer?.items.map((item) => [item.label, item.path])).toEqual([
      ["Operations", "/business/operations"],
      ["Test Chat", "/developer/test-chat"],
      ["Commerce Learning", "/developer/commerce-learning"],
      ["Recommendation Diagnostics", "/developer/recommendations"],
      ["Commerce Sales Explorer", "/developer/commerce-sales"],
      ["Fanvue API Explorer", "/developer/fanvue-api-explorer"],
      ["Fanvue Webhook Monitor", "/developer/fanvue-webhook-monitor"],
      ["Customer Commerce", "/developer/customer-commerce"],
      ["Purchase Intents", "/developer/purchase-intents"],
      ["Customer Sales Brain", "/developer/customer-sales-brain"],
      ["Commercial Offering Selector", "/developer/offering-selector"],
    ]);
    expect(navigationGroups.at(-1)?.label).toBe("Developer Tools");
    expect(navigationGroups.at(-2)?.label).toBe("Administration");
    expect(navigationGroups.at(-3)?.label).toBe("Training");
    expect(navigationGroups.at(-3)?.items).toHaveLength(1);
    expect(navigationGroups.at(-3)?.items[0]).toMatchObject({ label: "AI Training", path: "/training/ai-training" });
    expect(navigationGroups.at(-4)?.label).toBe("Tools");
    expect(navigationGroups.find((group) => group.label === "Business")?.items.at(-1)?.label).toBe("API Balances");
  });
});

describe("AI navigation cleanup", () => {
  it("removes the primary AI group and places Ava Rules in Administration", () => {
    expect(navigationGroups.some((group) => group.label === "AI")).toBe(false);
    const allItems = navigationGroups.flatMap((group) => group.items);
    expect(allItems.map((item) => item.label)).not.toEqual(
      expect.arrayContaining(["Ava Coach", "Creator Agent", "Developer Agent", "AI Training"]),
    );
    const administration = navigationGroups.find((group) => group.label === "Administration");
    expect(administration?.items.map((item) => [item.label, item.path])).toContainEqual([
      "Ava Rules", "/agents/ai-training",
    ]);
  });
});
