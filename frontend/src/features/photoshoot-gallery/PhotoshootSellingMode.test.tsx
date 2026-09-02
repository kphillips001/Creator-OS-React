import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  it("offers Session teaser authoring only while the eligible first shot is selected", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json({
      ...detail, shotCount: 2,
      members: [
        { assetId: 10, shotOrder: 1, isHero: true, imageUrl: "/shot-1", intelligence: {} },
        { assetId: 11, shotOrder: 2, imageUrl: "/shot-2", intelligence: {} },
      ],
      sessionTeaser: { eligible: true, reason: null, sourceAssetId: 10, hasSessionTeaser: false },
    }));
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} />);

    expect(await screen.findByRole("button", { name: "Create Teaser" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Select shot 2" }));
    expect(screen.queryByRole("button", { name: "Create Teaser" })).not.toBeInTheDocument();
  });

  it("starts the existing teaser-intent flow from the Selected Shot action", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).endsWith("/session-teaser-intents") && init?.method === "POST") return json({ redirect: "#teaser-editor" });
      return json({ ...detail, sessionTeaser: { eligible: true, reason: null, sourceAssetId: 10, hasSessionTeaser: false } });
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} />);
    const card = (await screen.findByRole("heading", { name: "Selected Shot — Shot 1" })).closest("article")!;
    fireEvent.click(within(card).getByRole("button", { name: "Create Teaser" }));

    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/v1/photoshoot-gallery/set-1/session-teaser-intents",
      { method: "POST" },
    ));
    await waitFor(() => expect(window.location.hash).toBe("#teaser-editor"));
    window.history.replaceState({}, "", "/");
  });

  it("hides teaser authoring when the backend says it is ineligible", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json({
      ...detail,
      sessionTeaser: { eligible: false, reason: "This Photoshoot already has commercial preparation or customer activity.", sourceAssetId: 10, hasSessionTeaser: false },
    }));
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} />);
    await screen.findByRole("button", { name: "Close" });
    expect(screen.queryByRole("button", { name: "Create Teaser" })).not.toBeInTheDocument();
  });

  it("hides teaser authoring for Bundle mode and labels an existing teaser replacement", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    fetch.mockImplementationOnce(() => json({ ...detail, sellingMode: "BUNDLE", sessionTeaser: { eligible: true, reason: null, sourceAssetId: 10, hasSessionTeaser: false } }));
    const view = render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} />);
    await screen.findByRole("button", { name: "Close" });
    expect(screen.queryByRole("button", { name: "Create Teaser" })).not.toBeInTheDocument();
    view.unmount();

    fetch.mockImplementationOnce(() => json({ ...detail, sessionTeaser: { eligible: true, reason: null, sourceAssetId: 10, hasSessionTeaser: true } }));
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} />);
    expect(await screen.findByRole("button", { name: "Replace Teaser" })).toBeEnabled();
  });

  it("defers strategy generation only until the authored Session teaser exists", async () => {
    const missingStrategy = {
      deliverableId: "set-1", photoshootSessionId: "session-1", sellingMode: "SESSION",
      strategyVersion: "", strategyExists: false, strategyStatus: "MISSING",
      status: "STRATEGY_REQUIRED", statusLabel: "Not Prepared", paidStepCount: 0,
      readyPaidStepCount: 0, teaserReady: false, steps: [], strategyOperation: null,
    };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/sale-preparation")) return json(missingStrategy);
      if (url.endsWith("/session-sales-strategy") && init?.method === "POST") {
        return json({ ...missingStrategy, strategyOperation: { operationId: "operation-1", status: "QUEUED" } });
      }
      return json({ ...detail, sessionTeaser: { eligible: true, reason: null, sourceAssetId: 20, hasSessionTeaser: true } });
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} enableSessionSelling />);

    expect(await screen.findByRole("button", { name: "Replace Teaser" })).toBeEnabled();
    await waitFor(() => expect(fetch).toHaveBeenCalledWith(
      "/api/v1/assets/photoshoots/set-1/session-sales-strategy",
      expect.objectContaining({ method: "POST" }),
    ));
    expect(screen.queryByRole("heading", { name: "Create Teaser First" })).not.toBeInTheDocument();
  });

  it("surfaces a recoverable failed authored-teaser strategy before commercial configuration", async () => {
    const failed = {
      deliverableId: "set-1", photoshootSessionId: "session-1", sellingMode: "SESSION",
      strategyVersion: "", strategyExists: false, strategyStatus: "MISSING",
      status: "STRATEGY_REQUIRED", statusLabel: "Not Prepared", paidStepCount: 0,
      readyPaidStepCount: 0, teaserReady: false, steps: [],
      strategyOperation: { operationId: "operation-1", status: "FAILED", errorMessage: "Complete persisted Production and Shot Intelligence is required." },
    };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input).endsWith("/sale-preparation")) return json(failed);
      return json({ ...detail, sessionTeaser: { eligible: true, reason: null, sourceAssetId: 20, hasSessionTeaser: true } });
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} enableSessionSelling />);

    expect(await screen.findByRole("button", { name: "Replace Teaser" })).toBeEnabled();
    const recovery = await screen.findByRole("heading", { name: "Strategy Needs Attention" });
    expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
    expect(screen.getByText("Complete persisted Production and Shot Intelligence is required.")).toBeInTheDocument();
    expect(recovery.compareDocumentPosition(screen.getByRole("heading", { name: "Selling Mode" })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(fetch.mock.calls.some(([input, init]) => String(input).endsWith("/session-sales-strategy") && init?.method === "POST")).toBe(false);
  });

  it("multi-selects eligible members, confirms the count, and refreshes after moving", async () => {
    let members = Array.from({ length: 4 }, (_, index) => ({
      assetId: 10 + index, shotOrder: index + 1, isHero: index === 0,
      imageUrl: `/shot-${index + 1}`, intelligence: {},
    }));
    const changed = vi.fn();
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/members/move-to-images") && init?.method === "POST") {
        expect(JSON.parse(String(init.body))).toEqual({ assetIds: [10, 11] });
        members = members.slice(2).map((member, index) => ({ ...member, shotOrder: index + 1, isHero: index === 0 }));
        return json({ movedCount: 2 });
      }
      return json({ ...detail, shotCount: members.length, heroAssetId: members[0]?.assetId,
        members, memberCuration: { eligible: members.length > 2, reason: members.length > 2 ? null : "A Photoshoot must retain at least 2 images.", memberCount: members.length, maximumExtractable: Math.max(0, members.length - 2) } });
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} onMembersChanged={changed} />);

    fireEvent.click(await screen.findByRole("button", { name: "Select" }));
    expect(screen.getByText("0 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move to Images" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Select All Eligible" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("0 selected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select Shot 1 for moving" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Shot 2 for moving" }));
    fireEvent.click(screen.getByRole("button", { name: "Move to Images" }));
    const dialog = screen.getByRole("dialog", { name: "Move 2 Images?" });
    expect(within(dialog).getByText("Photoshoot: 4 → 2 images")).toBeInTheDocument();
    expect(within(dialog).getByText(/new Photoshoot cover/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Move to Images" }));

    expect(await screen.findByText("2 images moved to Asset Library → Images")).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Select shot/)).toHaveLength(2);
    expect(screen.getAllByText(/2 images/).length).toBeGreaterThanOrEqual(1);
    expect(changed).toHaveBeenCalledWith(expect.objectContaining({ shotCount: 2 }));
    expect(screen.getByRole("link", { name: "View Images" })).toHaveAttribute("href", "/library/assets?assetType=images");
  });

  it("disables selection for commercially protected Photoshoots", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json({ ...detail,
      memberCuration: { eligible: false, reason: "This Photoshoot has commercial activity and its members cannot be changed.", memberCount: 4, maximumExtractable: 2 } }));
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} />);
    await screen.findByRole("button", { name: "Close" });
    expect(screen.queryByRole("button", { name: "Select" })).not.toBeInTheDocument();
  });

  it("renders Generation Library imports as unconfigured Bundle-only Photoshoots", async () => {
    const members = Array.from({ length: 6 }, (_, index) => ({
      assetId: 10 + index, shotOrder: index + 1, isHero: index === 3,
      imageUrl: `/shot-${index + 1}`, intelligence: {},
    }));
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => json({
      ...detail, sourceKind: "GENERATION_LIBRARY_IMPORT", sellingMode: "BUNDLE",
      bundleSalesChannel: null, shotCount: 6, heroAssetId: 13, members,
      memberCuration: { eligible: true, reason: null, memberCount: 6, maximumExtractable: 4 },
    }));
    const close = vi.fn();
    render(<PhotoshootViewer deliverableId="set-1" onClose={close} enableSessionSelling />);

    const select = await screen.findByRole("button", { name: "Select" });
    expect(select).toBeVisible();
    expect(select).toHaveClass("photoshoot-detail-select");
    expect(await screen.findByRole("button", { name: /Sell the complete Photoshoot/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/6 images/)).toBeInTheDocument();
    expect(screen.getAllByLabelText(/Select shot/)).toHaveLength(6);
    expect(screen.getByRole("button", { name: "Select shot 4" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Select shot 1" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Create Video" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sell this Photoshoot progressively/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chats/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /Ava's Content Wall/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText(/Choose Chats or Ava's Content Wall/)).toBeInTheDocument();
    expect(fetch.mock.calls.some(([input]) => String(input).includes("sale-preparation"))).toBe(false);
    fireEvent.click(select);
    expect(screen.getAllByRole("button", { name: /Select Shot \d for moving/ })).toHaveLength(6);
    fireEvent.click(screen.getByRole("button", { name: "Select Shot 1 for moving" }));
    fireEvent.click(screen.getByRole("button", { name: "Select Shot 2 for moving" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Move to Images" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Exit Select" }));
    expect(screen.getByRole("button", { name: "Select" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(close).toHaveBeenCalledOnce();
  });

  it("shows the canonical promotional teaser as supporting Commercial Assets", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json({
      ...detail,
      commercialAssets: [{ assetId: 145, kind: "PROMOTIONAL_TEASER", label: "Promotional Teaser", status: "READY", previewUrl: "/api/v1/assets/145/media" }],
    }));
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} />);

    expect(await screen.findByRole("heading", { name: "Commercial Assets" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Promotional Teaser" })).toHaveAttribute("src", "/api/v1/assets/145/media");
    expect(screen.getAllByLabelText(/Select shot/)).toHaveLength(1);
  });

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
    expect(await screen.findByRole("button", { name: "Set Session Prices" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Bundle/ }));
    expect(await screen.findByText("Bundle Not Configured")).toBeInTheDocument();
    expect(screen.getByText("5 images")).toBeInTheDocument();
    expect(screen.getByLabelText("Bundle Price")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Set Session Prices" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/selling-mode"), expect.objectContaining({ method: "PUT" }));

    fireEvent.click(screen.getByRole("button", { name: /Sell this Photoshoot progressively/ }));
    expect(await screen.findByRole("button", { name: "Set Session Prices" })).toBeInTheDocument();
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

  it("saves a Bundle caption, refreshes readiness, and publishes one persisted WALL package", async () => {
    let caption: string | null = null;
    let posted = false;
    const options = Array.from({ length: 5 }, (_, index) => ({ text: `All 3 photos are in this complete set option ${index + 1}` }));
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/content-vault/captions/generate")) return json({ profile: "CONTENT_VAULT_PHOTOSHOOT_BUNDLE", captions: options });
      if (url.endsWith("/content-vault/caption") && init?.method === "PUT") {
        caption = JSON.parse(String(init.body)).text;
        return json({ caption: { text: caption, source: "GROK" } });
      }
      if (url.includes("/commerce-authoring/") && init?.method === "POST") {
        posted = true; return json({ status: "PUBLISHED" });
      }
      if (url.includes("sale-preparation")) return json({
        deliverableId: "set-1", photoshootSessionId: "session-1", sellingMode: "BUNDLE",
        bundleSalesChannel: "CONTENT_WALL", status: "READY", statusLabel: "Paid Bundle Ready",
        imageCount: 3, priceMinor: 1799, currency: "USD", offeringId: "offering-1",
        deliveryUrl: "https://test.invalid/bundle",
        promotionalTeaser: { status: "READY", previewUrl: "/preview", candidates: [] },
        contentVaultCaption: caption ? { text: caption, source: "GROK", updatedAt: "now", offeringId: "offering-1", paidImageCount: 3 } : null,
        contentVaultPublication: { status: posted ? "PUBLISHED" : "NOT_PUBLISHED", canPublish: Boolean(caption) && !posted, configured: true },
      });
      return json({ ...detail, sellingMode: "BUNDLE", bundleSalesChannel: "CONTENT_WALL" });
    });
    render(<PhotoshootViewer deliverableId="set-1" onClose={() => undefined} enableSessionSelling />);
    expect(await screen.findByText("3 Photos")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Generate Captions with AI" }));
    const chooser = await screen.findByRole("dialog", { name: "Choose Bundle Content Vault Caption" });
    fireEvent.click(within(chooser).getByRole("button", { name: options[0]!.text }));
    fireEvent.click(within(chooser).getByRole("button", { name: "Use Caption" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Publish to Content Vault" }));
    expect(await screen.findByRole("button", { name: "Published to Content Vault" })).toBeDisabled();
    expect(fetch).toHaveBeenCalledWith("/api/v1/commerce-authoring/offering-1/telegram-content-vault", expect.objectContaining({ method: "POST" }));
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
