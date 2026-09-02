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
  salesSessions: [{ salesSessionId: "session-1", commercialFoundationType: "CONVERSATION", conversationThreadId: "thread-1" }],
  customerIntelligenceProfile: { profile_state: "PARTIAL", identity_confidence: 1, facts: [{ authority: "Purchase Intents", record_id: "intent-1" }], spending_profile: { USD: { value: 4200 } }, purchase_preferences: [{ subject: "PHOTOSET" }], media_preferences: [], classifications: [{ label: "PURCHASER" }], recommendation_history: { presented_count: 1 }, opportunities: [{ type: "REPEATED_VIDEO_PURCHASE", provenance: { source_ids: ["video-0", "video-1"], aggregate_evidence: false } }], section_states: { spending: "SUFFICIENT", ownership: "UNAVAILABLE" }, section_state_reasons: { ownership: ["SOURCE_UNAVAILABLE:ownership:RuntimeError", "EXCLUDED_EVIDENCE_COUNT:1"] }, conflicts: [], insufficiencies: ["SOURCE_UNAVAILABLE:ownership:RuntimeError"], provenance: { included_evidence_count: 4, source_failures: { ownership: "RuntimeError" } } },
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
    for (const heading of ["Identity", "Relationship", "Customer Value", "Journey", "Commerce and Ownership", "Recommendation History", "Conversation Summary", "Buyer Session", "Sales Session History", "Retention and Growth", "Business Guidance", "Customer Intelligence Profile"]) expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Customer details" })).toHaveTextContent("CONVERSATION");
    for (const heading of ["Authoritative facts", "Derived metrics", "Inferred preferences", "Classifications", "Interpreted opportunities and risks", "Historical decisions", "Provenance, conflicts, and insufficiencies"]) expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByText("Identity confidence").nextSibling).toHaveTextContent("100%");
    expect(screen.getByRole("complementary", { name: "Customer details" })).toHaveTextContent("UNAVAILABLE");
    expect(screen.getByRole("complementary", { name: "Customer details" })).toHaveTextContent("video-0");
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

  it("requires confirmation and reason to block and deliberately restore one customer", async () => {
    const normal = { ...customer, interactionSafety: { safetyStatus: "NORMAL", decision: "ALLOWED", policyEnabled: true, reason: null, effectiveAt: null, history: [] } };
    const blocked = { ...customer, interactionSafety: { safetyStatus: "UNDERAGE_BLOCKED", decision: "BLOCKED_UNDERAGE", policyEnabled: true, reason: "Operator verified concern", effectiveAt: "2026-08-24T00:00:00Z", history: [{ previous_status: "NORMAL", new_status: "UNDERAGE_BLOCKED" }] } };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (init?.method === "PUT") return response(blocked);
      return String(input).includes("7%3A42") ? response(normal) : response(listing);
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<BusinessCustomersPage />); await screen.findByText("Avery");
    fireEvent.click(screen.getByRole("button", { name: "View details" }));
    await screen.findByRole("heading", { name: "Interaction Safety" });
    fireEvent.change(screen.getByLabelText("Safety change reason"), { target: { value: "Operator verified concern" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark UNDERAGE — BLOCKED" }));
    expect(await screen.findByText("UNDERAGE — CHAT BLOCKED")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT" && String(init.body).includes("UNDERAGE_BLOCKED"))).toBe(true);
    expect(screen.getByRole("button", { name: "Restore NORMAL" })).toBeInTheDocument();
  });
});
