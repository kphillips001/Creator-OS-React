import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BusinessAssetsPage } from "./BusinessAssetsPage";

const item = {
  asset_id: 42, asset_name: "portrait.png", imageUrl: "/api/v1/assets/42/media",
  analysisStatus: "READY", downstreamStatus: "CHAT_INVENTORY_READY", commerceStatus: "Chat Ready",
  source_workflow: "photoshoot", commerce_destination: "CUSTOMER_CONVERSATIONS", current_lifecycle: "CHAT_READY",
  chat_ready: true, fulfillment_ready: true, recommendation_ready: true, fanvue_upload_status: "COMPLETE", media_link_status: "VERIFIED",
  product_ids: [], experience_ids: [], availability: "Chat Ready", waiting_for_media_link: false, awaiting_destination: false,
  blocked: false, block_reasons: [], warnings: [], lifecycle_steps: [], metrics: { recommendation_count: 0, offer_count: 0, delivery_count: 0, purchase_count: 0, revenue_cents: 0 },
};
const listing = { items: [item], summary: { total_business_assets: 1, chat_ready: 1, fulfillment_ready: 1, awaiting_destination: 0, waiting_for_media_link: 0, blocked: 0, recommendation_ready: 1 }, total: 1, page: 1, pageSize: 24, totalPages: 1 };
const detail = { item, asset: {}, analysis: { NUDENET: "COMPLETE", VISION: "COMPLETE", GROK: "COMPLETE", CONTENT_INTELLIGENCE: "COMPLETE" }, analysisResults: { NUDENET: { classification: "SAFE", confidence: .91, detectedCategories: ["FACE_FEMALE"], providerVersion: "nudenet-1" }, VISION: { shortDescription: "Studio portrait", tags: ["portrait"], lighting: "soft", people: [] }, GROK: { mood: "calm", semanticSummary: "Quiet confidence" }, CONTENT_INTELLIGENCE: { commerceClassification: "TEASE", contentRating: "EXPLICIT", suggestedCollections: ["Portraits"], searchKeywords: ["portrait"], decisionEngineSummary: "Use for premium offers" } }, contentIntelligence: { status: "COMPLETE" }, commerceRegistration: {}, destination: { history: [], routingIntents: [] }, fulfillment: { provider_processing_status: "COMPLETE", media_link_verification_state: "VERIFIED" }, chatCommerce: { availability_state: "CHAT_READY" } };
const response = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

afterEach(() => vi.restoreAllMocks());

describe("Commerce Library", () => {
  it("shows the required read-only table and opens analysis and commerce details", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/business-assets/42" ? response(detail) : response(listing));
    render(<BusinessAssetsPage />);
    expect(await screen.findByRole("heading", { name: "Commerce Library" })).toBeInTheDocument();
    for (const heading of ["Preview", "Asset Name", "Current Status", "Commerce Status"]) expect(screen.getByText(heading)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archive portrait.png" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "View details for portrait.png" }));
    expect(await screen.findByRole("complementary", { name: "Business Asset details" })).toBeInTheDocument();
    for (const name of ["NudeNet", "Vision", "Grok", "Content Intelligence", "Fanvue", "Media Link", "Chat Status"]) expect(screen.getByText(name)).toBeInTheDocument();
    const vision = screen.getByRole("button", { name: /Vision Complete/i });
    expect(vision).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Studio portrait").closest(".provider-analysis__content")).toHaveAttribute("aria-hidden", "true");
    fireEvent.click(vision);
    expect(vision).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Studio portrait")).toBeInTheDocument();
    expect(screen.getByText("soft")).toBeInTheDocument();
    expect(screen.queryByText("People")).not.toBeInTheDocument();
    fireEvent.click(vision);
    expect(vision).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByRole("button", { name: /Content Intelligence Complete/i }));
    for (const retained of ["Suggested Collections", "Search Keywords", "Decision Engine Summary"]) expect(screen.getByText(retained)).toBeInTheDocument();
    expect(screen.queryByText("Commerce Classification")).not.toBeInTheDocument();
    expect(screen.queryByText("Content Rating")).not.toBeInTheDocument();
    for (const action of [/upload asset/i, /delete asset/i, /edit asset/i, /register asset/i, /generate teaser/i]) {
      expect(screen.queryByRole("button", { name: action })).not.toBeInTheDocument();
    }
  });

  it("requests each required commerce status filter", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(listing));
    render(<BusinessAssetsPage />);
    await screen.findByText("portrait.png");
    fireEvent.click(screen.getByRole("button", { name: "Needs Upload" }));
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => String(input).includes("commerce_status=Needs+Upload"))).toBe(true));
    for (const name of ["All", "Analyzing", "Analysis Failed", "Ready", "Needs Upload", "Needs Media Link", "Chat Ready"]) expect(screen.getByRole("button", { name })).toBeInTheDocument();
  });

  it("confirms and archives without offering permanent deletion", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (String(input) === "/api/v1/business-assets/42/archive" && init?.method === "POST") return response({ assetId: 42, isArchived: true, archivedAt: "2026-07-20T20:00:00Z" });
      if (String(input) === "/api/v1/business-assets/42") return response(detail);
      return response(listing);
    });
    render(<BusinessAssetsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Archive portrait.png" }));
    const dialog = screen.getByRole("dialog", { name: "Archive Commerce Asset?" });
    expect(dialog).toHaveTextContent("This will remove the asset from active commerce, sales rotation, Decision Engine inventory, and future product eligibility.");
    expect(dialog).toHaveTextContent("The asset will be preserved in the Commerce Archive and may be restored later.");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Archive" }).at(-1)!);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/v1/business-assets/42/archive", { method: "POST" }));
    expect(screen.queryByText("Delete Permanently")).not.toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(await response({ ...listing, items: [], total: 0 }));
    const view = render(<BusinessAssetsPage />);
    expect(await screen.findByText("No Business Assets found.")).toBeInTheDocument();
    view.unmount();
    fetch.mockResolvedValueOnce(await response({ detail: "Library unavailable" }, 503));
    render(<BusinessAssetsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Library unavailable");
  });
});
