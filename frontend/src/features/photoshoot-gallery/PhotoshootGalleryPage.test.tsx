import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { PhotoshootGalleryPage } from "./PhotoshootGalleryPage";

const item = { deliverableId: "set-1", name: "Golden Hour Escape", description: "A two-image outdoor collection in warm natural light.", completedAt: "2026-07-21T00:00:00Z", shotCount: 2, imageUrl: "/cover", registrationState: "PHOTOSHOOT_COMPLETE" };

function GalleryHarness() {
  const navigate = useNavigate();
  return <><button onClick={() => navigate("/library/photoshoots", { state: { newlyCompletedDeliverableId: "set-1" } })}>Show completed Photoshoot</button><PhotoshootGalleryPage /></>;
}

describe("PhotoshootGalleryPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads Gallery data without triggering intelligence analysis", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
      JSON.stringify({ items: [item] }), { status: 200, headers: { "content-type": "application/json" } }));
    render(<MemoryRouter><PhotoshootGalleryPage /></MemoryRouter>);
    await screen.findByText("2 Images", { exact: false });
    expect(fetchSpy.mock.calls.every(([input]) => !String(input).includes("intelligence"))).toBe(true);
  });

  it("opens a photo-first detail view without duplicating the Gallery card", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify(
      String(input).endsWith("set-1") ? { ...item, intelligence: { mood: ["warm"] }, members: [{ assetId: 12, shotOrder: 1, imageUrl: "/shot" }], technical: { sessionId: "internal-1" } } : { items: [item] }
    ), { status: 200, headers: { "content-type": "application/json" } })));
    render(<MemoryRouter><PhotoshootGalleryPage /></MemoryRouter>);
    expect(await screen.findByText("2 Images", { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("Golden Hour Escape")).not.toBeInTheDocument();
    expect(screen.queryByText("A two-image outdoor collection in warm natural light.")).not.toBeInTheDocument();
    const addButton = screen.getByRole("button", { name: /Add to Asset Library/ });
    expect(addButton).toHaveClass("library-action-button", "library-action-button--accent");
    expect(addButton.querySelector("svg")).toHaveClass("lucide-package");
    expect(addButton).toHaveAttribute("title", "Add to Asset Library");
    expect(screen.getByRole("article").querySelector("img")).toHaveClass("contained-media-image");
    expect(screen.queryByText(/7\/20\/2026/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("article"));
    await waitFor(() => expect(screen.getByLabelText("Photoshoot filmstrip")).toBeInTheDocument());
    expect(document.querySelector(".photoshoot-gallery-card")).not.toBeInTheDocument();
    expect(screen.queryByText("Golden Hour Escape")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Select shot 1" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("img", { name: "Shot 1" })).toHaveClass("contained-media-image");
    expect(screen.getByRole("heading", { name: "Photoshoot Summary" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Selected Shot — Shot 1" })).toBeInTheDocument();
    expect(screen.getByText("Commerce")).toBeInTheDocument();
    expect(screen.getByText("Technical Details")).toBeInTheDocument();
    expect(screen.getByText("Not Added").closest("details")).not.toHaveAttribute("open");
  });

  it("keeps Production Analysis visible while shot selection updates Shot Analysis", async () => {
    const request = vi.spyOn(globalThis, "fetch").mockImplementation((input) => Promise.resolve(new Response(JSON.stringify(
      String(input).endsWith("set-1") ? {
        ...item, intelligence: {}, productionIntelligence: { story: "An indoor progression", theme: "Intimacy", input_snapshot: { raw: "hidden" }, sales_strategy: { reasoning: "hidden" } },
        members: [
          { assetId: 12, shotOrder: 1, imageUrl: "/shot-1", intelligence: { sequence_role: "opening", suggested_content_uses: ["Teaser"], quality_observations: "hidden reasoning" } },
          { assetId: 13, shotOrder: 2, imageUrl: "/shot-2", intelligence: { sequence_role: "closing", suggested_content_uses: ["Premium finale"], continuity_observations: "hidden reasoning" } },
        ], technical: {},
      } : { items: [item] }
    ), { status: 200, headers: { "content-type": "application/json" } })));
    render(<MemoryRouter><PhotoshootGalleryPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("article"));
    expect(await screen.findByRole("heading", { name: "Photoshoot Summary" })).toBeInTheDocument();
    expect(screen.getByText("An indoor progression")).toBeInTheDocument();
    expect((await screen.findAllByRole("button", { name: /Select shot/ })).map((button) => button.getAttribute("aria-label"))).toEqual(["Select shot 1", "Select shot 2"]);
    expect(screen.getByRole("heading", { name: "Selected Shot — Shot 1" })).toBeInTheDocument();
    expect(screen.getByText("Teaser")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select shot 2" }));
    expect(screen.getByRole("heading", { name: "Selected Shot — Shot 2" })).toBeInTheDocument();
    expect(screen.getByText("Premium finale")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Photoshoot Summary" })).toBeInTheDocument();
    expect(screen.getByText("An indoor progression")).toBeInTheDocument();
    expect(screen.queryByText("hidden reasoning")).not.toBeInTheDocument();
    expect(screen.queryByText("hidden")).not.toBeInTheDocument();
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(request).toHaveBeenCalledTimes(2);
    expect(request.mock.calls.every(([input]) => String(input).startsWith("/api/v1/photoshoot-gallery"))).toBe(true);
  });

  it("adds once, refreshes, and replaces the action with a badge", async () => {
    let added = false;
    const request = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.endsWith("/add-to-asset-library") && init?.method === "POST") {
        added = true;
        return Promise.resolve(new Response(JSON.stringify({ ...item, registrationState: "IN_ASSET_LIBRARY" }), { status: 200, headers: { "content-type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify({ items: added ? [] : [item] }), { status: 200, headers: { "content-type": "application/json" } }));
    });
    render(<MemoryRouter><PhotoshootGalleryPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Add to Asset Library/ }));
    expect(await screen.findByText("No completed Photoshoots found.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add to Asset Library/ })).not.toBeInTheDocument();
    expect(request.mock.calls.filter(([input]) => String(input).endsWith("/add-to-asset-library"))).toHaveLength(1);
  });

  it("highlights the Photoshoot just completed by Studio", async () => {
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", { configurable: true, value: vi.fn() });
    let loads = 0;
    const request = vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      loads += 1;
      return Promise.resolve(new Response(JSON.stringify({ items: loads > 1 ? [item] : [] }), {
        status: 200, headers: { "content-type": "application/json" },
      }));
    });
    render(<MemoryRouter initialEntries={["/library/photoshoots"]}><GalleryHarness /></MemoryRouter>);
    await screen.findByText("No completed Photoshoots found.");
    fireEvent.click(screen.getByRole("button", { name: "Show completed Photoshoot" }));
    const card = await screen.findByRole("article", { name: /Open completed Photoshoot with 2 images/ });
    expect(card).toHaveClass("photoshoot-gallery-card--new");
    expect(screen.getByText("Just completed")).toBeInTheDocument();
    expect(request).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(card.scrollIntoView).toHaveBeenCalled());
  });
});
