import { describe, expect, it } from "vitest";

import { photoshootCommercialBadges } from "./photoshootSalesClassification";

describe("Photoshoot commercial badges", () => {
  it("projects canonical SESSION independently from readiness and optional channel", () => {
    expect(photoshootCommercialBadges({
      sellingMode: "SESSION",
      bundleSalesChannel: null,
      sessionSelling: null,
    })).toEqual({ sellingMode: "SESSION" });
    expect(photoshootCommercialBadges({
      sellingMode: "SESSION",
      bundleSalesChannel: null,
      sessionSelling: {
        deliverableId: "session-1", photoshootSessionId: "runtime-1",
        sellingMode: "SESSION", strategyVersion: "v1", status: "READY",
        statusLabel: "Ready", paidStepCount: 1, readyPaidStepCount: 1,
        teaserReady: true, steps: [],
      },
    })).toEqual({ sellingMode: "SESSION" });
  });

  it("does not infer SESSION without canonical selling-mode data", () => {
    expect(photoshootCommercialBadges({
      sellingMode: undefined,
      bundleSalesChannel: null,
      sessionSelling: null,
    })).toBeNull();
  });

  it("projects canonical BUNDLE before sale preparation exists", () => {
    expect(photoshootCommercialBadges({
      sellingMode: "BUNDLE",
      bundleSalesChannel: "CHAT",
      sessionSelling: null,
    })).toEqual({ sellingMode: "BUNDLE" });
  });

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
