import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CommercialAdministrationPage } from "./CommercialAdministrationPage";

const response = (body: unknown, ok = true, status = ok ? 200 : 409) => Promise.resolve({ ok, status, json: () => Promise.resolve(body) } as Response);
const fixtures: Record<string, unknown> = {
  customers: { items: [{ customerId: "7:42", displayName: "Avery", relationshipStage: "PURCHASER", purchaseCount: 2 }] },
  "business-assets": { items: [{ asset_id: 101, asset_name: "Hero", blocked: true, block_reasons: ["Missing effective Commercial Role"], commerceStatus: "BLOCKED" }] },
  products: { items: [{ productId: "product-1", productStatus: "ACTIVE", recommendationEligibility: { eligible: true } }] },
  "commercial-offerings": { items: [{ offeringId: "offering-1", offeringType: "PHOTOSET", status: "DRAFT", createdAt: "2026-07-31T12:00:00Z" }] },
  "sales-sessions": { items: [{ salesSessionId: "session-1", creatorProfileId: 7, fanvueUserId: 42, commercialFoundationType: "PHOTOSHOOT", commercialFoundationReference: "photoshoot-1", state: "ACTIVE", progressionStage: "DISCOVERY", lastActivityAt: "2026-07-31T12:00:00Z" }] },
  "commercial-publications": { items: [{ publicationId: "publication-1", commercialOfferingId: "offering-1", provider: "FANVUE", status: "FAILED", updatedAt: "2026-07-31T12:00:00Z", lastError: "Upload failed safely.", retryCount: 1, publicationMetadata: {}, providerResourceStatus: "UNKNOWN" }] },
  "commercial-administration/purchase-intents": { items: [{ purchaseIntentId: "intent-1", creatorProfileId: 7, fanvueAccountId: 7, commercialOfferingId: "offering-1", commercialPublicationId: "publication-1", provider: "FANVUE", status: "PRESENTED", attributionResult: "DIRECT", createdMetadata: { presentationHistory: ["shown"] } }] },
  "sales/decisions": { items: [{ decisionId: "decision-1", customerId: "7:42", customerName: "Avery", sellDecision: true, authorizationState: "authorized", reason: "Ranked candidate", deliveryState: "pending", outcomeState: "none", dataStatus: "complete", warnings: [], partialSections: [], recommendation: { commercialOfferingId: "offering-1" } }] },
};

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
    const url = String(input);
    if (init?.method === "POST") return response({ status: "PUBLISHING" });
    if (url.includes("/commercial-roles/vocabulary")) return response({ roles: ["CORE"] });
    if (url.includes("/commercial-roles/assets/101/history")) return response({ items: [] });
    if (url.includes("/commercial-roles/assets/101")) return response({ items: [{ assignmentId: "role-1", assetId: 101, role: "CORE", state: "SUGGESTED", origin: "AI", rationale: "Lineage evidence", suggestionConfidence: .9, evidence: { signal: "asset_lineage" } }] });
    if (url.includes("/asset-lineage/assets/101")) return response({ asset_id: 101, classification: "ROOT", roots: [], parents: [], children: [], siblings: [], ancestors: [], descendants: [], family_asset_ids: [101], relationships: [], photoshoot_contexts: [], ambiguous: false, complete: true, integrity_status: "VALID", provenance_complete: true, completeness_issues: [] });
    if (url.includes("/commercial-fulfillments/offering-1")) return response({ offeringId: "offering-1", title: "Set", offeringType: "PHOTOSET", primarySalesChannel: "AI_CHAT", orderedAssetIds: [101], heroAssetId: 101, publicationId: "publication-1", fulfillable: false, ineligibilityReason: "Publication failed", eligibleForAiChat: false, eligibleForTelegramWall: false });
    if (url.includes("/business-assets/101")) return response({ item: { asset_id: 101 }, commerceRegistration: { productIds: ["product-1"], offeringIds: ["offering-1"] } });
    if (url.includes("/sales-sessions/session-1/history")) return response({ items: [] });
    if (url.includes("/sales-sessions/session-1/commercial-context")) return response({ customerId: "7:42", purchaseIntents: [] });
    if (url.includes("/customers/7%3A42")) return response({ customerId: "7:42", displayName: "Avery", commerceAndOwnership: { ownershipIntelligence: { state: "CONFIRMED_OWNERSHIP" } }, customerIntelligenceProfile: { profile_state: "PARTIAL", identity_confidence: 1, facts: [{ authority: "Purchase Intents", record_id: "intent-1" }, { authority: "Customer Commerce Transactions", record_id: "tx-1" }], conflicts: [], insufficiencies: ["SOURCE_UNAVAILABLE:ownership:RuntimeError"], provenance: { included_evidence_count: 2, source_failures: { ownership: "RuntimeError" }, excluded_source_evidence_counts: { ownership: 1 } }, calculation_metadata: { method_version: "customer-intelligence-v1", calculated_at: "2026-07-31T12:00:00Z" }, section_states: { spending: "SUFFICIENT", ownership: "UNAVAILABLE" }, section_state_reasons: { ownership: ["SOURCE_UNAVAILABLE:ownership:RuntimeError", "EXCLUDED_EVIDENCE_COUNT:1"] }, spending_profile: {}, session_profile: {}, engagement_profile: {}, purchase_preferences: [], media_preferences: [], opportunities: [{ type: "REPEATED_VIDEO_PURCHASE", provenance: { source_ids: ["video-0", "video-1"], aggregate_evidence: false } }], risks: [{ type: "AGGREGATE_RISK", provenance: { source_ids: [], aggregate_evidence: true, aggregate_name: "risk_aggregate" } }], recommendation_history: {} } });
    if (url.includes("/sales/decisions/decision-1")) return response({ decisionId: "decision-1", customerId: "7:42", classificationAndRouting: { strategy: "sell" }, sellDecision: { reasoning: "Ranked candidate" }, recommendation: { candidateOfferings: ["offering-1"], rejectedCandidates: [] }, customerContext: { ownership: "confirmed" }, delivery: { state: "pending" }, outcomeAndLearning: { suppression: [] }, warnings: [], partialSections: [] });
    const key = Object.keys(fixtures).find((name) => url.includes(`/api/v1/${name}`));
    return response(key ? fixtures[key] : { items: [] });
  });
}

afterEach(() => vi.restoreAllMocks());

describe("CommercialAdministrationPage", () => {
  it("loads one supported workspace with all six operator areas", async () => {
    mockFetch();
    render(<MemoryRouter><CommercialAdministrationPage /></MemoryRouter>);
    expect(await screen.findByText("Commercial Administration")).toBeInTheDocument();
    for (const area of ["Overview", "Customers", "Catalog", "Sales", "Delivery", "Diagnostics"]) expect(screen.getByRole("tab", { name: area })).toBeInTheDocument();
    expect(await screen.findByText("Upload failed safely.")).toBeInTheDocument();
  });

  it("preserves missing authority data as an explicit partial state", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("customers") ? response({ detail: "Unavailable" }, false) : response({ items: [] }));
    render(<MemoryRouter><CommercialAdministrationPage /></MemoryRouter>);
    expect(await screen.findByText(/Partial data: Customers unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/Missing evidence remains unknown/)).toBeInTheDocument();
  });

  it("shows canonical deep links and no manual Media Link input", async () => {
    mockFetch();
    render(<MemoryRouter initialEntries={["/commercial-administration?area=delivery"]}><CommercialAdministrationPage /></MemoryRouter>);
    expect(await screen.findByText("Delivery and publication")).toBeInTheDocument();
    expect(screen.getByText(/Media Links are display-only/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Media Link/i)).not.toBeInTheDocument();
    expect(screen.getByText("offering-1")).toBeInTheDocument();
  });

  it("delegates publication retry and refreshes authoritative state", async () => {
    const fetch = mockFetch();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryRouter initialEntries={["/commercial-administration?area=delivery"]}><CommercialAdministrationPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(fetch.mock.calls.some(([url, init]) => String(url).endsWith("/publication-1/retry") && init?.method === "POST")).toBe(true));
  });

  it("shows structured lineage evidence and confirms delegated Role approval", async () => {
    const fetch = mockFetch();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryRouter initialEntries={["/commercial-administration?area=catalog&asset=101"]}><CommercialAdministrationPage /></MemoryRouter>);
    expect(await screen.findByText(/Lineage evidence/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(fetch.mock.calls.some(([url, init]) => String(url).endsWith("/assets/101/approve") && init?.method === "POST")).toBe(true));
    expect(window.confirm).toHaveBeenCalled();
  });

  it("presents stale canonical Session transitions distinctly", async () => {
    const fetch = mockFetch();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetch.mockImplementation((input, init) => init?.method === "POST" ? response({ detail: "Session changed during transition." }, false) : mockResponse(String(input)));
    render(<MemoryRouter initialEntries={["/commercial-administration?area=sales&session=session-1"]}><CommercialAdministrationPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Complete" }));
    expect(await screen.findByText(/Stale or unsupported transition/)).toBeInTheDocument();
  });

  it("preserves customer context with canonical breadcrumbs", async () => {
    mockFetch();
    render(<MemoryRouter initialEntries={["/commercial-administration?area=customers&customer=7%3A42"]}><CommercialAdministrationPage /></MemoryRouter>);
    expect(await screen.findByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent("7:42");
    expect((await screen.findAllByText(/CONFIRMED_OWNERSHIP/)).length).toBeGreaterThan(0);
    expect(screen.getByText("Canonical Customer Intelligence profile")).toBeInTheDocument();
    expect(screen.getByText("customer-intelligence-v1")).toBeInTheDocument();
    expect(screen.getByText("Source navigation")).toBeInTheDocument();
    expect(screen.getByText("Per-output provenance")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open canonical source" })).toBeInTheDocument();
    expect(screen.getByText("Non-navigable source")).toBeInTheDocument();
    expect(screen.getByText("Canonical Customer Intelligence profile").closest("section")).toHaveTextContent("RuntimeError");
    expect(screen.getByText("Canonical Customer Intelligence profile").closest("section")).toHaveTextContent("video-0");
    expect(screen.getByText("Canonical Customer Intelligence profile").closest("section")).toHaveTextContent("aggregate_evidence");
  });

  it("starts a Session through the canonical service with confirmation", async () => {
    const fetch = mockFetch(); vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryRouter initialEntries={["/commercial-administration?area=sales"]}><CommercialAdministrationPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Start Session" }));
    fireEvent.change(screen.getByLabelText("Fanvue Account ID"), { target: { value: "7" } }); fireEvent.change(screen.getByLabelText("Fanvue Customer ID"), { target: { value: "42" } }); fireEvent.change(screen.getByLabelText("Commercial Foundation Reference"), { target: { value: "photoshoot-1" } }); fireEvent.click(screen.getByRole("button", { name: "Confirm Session start" }));
    await waitFor(() => expect(fetch.mock.calls.some(([url, init]) => String(url).endsWith("/api/v1/sales-sessions") && init?.method === "POST")).toBe(true)); expect(window.confirm).toHaveBeenCalled();
  });

  it("starts a Conversation-founded Session without a Photoshoot reference", async () => {
    const fetch = mockFetch(); vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryRouter initialEntries={["/commercial-administration?area=sales"]}><CommercialAdministrationPage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "Start Session" }));
    fireEvent.change(screen.getByLabelText("Foundation Type"), { target: { value: "CONVERSATION" } });
    expect(screen.queryByLabelText("Commercial Foundation Reference")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Fanvue Account ID"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Fanvue Customer ID"), { target: { value: "42" } });
    fireEvent.change(screen.getByLabelText("Conversation Thread ID"), { target: { value: "11" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm Session start" }));
    await waitFor(() => expect(fetch.mock.calls.some(([url, init]) => {
      if (!String(url).endsWith("/api/v1/sales-sessions") || init?.method !== "POST") return false;
      const body = JSON.parse(String(init.body));
      return body.commercialFoundationType === "CONVERSATION" && body.conversationThreadId === 11 && !("commercialFoundationReference" in body);
    })).toBe(true));
  });

  it("consumes canonical identifiers in Purchase Intent and Intelligence inspectors", async () => {
    mockFetch(); const view = render(<MemoryRouter initialEntries={["/commercial-administration?area=sales&intent=intent-1"]}><CommercialAdministrationPage /></MemoryRouter>);
    expect(await screen.findByText("Purchase Intent inspection")).toBeInTheDocument(); expect(screen.getAllByText("intent-1").length).toBeGreaterThan(0); view.unmount();
    render(<MemoryRouter initialEntries={["/commercial-administration?area=diagnostics&decision=decision-1"]}><CommercialAdministrationPage /></MemoryRouter>);
    expect(await screen.findByText("Commercial Intelligence inspector")).toBeInTheDocument(); expect(screen.getByText(/never reruns a decision/i)).toBeInTheDocument();
  });

  it("exposes pending and missing Commercial Role queues with filters", async () => {
    mockFetch(); render(<MemoryRouter initialEntries={["/commercial-administration?area=catalog"]}><CommercialAdministrationPage /></MemoryRouter>);
    expect(await screen.findByText("Commercial Role queues")).toBeInTheDocument(); expect(screen.getByLabelText("Role queue filter")).toBeInTheDocument(); expect(screen.getByText("90%")).toBeInTheDocument();
  });
});

function mockResponse(url: string) {
  if (url.includes("/sales-sessions/session-1/history")) return response({ items: [] });
  if (url.includes("/sales-sessions/session-1/commercial-context")) return response({ customerId: "7:42", purchaseIntents: [] });
  const key = Object.keys(fixtures).find((name) => url.includes(`/api/v1/${name}`));
  return response(key ? fixtures[key] : { items: [] });
}
