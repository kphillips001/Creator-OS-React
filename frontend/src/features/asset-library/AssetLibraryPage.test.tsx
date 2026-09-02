import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AssetLibraryPage } from "./AssetLibraryPage";
import { StandaloneSalePreparationDialog } from "./StandaloneSalePreparationDialog";
import type { AssetLibraryItem, ContentVaultCaptionDraft } from "./types";

const stylesheetText = readFileSync(resolve("src/features/asset-library/asset-library.css"), "utf8");
const sharedStylesheetText = readFileSync(resolve("src/shared/ui/shared-ui.css"), "utf8");

const asset = {
  libraryItemId: "asset:42",
  itemKind: "registered_asset" as const,
  assetId: 42,
  generationId: null,
  fileName: "portrait.png",
  mediaType: "image",
  classification: "premium",
  status: "approved",
  createdAt: "2026-01-02T00:00:00Z",
  tags: ["portrait"],
  themes: ["studio"],
  isReference: false,
  isCanonicalReference: false,
  mediaAvailable: true,
  imageUrl: "/api/v1/assets/42/thumbnail",
};

const response = (body: unknown, ok = true) => Promise.resolve(new Response(
  JSON.stringify(body),
  { status: ok ? 200 : 500, headers: { "Content-Type": "application/json" } },
));

beforeEach(() => {
  window.history.replaceState({}, "", "/library/assets");
  window.sessionStorage.removeItem("creator-os.asset-library.moved-asset-id");
});
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

async function openAssetType(name: "Images" | "Photoshoots" | "Videos" | "Teasers") {
  fireEvent.click(await screen.findByRole("button", { name: new RegExp(`^${name}`) }));
}

describe("AssetLibraryPage", () => {
  it("consumes a moved Asset handoff and opens the existing inspector even when the Asset is not on page one", async () => {
    const movedAsset = { ...asset, libraryItemId: "asset:77", assetId: 77, displayName: "Newly Moved Portrait", fileName: "moved.png" };
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    window.sessionStorage.setItem("creator-os.asset-library.moved-asset-id", "77");
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/counts") return response({ images: 2, photoshoots: 0, videos: 0 });
      if (url === "/api/v1/assets/77") return response(movedAsset);
      if (url.startsWith("/api/v1/assets?")) return response({ assets: [{ ...asset, displayName: "First Page Portrait" }], total: 2, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
      return response({ detail: "Unexpected request" }, false);
    });

    render(<AssetLibraryPage />);

    expect(await screen.findByRole("heading", { name: "Newly Moved Portrait" })).toBeInTheDocument();
    expect(screen.getByText("Asset #77")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/77", expect.objectContaining({ cache: "no-store" }));
    expect(window.sessionStorage.getItem("creator-os.asset-library.moved-asset-id")).toBeNull();
  });

  it("keeps independent Chat and Wall selective drafts valid while switching destinations", () => {
    const teaser = (distributionUse: "CHAT" | "CONTENT_VAULT") => ({
      id: distributionUse, distributionUse, teaserStyle: "SELECTIVE_BLUR" as const,
      status: "READY" as const, derivedAssetId: distributionUse === "CHAT" ? 90 : 91,
      previewUrl: `/${distributionUse}.png`, maskUrl: `/${distributionUse}-mask.png`, blurStrength: 24,
    });
    const preparedAsset = { ...asset, classification: "SINGLE_IMAGE", displayName: "Draft Image", standaloneSalePreparation: {
      assetId: 42, status: "READY" as const, statusLabel: "Ready", intelligenceReady: true,
      blurredTeaserReady: true, destinations: ["CHAT" as const], teaserStyle: "SELECTIVE_BLUR" as const,
      foundationReady: true, chatReady: true, vaultReady: true, teasers: [teaser("CHAT"), teaser("CONTENT_VAULT")],
    } };
    render(<StandaloneSalePreparationDialog asset={preparedAsset} onClose={vi.fn()} onStarted={vi.fn()} />);
    const dialog = screen.getByRole("dialog", { name: "Edit Sale Preparation" });
    const save = within(dialog).getByRole("button", { name: "Save Changes" });
    expect(save).toBeEnabled();
    fireEvent.click(within(dialog).getByLabelText("Ava's Content Vault"));
    expect(within(dialog).getByLabelText("Selective Blur")).toBeChecked();
    expect(save).toBeEnabled();
    fireEvent.click(within(dialog).getByLabelText("Chat Selling"));
    expect(within(dialog).getByText("Chat Teaser")).toBeInTheDocument();
    expect(save).toBeEnabled();
    fireEvent.click(within(dialog).getByLabelText("Ava's Content Vault"));
    fireEvent.click(within(dialog).getByLabelText("Full Blur"));
    expect(save).toBeEnabled();
    fireEvent.click(within(dialog).getByLabelText("Selective Blur"));
    expect(save).toBeEnabled();
  });

  it("defaults Wall to Full Blur and submits one destination with its explicit strategy", async () => {
    const onStarted = vi.fn();
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
      assetId: 42, status: "PREPARING", statusLabel: "Preparing", intelligenceReady: true,
      destinations: ["CONTENT_VAULT"], teaserStyle: "FULL_BLUR", teasers: [],
    }));
    render(<StandaloneSalePreparationDialog asset={{ ...asset, classification: "SINGLE_IMAGE", displayName: "Wall Draft" }} onClose={vi.fn()} onStarted={onStarted} />);
    const dialog = screen.getByRole("dialog", { name: "Prepare for Sale" });
    expect(within(dialog).getByRole("spinbutton", { name: "Price" })).toHaveValue(9.99);
    fireEvent.click(within(dialog).getByLabelText("Ava's Content Vault"));
    expect(within(dialog).getByLabelText("Full Blur")).toBeChecked();
    expect(within(dialog).getByRole("button", { name: "Prepare for Sale" })).toBeEnabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Prepare for Sale" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42/sale-preparation", expect.objectContaining({
      body: JSON.stringify({ priceMinor: 999, destinations: ["CONTENT_VAULT"], teaserStyle: "FULL_BLUR" }),
    }));
  });

  it("reassigns a prepared Single Image through the canonical destination endpoint", async () => {
    const onStarted = vi.fn();
    const preparedAsset = { ...asset, classification: "SINGLE_IMAGE", displayName: "Chat Image", standaloneSalePreparation: {
      assetId: 42, status: "READY" as const, statusLabel: "Ready", intelligenceReady: true,
      blurredTeaserReady: false,
      destinations: ["CHAT" as const], teaserStyle: "SELECTIVE_BLUR" as const,
      foundationReady: true, chatReady: true, vaultReady: false, teasers: [], priceMinor: 1099,
    } };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
      ...preparedAsset.standaloneSalePreparation, destinations: ["CONTENT_VAULT"],
      teaserStyle: "FULL_BLUR", vaultReady: true,
    }));
    render(<StandaloneSalePreparationDialog asset={preparedAsset} reassign onClose={vi.fn()} onStarted={onStarted} />);

    const dialog = screen.getByRole("dialog", { name: "Reassign Sales Destination" });
    expect(within(dialog).getByText(/Current Destination:/)).toHaveTextContent("Chat");
    expect(within(dialog).getByLabelText("Ava's Content Vault")).toBeChecked();
    fireEvent.click(within(dialog).getByRole("button", { name: "Reassign" }));

    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42/sale-destination", expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ priceMinor: 1099, destination: "CONTENT_VAULT", teaserStyle: "FULL_BLUR" }),
    }));
  });

  it("enables Wall to Chat reassignment when an accepted Chat teaser already exists", () => {
    const chatTeaser = { id: "chat-ready", distributionUse: "CHAT" as const, teaserStyle: "SELECTIVE_BLUR" as const,
      status: "READY" as const, derivedAssetId: 90, previewUrl: "/chat.png" };
    const preparedAsset = { ...asset, classification: "SINGLE_IMAGE", standaloneSalePreparation: {
      assetId: 42, status: "READY" as const, statusLabel: "Ready", intelligenceReady: true,
      blurredTeaserReady: true, destinations: ["CONTENT_VAULT" as const], teaserStyle: "SELECTIVE_BLUR" as const,
      foundationReady: true, chatReady: true, vaultReady: true, teasers: [chatTeaser], priceMinor: 999,
    } };
    render(<StandaloneSalePreparationDialog asset={preparedAsset} reassign onClose={vi.fn()} onStarted={vi.fn()} />);

    expect(screen.getByLabelText("Chat Selling")).toBeChecked();
    expect(screen.getByRole("button", { name: "Reassign" })).toBeEnabled();
    expect(screen.getByText("Teaser Ready")).toBeInTheDocument();
  });

  it("explains and exposes the missing Chat teaser prerequisite without accepting the Wall teaser", () => {
    const wallTeaser = { id: "wall-ready", distributionUse: "CONTENT_VAULT" as const, teaserStyle: "SELECTIVE_BLUR" as const,
      status: "READY" as const, derivedAssetId: 91, previewUrl: "/wall.png" };
    const preparedAsset = { ...asset, classification: "SINGLE_IMAGE", standaloneSalePreparation: {
      assetId: 42, status: "READY" as const, statusLabel: "Ready", intelligenceReady: true,
      blurredTeaserReady: true, destinations: ["CONTENT_VAULT" as const], teaserStyle: "SELECTIVE_BLUR" as const,
      foundationReady: true, chatReady: false, vaultReady: true, teasers: [wallTeaser], priceMinor: 999,
    } };
    render(<StandaloneSalePreparationDialog asset={preparedAsset} reassign onClose={vi.fn()} onStarted={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Reassign" })).toBeDisabled();
    expect(screen.getByText("Create, save, and accept a Chat teaser before reassigning.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create Selective Teaser" }));
    expect(screen.getByRole("dialog", { name: "Selective Blur Editor" })).toBeInTheDocument();
    expect(stylesheetText).toMatch(/scroll-padding-block-end:\s*96px/);
  });

  it("exposes the compact destination reassignment action on prepared Image cards", async () => {
    const preparedAsset = { ...asset, classification: "SINGLE_IMAGE", displayName: "Wall Single", standaloneSalePreparation: {
      assetId: 42, status: "READY" as const, statusLabel: "Ready", intelligenceReady: true,
      blurredTeaserReady: true, destinations: ["CONTENT_VAULT" as const], teaserStyle: "FULL_BLUR" as const,
      foundationReady: true, chatReady: false, vaultReady: true, teasers: [], priceMinor: 1099,
    } };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
      assets: [preparedAsset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"],
    }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");

    const card = (await screen.findByText("Wall Single")).closest("article")!;
    fireEvent.click(within(card).getByRole("button", { name: "Reassign sales destination" }));

    expect(screen.getByRole("dialog", { name: "Reassign Sales Destination" })).toBeInTheDocument();
    expect(screen.getByText(/Current Destination:/)).toHaveTextContent("TG Wall");
  });
  it("returns a registered Single Image and refreshes it out of Asset Library", async () => {
    const registered = { ...asset, generationId: "generated-1", classification: "SINGLE_IMAGE" };
    let returned = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/move-back-to-generation-library") && init?.method === "POST") {
        returned = true;
        return response({ success: true, message: "Image returned to Generation Library. Asset Intelligence was removed." });
      }
      return response({ assets: returned ? [] : [registered], total: returned ? 0 : 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Images");

    fireEvent.click(await screen.findByRole("button", { name: "Move to Generation Library" }));

    expect(await screen.findByText("Image returned to Generation Library. Asset Intelligence was removed.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("portrait.png")).not.toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/generation-library/generated-1/move-back-to-generation-library",
      { method: "POST" },
    );
  });

  it("polls visible non-terminal intelligence once per interval and preserves the selected inspector", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const analyzing = [
      { ...asset, intelligenceStatus: "GROK_RUNNING", displayName: "Analyzing Portrait" },
      { ...asset, assetId: 43, libraryItemId: "asset:43", intelligenceStatus: "VISION_PENDING", displayName: "Queued Portrait" },
    ];
    const detailCalls = new Map<number, number>();
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const match = url.match(/^\/api\/v1\/assets\/(42|43)$/);
      if (match) {
        const id = Number(match[1]);
        const calls = (detailCalls.get(id) || 0) + 1;
        detailCalls.set(id, calls);
        const current = analyzing.find((item) => item.assetId === id)!;
        return response(calls === 1 && id === 42
          ? current
          : { ...current, intelligenceStatus: "READY" });
      }
      return response({ assets: analyzing, total: 2, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    const view = render(<AssetLibraryPage />);
    const firstCard = (await screen.findByText("Analyzing Portrait")).closest("article")!;
    expect(within(firstCard).getByText("ANALYZING")).toBeInTheDocument();
    fireEvent.click(within(firstCard).getByRole("button", { name: "Open Image" }));
    const inspector = await screen.findByLabelText("Selected asset details");
    expect(within(inspector).getByText("ANALYZING")).toBeInTheDocument();
    const gridCalls = fetch.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/assets?")).length;

    await act(() => vi.advanceTimersByTimeAsync(3000));
    await waitFor(() => expect(within(firstCard).getByText("READY")).toBeInTheDocument());
    expect(screen.getByLabelText("Selected asset details")).toBe(inspector);
    expect(within(inspector).getByText("READY")).toBeInTheDocument();
    expect(detailCalls.get(42)).toBe(2); // inspector load + one polling request
    expect(detailCalls.get(43)).toBe(1);

    await act(() => vi.advanceTimersByTimeAsync(9000));
    expect(detailCalls.get(42)).toBe(2);
    expect(detailCalls.get(43)).toBe(1);
    expect(fetch.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/assets?")).length).toBe(gridCalls);
    view.unmount();
  });

  it("cancels intelligence polling when the Asset Library unmounts", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let detailCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input) === "/api/v1/assets/42") {
        detailCalls += 1;
        return response({ ...asset, intelligenceStatus: "GROK_RUNNING" });
      }
      return response({
        assets: [{ ...asset, intelligenceStatus: "GROK_RUNNING", displayName: "Analyzing Portrait" }],
        total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [],
      });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    const view = render(<AssetLibraryPage />);
    await screen.findByText("Analyzing Portrait");
    view.unmount();
    await act(() => vi.advanceTimersByTimeAsync(9000));
    expect(detailCalls).toBe(0);
  });

  it.each(["READY", "PARTIAL", "FAILED", "GROK_FAILED"])(
    "does not poll terminal intelligence state %s and cleans up on unmount",
    async (intelligenceStatus) => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
        assets: [{ ...asset, intelligenceStatus, displayName: "Settled Portrait" }],
        total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [],
      }));
      window.history.replaceState({}, "", "/library/assets?assetType=images");
      const view = render(<AssetLibraryPage />);
      await screen.findByText("Settled Portrait");
      const initialCalls = fetch.mock.calls.length;
      await act(() => vi.advanceTimersByTimeAsync(9000));
      expect(fetch).toHaveBeenCalledTimes(initialCalls);
      view.unmount();
      await act(() => vi.advanceTimersByTimeAsync(9000));
      expect(fetch).toHaveBeenCalledTimes(initialCalls);
    },
  );

  it("prepares a registered image for sale from the card", async () => {
    const prepared = { assetId: 42, status: "PREPARING", statusLabel: "Preparing...", intelligenceReady: true, blurredTeaserReady: true };
    vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      if (String(input) === "/api/v1/assets/42/sale-preparation" && options?.method === "POST") return response(prepared);
      return response({ assets: [{ ...asset, displayName: "Sunlit Kitchen Reveal", intelligenceStatus: "READY", standaloneSalePreparation: { ...prepared, status: "NOT_PREPARED", statusLabel: "Prepare for Sale", blurredTeaserReady: false } }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    const prompt = vi.spyOn(window, "prompt");
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    render(<AssetLibraryPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare for Sale" }));
    const dialog = await screen.findByRole("dialog", { name: "Prepare for Sale" });
    expect(within(dialog).getByText("Sunlit Kitchen Reveal")).toBeInTheDocument();
    expect(prompt).not.toHaveBeenCalled();
    const chat = within(dialog).getByLabelText("Chat Selling");
    const vault = within(dialog).getByLabelText("Ava's Content Vault");
    expect(chat).toBeChecked();
    expect(vault).not.toBeChecked();
    expect(within(dialog).getByText("Chat Teaser")).toBeInTheDocument();
    expect(within(dialog).queryByText("Content Vault Teaser")).not.toBeInTheDocument();
    fireEvent.click(vault);
    expect(chat).not.toBeChecked();
    expect(vault).toBeChecked();
    expect(within(dialog).queryByText("Chat Teaser")).not.toBeInTheDocument();
    expect(within(dialog).getByText("Content Vault Teaser")).toBeInTheDocument();
    fireEvent.click(chat);
    expect(chat).toBeChecked();
    expect(vault).not.toBeChecked();
    fireEvent.click(vault);
    fireEvent.change(within(dialog).getByLabelText("Price"), { target: { value: "12.50" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Prepare for Sale" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Prepare for Sale" })).not.toBeInTheDocument());
    expect(await screen.findByText("Preparing")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42/sale-preparation", expect.objectContaining({
      method: "POST", body: JSON.stringify({ priceMinor: 1250, destinations: ["CONTENT_VAULT"], teaserStyle: "FULL_BLUR" }),
    }));
  });

  it("shows persisted standalone destinations on cards and in Asset details", async () => {
    const preparation = (destinations: ("CHAT" | "CONTENT_VAULT")[], status = "READY") => ({
      assetId: 42, status, statusLabel: status, intelligenceReady: true,
      blurredTeaserReady: true, destinations, foundationReady: true,
      chatReady: destinations.includes("CHAT"), vaultReady: destinations.includes("CONTENT_VAULT"), teasers: [],
    });
    const assets = [
      { ...asset, assetId: 42, libraryItemId: "asset:42", displayName: "Chat Image", standaloneSalePreparation: preparation(["CHAT"]) },
      { ...asset, assetId: 43, libraryItemId: "asset:43", displayName: "Vault Image", standaloneSalePreparation: preparation(["CONTENT_VAULT"]) },
      { ...asset, assetId: 44, libraryItemId: "asset:44", displayName: "Both Image", standaloneSalePreparation: preparation(["CHAT", "CONTENT_VAULT"], "NEEDS_ATTENTION") },
      { ...asset, assetId: 45, libraryItemId: "asset:45", displayName: "Unprepared Image", standaloneSalePreparation: preparation([], "NOT_PREPARED") },
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input) === "/api/v1/assets/44") return response(assets[2]);
      return response({ assets, total: 4, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    render(<AssetLibraryPage />);
    await screen.findByText("Chat Image");
    const card = (name: string) => screen.getByText(name).closest("article")!;
    expect(within(card("Chat Image")).getByLabelText("Selling and publishing destinations")).toHaveTextContent("Chat");
    expect(within(card("Vault Image")).getByLabelText("Selling and publishing destinations")).toHaveTextContent("WALL");
    expect(within(card("Vault Image")).queryByText("Content Vault")).not.toBeInTheDocument();
    expect(within(card("Both Image")).queryByLabelText("Selling and publishing destinations")).not.toBeInTheDocument();
    expect(within(card("Both Image")).getByText("Needs Attention")).toBeInTheDocument();
    expect(within(card("Unprepared Image")).queryByLabelText("Selling and publishing destinations")).not.toBeInTheDocument();
    fireEvent.click(within(card("Both Image")).getByRole("button", { name: "Open Image" }));
    const detail = await screen.findByLabelText("Selected asset details");
    expect(within(detail).getByRole("heading", { name: "Selling / Publishing" })).toBeInTheDocument();
    expect(within(detail).queryByLabelText("Selling and publishing destinations")).not.toBeInTheDocument();
  });

  it("folds authoritative persisted publication state into the Single Image WALL badge", async () => {
    const preparation = (destination: "CHAT" | "CONTENT_VAULT", publicationStatus: "NOT_PUBLISHED" | "PUBLISHING" | "FAILED" | "PUBLISHED") => ({
      assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true,
      destinations: [destination], foundationReady: true, chatReady: destination === "CHAT",
      vaultReady: destination === "CONTENT_VAULT", teasers: [],
      contentVaultPublication: { status: publicationStatus, canPublish: publicationStatus === "NOT_PUBLISHED", configured: true },
    });
    const assets = [
      { ...asset, displayName: "Not Published", classification: "SINGLE_IMAGE", standaloneSalePreparation: preparation("CONTENT_VAULT", "NOT_PUBLISHED") },
      { ...asset, assetId: 43, libraryItemId: "asset:43", displayName: "Publishing", classification: "SINGLE_IMAGE", standaloneSalePreparation: preparation("CONTENT_VAULT", "PUBLISHING") },
      { ...asset, assetId: 44, libraryItemId: "asset:44", displayName: "Failed", classification: "SINGLE_IMAGE", standaloneSalePreparation: preparation("CONTENT_VAULT", "FAILED") },
      { ...asset, assetId: 45, libraryItemId: "asset:45", displayName: "Published Wall", classification: "SINGLE_IMAGE", standaloneSalePreparation: preparation("CONTENT_VAULT", "PUBLISHED") },
      { ...asset, assetId: 46, libraryItemId: "asset:46", displayName: "Published Chat", classification: "SINGLE_IMAGE", standaloneSalePreparation: preparation("CHAT", "PUBLISHED") },
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ assets, total: 5, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    render(<AssetLibraryPage />); await screen.findByText("Published Wall");
    const card = (name: string) => screen.getByText(name).closest("article")!;
    expect(within(card("Published Wall")).getByText("✓ WALL")).toBeInTheDocument();
    expect(within(card("Published Wall")).getByText("Ready")).toBeInTheDocument();
    expect(within(card("Published Wall")).queryByText("Posted")).not.toBeInTheDocument();
    for (const name of ["Not Published", "Publishing", "Failed", "Published Chat"]) {
      expect(within(card(name)).queryByText("✓ WALL")).not.toBeInTheDocument();
    }
    expect(within(card("Not Published")).getByText("WALL")).toBeInTheDocument();
    expect(within(card("Published Chat")).getByText("Chat")).toBeInTheDocument();
  });

  it("shows canonical prepared prices beneath Registered only on READY Single Images", async () => {
    const prepared = (destination: "CHAT" | "CONTENT_VAULT", priceMinor: number, currency: string) => ({
      assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true,
      destinations: [destination], foundationReady: true, chatReady: destination === "CHAT",
      vaultReady: destination === "CONTENT_VAULT", teasers: [], priceMinor, currency,
    });
    const assets = [
      { ...asset, classification: "SINGLE_IMAGE", displayName: "Wall Image", standaloneSalePreparation: prepared("CONTENT_VAULT", 1099, "USD") },
      { ...asset, assetId: 43, libraryItemId: "asset:43", classification: "SINGLE_IMAGE", displayName: "Chat Image", standaloneSalePreparation: prepared("CHAT", 799, "GBP") },
      { ...asset, assetId: 44, libraryItemId: "asset:44", classification: "SINGLE_IMAGE", displayName: "Unprepared Image", standaloneSalePreparation: { ...prepared("CHAT", 0, "USD"), status: "NOT_PREPARED", destinations: [] } },
      { ...asset, assetId: 45, libraryItemId: "asset:45", mediaType: "video", classification: "VIDEO", displayName: "Video Asset", standaloneSalePreparation: prepared("CHAT", 2500, "USD") },
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ assets, total: 4, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    window.history.replaceState({}, "", "/library/assets?assetType=images"); render(<AssetLibraryPage />);
    const card = (name: string) => screen.getByText(name).closest("article")!;
    await screen.findByText("Wall Image");
    const wallRows = within(card("Wall Image")).getAllByRole("term").map((node) => node.textContent);
    expect(wallRows).toEqual(["Type", "Intelligence", "Registered", "Price"]);
    expect(within(card("Wall Image")).getByText("$10.99")).toBeInTheDocument();
    expect(within(card("Chat Image")).getByText("£7.99")).toBeInTheDocument();
    expect(within(card("Unprepared Image")).getByText("Not Priced")).toBeInTheDocument();
    expect(within(card("Unprepared Image")).queryByText("$0.00")).not.toBeInTheDocument();
    expect(within(card("Video Asset")).queryByText("Price")).not.toBeInTheDocument();
  });

  it("updates the card price immediately after editing persisted sale preparation", async () => {
    const state = (priceMinor: number) => ({ assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true,
      destinations: ["CONTENT_VAULT"], teaserStyle: "FULL_BLUR", foundationReady: true, chatReady: false,
      vaultReady: true, teasers: [], priceMinor, currency: "USD" });
    vi.spyOn(globalThis, "fetch").mockImplementation((input, options) =>
      String(input) === "/api/v1/assets/42/sale-preparation" && options?.method === "POST"
        ? response(state(1499))
        : response({ assets: [{ ...asset, classification: "SINGLE_IMAGE", displayName: "Editable Wall", standaloneSalePreparation: state(1799) }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    window.history.replaceState({}, "", "/library/assets?assetType=images"); render(<AssetLibraryPage />);
    const card = (await screen.findByText("Editable Wall")).closest("article")!;
    expect(within(card).getByText("$17.99")).toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "Edit Sale Preparation" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit Sale Preparation" });
    fireEvent.change(within(dialog).getByLabelText("Price"), { target: { value: "14.99" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit Sale Preparation" })).not.toBeInTheDocument());
    expect(within(card).getByText("$14.99")).toBeInTheDocument();
    expect(within(card).queryByText("$17.99")).not.toBeInTheDocument();
  });

  it("uses an Images-only destination filter that composes with search and authoritative counts", async () => {
    const chatImage = { ...asset, displayName: "Golden Chat", classification: "SINGLE_IMAGE", standaloneSalePreparation: { assetId: 42, status: "READY", destinations: ["CHAT"] } };
    const wallImage = { ...asset, assetId: 43, libraryItemId: "asset:43", displayName: "Golden Wall", classification: "SINGLE_IMAGE", standaloneSalePreparation: { assetId: 43, status: "READY", destinations: ["CONTENT_VAULT"] } };
    const unpreparedImage = { ...asset, assetId: 44, libraryItemId: "asset:44", displayName: "Waiting Image", classification: "SINGLE_IMAGE", standaloneSalePreparation: { assetId: 44, status: "NOT_PREPARED", destinations: [] } };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = new URL(String(input), "http://localhost");
      if (url.searchParams.get("page_size") === "1") return response({ assets: [], total: 3, page: 1, pageSize: 1, totalPages: 3, classifications: [] });
      const destination = url.searchParams.get("destination");
      const search = url.searchParams.get("search");
      const choices = destination === "CHAT" ? [chatImage]
        : destination === "CONTENT_VAULT" ? [wallImage]
          : destination === "NOT_PREPARED" ? [unpreparedImage]
            : [chatImage, wallImage, unpreparedImage];
      const assets = search ? choices.filter((item) => item.displayName.toLowerCase().includes(search.toLowerCase())) : choices;
      return response({ assets, total: assets.length, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    render(<AssetLibraryPage />);

    const destination = await screen.findByLabelText("Destination");
    expect(screen.queryByLabelText("Classification")).not.toBeInTheDocument();
    expect(within(destination).getByRole("option", { name: "All destinations" })).toBeInTheDocument();
    expect(within(destination).getByRole("option", { name: "Chat" })).toBeInTheDocument();
    expect(within(destination).getByRole("option", { name: "Wall" })).toBeInTheDocument();
    expect(within(destination).getByRole("option", { name: "Not Prepared" })).toBeInTheDocument();
    expect(screen.queryByText("Classification", { selector: "dt" })).not.toBeInTheDocument();

    fireEvent.change(destination, { target: { value: "CHAT" } });
    expect(await screen.findByText("Golden Chat")).toBeInTheDocument();
    expect(screen.queryByText("Golden Wall")).not.toBeInTheDocument();
    expect(screen.getByText("1-1 of 1")).toBeInTheDocument();

    fireEvent.change(destination, { target: { value: "CONTENT_VAULT" } });
    expect(await screen.findByText("Golden Wall")).toBeInTheDocument();
    expect(screen.getByLabelText("Selling and publishing destinations")).toHaveTextContent("WALL");

    fireEvent.change(destination, { target: { value: "NOT_PREPARED" } });
    expect(await screen.findByText("Waiting Image")).toBeInTheDocument();
    expect(within(screen.getByText("Waiting Image").closest("article")!).getByText("Not Prepared")).toBeInTheDocument();

    fireEvent.change(destination, { target: { value: "CHAT" } });
    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: "Golden" } });
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
      const url = new URL(String(input), "http://localhost");
      return url.searchParams.get("destination") === "CHAT" && url.searchParams.get("search") === "Golden";
    })).toBe(true));
    expect(screen.getByText("Golden Chat")).toBeInTheDocument();
  });

  it("cancels Single Image preparation without submitting and validates price", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ assets: [{ ...asset, displayName: "Sunlit Kitchen Reveal", intelligenceStatus: "READY", standaloneSalePreparation: { assetId: 42, status: "NOT_PREPARED", statusLabel: "Prepare for Sale", intelligenceReady: true, blurredTeaserReady: false } }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] }));
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    render(<AssetLibraryPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Prepare for Sale" }));
    const dialog = await screen.findByRole("dialog", { name: "Prepare for Sale" });
    fireEvent.change(within(dialog).getByLabelText("Price"), { target: { value: "2.99" } });
    expect(within(dialog).getByRole("button", { name: "Prepare for Sale" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Prepare for Sale" })).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([, options]) => options?.method === "POST")).toBe(false);
  });

  it("restores persisted READY and Needs Attention states and retries idempotently", async () => {
    let status = "NEEDS_ATTENTION";
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      if (String(input) === "/api/v1/assets/42/sale-preparation/retry" && options?.method === "POST") {
        status = "PREPARING";
        return response({ assetId: 42, status, statusLabel: "Preparing...", intelligenceReady: true, blurredTeaserReady: true });
      }
      return response({ assets: [{ ...asset, displayName: "Sunlit Kitchen Reveal", intelligenceStatus: "READY", standaloneSalePreparation: { assetId: 42, status, statusLabel: status === "READY" ? "Ready" : "Needs Attention", intelligenceReady: true, blurredTeaserReady: true, error: "Upload timed out" } }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    const view = render(<AssetLibraryPage />);
    expect(await screen.findByText("Needs Attention")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Preparation" }));
    const dialog = await screen.findByRole("dialog", { name: "Retry Preparation" });
    fireEvent.click(within(dialog).getByLabelText("Chat Selling"));
    fireEvent.click(within(dialog).getByLabelText("Ava's Content Vault"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry Preparation" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42/sale-preparation/retry", expect.objectContaining({ method: "POST" })));
    view.unmount(); status = "READY";
    render(<AssetLibraryPage />);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Sale Preparation" })).toBeEnabled();
  });

  it("reconciles the selected inspector as soon as a failed retry is accepted", async () => {
    const failed = {
      assetId: 42, status: "NEEDS_ATTENTION", statusLabel: "Needs Attention",
      intelligenceReady: true, blurredTeaserReady: true,
      destinations: ["CONTENT_VAULT"], teaserStyle: "FULL_BLUR",
      priceMinor: 1399, currency: "USD", foundationReady: false,
      error: "Fanvue request failed with HTTP 503.", teasers: [],
    };
    const preparing = {
      ...failed, status: "PREPARING", statusLabel: "Preparing...",
      error: null,
    };
    const item = {
      ...asset, classification: "SINGLE_IMAGE", displayName: "Kitchen Seductive Glance",
      standaloneSalePreparation: failed,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      const url = String(input);
      if (url === "/api/v1/assets/42") return response(item);
      if (url === "/api/v1/assets/42/sale-preparation/retry" && options?.method === "POST") {
        return response(preparing);
      }
      return response({ assets: [item], total: 1, page: 1, pageSize: 18,
        totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    render(<AssetLibraryPage />);
    const card = (await screen.findByText("Kitchen Seductive Glance")).closest("article")!;
    fireEvent.click(within(card).getByRole("button", { name: "Open Image" }));
    const inspector = await screen.findByLabelText("Selected asset details");
    expect(within(inspector).getByText("Fanvue request failed with HTTP 503.")).toBeInTheDocument();
    fireEvent.click(within(inspector).getByRole("button", { name: "Retry Sale Preparation" }));
    const dialog = await screen.findByRole("dialog", { name: "Retry Preparation" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Retry Preparation" }));

    await waitFor(() => expect(within(inspector).getAllByText("Preparing")).toHaveLength(2));
    expect(within(inspector).queryByText("Fanvue request failed with HTTP 503.")).not.toBeInTheDocument();
    expect(within(inspector).queryByRole("button", { name: "Retry Sale Preparation" })).not.toBeInTheDocument();
  });

  it("quietly polls only preparation state and keeps the PREPARING card mounted", async () => {
    let inspectionCount = 0;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/42/sale-preparation") {
        inspectionCount += 1;
        return response({ assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true, blurredTeaserReady: true, destinations: ["CHAT"], priceMinor: 1499, currency: "USD" });
      }
      return response({ assets: [{ ...asset, displayName: "Sunlit Kitchen Reveal", classification: "SINGLE_IMAGE", intelligenceStatus: "READY", standaloneSalePreparation: { assetId: 42, status: "PREPARING", statusLabel: "Preparing...", intelligenceReady: true, blurredTeaserReady: true, destinations: ["CHAT"] } }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=images");
    render(<AssetLibraryPage />);
    const title = await screen.findByText("Sunlit Kitchen Reveal");
    const card = title.closest("article");
    const gridRequestsBefore = fetch.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/assets?")).length;
    expect(within(card!).getByText("Price")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument(), { timeout: 5500 });

    expect(screen.getByText("Sunlit Kitchen Reveal").closest("article")).toBe(card);
    expect(screen.queryByText("Loading assets...")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Selling and publishing destinations")).toHaveTextContent("Chat");
    expect(within(card!).getByText("$14.99")).toBeInTheDocument();
    expect(inspectionCount).toBe(1);
    expect(fetch.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/assets?")).length).toBe(gridRequestsBefore);
  }, 7000);

  it("keeps Photoshoot preparation in the viewer rather than the grid card", async () => {
    let prepared = false;
    const photoshoot = { ...asset, libraryItemId: "photoshoot:set-1", itemKind: "photoshoot" as const, assetId: null, deliverableId: "set-1", generationId: null, fileName: "Sunlit Serenity", mediaType: "photoshoot", classification: null, status: "IN_ASSET_LIBRARY", shotCount: 6, sellingMode: "SESSION", bundleSalesChannel: null };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      if (String(input) === "/api/v1/photoshoot-gallery/set-1") return response({
        deliverableId: "set-1", name: "Sunlit Serenity", description: null,
        completedAt: "2026-01-02T00:00:00Z", shotCount: 6, imageUrl: "/cover",
        registrationState: "IN_ASSET_LIBRARY", sellingMode: "SESSION",
        intelligence: {}, productionIntelligence: {}, technical: {},
        sessionTeaser: { eligible: true, reason: null, sourceAssetId: 1, hasSessionTeaser: false },
        members: Array.from({ length: 6 }, (_, index) => ({ assetId: index + 1, shotOrder: index + 1, imageUrl: `/shot-${index + 1}` })),
      });
      if (String(input).endsWith("/assets/photoshoots/set-1/sale-preparation")) {
        if (options?.method === "POST") prepared = true;
        return response({
        deliverableId: "set-1", photoshootSessionId: "session-1", strategyVersion: "v1",
        status: prepared ? "READY" : "NOT_PREPARED",
        statusLabel: prepared ? "Ready for Session Selling" : "Not Prepared", paidStepCount: 1,
        readyPaidStepCount: prepared ? 1 : 0, teaserReady: true, steps: [
          { assetId: 1, shotOrder: 1, position: 1, role: "FREE_TEASER", access: "FREE", ready: true },
          { assetId: 2, shotOrder: 2, position: 2, role: "FIRST_UNLOCK", access: "PAID",
            ready: prepared, priceMinor: prepared ? 500 : null },
        ],
        });
      }
      if (String(input).endsWith("/commercial-offerings/photoshoots/set-1/prepare")) return response({
        deliverableId: "set-1", title: "Sunlit Serenity", description: "A complete set.",
        heroAssetId: 2, coverAssetId: 3, supportedChannels: ["AI_CHAT", "TELEGRAM_WALL"],
        members: Array.from({ length: 6 }, (_, index) => ({ assetId: index + 1, shotOrder: index + 1, imageUrl: `/shot-${index + 1}` })),
      });
      return response({ assets: [{ ...photoshoot,
        sessionSelling: prepared ? { status: "READY", statusLabel: "Ready" } : undefined,
        commercialPrice: prepared ? { status: "PRICED", amountMinor: 500, currency: "USD", kind: "SESSION_TOTAL" } : undefined,
      }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Photoshoots");
    expect(await screen.findByText("Sunlit Serenity")).toBeInTheDocument();
    expect(screen.getByText(/Photoshoot.*6 Images/)).toBeInTheDocument();
    expect(screen.getByText("Not Prepared")).toBeInTheDocument();
    expect(screen.getByText("SESSION")).toBeInTheDocument();
    const card = screen.getByRole("button", { name: "Open Photoshoot cover" }).closest("article")!;
    expect(within(card).queryByRole("button", { name: "Prepare for Sale" })).not.toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Reassign Photoshoot commerce" })).toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Archive" })).toBeInTheDocument();
    expect(within(card).getAllByRole("button")).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: "Open Photoshoot" }));
    expect(await screen.findByText("Shot 6")).toBeInTheDocument();
    expect(screen.getByLabelText("Photoshoot filmstrip")).toBeInTheDocument();
    const selectedShot = screen.getByRole("heading", { name: "Selected Shot — Shot 1" }).closest("article")!;
    expect(within(selectedShot).getByRole("button", { name: "Create Teaser" })).toBeEnabled();
    expect(document.querySelectorAll(".photoshoot-detail-shot__media")).toHaveLength(6);
    expect(screen.getAllByRole("button", { name: /Select shot/ }).map((button) => button.getAttribute("aria-label"))).toEqual([
      "Select shot 1", "Select shot 2", "Select shot 3", "Select shot 4", "Select shot 5", "Select shot 6",
    ]);
    expect(screen.queryByRole("dialog", { name: /Asset .* preview/ })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/photoshoot-gallery/set-1", expect.objectContaining({ cache: "no-store" }));
    expect(screen.getByText("Selling Mode")).toBeInTheDocument();
    const libraryRequestsBeforePreparation = fetch.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/assets?")).length;
    fireEvent.click(await screen.findByRole("button", { name: "Set Session Prices" }));
    const prepareDialog = await screen.findByRole("dialog", { name: "Prepare Session" });
    expect(await screen.findByLabelText("Shot 2 price")).toBeInTheDocument();
    expect(screen.getByLabelText("Photoshoot filmstrip")).toBeInTheDocument();
    expect(screen.queryByText("Loading assets...")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Shot 2 price"), { target: { value: "5.00" } });
    fireEvent.click(within(prepareDialog).getByRole("button", { name: "Prepare Session" }));
    expect(await screen.findByRole("heading", { name: "READY" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(await screen.findByText("$5.00 Total")).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/assets?")).length).toBeGreaterThan(libraryRequestsBeforePreparation);
  });

  it("shows canonical Bundle and complete Session prices on Photoshoot cards", async () => {
    const photoshoot = (id: string, name: string, sellingMode: "SESSION" | "BUNDLE", commercialPrice: AssetLibraryItem["commercialPrice"]) => ({
      ...asset, libraryItemId: `photoshoot:${id}`, itemKind: "photoshoot" as const,
      assetId: null, deliverableId: id, generationId: null, fileName: name,
      mediaType: "photoshoot", classification: null, shotCount: 6, sellingMode,
      bundleSalesChannel: sellingMode === "BUNDLE" ? "CONTENT_WALL" as const : null,
      sessionSelling: { sellingMode, status: "READY", statusLabel: "Ready" }, commercialPrice,
    });
    const assets = [
      photoshoot("session", "Priced Session", "SESSION", { status: "PRICED", amountMinor: 8395, currency: "USD", kind: "SESSION_TOTAL" }),
      photoshoot("bundle", "Priced Bundle", "BUNDLE", { status: "PRICED", amountMinor: 2499, currency: "USD", kind: "BUNDLE" }),
      photoshoot("waiting", "Waiting Session", "SESSION", { status: "NOT_PRICED", amountMinor: null, currency: "USD", kind: "SESSION_TOTAL" }),
      photoshoot("incomplete", "Incomplete Session", "SESSION", { status: "INCOMPLETE", amountMinor: null, currency: "USD", kind: "SESSION_TOTAL" }),
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ assets, total: 4, page: 1, pageSize: 18, totalPages: 1, classifications: [] }));
    window.history.replaceState({}, "", "/library/assets?assetType=photoshoots");
    render(<AssetLibraryPage />);

    const card = (name: string) => screen.getByText(name).closest("article")!;
    await screen.findByText("Priced Session");
    expect(within(card("Priced Session")).getByText("$83.95 Total")).toBeInTheDocument();
    expect(within(card("Priced Bundle")).getByText("$24.99")).toBeInTheDocument();
    expect(within(card("Waiting Session")).getByText("Not Priced")).toBeInTheDocument();
    expect(within(card("Incomplete Session")).getByText("Pricing Incomplete")).toBeInTheDocument();
    for (const name of ["Priced Session", "Priced Bundle", "Waiting Session", "Incomplete Session"]) {
      expect(card(name).querySelector(".asset-card__photoshoot-badges")).not.toHaveTextContent(/\$|priced|pricing/i);
    }
  });

  it("reassigns a Photoshoot selling mode from its card and refreshes the canonical badge", async () => {
    let sellingMode: "SESSION" | "BUNDLE" = "SESSION";
    const photoshoot = () => ({ ...asset, libraryItemId: "photoshoot:set-mode", itemKind: "photoshoot" as const,
      assetId: null, deliverableId: "set-mode", generationId: null, fileName: "Hardwood Tease",
      mediaType: "photoshoot", classification: null, status: "IN_ASSET_LIBRARY", shotCount: 3,
      sellingMode, bundleSalesChannel: null });
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      if (String(input).endsWith("/photoshoots/set-mode/commerce-assignment") && options?.method === "PUT") {
        sellingMode = (JSON.parse(String(options.body)) as { sellingMode: "SESSION" | "BUNDLE" }).sellingMode;
        return response({ deliverableId: "set-mode", sellingMode, bundleSalesChannel: sellingMode === "BUNDLE" ? "CHAT" : null });
      }
      return response({ assets: [photoshoot()], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Photoshoots");
    const card = (await screen.findByText("Hardwood Tease")).closest("article")!;
    expect(within(card).getByText("SESSION")).toBeInTheDocument();

    fireEvent.click(within(card).getByRole("button", { name: "Reassign Photoshoot commerce" }));
    const dialog = screen.getByRole("dialog", { name: "Reassign Photoshoot" });
    expect(within(dialog).getByText(/Current selling mode:/)).toHaveTextContent("SESSION");
    fireEvent.click(within(dialog).getByRole("radio", { name: /Bundle/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Reassign" }));

    await waitFor(() => expect(within(card).getByText("BUNDLE")).toBeInTheDocument());
    expect(screen.queryByRole("dialog", { name: "Reassign Photoshoot" })).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining("/photoshoots/set-mode/commerce-assignment"), expect.objectContaining({
      method: "PUT", body: JSON.stringify({ sellingMode: "BUNDLE", bundleSalesChannel: "CHAT" }),
    }));
  });

  it("reassigns a Bundle from Chat to Wall using the canonical combined assignment", async () => {
    let channel: "CHAT" | "CONTENT_WALL" = "CHAT";
    const photoshoot = () => ({ ...asset, libraryItemId: "photoshoot:set-channel", itemKind: "photoshoot" as const,
      assetId: null, deliverableId: "set-channel", generationId: null, fileName: "Counter Open-Leg Tease",
      mediaType: "photoshoot", classification: null, status: "IN_ASSET_LIBRARY", shotCount: 3,
      sellingMode: "BUNDLE" as const, bundleSalesChannel: channel,
      sessionSelling: { sellingMode: "BUNDLE" as const, bundleSalesChannel: channel,
        salesChannel: channel === "CONTENT_WALL" ? "WALL" as const : "CHAT" as const,
        imageCount: 3, status: "READY" as const } });
    vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      if (String(input).endsWith("/photoshoots/set-channel/commerce-assignment") && options?.method === "PUT") {
        channel = (JSON.parse(String(options.body)) as { bundleSalesChannel: typeof channel }).bundleSalesChannel;
        return response({ deliverableId: "set-channel", sellingMode: "BUNDLE", bundleSalesChannel: channel });
      }
      return response({ assets: [photoshoot()], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Photoshoots");
    const card = (await screen.findByText("Counter Open-Leg Tease")).closest("article")!;
    fireEvent.click(within(card).getByRole("button", { name: "Reassign Photoshoot commerce" }));
    const dialog = screen.getByRole("dialog", { name: "Reassign Photoshoot" });
    expect(within(dialog).getByRole("button", { name: "Reassign" })).toBeDisabled();
    fireEvent.click(within(dialog).getByRole("radio", { name: /Wall/ }));
    expect(within(dialog).getByRole("button", { name: "Reassign" })).toBeEnabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Reassign" }));
    await waitFor(() => expect(within(card).getByText("WALL")).toBeInTheDocument());
    expect(within(card).getByText("BUNDLE")).toBeInTheDocument();
  });

  it("opens an imported Photoshoot card through the canonical six-shot viewer", async () => {
    let cardProjectionRequests = 0;
    const imported = { ...asset, libraryItemId: "photoshoot:import-1", itemKind: "photoshoot" as const,
      assetId: null, deliverableId: "import-1", generationId: null, fileName: "Imported Editorial",
      mediaType: "photoshoot", classification: null, status: "IN_ASSET_LIBRARY", shotCount: 6,
      sellingMode: "BUNDLE", bundleSalesChannel: null, sourceKind: "GENERATION_LIBRARY_IMPORT" };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input) === "/api/v1/photoshoot-gallery/import-1") return response({
        deliverableId: "import-1", name: "Imported Editorial", description: null,
        completedAt: "2026-08-12T00:00:00Z", shotCount: 6, heroAssetId: 104,
        imageUrl: "/cover", registrationState: "IN_ASSET_LIBRARY", sellingMode: "BUNDLE",
        bundleSalesChannel: null, sourceKind: "GENERATION_LIBRARY_IMPORT",
        intelligence: {}, productionIntelligence: {}, technical: {},
        members: Array.from({ length: 6 }, (_, index) => ({ assetId: 101 + index,
          shotOrder: index + 1, isHero: index === 3, imageUrl: `/shot-${index + 1}`, intelligence: {} })),
      });
      if (String(input).startsWith("/api/v1/assets?")) cardProjectionRequests += 1;
      return response({ assets: [imported], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Photoshoots");
    fireEvent.click(await screen.findByRole("button", { name: "Open Photoshoot" }));

    expect(await screen.findByLabelText("Photoshoot filmstrip")).toBeInTheDocument();
    expect(document.querySelectorAll(".photoshoot-detail-shot__media")).toHaveLength(6);
    expect(screen.getByRole("button", { name: "Select shot 4" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Create Video" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Sell this Photoshoot progressively/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sell the complete Photoshoot/ })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/photoshoot-gallery/import-1", expect.objectContaining({ cache: "no-store" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(cardProjectionRequests).toBeGreaterThanOrEqual(2));
  });

  it("renders separate readiness and commercial badges and filters Photoshoots with search", async () => {
    const photoshoots = [
      { ...asset, libraryItemId: "photoshoot:chat", itemKind: "photoshoot" as const, assetId: null, deliverableId: "chat", fileName: "Shower Bundle", mediaType: "photoshoot", classification: null, shotCount: 3, sellingMode: "BUNDLE", bundleSalesChannel: "CHAT", sessionSelling: { sellingMode: "BUNDLE", bundleSalesChannel: "CHAT", imageCount: 3, status: "READY", autonomousSales: { status: "READY" } } },
      { ...asset, libraryItemId: "photoshoot:chat-setup", itemKind: "photoshoot" as const, assetId: null, deliverableId: "chat-setup", fileName: "Evening Bundle", mediaType: "photoshoot", classification: null, shotCount: 2, sellingMode: "BUNDLE", bundleSalesChannel: "CHAT", sessionSelling: { sellingMode: "BUNDLE", bundleSalesChannel: "CHAT", imageCount: 2, status: "READY", autonomousSales: { status: "NEEDS_SETUP" } } },
      { ...asset, libraryItemId: "photoshoot:session", itemKind: "photoshoot" as const, assetId: null, deliverableId: "session", fileName: "Shower Session", mediaType: "photoshoot", classification: null, shotCount: 4, sellingMode: "SESSION", bundleSalesChannel: null, sessionSelling: { deliverableId: "session", photoshootSessionId: "session-runtime", sellingMode: "SESSION", strategyVersion: "photoshoot_session_sales_v1", status: "READY", statusLabel: "Ready for Session Selling", paidStepCount: 1, readyPaidStepCount: 1, teaserReady: true, steps: [{ assetId: 201, shotOrder: 1, position: 1, role: "FREE_TEASER", access: "FREE", ready: true }, { assetId: 202, shotOrder: 2, position: 2, role: "FIRST_UNLOCK", access: "PAID", ready: true, offeringId: "offering-session", offeringStatus: "READY", publicationStatus: "LIVE" }] } },
      { ...asset, libraryItemId: "photoshoot:session-no-channel", itemKind: "photoshoot" as const, assetId: null, deliverableId: "session-no-channel", fileName: "Private Session", mediaType: "photoshoot", classification: null, shotCount: 4, sellingMode: "SESSION", bundleSalesChannel: null, sessionSelling: { deliverableId: "session-no-channel", photoshootSessionId: "session-runtime-2", sellingMode: "SESSION", strategyVersion: "photoshoot_session_sales_v1", status: "READY", statusLabel: "Ready for Session Selling", paidStepCount: 1, readyPaidStepCount: 1, teaserReady: true, steps: [{ assetId: 203, shotOrder: 2, position: 1, role: "FIRST_UNLOCK", access: "PAID", ready: true }] } },
      { ...asset, libraryItemId: "photoshoot:wall", itemKind: "photoshoot" as const, assetId: null, deliverableId: "wall", fileName: "Morning Wall", mediaType: "photoshoot", classification: null, shotCount: 5, sellingMode: "BUNDLE", bundleSalesChannel: "CONTENT_WALL", sessionSelling: { sellingMode: "BUNDLE", bundleSalesChannel: "CONTENT_WALL", imageCount: 5, status: "READY" } },
    ];
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = new URL(String(input), "http://localhost");
      if (url.searchParams.get("media_type") !== "photoshoot") return response({ assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
      const classification = url.searchParams.get("classification");
      const search = (url.searchParams.get("search") || "").toLowerCase();
      const selected = photoshoots.filter((item) => (!classification || item.sellingMode === "SESSION" && classification === "SESSION" || item.sellingMode === "BUNDLE" && item.bundleSalesChannel === "CHAT" && classification === "CHAT" || item.sellingMode === "BUNDLE" && item.bundleSalesChannel === "CONTENT_WALL" && classification === "WALL") && (!search || item.fileName.toLowerCase().includes(search)));
      return response({ assets: selected, total: selected.length, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=photoshoots");
    render(<AssetLibraryPage />);

    expect(await screen.findByText("Shower Bundle")).toBeInTheDocument();
    expect(screen.getByText("Shower Session")).toBeInTheDocument();
    expect(screen.getByText("Morning Wall")).toBeInTheDocument();
    expect(within(screen.getByText("Shower Bundle").closest("article")!).getByText("Ready")).toBeInTheDocument();
    expect(within(screen.getByText("Evening Bundle").closest("article")!).getByText("Needs Setup")).toBeInTheDocument();
    expect(within(screen.getByText("Morning Wall").closest("article")!).getByText("Ready")).toBeInTheDocument();
    expect(screen.getAllByText("CHAT")).toHaveLength(3);
    expect(screen.getAllByText("SESSION")).toHaveLength(2);
    expect(screen.getByText("WALL")).toBeInTheDocument();
    expect(screen.getAllByText("BUNDLE")).toHaveLength(3);
    const badgeText = (name: string) => Array.from(
      screen.getByText(name).closest("article")!.querySelectorAll(".asset-card__photoshoot-badges em"),
    ).map((node) => node.textContent?.toUpperCase());
    expect(badgeText("Shower Bundle")).toEqual(["READY", "CHAT", "BUNDLE"]);
    expect(badgeText("Shower Session")).toEqual(["READY", "CHAT", "SESSION"]);
    expect(badgeText("Private Session")).toEqual(["READY", "SESSION"]);
    expect(badgeText("Morning Wall")).toEqual(["READY", "WALL", "BUNDLE"]);
    expect(within(screen.getByText("Shower Session").closest("article")!).getByText("SESSION"))
      .toHaveClass("photoshoot-badge--session");
    expect(within(screen.getByText("Shower Bundle").closest("article")!).getByText("BUNDLE"))
      .toHaveClass("photoshoot-badge--bundle");
    expect(within(screen.getByText("Shower Session").closest("article")!).getByText("CHAT"))
      .toHaveClass("photoshoot-badge--channel");
    expect(screen.getByLabelText("Classification")).toHaveTextContent("All classificationsChatSessionWall");

    fireEvent.change(screen.getByLabelText("Classification"), { target: { value: "CHAT" } });
    await waitFor(() => expect(screen.queryByText("Shower Session")).not.toBeInTheDocument());
    expect(screen.getByText("Shower Bundle")).toBeInTheDocument();
    expect(screen.queryByText("Morning Wall")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: "morning" } });
    expect(await screen.findByText("No assets found.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Classification"), { target: { value: "WALL" } });
    expect(await screen.findByText("Morning Wall")).toBeInTheDocument();
    expect(screen.queryByText("Shower Bundle")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Classification"), { target: { value: "SESSION" } });
    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: "shower" } });
    expect(await screen.findByText("Shower Session")).toBeInTheDocument();
    expect(screen.queryByText("Shower Bundle")).not.toBeInTheDocument();

    const actionGroup = screen.getByLabelText("Asset actions");
    expect(within(actionGroup).getByRole("button", { name: "Open Photoshoot" })).toBeInTheDocument();
    expect(within(actionGroup).getByRole("button", { name: "Archive" })).toBeInTheDocument();
    expect(within(actionGroup).queryByRole("button", { name: "Prepare for Sale" })).not.toBeInTheDocument();
    expect(sharedStylesheetText).toMatch(/\.library-action-group\s*\{[^}]*grid-auto-columns:\s*minmax\(0,1fr\)/);
  });

  it("folds authoritative posted state into the WALL badge for Photoshoot Bundles", async () => {
    const wall = (name: string, status: "NOT_PUBLISHED" | "PUBLISHED", id: string) => ({
      ...asset, libraryItemId: `photoshoot:${id}`, itemKind: "photoshoot" as const,
      assetId: null, deliverableId: id, fileName: name, mediaType: "photoshoot",
      classification: null, shotCount: 3, sellingMode: "BUNDLE", bundleSalesChannel: "CONTENT_WALL",
      sessionSelling: { sellingMode: "BUNDLE", bundleSalesChannel: "CONTENT_WALL", salesChannel: "WALL",
        imageCount: 3, status: "READY", contentVaultPublication: { status, canPublish: status !== "PUBLISHED", configured: true } },
    });
    const assets = [wall("Unposted Wall Bundle", "NOT_PUBLISHED", "wall-open"),
      wall("Posted Wall Bundle", "PUBLISHED", "wall-posted")];
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({
      assets, total: 2, page: 1, pageSize: 18, totalPages: 1, classifications: [],
    }));
    window.history.replaceState({}, "", "/library/assets?assetType=photoshoots");
    render(<AssetLibraryPage />);
    const card = (name: string) => screen.getByText(name).closest("article")!;
    await screen.findByText("Posted Wall Bundle");
    expect(Array.from(card("Posted Wall Bundle").querySelectorAll(".asset-card__photoshoot-badges em"))
      .map((node) => node.textContent)).toEqual(["Ready", "✓ WALL", "BUNDLE"]);
    expect(within(card("Posted Wall Bundle")).queryByText("POSTED")).not.toBeInTheDocument();
    expect(Array.from(card("Unposted Wall Bundle").querySelectorAll(".asset-card__photoshoot-badges em"))
      .map((node) => node.textContent)).toEqual(["Ready", "WALL", "BUNDLE"]);
  });

  it("opens Image details from both the image and Open action", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/42") return response({
        ...asset, displayName: "Sunlit Kitchen Reveal", classification: "SINGLE_IMAGE",
        registrationSource: "generation_library", intelligenceStatus: "READY",
        intelligenceDetails: {
          status: "READY",
          title: "Sunlit Kitchen Reveal", summary: "A quiet sunlit domestic portrait.",
          mood: "serene yet charged", atmosphere: "warm, hushed privacy",
          safetyClassification: "EXPLICIT", nudityLevel: "explicit",
          themes: ["intimate domesticity"], tags: ["natural light"],
        },
      });
      return response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["premium"] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Images");

    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    await screen.findByRole("heading", { name: "Sunlit Kitchen Reveal" });
    const detail = await screen.findByRole("complementary", { name: "Selected asset details" });
    expect(within(detail).getByText("Single Image", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Sunlit Kitchen Reveal" })).toBeInTheDocument();
    expect(within(detail).getByText("Asset Details").closest("details")).not.toHaveAttribute("open");
    fireEvent.click(within(detail).getByText("Asset Details"));
    expect(within(detail).getByText("generation_library")).toBeInTheDocument();
    expect(within(detail).getByRole("heading", { name: /Image Intelligence/ })).toHaveTextContent("READY");
    expect(within(detail).getByText("A quiet sunlit domestic portrait.")).toBeInTheDocument();
    expect(within(detail).getByText("serene yet charged")).toBeInTheDocument();
    expect(within(detail).getByText("intimate domesticity")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close asset details" }));
    fireEvent.click(screen.getByRole("button", { name: "Move to Generation Library" }));

    await screen.findByRole("heading", { name: "Sunlit Kitchen Reveal" });
    const reopened = await screen.findByRole("complementary", { name: "Selected asset details" });
    fireEvent.click(within(reopened).getByText("Asset Details"));
    expect(within(reopened).getByText("generation_library")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42", { cache: "no-store" });
  });

  it("shows an existing blurred preview under Commercial Assets", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input) === "/api/v1/assets/42") return response({
        ...asset, classification: "SINGLE_IMAGE",
        standaloneSalePreparation: { assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true, blurredTeaserReady: true, destinations: ["CONTENT_VAULT"], foundationReady: true, chatReady: false, vaultReady: true, teasers: [], priceMinor: 999, deliveryUrl: "https://fanvue.example/media" },
        commercialAssets: [{ kind: "BLURRED_PREVIEW", label: "Blurred Preview", status: "READY", previewUrl: "/api/v1/assets/42/derivatives/blurred-preview" }],
      });
      return response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));

    expect(await screen.findByRole("heading", { name: "Sale Preparation" })).toBeInTheDocument();
    expect(screen.getAllByText("$9.99")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Blurred Preview" })).toHaveAttribute("src", "/api/v1/assets/42/derivatives/blurred-preview");
    fireEvent.click(screen.getByRole("button", { name: "Open Blurred Preview preview" }));
    expect(screen.getByRole("dialog", { name: "Asset 42 preview" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close preview" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit Sale Preparation" }));
    expect(screen.getByRole("dialog", { name: "Edit Sale Preparation" })).toBeInTheDocument();
  });

  it.each([
    ["CONTENT_VAULT", "TG Wall", "Chat Selling"],
    ["CHAT", "Chat", "Ava's Content Vault"],
  ] as const)("exposes inspector destination reassignment for a prepared %s Single Image", async (destination, currentLabel, alternateLabel) => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/assets/42"
      ? response({ ...asset, classification: "SINGLE_IMAGE", displayName: "Prepared Single",
        standaloneSalePreparation: { assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true,
          blurredTeaserReady: destination === "CONTENT_VAULT", destinations: [destination], foundationReady: true,
          chatReady: destination === "CHAT", vaultReady: destination === "CONTENT_VAULT", teasers: [], priceMinor: 999 } })
      : response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    await screen.findByRole("heading", { name: "Prepared Single" });
    const detail = await screen.findByLabelText("Selected asset details");

    fireEvent.click(within(detail).getByRole("button", { name: "Reassign Destination" }));
    const dialog = screen.getByRole("dialog", { name: "Reassign Sales Destination" });
    expect(within(dialog).getByText(/Current Destination:/)).toHaveTextContent(currentLabel);
    expect(within(dialog).getByLabelText(alternateLabel)).toBeChecked();
    expect(within(dialog).getByLabelText(destination === "CHAT" ? "Chat Selling" : "Ava's Content Vault")).toBeDisabled();
  });

  it("hides inspector reassignment for unprepared Singles and disables it for published Wall Singles", async () => {
    let prepared = false;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/assets/42"
      ? response({ ...asset, classification: "SINGLE_IMAGE", displayName: prepared ? "Published Single" : "Unprepared Single",
        ...(prepared ? { standaloneSalePreparation: { assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true,
          blurredTeaserReady: true, destinations: ["CONTENT_VAULT"], foundationReady: true, chatReady: false, vaultReady: true,
          teasers: [], priceMinor: 999, contentVaultPublication: { status: "PUBLISHED", canPublish: false, configured: true } } } : {}) })
      : response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    await screen.findByRole("heading", { name: "Unprepared Single" });
    let detail = await screen.findByLabelText("Selected asset details");
    expect(within(detail).queryByRole("button", { name: "Reassign Destination" })).not.toBeInTheDocument();

    prepared = true;
    fireEvent.click(within(detail).getByRole("button", { name: "Close asset details" }));
    fireEvent.click(screen.getByRole("button", { name: "Open Image" }));
    await screen.findByRole("heading", { name: "Published Single" });
    detail = await screen.findByLabelText("Selected asset details");
    expect(within(detail).getByRole("button", { name: "Reassign Destination" })).toBeDisabled();
    expect(within(detail).getByRole("button", { name: "Reassign Destination" })).toHaveAttribute("title", expect.stringContaining("published"));
  });

  it.each([
    ["CHAT", "Chat Selling"],
    ["CONTENT_VAULT", "Content Vault"],
  ] as const)("shows and safely exposes the canonical Fanvue Media Link for %s", async (destination, destinationLabel) => {
    const mediaLink = "https://fanvue.com/media/very-long-canonical-link-that-must-remain-complete?token=delivery-token";
    const clipboard = { writeText: vi.fn().mockResolvedValue(undefined) };
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: clipboard });
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/assets/42"
      ? response({
        ...asset, classification: "SINGLE_IMAGE", displayName: `${destination} Image`,
        standaloneSalePreparation: { assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true, destinations: [destination], foundationReady: true, deliveryUrl: mediaLink, teasers: [] },
        commercialAssets: [{ kind: "PROMOTIONAL_TEASER", label: `${destinationLabel} Teaser — Selective Blur`, styleLabel: "Selective Blur", distributionUse: destination, status: "READY", previewUrl: "/teaser.png" }],
      })
      : response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    await screen.findByRole("heading", { name: `${destination} Image` });
    const detail = await screen.findByLabelText("Selected asset details");

    expect(within(detail).getByText(mediaLink)).toHaveAttribute("title", mediaLink);
    const open = within(detail).getByRole("link", { name: /Open/ });
    expect(open).toHaveAttribute("href", mediaLink);
    expect(open).toHaveAttribute("target", "_blank");
    expect(open).toHaveAttribute("rel", expect.stringContaining("noopener"));
    fireEvent.click(within(detail).getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(clipboard.writeText).toHaveBeenCalledWith(mediaLink));
    expect(within(detail).getByRole("button", { name: "Copied" })).toBeInTheDocument();
    expect(within(detail).getByText(`Used for ${destinationLabel}`)).toBeInTheDocument();
    expect(fetch.mock.calls.every(([input]) => !String(input).startsWith("https://fanvue.com"))).toBe(true);
  });

  it("does not expose delivery controls while preparing or when a ready link is missing", async () => {
    let state: { status: string; foundationReady: boolean; deliveryUrl: string | null } = { status: "PREPARING", foundationReady: false, deliveryUrl: null };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/assets/42"
      ? response({ ...asset, classification: "SINGLE_IMAGE", standaloneSalePreparation: { assetId: 42, statusLabel: state.status, intelligenceReady: true, destinations: ["CHAT"], teasers: [], ...state } })
      : response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    await screen.findByRole("heading", { name: "Sale Preparation" });
    const detail = await screen.findByLabelText("Selected asset details");
    expect(within(detail).getAllByText("Preparing")).toHaveLength(2);
    expect(within(detail).queryByRole("link", { name: /Open/ })).not.toBeInTheDocument();
    expect(within(detail).queryByRole("button", { name: "Copy" })).not.toBeInTheDocument();

    state = { status: "READY", foundationReady: true, deliveryUrl: null };
    fireEvent.click(within(detail).getByRole("button", { name: "Close asset details" }));
    fireEvent.click(screen.getByRole("button", { name: "Open Image" }));
    await screen.findByRole("heading", { name: "Sale Preparation" });
    const reopened = await screen.findByLabelText("Selected asset details");
    expect(within(reopened).getByText("Needs Attention")).toBeInTheDocument();
    expect(within(reopened).queryByRole("link", { name: /Open/ })).not.toBeInTheDocument();
  });

  it("does not show a fake commercial preview for an unprepared image", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/assets/42"
      ? response({ ...asset, classification: "SINGLE_IMAGE", commercialAssets: [] })
      : response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    await screen.findByLabelText("Selected asset details");

    expect(screen.queryByRole("heading", { name: "Commercial Assets" })).not.toBeInTheDocument();
  });

  it("registers a staged card while preserving the uniform action layout", async () => {
    const staged = { ...asset, libraryItemId: "generation:generated-1", itemKind: "staged_generation" as const, assetId: null, generationId: "generated-1", status: "staged_asset_library", imageUrl: "/api/v1/generation-library/generated-1/thumbnail" };
    const secondStaged = { ...staged, libraryItemId: "generation:generated-2", generationId: "generated-2", imageUrl: "/api/v1/generation-library/generated-2/thumbnail" };
    let registered = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input).endsWith("/staged/generated-1/register")) {
        registered = true;
        return response({ success: true, assetId: 91, analysisStatus: "PENDING", message: "Asset registered. Analysis is pending." });
      }
      return response({ assets: registered ? [secondStaged] : [staged, secondStaged], total: registered ? 1 : 2, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Images");

    const previews = await screen.findAllByRole("button", { name: "Open Image" });
    expect(previews).toHaveLength(2);
    const card = previews[0]!.closest("article")!;
    expect(screen.getAllByRole("button", { name: "Register Asset" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Move to Generation Library" })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: "Archive" })).toHaveLength(2);
    const register = within(card).getByRole("button", { name: "Register Asset" });
    expect(within(card).getByRole("button", { name: "Move to Generation Library" })).toHaveAttribute("title", "Move to Generation Library");
    expect(register).toHaveAttribute("title", "Register Asset");
    expect(within(card).getByRole("button", { name: "Archive" })).toHaveAttribute("title", "Archive");
    fireEvent.click(register);
    expect(await screen.findByText("Asset registered. Analysis is pending.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("button", { name: "Register Asset" })).toHaveLength(1));
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/staged/generated-1/register", { method: "POST" });
    expect(within(card).queryByText("Staged generation")).not.toBeInTheDocument();
    expect(within(card).queryByText("Type")).not.toBeInTheDocument();
    expect(within(card).queryByText("Classification")).not.toBeInTheDocument();
    expect(within(card).queryByText("Created")).not.toBeInTheDocument();
    expect(within(card).queryByText("Unclassified")).not.toBeInTheDocument();
    expect(stylesheetText).toMatch(/\.asset-library-grid\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fill, 235px\)/);
    expect(stylesheetText).toMatch(/\.asset-card\s*\{[^}]*width:\s*235px/);
    expect(stylesheetText).toMatch(/\.asset-card__image\s*\{[^}]*height:\s*294px[^}]*aspect-ratio:\s*4\/5/);
    expect(stylesheetText).toMatch(/\.asset-card__photoshoot-badges\s*\{[^}]*display:\s*flex[^}]*justify-content:\s*center/);
    expect(within(card).getByRole("img")).toHaveClass("contained-media-image");
    expect(sharedStylesheetText).toMatch(/\.contained-media-image\s*\{[^}]*object-fit:\s*contain/);
    expect(within(card).queryByText("portrait.png")).not.toBeInTheDocument();
    expect(within(card).queryByText("Staged Image")).not.toBeInTheDocument();
    expect(stylesheetText).not.toMatch(/\.asset-card__actions(?:--icons)?\s*\{/);
    expect(sharedStylesheetText).toMatch(/\.library-action-group\s*\{[^}]*grid-auto-columns:\s*minmax\(0,1fr\)[^}]*width:\s*100%/);
    expect(sharedStylesheetText).toMatch(/\.library-action-button\s*\{[^}]*width:\s*100%[^}]*height:\s*34px/);
    expect(stylesheetText).toMatch(/@media\s*\(max-width:\s*600px\)[\s\S]*\.asset-library-grid\s*\{[^}]*repeat\(2, minmax\(0, 1fr\)\)/);
  });

  it("shows the backend JSON error instead of a parse failure", async () => {
    const staged = { ...asset, libraryItemId: "generation:generated-1", itemKind: "staged_generation" as const, assetId: null, generationId: "generated-1", status: "staged_asset_library" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).endsWith("/register")
      ? response({ detail: "Only staged Asset Library items can be registered." }, false)
      : response({ assets: [staged], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Register Asset" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only staged Asset Library items can be registered.");
    expect(screen.queryByText(/JSON\.parse/)).not.toBeInTheDocument();
  });

  it("handles a non-JSON backend failure without exposing JSON.parse", async () => {
    const staged = { ...asset, libraryItemId: "generation:generated-1", itemKind: "staged_generation" as const, assetId: null, generationId: "generated-1", status: "staged_asset_library" };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).endsWith("/register")
      ? Promise.resolve(new Response("Database unavailable", { status: 500, headers: { "Content-Type": "text/plain" } }))
      : response({ assets: [staged], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Register Asset" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Database unavailable");
    expect(screen.queryByText(/unexpected character|JSON\.parse/i)).not.toBeInTheDocument();
  });

  it("moves a staged item back and removes it from Asset Library", async () => {
    const staged = { ...asset, libraryItemId: "generation:generated-1", itemKind: "staged_generation" as const, assetId: null, generationId: "generated-1", status: "staged_asset_library" };
    let moved = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/staged/generated-1/archive")) {
        moved = true;
        return response({ success: true, message: "Asset archived." });
      }
      return response({ assets: moved ? [] : [staged], total: moved ? 0 : 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Archive" }));
    expect(await screen.findByText("Asset archived.")).toBeInTheDocument();
    expect(await screen.findByText("No assets found.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/staged/generated-1/archive", { method: "POST" });
  });

  it("archives a registered image by canonical Asset ID and reconciles the grid", async () => {
    const registered = {
      ...asset,
      assetId: 203,
      generationId: "regenerated_image_40fa88368c2351f7947298bb3872ea9e",
      classification: "SINGLE_IMAGE",
    };
    let archived = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url === "/api/v1/assets/203/archive" && init?.method === "POST") {
        archived = true;
        return response({ success: true, message: "Asset archived." });
      }
      if (url === "/api/v1/assets/counts") return response({ images: archived ? 0 : 1, photoshoots: 0, videos: 0, bundles: 0 });
      return response({ assets: archived ? [] : [registered], total: archived ? 0 : 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Images");

    fireEvent.click(await screen.findByRole("button", { name: "Archive" }));

    expect(await screen.findByText("Asset archived.")).toBeInTheDocument();
    expect(await screen.findByText("No assets found.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/203/archive", { method: "POST" });
    expect(fetch.mock.calls.some(([input]) => String(input).includes("regenerated_image_40fa") && String(input).endsWith("/archive"))).toBe(false);
  });

  it("sends search and filter values and paginates", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => response({
      assets: [asset], total: 36, page: String(input).includes("page=2") ? 2 : 1,
      pageSize: 18, totalPages: 2, classifications: ["premium"],
    }));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    await screen.findByText("Page 1 of 2");
    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: "portrait" } });
    fireEvent.change(screen.getByLabelText("Destination"), { target: { value: "CONTENT_VAULT" } });
    fireEvent.click(await screen.findByRole("button", { name: /Next/ }));

    await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
      const url = String(input);
      return url.includes("page=2") && url.includes("search=portrait") && url.includes("media_type=image") && url.includes("destination=CONTENT_VAULT") && !url.includes("classification=");
    })).toBe(true));
  });

  it("uses a responsive three-category Asset Type dashboard with backend totals and same-route navigation", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/counts") return response({
        images: 8, photoshoots: 3, videos: 2, bundles: 4, teasers: 6,
        destinationBreakdown: {
          images: { chat: 5, wall: 2, unassigned: 1 },
          photoshoots: { chat: 2, wall: 1, unassigned: 0 },
          totals: { chat: 7, wall: 3 },
          chatCommerceTypes: { single: 5, bundle: 1, session: 1 },
        },
      });
      return response({ assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);

    expect(screen.getByRole("heading", { name: "Browse Inventory" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "ASSET TYPE" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "SALES" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "ENGAGEMENT" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Images 8 Assets/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Videos 2 Videos/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Photoshoots 3 Photoshoots/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Chat 7 Assets/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /TG Wall 3 Assets/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Teasers 6 Assets/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Images/ })).not.toHaveTextContent("Chat");
    expect(screen.getByRole("button", { name: /Photoshoots/ })).not.toHaveTextContent("TG Wall");
    expect(screen.queryByText("Stories")).not.toBeInTheDocument();
    expect(screen.queryByText("Bundles")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /(?:Images|Videos|Photoshoots|Chat|TG Wall|Teasers)/ }).map((card) => card.textContent)).toEqual([
      "Images8 Assets",
      "Photoshoots3 Photoshoots",
      "Videos2 Videos",
      "Chat7 Assets",
      "TG Wall3 Assets",
      "Teasers6 Assets",
    ]);
    expect(stylesheetText).toMatch(/\.asset-type-grid\s*\{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/);
    expect(stylesheetText).toMatch(/@media \(max-width: 900px\)[\s\S]*?\.asset-type-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
    expect(stylesheetText).toMatch(/@media \(max-width: 600px\)[\s\S]*?\.asset-type-grid\s*\{[^}]*grid-template-columns:\s*1fr/);
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/counts", expect.objectContaining({ cache: "no-store" }));
    expect(fetch.mock.calls.some(([input]) => String(input).includes("page_size=1"))).toBe(false);
    expect(screen.queryByLabelText("Media type")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Classification")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Images 8 Assets/ }));
    expect(await screen.findByRole("button", { name: "Back to Asset Types" })).toBeInTheDocument();
    expect(window.location.search).toBe("?assetType=images");
    expect(screen.getByLabelText("Search assets")).toBeInTheDocument();
    expect(screen.getByLabelText("Destination")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back to Asset Types" }));
    expect(await screen.findByRole("heading", { name: "Browse Inventory" })).toBeInTheDocument();
    expect(window.location.search).toBe("");

    fireEvent.click(screen.getByRole("button", { name: /Videos 2 Videos/ }));
    expect(window.location.search).toBe("?assetType=videos");
    fireEvent.click(screen.getByRole("button", { name: "Back to Asset Types" }));

    fireEvent.click(await screen.findByRole("button", { name: /Photoshoots 3 Photoshoots/ }));
    expect(window.location.search).toBe("?assetType=photoshoots");
  });

  it("loads canonical Teasers with repository filtering and hides commerce controls", async () => {
    const teaser = { ...asset, classification: "SINGLE_IMAGE", displayName: "Reusable Teaser",
      contentDestination: "TEASER", commercialPrice: { status: "PRICED", amountMinor: 999, currency: "USD", kind: "SINGLE" },
      chatEnabled: true, timesSent: 3, lastSent: "2026-08-23T12:00:00Z",
      standaloneSalePreparation: { assetId: 42, status: "NOT_PREPARED", statusLabel: "Prepare for Sale", destinations: [] } };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url === "/api/v1/assets/counts") return response({ images: 1, photoshoots: 0, videos: 0, bundles: 0, teasers: 1 });
      if (url.endsWith("/engagement-teaser/chat-control")) {
        expect(init).toEqual(expect.objectContaining({ method: "PUT" }));
        expect(JSON.parse(String(init?.body))).toEqual({ enabled: false });
        return response({ assetId: 42, chatEnabled: false });
      }
      return response({ assets: [teaser], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    window.history.replaceState({}, "", "/library/assets?assetType=teasers");
    render(<AssetLibraryPage />);
    expect(await screen.findByText("Reusable Teaser")).toBeInTheDocument();
    expect(fetch.mock.calls.some(([input]) => String(input).includes("asset_purpose=TEASER"))).toBe(true);
    const card = screen.getByText("Reusable Teaser").closest("article")!;
    expect(within(card).getByText("TEASER")).toBeInTheDocument();
    expect(within(card).queryByText("Not Prepared")).not.toBeInTheDocument();
    expect(screen.queryByText("Price")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare for Sale" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Destination")).not.toBeInTheDocument();
    expect(within(card).getByText("Times Sent").parentElement).toHaveTextContent("3");
    expect(within(card).getByText("Last Sent").parentElement).not.toHaveTextContent("Never");
    fireEvent.click(within(card).getByRole("button", { name: "Disable Reusable Teaser for Chat" }));
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => String(input).endsWith("/engagement-teaser/chat-control"))).toBe(true));
  });

  it("opens bookmarkable unified Sales views with commerce-type filters", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/counts") return response({
        images: 8, photoshoots: 3, videos: 0, bundles: 0,
        destinationBreakdown: {
          images: { chat: 5, wall: 2, unassigned: 1 },
          photoshoots: { chat: 2, wall: 1, unassigned: 0 },
          totals: { chat: 7, wall: 3 },
          chatCommerceTypes: { single: 5, bundle: 1, session: 1 },
        },
      });
      return response({ assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);

    fireEvent.click(await screen.findByRole("button", { name: /Chat 7 Assets/ }));
    expect(window.location.search).toBe("?sales=chat");
    expect(screen.getByRole("heading", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All · 7" })).toHaveClass("is-active");
    expect(screen.getByRole("button", { name: "Single · 5" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bundle · 1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Session · 1" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Stories" })).not.toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
      const url = String(input);
      return url.includes("sales_destination=CHAT") && url.includes("sales_commerce_type=ALL");
    })).toBe(true));

    fireEvent.click(screen.getByRole("button", { name: "Single · 5" }));
    expect(window.location.search).toBe("?sales=chat&salesType=single");
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => String(input).includes("sales_commerce_type=SINGLE"))).toBe(true));

    fireEvent.click(screen.getByRole("button", { name: "Back to Asset Types" }));
    fireEvent.click(await screen.findByRole("button", { name: /TG Wall 3 Assets/ }));
    expect(window.location.search).toBe("?sales=wall");
    expect(screen.getByRole("heading", { name: "TG Wall" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Session" })).not.toBeInTheDocument();
  });

  it("restores a Sales destination and type from the bookmarkable query", async () => {
    window.history.replaceState({}, "", "/library/assets?sales=chat&salesType=session");
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/assets/counts"
      ? response({ images: 0, photoshoots: 0, videos: 0, bundles: 0, destinationBreakdown: { totals: { chat: 0, wall: 0 } } })
      : response({ assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [] }));
    render(<AssetLibraryPage />);
    expect(screen.getByRole("heading", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Session .* 0/ })).toHaveClass("is-active");
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => String(input).includes("sales_commerce_type=SESSION"))).toBe(true));
  });

  it("shows SINGLE only on standalone image cards in a Sales view", async () => {
    window.history.replaceState({}, "", "/library/assets?sales=chat");
    const single = {
      ...asset, classification: "SINGLE_IMAGE", displayName: "Chat portrait",
      standaloneSalePreparation: {
        assetId: 42, status: "READY" as const, statusLabel: "Ready",
        destinations: ["CHAT"], priceMinor: 1099, currency: "USD",
      },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/assets/counts"
      ? response({ images: 1, photoshoots: 0, videos: 0, bundles: 0, destinationBreakdown: { totals: { chat: 1, wall: 0 } } })
      : response({ assets: [single], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] }));
    render(<AssetLibraryPage />);
    const card = await screen.findByText("Chat portrait");
    expect(within(card.closest("article")!).getByText("SINGLE")).toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [] }));
    const view = render(<AssetLibraryPage />);
    await openAssetType("Images");
    expect(await screen.findByText("No assets found.")).toBeInTheDocument();
    view.unmount();
    window.history.replaceState({}, "", "/library/assets");

    fetch.mockImplementation((input) => String(input) === "/api/v1/assets/counts"
      ? response({ images: 0, photoshoots: 0, videos: 0, bundles: 0 })
      : response({ detail: "Asset service unavailable." }, false));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    expect(await screen.findByRole("alert")).toHaveTextContent("Asset service unavailable.");
  });

  it("generates, selects, and persists a WALL caption while retaining guidance", async () => {
    const options = Array.from({ length: 5 }, (_, index) => ({ text: `Caption choice ${index + 1}` }));
    let savedCaption: { text: string; style: string | null; source: "GROK" | "MANUAL"; updatedAt: string; assetId: number; offeringId: string } | null = null;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/content-vault/captions/generate")) return response({ profile: "CONTENT_VAULT_PPV", captions: options });
      if (url.endsWith("/content-vault/caption")) {
        const body = JSON.parse(String(init?.body));
        savedCaption = { ...body, updatedAt: "2026-08-08T00:00:00Z", assetId: 42, offeringId: "offering-1" };
        return response({ caption: savedCaption });
      }
      const prepared = { assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true, destinations: ["CONTENT_VAULT"], foundationReady: true, vaultReady: true, chatReady: false, teasers: [], priceMinor: 1799, deliveryUrl: "https://fanvue.example/media", contentVaultCaption: savedCaption };
      if (url === "/api/v1/assets/42") return response({ ...asset, displayName: "Playful Seductive Gaze", classification: "SINGLE_IMAGE", standaloneSalePreparation: prepared });
      return response({ assets: [{ ...asset, displayName: "Playful Seductive Gaze", classification: "SINGLE_IMAGE", standaloneSalePreparation: prepared }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    render(<AssetLibraryPage />); await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    expect(await screen.findByText("No caption selected.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Choose Caption" }));
    const dialog = await screen.findByRole("dialog", { name: "Choose Content Vault Caption" });
    expect(within(dialog).getByLabelText("Caption generation guidance")).toBeInTheDocument();
    expect(within(dialog).getByRole("radiogroup", { name: "Caption tone" })).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /Classy/i })).toHaveAttribute("aria-checked", "true");
    expect(within(dialog).getByRole("radio", { name: /Raunchy/i })).toHaveAttribute("aria-checked", "false");
    expect(within(dialog).getByText("Seductive & elevated")).toBeInTheDocument();
    expect(within(dialog).getByText("Direct & dirty")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Your Content Vault caption")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Use My Caption" })).toBeDisabled();
    expect(within(dialog).getByText("No generated options yet. Add optional guidance, then generate.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Generate Caption with Grok" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Use Selected Caption" })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Caption generation guidance"), {
      target: { value: "she's spreading her pussy" },
    });
    fireEvent.change(within(dialog).getByLabelText("Your Content Vault caption"), {
      target: { value: "My unsaved manual draft" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate Caption with Grok" }));
    expect(await within(dialog).findAllByText(/Caption choice/)).toHaveLength(5);
    expect(within(dialog).getByLabelText("Your Content Vault caption")).toHaveValue("My unsaved manual draft");
    const generateCalls = fetch.mock.calls.filter(([url]) => String(url).endsWith("/content-vault/captions/generate"));
    expect(generateCalls).toHaveLength(1);
    expect(JSON.parse(String(generateCalls[0]![1]?.body))).toEqual({
      tone: "CLASSY",
      guidance: "she's spreading her pussy",
    });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Raunchy/i }));
    expect(within(dialog).getByRole("radio", { name: /Raunchy/i })).toHaveAttribute("aria-checked", "true");
    fireEvent.change(within(dialog).getByLabelText("Caption generation guidance"), {
      target: { value: "make the second set more playful" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate 5 More" }));
    await waitFor(() => expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/content-vault/captions/generate"))).toHaveLength(2));
    expect(within(dialog).getByLabelText("Caption generation guidance")).toHaveValue("make the second set more playful");
    const refreshedGenerateCalls = fetch.mock.calls.filter(([url]) => String(url).endsWith("/content-vault/captions/generate"));
    expect(JSON.parse(String(refreshedGenerateCalls[1]![1]?.body))).toEqual({
      tone: "RAUNCHY",
      guidance: "make the second set more playful",
    });
    expect(window.sessionStorage.getItem("creator-os.content-vault-caption-tone")).toBe("RAUNCHY");
    await within(dialog).findByText("Caption choice 2");
    fireEvent.click(within(dialog).getByText("Caption choice 2"));
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/content-vault/caption"))).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Use Selected Caption" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Choose Content Vault Caption" })).not.toBeInTheDocument());
    expect(screen.getByText("Caption choice 2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Content Vault caption"), { target: { value: "My manually polished caption" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByLabelText("Content Vault caption")).not.toBeInTheDocument());
    expect(screen.getByText("My manually polished caption")).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/content-vault/captions/generate"))).toHaveLength(2);
    expect(fetch.mock.calls.some(([url]) => /vision|intelligence|fanvue|telegram/i.test(String(url)))).toBe(false);
  });

  it("saves a manual WALL caption without AI and refreshes authoritative publish readiness", async () => {
    let savedCaption: ContentVaultCaptionDraft | null = null;
    let preparationReads = 0;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      const publication = { status: "NOT_PUBLISHED", canPublish: Boolean(savedCaption), configured: true };
      const prepared = { assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true,
        destinations: ["CONTENT_VAULT"], foundationReady: true, vaultReady: true, chatReady: false,
        teasers: [], priceMinor: 1799, offeringId: "offering-1", publicationId: "publication-1",
        deliveryUrl: "https://fanvue.example/media", contentVaultCaption: savedCaption,
        contentVaultPublication: publication };
      if (url.endsWith("/content-vault/caption") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body)) as { text: string; style: null; source: "MANUAL" };
        savedCaption = { ...body, updatedAt: "2026-08-15T00:00:00Z", assetId: 42, offeringId: "offering-1" };
        return response({ caption: savedCaption });
      }
      if (url.endsWith("/sale-preparation")) { preparationReads += 1; return response(prepared); }
      if (url === "/api/v1/assets/42") return response({ ...asset, classification: "SINGLE_IMAGE", standaloneSalePreparation: prepared });
      return response({ assets: [{ ...asset, classification: "SINGLE_IMAGE", standaloneSalePreparation: prepared }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    render(<AssetLibraryPage />); await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    fireEvent.click(await screen.findByRole("button", { name: "Choose Caption" }));
    const dialog = screen.getByRole("dialog", { name: "Choose Content Vault Caption" });
    const manual = within(dialog).getByLabelText("Your Content Vault caption");
    fireEvent.change(manual, { target: { value: "   My own Unicode caption 🔥   " } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Use My Caption" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Choose Content Vault Caption" })).not.toBeInTheDocument());
    expect(screen.getByText("My own Unicode caption 🔥")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeEnabled();
    expect(preparationReads).toBe(1);
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/content-vault/captions/generate"))).toHaveLength(0);
    const saveCall = fetch.mock.calls.find(([url]) => String(url).endsWith("/content-vault/caption"));
    expect(JSON.parse(String(saveCall?.[1]?.body))).toEqual({ text: "My own Unicode caption 🔥", style: null, source: "MANUAL" });
  });

  it("cancels the chooser without replacing an existing saved caption", async () => {
    const savedCaption = { text: "Existing saved caption", style: null, source: "GROK" as const, updatedAt: "2026-08-08T00:00:00Z", assetId: 42, offeringId: "offering-1" };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const prepared = { assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true, destinations: ["CONTENT_VAULT"], foundationReady: true, vaultReady: true, chatReady: false, teasers: [], priceMinor: 1799, deliveryUrl: "https://fanvue.example/media", contentVaultCaption: savedCaption };
      if (url === "/api/v1/assets/42") return response({ ...asset, displayName: "Playful Seductive Gaze", classification: "SINGLE_IMAGE", standaloneSalePreparation: prepared });
      return response({ assets: [{ ...asset, displayName: "Playful Seductive Gaze", classification: "SINGLE_IMAGE", standaloneSalePreparation: prepared }], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    render(<AssetLibraryPage />); await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    expect(await screen.findByText("Existing saved caption")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Choose Another" }));
    const dialog = await screen.findByRole("dialog", { name: "Choose Content Vault Caption" });
    expect(within(dialog).getByLabelText("Your Content Vault caption")).toHaveValue("Existing saved caption");
    fireEvent.change(within(dialog).getByLabelText("Caption generation guidance"), {
      target: { value: "temporary guidance" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Choose Content Vault Caption" })).not.toBeInTheDocument());
    expect(screen.getByText("Existing saved caption")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/content-vault/caption"))).toHaveLength(0);
  });

  it("does not expose Content Vault caption authoring for CHAT assets", async () => {
    const chat = { ...asset, classification: "SINGLE_IMAGE", standaloneSalePreparation: { assetId: 42, status: "READY", destinations: ["CHAT"], foundationReady: true, chatReady: true, vaultReady: false, teasers: [] } };
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/assets/42" ? response(chat) : response({ assets: [chat], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] }));
    render(<AssetLibraryPage />); await openAssetType("Images"); fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    await screen.findByRole("heading", { name: "Sale Preparation" });
    expect(screen.queryByRole("heading", { name: "Content Vault Publishing" })).not.toBeInTheDocument();
  });

  it("publishes the persisted Content Vault package and refreshes only sale preparation", async () => {
    const basePreparation = {
      assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true,
      destinations: ["CONTENT_VAULT"], foundationReady: true, vaultReady: true,
      chatReady: false, teasers: [], priceMinor: 1799, currency: "USD",
      offeringId: "offering-1", deliveryUrl: "https://fanvue.example/media",
      contentVaultCaption: { text: "Saved exact caption", source: "GROK", updatedAt: "2026-08-08T00:00:00Z", assetId: 42, offeringId: "offering-1" },
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: true, configured: true,
        previewUrl: "/api/v1/commerce-authoring/offering-1/telegram-content-vault/media" },
    };
    let published = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url === "/api/v1/commerce-authoring/offering-1/telegram-content-vault" && init?.method === "POST") {
        published = true; return response({ status: "PUBLISHED" });
      }
      if (url === "/api/v1/assets/42/sale-preparation") return response({
        ...basePreparation,
        contentVaultPublication: published
          ? { status: "PUBLISHED", canPublish: false, configured: true, publishedAt: "2026-08-08T01:00:00Z", providerMessageId: "telegram-77" }
          : basePreparation.contentVaultPublication,
      });
      const item = { ...asset, displayName: "Playful Seductive Gaze", classification: "SINGLE_IMAGE", standaloneSalePreparation: {
        ...basePreparation,
        contentVaultPublication: published
          ? { status: "PUBLISHED", canPublish: false, configured: true, publishedAt: "2026-08-08T01:00:00Z", providerMessageId: "telegram-77" }
          : basePreparation.contentVaultPublication,
      } };
      if (url === "/api/v1/assets/42") return response(item);
      return response({ assets: [item], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    const view = render(<AssetLibraryPage />); await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    expect(await screen.findByAltText("Content Vault publication preview")).toHaveAttribute(
      "src", "/api/v1/commerce-authoring/offering-1/telegram-content-vault/media",
    );
    fireEvent.click(await screen.findByRole("button", { name: "Publish to Content Vault" }));
    await screen.findByRole("button", { name: "Published to Content Vault" });
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/commerce-authoring/offering-1/telegram-content-vault",
      expect.objectContaining({ method: "POST", body: "{}" }),
    );
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42/sale-preparation");
    expect(screen.getByText("Telegram message telegram-77")).toBeInTheDocument();
    expect(screen.getByText("Playful Seductive Gaze", { selector: ".asset-card__summary strong" }).closest("article")).toHaveTextContent("✓ WALL");
    expect(fetch.mock.calls.some(([url]) => String(url).includes("caption") && String(url).includes("telegram"))).toBe(false);

    const publishedPanel = screen.getByText("Published").closest("div")!;
    expect(publishedPanel).toHaveClass("content-vault-publishing__published");
    expect(within(publishedPanel).getByText(/Aug 8, 2026|Aug 7, 2026/)).toBeInTheDocument();

    view.unmount();
    render(<AssetLibraryPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    expect(await screen.findByRole("button", { name: "Published to Content Vault" })).toBeDisabled();
    expect(screen.getByText("Playful Seductive Gaze", { selector: ".asset-card__summary strong" }).closest("article")).toHaveTextContent("✓ WALL");
  });

  it("refreshes authoritative publish readiness after saving a caption and after reload", async () => {
    let savedCaption: ContentVaultCaptionDraft | null = null;
    const preparation = () => ({
      assetId: 42, status: "READY", statusLabel: "Ready", intelligenceReady: true,
      destinations: ["CONTENT_VAULT"], foundationReady: true, vaultReady: true,
      chatReady: false, teasers: [], priceMinor: 1799, currency: "USD",
      offeringId: "offering-1", deliveryUrl: "https://fanvue.example/media",
      contentVaultCaption: savedCaption,
      contentVaultPublication: savedCaption
        ? { status: "NOT_PUBLISHED", canPublish: true, configured: true, readinessError: null }
        : { status: "NOT_PUBLISHED", canPublish: false, configured: true, readinessError: "Select and save a Content Vault caption before publishing." },
    });
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/content-vault/captions/generate")) {
        return response({ profile: "CONTENT_VAULT_PPV", captions: Array.from({ length: 5 }, (_, index) => ({ text: index === 0 ? "Persisted caption" : `Alternative ${index + 1}` })) });
      }
      if (url.endsWith("/content-vault/caption") && init?.method === "PUT") {
        const body = JSON.parse(String(init.body));
        savedCaption = { ...body, updatedAt: "2026-08-08T00:00:00Z", assetId: 42, offeringId: "offering-1" };
        return response({ caption: savedCaption });
      }
      if (url === "/api/v1/assets/42/sale-preparation") return response(preparation());
      const item = { ...asset, classification: "SINGLE_IMAGE", standaloneSalePreparation: preparation() };
      if (url === "/api/v1/assets/42") return response(item);
      return response({ assets: [item], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });

    const first = render(<AssetLibraryPage />); await openAssetType("Images");
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    expect(await screen.findByText("Select and save a Content Vault caption before publishing.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Choose Caption" }));
    const chooser = await screen.findByRole("dialog", { name: "Choose Content Vault Caption" });
    fireEvent.click(within(chooser).getByRole("button", { name: "Generate Caption with Grok" }));
    fireEvent.click(await within(chooser).findByText("Persisted caption"));
    fireEvent.click(within(chooser).getByRole("button", { name: "Use Selected Caption" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeEnabled());
    expect(screen.queryByText("Select and save a Content Vault caption before publishing.")).not.toBeInTheDocument();
    expect(screen.getByText("Persisted caption")).toBeInTheDocument();

    first.unmount();
    render(<AssetLibraryPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    expect(await screen.findByText("Persisted caption")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publish to Content Vault" })).toBeEnabled();
  });

  it("uses opaque themed surfaces for the caption chooser and its options", () => {
    expect(stylesheetText).toMatch(/\.caption-chooser\s*\{[^}]*background:linear-gradient\(180deg,var\(--color-surface-raised\),var\(--color-surface-inset\)\)/);
    expect(stylesheetText).toMatch(/\.caption-chooser-backdrop\s*\{[^}]*background:rgb\(0 0 0 \/ 78%\)/);
    expect(stylesheetText).toMatch(/\.caption-options > button\s*\{[^}]*background:var\(--color-surface-inset\)/);
    expect(stylesheetText).toMatch(/\.caption-options > button\.is-selected[^}]*background:var\(--color-accent-surface\)/);
    expect(stylesheetText).not.toMatch(/\.caption-chooser\s*\{[^}]*background:var\(--color-surface\)/);
  });

  it("opens canonical Single Image media in a navigable lightbox without losing library state", async () => {
    const images = [
      { ...asset, classification: "SINGLE_IMAGE", displayName: "Playful Seductive Gaze" },
      { ...asset, assetId: 43, libraryItemId: "asset:43", imageUrl: "/api/v1/assets/43/thumbnail", classification: "SINGLE_IMAGE", displayName: "Golden Hour Balcony Gaze" },
    ];
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/42") return response(images[0]);
      if (url === "/api/v1/assets/43") return response(images[1]);
      return response({ assets: images, total: 2, page: 1, pageSize: 18, totalPages: 1, classifications: ["SINGLE_IMAGE"] });
    });
    render(<AssetLibraryPage />); await openAssetType("Images");
    fireEvent.change(screen.getByLabelText("Search assets"), { target: { value: "gaze" } });
    fireEvent.change(screen.getByLabelText("Destination"), { target: { value: "CONTENT_VAULT" } });
    fireEvent.click((await screen.findAllByRole("button", { name: "Open Image" }))[0]!);

    const dialog = await screen.findByRole("dialog", { name: "Playful Seductive Gaze full-size preview" });
    expect(within(dialog).getByRole("img", { name: "Playful Seductive Gaze preview" })).toHaveAttribute("src", "/api/v1/assets/42/preview");
    expect(within(dialog).getByRole("link", { name: "View Full Resolution" })).toHaveAttribute("href", "/api/v1/assets/42/media");
    expect(await screen.findByRole("heading", { name: "Playful Seductive Gaze" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search assets")).toHaveValue("gaze");
    expect(screen.getByLabelText("Destination")).toHaveValue("CONTENT_VAULT");
    expect(within(dialog).getByRole("button", { name: "Previous image" })).toBeDisabled();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    const nextDialog = await screen.findByRole("dialog", { name: "Golden Hour Balcony Gaze full-size preview" });
    expect(within(nextDialog).getByRole("img", { name: "Golden Hour Balcony Gaze preview" })).toHaveAttribute("src", "/api/v1/assets/43/preview");
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    const returnedDialog = await screen.findByRole("dialog", { name: "Playful Seductive Gaze full-size preview" });
    fireEvent.click(within(returnedDialog).getByRole("button", { name: "Close preview" }));
    expect(screen.queryByRole("dialog", { name: /full-size preview/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Open Image" })[0]!);
    await screen.findByRole("dialog", { name: "Playful Seductive Gaze full-size preview" });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: /full-size preview/ })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Playful Seductive Gaze" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search assets")).toHaveValue("gaze");
    expect(screen.getByLabelText("Destination")).toHaveValue("CONTENT_VAULT");
    expect(fetch.mock.calls.some(([url]) => String(url).includes("sale-preparation"))).toBe(false);
  });
});
