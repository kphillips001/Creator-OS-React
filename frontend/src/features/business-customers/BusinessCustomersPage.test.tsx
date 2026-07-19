import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BusinessCustomersPage } from "./BusinessCustomersPage";

const customer = {
  customerId: "7:42", displayName: "Avery", providerIdentities: [{ provider: "fanvue", username: "avery" }], relationshipStatus: "subscriber",
  relationshipStage: "engaged", buyerTier: "warm", valueTier: "HIGH_VALUE", customerHealth: "HEALTHY", lifecycleStage: "ACTIVE_RELATIONSHIP",
  totalSpendCents: 4200, purchaseCount: 2, lastActivityAt: "2026-07-19T10:00:00Z", retentionRisk: "HEALTHY", activeBuyerSession: true,
  nextRecommendedAction: "Continue relationship building", isSubscriber: true, isFollower: true,
  identity: { customer_id: "7:42", provider: "fanvue" }, relationship: { stage: "engaged" }, customerValue: { tier: "HIGH_VALUE" },
  journey: { stage: "RELATIONSHIP_BUILDING" }, commerceAndOwnership: { entitlement_count: 2 }, recommendationHistory: { offer_count: 1 },
  conversationSummary: { message_count: 12 }, buyerSession: { active_session: true }, retentionAndGrowth: { retention_risk: "HEALTHY" },
  businessGuidance: { next_recommended_action: "Continue relationship building" },
};
const listing = { items: [customer], summary: { total: 1, active: 1, purchasers: 1, highValue: 1, atRisk: 0, activeSessions: 1 }, total: 1, page: 1, pageSize: 24, totalPages: 1 };
const response = (body: unknown, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);

afterEach(() => vi.restoreAllMocks());

describe("BusinessCustomersPage", () => {
  it("renders customer intelligence and opens a read-only detail drawer", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("7%3A42") ? response(customer) : response(listing));
    render(<BusinessCustomersPage />);
    expect(await screen.findByText("Avery")).toBeInTheDocument();
    expect(screen.getByText("$42.00 · 2 purchases")).toBeInTheDocument();
    expect(screen.getByText("Active buyer session")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View details" }));
    expect(await screen.findByRole("complementary", { name: "Customer details" })).toBeInTheDocument();
    for (const heading of ["Identity", "Relationship", "Customer Value", "Journey", "Commerce and Ownership", "Recommendation History", "Conversation Summary", "Buyer Session", "Retention and Growth", "Business Guidance"]) expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit|message|offer|fulfill|relationship/i })).not.toBeInTheDocument();
  });

  it("sends customer search and filters", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(listing));
    render(<BusinessCustomersPage />);
    await screen.findByText("Avery");
    fireEvent.change(screen.getByLabelText("Search Customers"), { target: { value: "avery" } });
    fireEvent.change(screen.getByLabelText("Relationship stage"), { target: { value: "engaged" } });
    fireEvent.change(screen.getByLabelText("Buyer session"), { target: { value: "true" } });
    await waitFor(() => expect(fetch.mock.calls.some(([input]) => {
      const url = String(input); return url.includes("search=avery") && url.includes("relationship_stage=engaged") && url.includes("active_session=true");
    })).toBe(true));
  });

  it("renders empty and backend error states", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(await response({ ...listing, items: [], total: 0, summary: { ...listing.summary, total: 0 } }));
    const view = render(<BusinessCustomersPage />);
    expect(await screen.findByText("No Customers found.")).toBeInTheDocument();
    view.unmount();
    fetch.mockResolvedValueOnce(await response({ detail: "Customer service unavailable." }, false));
    render(<BusinessCustomersPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Customer service unavailable.");
  });
});
