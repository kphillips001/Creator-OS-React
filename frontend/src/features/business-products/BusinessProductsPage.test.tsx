import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BusinessProductsPage } from "./BusinessProductsPage";

const product = {
  productId: "ac107a53-1548-4414-b243-e68d59672dd8", creatorProfileId: 7, internalName: "premium-portrait", displayName: "Premium Portrait",
  description: "A premium portrait.", productType: "SINGLE_IMAGE", deliveryType: "PAID", productStatus: "ACTIVE", approvalStatus: "APPROVED",
  reviewStatus: "Publishing Review", productOrigin: "AI Product Draft", priceCents: 2499, basePriceCents: 2499, minPriceCents: 1899,
  maxPriceCents: 3399, currency: "USD", tags: ["portrait"], themes: ["studio"], fulfillmentStrategy: "FANVUE_PAID_CHAT",
  fulfillmentStatus: "READY", mediaLink: "local://asset/42", activationSource: "ai_auto_activation", activationReason: "Eligible", assetCount: 1,
  coverAssetId: 42, previewAssetId: 42, imageUrl: "/api/v1/assets/42/media", publishingStatus: "Fanvue URL available", publishingDetail: "Ready",
  lifecycleStage: "ACTIVE", lifecycle: { product_status: "ACTIVE" }, availabilityStatus: "AVAILABLE", availability: { available_for_customers: true },
  recommendationEligibility: { eligible: true, reason: null }, businessHealth: "ACTIVE", business: { product_health: "ACTIVE" },
  performance: { status: "NO_DATA" }, review: { approval_status: "APPROVED" }, aiPricingRecommendation: { pricing_rule: "VIP_SINGLE_IMAGE" },
  composition: [{ assetId: 42, fileName: "portrait.png", mediaType: "image", classification: "VIP", imageUrl: "/api/v1/assets/42/media" }],
  experience: null, warnings: [],
};
const listing = { items: [product], summary: { total: 1, drafts: 0, needsReview: 0, readyToPublish: 0, active: 1, available: 1, waitingForMediaLink: 0, needsAttention: 0, recommendationEligible: 1 }, total: 1, page: 1, pageSize: 24, totalPages: 1 };
const response = (body: unknown, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);

afterEach(() => vi.restoreAllMocks());

describe("BusinessProductsPage", () => {
  it("renders Product projections and opens the read-only drawer", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes(product.productId) ? response(product) : response(listing));
    render(<BusinessProductsPage />);
    expect(await screen.findByText("Premium Portrait")).toBeInTheDocument();
    expect(screen.getByText("Recommendation · Eligible")).toBeInTheDocument();
    expect(screen.getByText("$24.99")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View details" }));
    expect(await screen.findByRole("complementary", { name: "Product details" })).toBeInTheDocument();
    expect(screen.getByText("AI Pricing Recommendation")).toBeInTheDocument();
    expect(screen.getByText("Business Health")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit|approve|publish|retry|archive/i })).not.toBeInTheDocument();
  });

  it("sends search and Product filters", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(listing));
    render(<BusinessProductsPage />);
    await screen.findByText("Premium Portrait");
    fireEvent.change(screen.getByLabelText("Search Products"), { target: { value: "portrait" } });
    fireEvent.change(screen.getByLabelText("Product status"), { target: { value: "ACTIVE" } });
    fireEvent.change(screen.getByLabelText("Product type"), { target: { value: "SINGLE_IMAGE" } });
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
      const url = String(input); return url.includes("search=portrait") && url.includes("product_status=ACTIVE") && url.includes("product_type=SINGLE_IMAGE");
    })).toBe(true));
  });

  it("renders empty and backend error states", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(await response({ ...listing, items: [], total: 0, summary: { ...listing.summary, total: 0 } }));
    const view = render(<BusinessProductsPage />);
    expect(await screen.findByText("No Products found.")).toBeInTheDocument();
    view.unmount();
    fetch.mockResolvedValueOnce(await response({ detail: "Product service unavailable." }, false));
    render(<BusinessProductsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Product service unavailable.");
  });
});
