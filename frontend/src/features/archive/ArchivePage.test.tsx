import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(screen.queryByText("Sunlit Serenity")).not.toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith("/api/v1/assets/archived/photoshoots/set-1/restore", { method: "POST" });
  });
});
