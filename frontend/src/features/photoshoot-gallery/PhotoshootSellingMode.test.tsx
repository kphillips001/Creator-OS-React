import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PhotoshootViewer } from "./PhotoshootViewer";

const detail = {
  deliverableId: "set-1", sessionId: "session-1", name: "Test Photoshoot",
  description: null, completedAt: "2026-08-07T12:00:00Z", shotCount: 1,
  heroAssetId: 10, imageUrl: "/hero", intelligenceStatus: "READY",
  registrationState: "IN_ASSET_LIBRARY", sellingMode: "SESSION",
  intelligence: {}, productionIntelligence: {}, technical: {},
  members: [{ assetId: 10, shotOrder: 1, imageUrl: "/shot", intelligence: {} }],
};

const json = (body: unknown, ok = true) => Promise.resolve({
  ok, status: ok ? 200 : 409, json: () => Promise.resolve(body),
} as Response);

afterEach(() => vi.restoreAllMocks());

describe("Photoshoot selling mode", () => {
  it("persists Bundle, hides Session controls, and restores them when switched back", async () => {
    let mode = "SESSION";
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      if (url.endsWith("/selling-mode")) {
        mode = JSON.parse(String(options?.body)).sellingMode;
        return json({ deliverableId: "set-1", sellingMode: mode });
      }
      if (url.includes("sale-preparation")) return mode === "BUNDLE" ? json({
        deliverableId: "set-1", photoshootSessionId: "session-1", sellingMode: "BUNDLE",
        status: "NOT_CONFIGURED", statusLabel: "Bundle Not Configured", imageCount: 5,
        priceMinor: null, currency: "USD",
      }) : json({ deliverableId: "set-1", photoshootSessionId: "session-1", sellingMode: "SESSION",
        strategyVersion: "v1", status: "NOT_PREPARED", statusLabel: "Not Prepared",
        paidStepCount: 0, readyPaidStepCount: 0, teaserReady: true, steps: [] });
      return json({ ...detail, sellingMode: mode });
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} enableSessionSelling />);
    const session = await screen.findByRole("button", { name: /Sell this Photoshoot progressively/ });
    expect(session).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("button", { name: "Prepare Session" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Bundle/ }));
    expect(await screen.findByText("Bundle Not Configured")).toBeInTheDocument();
    expect(screen.getByText("5 images")).toBeInTheDocument();
    expect(screen.getByLabelText("Bundle Price")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare Session" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/selling-mode"), expect.objectContaining({ method: "PUT" }));

    fireEvent.click(screen.getByRole("button", { name: /Sell this Photoshoot progressively/ }));
    expect(await screen.findByRole("button", { name: "Prepare Session" })).toBeInTheDocument();
  });

  it("shows the exclusive Bundle channel, persists Content Wall, and restores Chat UI", async () => {
    let channel = "CHAT";
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      if (url.endsWith("/bundle-sales-channel")) {
        channel = JSON.parse(String(options?.body)).bundleSalesChannel;
        return json({ deliverableId: "set-1", bundleSalesChannel: channel });
      }
      if (url.includes("sale-preparation")) return json({
        deliverableId: "set-1", photoshootSessionId: "session-1", sellingMode: "BUNDLE",
        bundleSalesChannel: channel, status: "READY", statusLabel: "Paid Bundle Ready",
        imageCount: 5, priceMinor: 2500, currency: "USD", deliveryUrl: "https://test.invalid/bundle",
        promotionalTeaser: { status: "READY", statusLabel: "Ready", commercialRole: "BUNDLE_PROMOTIONAL_TEASER", sourceAssetId: 10, teaserAssetId: 20, blurStrength: 20, maskWidth: 100, maskHeight: 100, maskVersion: "v1", maskUrl: "/mask", previewUrl: "/preview", error: null, candidates: [] },
        autonomousSales: channel === "CHAT"
          ? { status: "READY", statusLabel: "Ready to Sell", reason: null }
          : { status: "DISABLED", statusLabel: "Chat Sales Disabled", reason: "Designated for Ava's Content Wall" },
      });
      return json({ ...detail, sellingMode: "BUNDLE", bundleSalesChannel: channel });
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} enableSessionSelling />);
    expect(await screen.findByRole("heading", { name: "Sell Bundle Through" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chats/ })).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("Autonomous Sales: Ready to Sell")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Ava's Content Wall/ }));
    expect(await screen.findByText("This Bundle is designated for Ava's Content Wall.")).toBeInTheDocument();
    expect(screen.getByText("Disabled — designated for Ava's Content Wall")).toBeInTheDocument();
    expect(screen.queryByText("Autonomous Sales: Ready to Sell")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Chats/ }));
    expect(await screen.findByText("Autonomous Sales: Ready to Sell")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/bundle-sales-channel"), expect.objectContaining({ method: "PUT" }));
  });

  it("retains the authoritative Bundle channel when persistence fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/bundle-sales-channel")) return json({ detail: "Bundle sales channel is locked." }, false);
      if (url.includes("sale-preparation")) return json({
        deliverableId: "set-1", photoshootSessionId: "session-1", sellingMode: "BUNDLE",
        bundleSalesChannel: "CHAT", status: "NOT_CONFIGURED", statusLabel: "Bundle Not Configured",
        imageCount: 5, priceMinor: null, currency: "USD",
      });
      return json({ ...detail, sellingMode: "BUNDLE", bundleSalesChannel: "CHAT" });
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} enableSessionSelling />);
    fireEvent.click(await screen.findByRole("button", { name: /Ava's Content Wall/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bundle sales channel is locked.");
    expect(screen.getByRole("button", { name: /Chats/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("This Bundle is designated for Ava's Content Wall.")).not.toBeInTheDocument();
  });

  it("surfaces an API error and retains the authoritative displayed mode", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/selling-mode")) return json({ detail: "Selling mode is locked." }, false);
      if (url.includes("sale-preparation")) return json({
        deliverableId: "set-1", photoshootSessionId: "session-1", sellingMode: "SESSION",
        strategyVersion: "v1", status: "NOT_PREPARED", statusLabel: "Not Prepared",
        paidStepCount: 0, readyPaidStepCount: 0, teaserReady: true, steps: [],
      });
      return json(detail);
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} enableSessionSelling />);
    fireEvent.click(await screen.findByRole("button", { name: /Bundle/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Selling mode is locked.");
    expect(screen.getByRole("button", { name: /Sell this Photoshoot progressively/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("Bundle Not Configured")).not.toBeInTheDocument();
  });
});
