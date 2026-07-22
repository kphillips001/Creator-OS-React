import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PhotoshootGalleryPage } from "./PhotoshootGalleryPage";

const item = { deliverableId: "set-1", name: "Golden Hour Escape", description: "A two-image outdoor collection in warm natural light.", completedAt: "2026-07-21T00:00:00Z", shotCount: 2, imageUrl: "/cover", registrationState: "PHOTOSHOOT_COMPLETE" };

describe("PhotoshootGalleryPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("opens details from the card and offers Asset Library transfer in both locations", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify(
      String(input).endsWith("set-1") ? { ...item, intelligence: { mood: ["warm"] }, members: [{ assetId: 12, shotOrder: 1, imageUrl: "/shot" }], technical: { sessionId: "internal-1" } } : { items: [item] }
    ), { status: 200, headers: { "content-type": "application/json" } })));
    render(<PhotoshootGalleryPage />);
    expect(await screen.findByText("Golden Hour Escape")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Add to Asset Library/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("article"));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Timeline" })).toBeInTheDocument());
    expect(screen.getByText("Not Added")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Add to Asset Library/ })).toHaveLength(2);
  });

  it("adds once, refreshes, and replaces the action with a badge", async () => {
    let added = false;
    const request = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/add-to-asset-library") && init?.method === "POST") {
        added = true;
        return Promise.resolve(new Response(JSON.stringify({ ...item, registrationState: "IN_ASSET_LIBRARY" }), { status: 200, headers: { "content-type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify({ items: [{ ...item, registrationState: added ? "IN_ASSET_LIBRARY" : "PHOTOSHOOT_COMPLETE" }] }), { status: 200, headers: { "content-type": "application/json" } }));
    });
    render(<PhotoshootGalleryPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Add to Asset Library/ }));
    expect(await screen.findByText(/In Asset Library/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add to Asset Library/ })).not.toBeInTheDocument();
    expect(request.mock.calls.filter(([input]) => String(input).endsWith("/add-to-asset-library"))).toHaveLength(1);
  });
});
