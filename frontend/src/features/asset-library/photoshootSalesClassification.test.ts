import { describe, expect, it } from "vitest";

import { photoshootCommercialBadges } from "./photoshootSalesClassification";

describe("Photoshoot commercial badges", () => {
  it("projects POSTED only from persisted WALL publication state", () => {
    const base = {
      sellingMode: "BUNDLE" as const,
      bundleSalesChannel: "CONTENT_WALL" as const,
      sessionSelling: {
        sellingMode: "BUNDLE" as const, bundleSalesChannel: "CONTENT_WALL" as const,
        salesChannel: "WALL" as const, deliverableId: "set-1", photoshootSessionId: "session-1",
        status: "READY" as const, statusLabel: "Ready", imageCount: 3,
        priceMinor: 1799, currency: "USD",
        contentVaultPublication: { status: "NOT_PUBLISHED" as const, canPublish: true, configured: true },
      },
    };
    expect(photoshootCommercialBadges(base)?.posted).toBe(false);
    expect(photoshootCommercialBadges({
      ...base,
      sessionSelling: {
        ...base.sessionSelling,
        contentVaultPublication: { status: "PUBLISHED" as const, canPublish: false, configured: true },
      },
    })?.posted).toBe(true);
  });
});
