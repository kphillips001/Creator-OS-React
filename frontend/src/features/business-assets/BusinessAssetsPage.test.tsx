import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BusinessAssetsPage } from "./BusinessAssetsPage";

const item = {
  asset_id: 42, asset_name: "portrait.png", imageUrl: "/api/v1/assets/42/media", source_workflow: "photoshoot",
  commerce_destination: "CUSTOMER_CONVERSATIONS", current_lifecycle: "CHAT_READY", chat_ready: true,
  fulfillment_ready: true, recommendation_ready: true, fanvue_upload_status: "ready", media_link_status: "VERIFIED",
  product_ids: ["product-1"], experience_ids: ["experience-1"], availability: "Chat Ready", waiting_for_media_link: false,
  awaiting_destination: false, blocked: false, block_reasons: [], warnings: [], lifecycle_steps: [["Intelligence", "Complete"]],
  metrics: { recommendation_count: 1, offer_count: 0, delivery_count: 0, purchase_count: 0, revenue_cents: 0 },
};
const listing = { items: [item], summary: { total_business_assets: 1, chat_ready: 1, fulfillment_ready: 1, awaiting_destination: 0, waiting_for_media_link: 0, blocked: 0, recommendation_ready: 1 }, total: 1, page: 1, pageSize: 24, totalPages: 1 };
const response = (body: unknown, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);

afterEach(() => vi.restoreAllMocks());

describe("BusinessAssetsPage", () => {
  it("renders business readiness and opens the read-only detail drawer", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input) === "/api/v1/business-assets/42"
      ? response({ item, asset: {}, contentIntelligence: { status: "COMPLETE", ready: true }, commerceRegistration: { commerce_registration_status: "REGISTERED" }, destination: { history: [], routingIntents: [] }, fulfillment: { lifecycle_state: "FULFILLMENT_READY" }, chatCommerce: { recommendation_eligible: true } })
      : response(listing));
    render(<BusinessAssetsPage />);
    expect(await screen.findByText("portrait.png")).toBeInTheDocument();
    expect(screen.getByText("Recommendation · Ready")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View details" }));
    expect(await screen.findByRole("complementary", { name: "Business Asset details" })).toBeInTheDocument();
    expect(screen.getByText("Content Intelligence")).toBeInTheDocument();
    expect(screen.queryByText(/retry/i)).not.toBeInTheDocument();
  });

  it("sends search and readiness filters", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(listing));
    render(<BusinessAssetsPage />);
    await screen.findByText("portrait.png");
    fireEvent.change(screen.getByLabelText("Search Business Assets"), { target: { value: "portrait" } });
    fireEvent.change(screen.getByLabelText("Readiness"), { target: { value: "recommendation_ready" } });
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => String(input).includes("search=portrait") && String(input).includes("recommendation_ready=true"))).toBe(true));
  });

  it("shows empty and error states", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(await response({ ...listing, items: [], total: 0, summary: { ...listing.summary, total_business_assets: 0 } }));
    const view = render(<BusinessAssetsPage />);
    expect(await screen.findByText("No Business Assets found.")).toBeInTheDocument();
    view.unmount();
    fetch.mockResolvedValueOnce(await response({ detail: "Business service unavailable." }, false));
    render(<BusinessAssetsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Business service unavailable.");
  });
});
