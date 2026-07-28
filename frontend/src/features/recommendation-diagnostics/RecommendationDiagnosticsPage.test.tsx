import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RecommendationDiagnosticsPage } from "./RecommendationDiagnosticsPage";

const item = {
  outcomeId: "outcome-1", timestamp: "2026-07-25T12:00:00Z",
  buyer: "buyer-a1b2c3d4e5", offeringId: "offering-1",
  outcome: "PURCHASED",
  engineVersion: "commerce_recommendation_v2_intelligent",
  activeIntentOverride: false, candidateCount: 2, eligibleCount: 2,
  rejectedCount: 1, selectedScore: 0.843, selectedTitle: "Beach Set",
  explanation: "Beach Set ranked highest.",
  evidence: { themes: ["beach"] },
  trace: { recommendationTrace: [{
    rank: 1, offeringId: "offering-1", title: "Beach Set",
    finalScore: 0.843, selected: true,
    reason: "Beach Set ranked highest.",
    components: [{
      key: "semantic_match", rawValue: 0.84,
      weightedContribution: 0.378, explanation: "Matched beach.",
      evidence: { matchedTokens: ["beach"] },
    }],
  }] },
};

afterEach(() => vi.unstubAllGlobals());

describe("RecommendationDiagnosticsPage", () => {
  it("loads, filters, and opens the exact read-only ranking trace", async () => {
    const fetch = vi.fn((input: RequestInfo | URL) => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(String(input).endsWith("outcome-1") ? {
        ...item,
        purchaseIntent: { status: "PURCHASED", attribution: "ATTRIBUTED" },
        currentLearningProfile: {
          preferences: { themes: { beach: { score: 1 } } },
          outcomeCounts: { PURCHASED: 1 }, confidence: 0.5,
          evidenceCount: 1, snapshotType: "CURRENT_PROFILE",
          updatedAt: item.timestamp,
        },
      } : {
        items: [item], total: 1,
        statistics: {
          outcomes: 1, profiles: 1, purchases: 1,
          ignoredExpired: 0, latest: item.timestamp,
        },
      }),
    } as Response));
    vi.stubGlobal("fetch", fetch);
    render(<RecommendationDiagnosticsPage />);

    expect(await screen.findByText("buyer-a1b2c3d4e5")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open details" }));
    expect(await screen.findByText("Decision overview")).toBeInTheDocument();
    expect(screen.getAllByText("0.843").length).toBeGreaterThan(0);
    expect(screen.getByText("Matched beach.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Outcome"), {
      target: { value: "PURCHASED" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(
      fetch.mock.calls.some(([url]) => String(url).includes("outcome=PURCHASED")),
    ).toBe(true));
    expect(screen.queryByRole("button", { name: /delete|edit|rerun/i }))
      .not.toBeInTheDocument();
  });

  it("renders empty and API error states", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({
        items: [], total: 0,
        statistics: {
          outcomes: 0, profiles: 0, purchases: 0,
          ignoredExpired: 0, latest: null,
        },
      }),
    } as Response)));
    const view = render(<RecommendationDiagnosticsPage />);
    expect(await screen.findByText(
      "No recommendation outcomes match these filters.",
    )).toBeInTheDocument();
    view.unmount();

    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false,
      json: () => Promise.resolve({ detail: "Diagnostics unavailable" }),
    } as Response)));
    render(<RecommendationDiagnosticsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Diagnostics unavailable",
    );
  });
});
