import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TestChatPage } from "./TestChatPage";

const session = {
  session_id: "session-1",
  test_user: { name: "Test User", relationship: "warm", buyer_tier: "new_buyer" },
  messages: [],
  external_sends_disabled: true,
};

describe("TestChatPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads, sends a customer message, and displays the narrow decision summary", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        reply: "I can help with that.",
        intent: "high", relationship: "sales", sell: true,
        reason: "No eligible products", product: null, asset: null,
        commerce_lookup_attempted: true, requested_media_type: "PHOTOSET",
        requested_themes: ["beach"], offering_selected: true,
        offering_id: "offer-1", offering_type: "PHOTOSET",
        offering_title: "Beach Set", price_minor: 999, currency: "USD",
        primary_sales_channel: "AI_CHAT", provider: "FANVUE",
        fulfillable: true, recommendation_reason: "EXACT_MEDIA_TYPE_MATCH",
        no_offering_reason: null, delivery_url: "https://fanvue.com/fvml-active",
        legacy_offer_requested: true, commerce_offer_authorized: true,
        final_offer_authorized: true,
        commerce_execution_policy: "COMMERCE_PRESENTATION_ALLOWED",
        customer_sales_decision: "PRESENT_OFFER",
        customer_sales_reason_code: "NO_ACTIVE_OFFER",
        authoritative_offering_selected: true,
        selection_source: "COMMERCIAL_OFFERING_SELECTOR",
        commerce_prompt_mode: "PRESENT_OFFER",
        legacy_recommendation_used: false,
        recommendation_diagnostics: {
          recommendationEngineVersion: "commerce_recommendation_v2_intelligent",
          eligibleCount: 2, activeIntentApplied: false,
          recommendationSummary: "Beach Set ranked highest.",
          recommendationTrace: [{
            rank: 1, offeringId: "offer-1", title: "Beach Set",
            publishedAt: "2026-07-25T00:00:00Z", activeIntentMatch: false,
            selected: true, finalScore: 0.843,
            reason: "Beach Set ranked highest.",
            components: [{
              key: "semantic_match", rawValue: 0.84, weight: 0.45,
              weightedContribution: 0.378,
              explanation: "Matched beach.", affectedRanking: true,
              evidence: { matchedTokens: ["beach"] },
            }],
          }],
        },
        commerce_learning_profile: {
          preferences: { themes: { beach: {
            score: 0.9, confidence: 0.8, observations: 4,
          } } },
          outcomeCounts: { PURCHASED: 2 },
          preferredOfferingType: "PHOTOSET",
          preferredPriceMinMinor: 999, preferredPriceMaxMinor: 1499,
          repeatPurchaseFrequency: 0.5, confidence: 0.8, evidenceCount: 6,
        },
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);

    expect(await screen.findByText("new_buyer")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "What can I buy?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findAllByText("I can help with that.")).toHaveLength(2);
    expect(screen.getByText("No eligible products")).toBeInTheDocument();
    expect(screen.getByText("YES")).toBeInTheDocument();
    expect(screen.getAllByText("Beach Set").length).toBeGreaterThan(0);
    expect(screen.getByText("$9.99")).toBeInTheDocument();
    expect(screen.getByText("EXACT_MEDIA_TYPE_MATCH")).toBeInTheDocument();
    expect(screen.getByText("COMMERCE_PRESENTATION_ALLOWED")).toBeInTheDocument();
    expect(screen.getByText("COMMERCIAL_OFFERING_SELECTOR")).toBeInTheDocument();
    expect(screen.getByText("Legacy recommendation used")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Recommendation Decision"));
    expect(screen.getByText("Score breakdown")).toBeInTheDocument();
    expect(screen.getByText("0.843")).toBeInTheDocument();
    expect(screen.getByText("Matched beach.")).toBeInTheDocument();
    expect(screen.getByText(/80% profile confidence/)).toBeInTheDocument();
    expect(screen.getByText("Final authorization")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://fanvue.com/fvml-active" })).toBeInTheDocument();
    expect(screen.getAllByText("None").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("🚫 External Sends Disabled")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/developer/test-chat/turns",
      expect.objectContaining({ method: "POST" }),
    ));
  });

  it("shows developer-only engine diagnostics in a collapsible error card", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: {
        exception_type: "RuntimeError", exception_message: "OpenAI API key is not configured.",
        file: "C:/Creator-OS-React/app/main.py", line_number: "54",
        stack_trace: "Traceback…", root_cause: "Missing OpenAI configuration",
      } }), { status: 502 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText("new_buyer");
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Sales Agent Error")).toBeInTheDocument();
    expect(screen.getByText("RuntimeError")).toBeInTheDocument();
    expect(screen.getByText("OpenAI API key is not configured.")).toBeInTheDocument();
    expect(screen.getByText("Stack trace")).toBeInTheDocument();
  });

  it("shows a safe no-offering decision while external sends remain disabled", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        reply: "Let me keep looking for something that suits you.",
        intent: "high", relationship: "sales", sell: true,
        reason: "Buying intent detected", product: null, asset: null,
        commerce_lookup_attempted: false, requested_media_type: "STORY",
        requested_themes: [], offering_selected: false,
        offering_id: null, offering_type: null, offering_title: null,
        price_minor: null, currency: null, primary_sales_channel: "AI_CHAT",
        provider: null, fulfillable: false, recommendation_reason: null,
        no_offering_reason: "UNSUPPORTED_OFFERING_TYPE", delivery_url: null,
      }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<MemoryRouter><TestChatPage /></MemoryRouter>);
    await screen.findByText("new_buyer");
    fireEvent.change(screen.getByLabelText("Customer"), { target: { value: "Can I buy a story?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("UNSUPPORTED_OFFERING_TYPE")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Recommendation Decision"));
    expect(screen.getByText(
      "No observed commerce-learning history yet.",
    )).toBeInTheDocument();
    expect(screen.getByText("🚫 External Sends Disabled")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
