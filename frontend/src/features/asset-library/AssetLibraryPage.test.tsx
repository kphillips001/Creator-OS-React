import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AssetLibraryPage } from "./AssetLibraryPage";
import { StandaloneSalePreparationDialog } from "./StandaloneSalePreparationDialog";
import type { ContentVaultCaptionDraft } from "./types";

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

beforeEach(() => window.history.replaceState({}, "", "/library/assets"));
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

async function openAssetType(name: "Images" | "Photoshoots" | "Videos") {
  fireEvent.click(await screen.findByRole("button", { name: new RegExp(`^${name}`) }));
}

describe("AssetLibraryPage", () => {
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
    fireEvent.click(within(dialog).getByLabelText("Ava's Content Vault"));
    expect(within(dialog).getByLabelText("Full Blur")).toBeChecked();
    expect(within(dialog).getByRole("button", { name: "Prepare for Sale" })).toBeEnabled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Prepare for Sale" }));
    await waitFor(() => expect(onStarted).toHaveBeenCalled());
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42/sale-preparation", expect.objectContaining({
      body: JSON.stringify({ priceMinor: 1000, destinations: ["CONTENT_VAULT"], teaserStyle: "FULL_BLUR" }),
    }));
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
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
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
      { ...asset, classification: "SINGLE_IMAGE", displayName: "Wall Image", standaloneSalePreparation: prepared("CONTENT_VAULT", 1799, "USD") },
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
    expect(within(card("Wall Image")).getByText("$17.99")).toBeInTheDocument();
    expect(within(card("Chat Image")).getByText("£7.99")).toBeInTheDocument();
    expect(within(card("Unprepared Image")).queryByText("Price")).not.toBeInTheDocument();
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
    expect(within(card!).queryByText("Price")).not.toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument(), { timeout: 5500 });

    expect(screen.getByText("Sunlit Kitchen Reveal").closest("article")).toBe(card);
    expect(screen.queryByText("Loading assets...")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Selling and publishing destinations")).toHaveTextContent("Chat");
    expect(within(card!).getByText("Price")).toBeInTheDocument();
    expect(within(card!).getByText("$14.99")).toBeInTheDocument();
    expect(inspectionCount).toBe(1);
    expect(fetch.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/assets?")).length).toBe(gridRequestsBefore);
  }, 7000);

  it("keeps Photoshoot preparation in the viewer rather than the grid card", async () => {
    const photoshoot = { ...asset, libraryItemId: "photoshoot:set-1", itemKind: "photoshoot" as const, assetId: null, deliverableId: "set-1", generationId: null, fileName: "Sunlit Serenity", mediaType: "photoshoot", classification: null, status: "IN_ASSET_LIBRARY", shotCount: 6, sellingMode: "SESSION", bundleSalesChannel: null };
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, options) => {
      if (String(input) === "/api/v1/photoshoot-gallery/set-1") return response({
        deliverableId: "set-1", name: "Sunlit Serenity", description: null,
        completedAt: "2026-01-02T00:00:00Z", shotCount: 6, imageUrl: "/cover",
        registrationState: "IN_ASSET_LIBRARY", intelligence: {}, technical: {},
        members: Array.from({ length: 6 }, (_, index) => ({ assetId: index + 1, shotOrder: index + 1, imageUrl: `/shot-${index + 1}` })),
      });
      if (String(input).endsWith("/assets/photoshoots/set-1/sale-preparation")) return response({
        deliverableId: "set-1", photoshootSessionId: "session-1", strategyVersion: "v1",
        status: options?.method === "POST" ? "READY" : "NOT_PREPARED",
        statusLabel: options?.method === "POST" ? "Ready for Session Selling" : "Not Prepared", paidStepCount: 1,
        readyPaidStepCount: options?.method === "POST" ? 1 : 0, teaserReady: true, steps: [
          { assetId: 1, shotOrder: 1, position: 1, role: "FREE_TEASER", access: "FREE", ready: true },
          { assetId: 2, shotOrder: 2, position: 2, role: "FIRST_UNLOCK", access: "PAID",
            ready: options?.method === "POST", priceMinor: options?.method === "POST" ? 500 : null },
        ],
      });
      if (String(input).endsWith("/commercial-offerings/photoshoots/set-1/prepare")) return response({
        deliverableId: "set-1", title: "Sunlit Serenity", description: "A complete set.",
        heroAssetId: 2, coverAssetId: 3, supportedChannels: ["AI_CHAT", "TELEGRAM_WALL"],
        members: Array.from({ length: 6 }, (_, index) => ({ assetId: index + 1, shotOrder: index + 1, imageUrl: `/shot-${index + 1}` })),
      });
      return response({ assets: [photoshoot], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Photoshoots");
    expect(await screen.findByText("Sunlit Serenity")).toBeInTheDocument();
    expect(screen.getByText(/Photoshoot.*6 Images/)).toBeInTheDocument();
    expect(screen.getByText("Not Prepared")).toBeInTheDocument();
    expect(screen.queryByText("SESSION")).not.toBeInTheDocument();
    const card = screen.getByRole("button", { name: "Open Photoshoot cover" }).closest("article")!;
    expect(within(card).queryByRole("button", { name: "Prepare for Sale" })).not.toBeInTheDocument();
    expect(within(card).getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(within(card).getAllByRole("button")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Open Photoshoot" }));
    expect(await screen.findByText("Shot 6")).toBeInTheDocument();
    expect(screen.getByLabelText("Photoshoot filmstrip")).toBeInTheDocument();
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
    expect(fetch.mock.calls.filter(([input]) => String(input).startsWith("/api/v1/assets?")).length).toBe(libraryRequestsBeforePreparation);
  });

  it("renders separate readiness and commercial badges and filters Photoshoots with search", async () => {
    const photoshoots = [
      { ...asset, libraryItemId: "photoshoot:chat", itemKind: "photoshoot" as const, assetId: null, deliverableId: "chat", fileName: "Shower Bundle", mediaType: "photoshoot", classification: null, shotCount: 3, sellingMode: "BUNDLE", bundleSalesChannel: "CHAT", sessionSelling: { sellingMode: "BUNDLE", bundleSalesChannel: "CHAT", imageCount: 3, status: "READY", autonomousSales: { status: "READY" } } },
      { ...asset, libraryItemId: "photoshoot:chat-setup", itemKind: "photoshoot" as const, assetId: null, deliverableId: "chat-setup", fileName: "Evening Bundle", mediaType: "photoshoot", classification: null, shotCount: 2, sellingMode: "BUNDLE", bundleSalesChannel: "CHAT", sessionSelling: { sellingMode: "BUNDLE", bundleSalesChannel: "CHAT", imageCount: 2, status: "READY", autonomousSales: { status: "NEEDS_SETUP" } } },
      { ...asset, libraryItemId: "photoshoot:session", itemKind: "photoshoot" as const, assetId: null, deliverableId: "session", fileName: "Shower Session", mediaType: "photoshoot", classification: null, shotCount: 4, sellingMode: "SESSION", bundleSalesChannel: null, sessionSelling: { deliverableId: "session", photoshootSessionId: "session-runtime", sellingMode: "SESSION", strategyVersion: "photoshoot_session_sales_v1", status: "READY", statusLabel: "Ready for Session Selling", paidStepCount: 1, readyPaidStepCount: 1, teaserReady: true, steps: [{ assetId: 201, shotOrder: 1, position: 1, role: "FREE_TEASER", access: "FREE", ready: true }, { assetId: 202, shotOrder: 2, position: 2, role: "FIRST_UNLOCK", access: "PAID", ready: true, offeringId: "offering-session", offeringStatus: "READY", publicationStatus: "LIVE" }] } },
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
    expect(screen.getByText("SESSION")).toBeInTheDocument();
    expect(screen.getByText("WALL")).toBeInTheDocument();
    expect(screen.getAllByText("BUNDLE")).toHaveLength(3);
    const badgeText = (name: string) => Array.from(
      screen.getByText(name).closest("article")!.querySelectorAll(".asset-card__photoshoot-badges em"),
    ).map((node) => node.textContent?.toUpperCase());
    expect(badgeText("Shower Bundle")).toEqual(["READY", "CHAT", "BUNDLE"]);
    expect(badgeText("Shower Session")).toEqual(["READY", "CHAT", "SESSION"]);
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
    expect(within(actionGroup).getByRole("button", { name: "Delete" })).toBeInTheDocument();
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
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(2);
    const register = within(card).getByRole("button", { name: "Register Asset" });
    expect(within(card).getByRole("button", { name: "Move to Generation Library" })).toHaveAttribute("title", "Move to Generation Library");
    expect(register).toHaveAttribute("title", "Register Asset");
    expect(within(card).getByRole("button", { name: "Delete" })).toHaveAttribute("title", "Delete");
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
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    expect(await screen.findByText("Asset archived.")).toBeInTheDocument();
    expect(await screen.findByText("No assets found.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/staged/generated-1/archive", { method: "POST" });
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

  it("uses a responsive Asset Type dashboard with backend totals and same-route navigation", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/counts") return response({ images: 8, photoshoots: 3, videos: 2, bundles: 4 });
      return response({ assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);

    expect(screen.getByRole("heading", { name: "Choose Asset Type" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Images 8 Assets/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Photoshoots 3 Photoshoots/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Videos 2 Videos/ })).toBeInTheDocument();
    expect(screen.queryByText("Stories")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Bundles 4 Bundles/ })).toHaveAttribute("href", "/library/bundles");
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
    expect(await screen.findByRole("heading", { name: "Choose Asset Type" })).toBeInTheDocument();
    expect(window.location.search).toBe("");
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
    expect(within(dialog).queryByText("Write your own caption")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Custom Content Vault caption")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Use My Caption" })).not.toBeInTheDocument();
    expect(within(dialog).getByText("No generated options yet. Add optional guidance, then generate.")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Generate Caption with Grok" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Use Selected Caption" })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Caption generation guidance"), {
      target: { value: "she's spreading her pussy" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate Caption with Grok" }));
    expect(await within(dialog).findAllByText(/Caption choice/)).toHaveLength(5);
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
      contentVaultPublication: { status: "NOT_PUBLISHED", canPublish: true, configured: true },
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
    expect(within(dialog).getByRole("img", { name: "Playful Seductive Gaze full-size image" })).toHaveAttribute("src", "/api/v1/assets/42/media");
    expect(await screen.findByRole("heading", { name: "Playful Seductive Gaze" })).toBeInTheDocument();
    expect(screen.getByLabelText("Search assets")).toHaveValue("gaze");
    expect(screen.getByLabelText("Destination")).toHaveValue("CONTENT_VAULT");
    expect(within(dialog).getByRole("button", { name: "Previous image" })).toBeDisabled();

    fireEvent.keyDown(window, { key: "ArrowRight" });
    const nextDialog = await screen.findByRole("dialog", { name: "Golden Hour Balcony Gaze full-size preview" });
    expect(within(nextDialog).getByRole("img", { name: "Golden Hour Balcony Gaze full-size image" })).toHaveAttribute("src", "/api/v1/assets/43/media");
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
