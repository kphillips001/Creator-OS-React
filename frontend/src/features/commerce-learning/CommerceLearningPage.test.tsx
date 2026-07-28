import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CommerceLearningPage } from "./CommerceLearningPage";

const profile = {
  learningProfileId: "learning-1",
  buyerUuid: "10000000-0000-0000-0000-000000000001",
  confidence: 0.8,
  evidenceCount: 8,
  preferences: {
    themes: {
      beach: { score: 0.9, confidence: 0.8, observations: 4 },
    },
  },
  outcomeCounts: { PRESENTED: 4, PURCHASED: 2 },
  preferredOfferingType: "PHOTOSET",
  averagePriceMinor: 999,
  updatedAt: "2026-07-25T12:00:00Z",
};

function response(body: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
  } as Response);
}

afterEach(() => vi.unstubAllGlobals());

describe("CommerceLearningPage", () => {
  it("renders profiles and opens observed outcomes without edit controls", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
      String(input).endsWith(profile.buyerUuid)
        ? response({
          ...profile,
          recentOutcomes: [{
            outcomeId: "outcome-1",
            offeringId: "offering-1",
            outcomeType: "PURCHASED",
            observedAt: "2026-07-25T12:00:00Z",
            evidence: { themes: ["beach"] },
          }],
        })
        : response({ items: [profile], total: 1 })
    ));

    render(<CommerceLearningPage />);
    const buyer = await screen.findByRole("button", {
      name: profile.buyerUuid,
    });
    expect(screen.getByText("80%")).toBeInTheDocument();
    fireEvent.click(buyer);

    expect(await screen.findByText("Observed Preferences")).toBeInTheDocument();
    expect(screen.getByText(/themes.*beach/i)).toBeInTheDocument();
    expect(screen.getByText("PURCHASED")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /edit|save/i }))
      .not.toBeInTheDocument();
  });

  it("shows the empty and error states", async () => {
    vi.stubGlobal("fetch", vi.fn(() => response({ items: [], total: 0 })));
    const view = render(<CommerceLearningPage />);
    expect(await screen.findByText(
      "No observed Commerce learning profiles.",
    )).toBeInTheDocument();
    view.unmount();

    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false,
      json: () => Promise.resolve({ detail: "Learning unavailable" }),
    } as Response)));
    render(<CommerceLearningPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Learning unavailable",
    );
  });
});
