import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArchivePage } from "./ArchivePage";

describe("ArchivePage", () => {
  afterEach(() => vi.restoreAllMocks());
  it("renders the archive destinations", () => {
    render(<MemoryRouter><ArchivePage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Archive" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Edited Content" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Published Content" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Prompt Workshop Archive" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Regenerated Content" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Regenerated Content" })).toHaveAttribute("href", "/system/archive/regenerated");
    expect(screen.getByRole("link", { name: "Open Prompt Workshop Archive" })).toHaveAttribute("href", "/system/archive/prompts");
    expect(screen.getByRole("link", { name: "Open Edited Content" })).toHaveAttribute("href", "/system/archive/edited");
    expect(screen.getByRole("link", { name: "Open Published Content" })).toHaveAttribute("href", "/system/archive/published");
    expect(screen.getByRole("link", { name: "Open Removed Content" })).toHaveAttribute("href", "/system/archive/removed");
  });

  it("opens the edited and published routes without duplicating their implementations", () => {
    const { unmount } = render(<MemoryRouter initialEntries={["/system/archive"]}><Routes><Route path="/system/archive" element={<ArchivePage />} /><Route path="/system/archive/edited" element={<div>Existing VersionHistoryPage</div>} /></Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole("link", { name: "Open Edited Content" }));
    expect(screen.getByText("Existing VersionHistoryPage")).toBeInTheDocument();
    unmount();
    render(<MemoryRouter initialEntries={["/system/archive"]}><Routes><Route path="/system/archive" element={<ArchivePage />} /><Route path="/system/archive/published" element={<div>Existing PostedContentPage</div>} /></Routes></MemoryRouter>);
    fireEvent.click(screen.getByRole("link", { name: "Open Published Content" }));
    expect(screen.getByText("Existing PostedContentPage")).toBeInTheDocument();
  });

  it("groups archived Asset types and restores the original identity", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).endsWith("/archived/photoshoots/set-1/restore") && init?.method === "POST") return Promise.resolve(new Response(JSON.stringify({ success: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
      return Promise.resolve(new Response(JSON.stringify({ items: [{ libraryItemId: "photoshoot:set-1", itemKind: "photoshoot", assetId: null, generationId: null, deliverableId: "set-1", fileName: "Sunlit Serenity", mediaType: "photoshoot", imageUrl: "/cover", shotCount: 4, archivedAt: "2026-07-21T00:00:00Z" }] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    render(<MemoryRouter><ArchivePage /></MemoryRouter>);

    expect(await screen.findByText("Sunlit Serenity")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Images" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Photoshoots" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Stories" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Videos" })).toBeInTheDocument();
    for (const title of ["Images", "Photoshoots", "Stories", "Videos"]) {
      expect(screen.getByRole("region", { name: title })).not.toHaveClass("archive-page__card");
    }
    expect(screen.getByRole("region", { name: "Stories" })).toContainElement(screen.getByText("No archived stories."));
    expect(screen.getByText("No archived stories.")).not.toHaveClass("asset-archive__state");
    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(screen.queryByText("Sunlit Serenity")).not.toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/archived/photoshoots/set-1/restore", { method: "POST" });
  });

  it("renders compact empty states beneath normal category headings", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    render(<MemoryRouter><ArchivePage /></MemoryRouter>);

    expect(await screen.findByText("No archived images.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Images" })).toContainElement(screen.getByText("No archived images."));
    expect(screen.getByRole("region", { name: "Photoshoots" })).toContainElement(screen.getByText("No archived photoshoots."));
    expect(screen.getByRole("region", { name: "Stories" })).toContainElement(screen.getByText("No archived stories."));
    expect(screen.getByRole("region", { name: "Videos" })).toContainElement(screen.getByText("No archived videos."));
  });

  it("renders discrete Image cards with canonical titles, safe fallbacks, and restore behavior", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input).endsWith("/archived/assets/42/restore") && init?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ success: true }), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify({ items: [
        { libraryItemId: "asset:42", itemKind: "registered_asset", assetId: 42, displayName: "Golden Hour Balcony", generationId: null, fileName: "regenerated_image_40fa88368c2351f7947298bb3872ea9e.png", mediaType: "image", imageUrl: "/portrait", archivedAt: "2026-08-20T00:00:00Z" },
        { libraryItemId: "asset:43", itemKind: "registered_asset", assetId: 43, generationId: null, fileName: "regenerated_image_43fa15e858abacbcb7689900ee1257af.png", mediaType: "image", imageUrl: "/portrait-2", archivedAt: "2026-08-19T00:00:00Z" },
      ] }), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    render(<MemoryRouter><ArchivePage /></MemoryRouter>);

    expect(await screen.findByText("Golden Hour Balcony")).toBeInTheDocument();
    const images = screen.getByRole("region", { name: "Images" });
    expect(within(images).getAllByRole("article")).toHaveLength(2);
    expect(within(images).getByText("Archived Image")).toBeInTheDocument();
    expect(within(images).queryByText("regenerated_image_40fa88368c2351f7947298bb3872ea9e.png")).not.toBeInTheDocument();
    expect(Array.from(images.querySelectorAll("time")).every((time) => time.textContent?.startsWith("Archived "))).toBe(true);
    fireEvent.click(within(images).getAllByRole("button", { name: "Restore" })[0]!);

    await waitFor(() => expect(screen.queryByText("Golden Hour Balcony")).not.toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/archived/assets/42/restore", { method: "POST" });
  });
});
