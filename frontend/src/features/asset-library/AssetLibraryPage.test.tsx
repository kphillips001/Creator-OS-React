import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AssetLibraryPage } from "./AssetLibraryPage";

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
afterEach(() => vi.restoreAllMocks());

async function openAssetType(name: "Images" | "Photoshoots" | "Stories" | "Videos") {
  fireEvent.click(await screen.findByRole("button", { name: new RegExp(`^${name}`) }));
}

describe("AssetLibraryPage", () => {
  it("renders and registers a Photoshoot as one curated Asset", async () => {
    const photoshoot = { ...asset, libraryItemId: "photoshoot:set-1", itemKind: "photoshoot" as const, assetId: null, deliverableId: "set-1", generationId: null, fileName: "Sunlit Serenity", mediaType: "photoshoot", classification: null, status: "IN_ASSET_LIBRARY", shotCount: 6 };
    let registered = false;
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      if (String(input).endsWith("/photoshoots/set-1/register")) {
        registered = true;
        return response({ success: true, message: "Photoshoot registered for Commerce." });
      }
      return response({ assets: registered ? [] : [photoshoot], total: registered ? 0 : 1, page: 1, pageSize: 18, totalPages: 1, classifications: [] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Photoshoots");
    expect(await screen.findByText("Sunlit Serenity")).toBeInTheDocument();
    expect(screen.getByText(/Photoshoot.*6 Images/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Register Asset" }));
    expect(await screen.findByText("Photoshoot registered for Commerce.")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/photoshoots/set-1/register", { method: "POST" });
  });

  it("opens Image details from both the image and Open action", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url === "/api/v1/assets/42") return response({ ...asset, registrationSource: "generation_library" });
      return response({ assets: [asset], total: 1, page: 1, pageSize: 18, totalPages: 1, classifications: ["premium"] });
    });
    render(<AssetLibraryPage />);
    await openAssetType("Images");

    fireEvent.click(await screen.findByRole("button", { name: "Open Image" }));
    expect(await screen.findByText("generation_library")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Close asset details" }));
    fireEvent.click(screen.getByRole("button", { name: "Move to Generation Library" }));

    expect(await screen.findByText("generation_library")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/42", { cache: "no-store" });
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
    expect(stylesheetText).toMatch(/\.asset-card__image img\s*\{[^}]*object-fit:\s*cover/);
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
    fireEvent.change(screen.getByLabelText("Classification"), { target: { value: "premium" } });
    fireEvent.click(await screen.findByRole("button", { name: /Next/ }));

    await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
      const url = String(input);
      return url.includes("page=2") && url.includes("search=portrait") && url.includes("media_type=image") && url.includes("classification=premium");
    })).toBe(true));
  });

  it("uses a responsive Asset Type dashboard with backend totals and same-route navigation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      const total = url.includes("media_type=image") ? 8 : url.includes("media_type=photoshoot") ? 3 : 0;
      return response({ assets: [], total, page: 1, pageSize: 1, totalPages: total ? total : 1, classifications: [] });
    });
    render(<AssetLibraryPage />);

    expect(screen.getByRole("heading", { name: "Choose Asset Type" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Images 8 Assets/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Photoshoots 3 Photoshoots/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Stories 0 Stories/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Videos 0 Videos/ })).toBeInTheDocument();
    expect(screen.queryByLabelText("Media type")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Classification")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Images 8 Assets/ }));
    expect(await screen.findByRole("button", { name: "Back to Asset Types" })).toBeInTheDocument();
    expect(window.location.search).toBe("?assetType=images");
    expect(screen.getByLabelText("Search assets")).toBeInTheDocument();
    expect(screen.getByLabelText("Classification")).toBeInTheDocument();

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

    fetch.mockImplementation((input) => /[?&]page_size=1(?:&|$)/.test(String(input))
      ? response({ assets: [], total: 0, page: 1, pageSize: 1, totalPages: 1, classifications: [] })
      : response({ detail: "Asset service unavailable." }, false));
    render(<AssetLibraryPage />);
    await openAssetType("Images");
    expect(await screen.findByRole("alert")).toHaveTextContent("Asset service unavailable.");
  });
});
