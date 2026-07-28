import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CustomerSalesBrainPage } from "./CustomerSalesBrainPage";

const decision = {
  creatorProfileId: 2, fanvueAccountId: 7,
  externalFanvueBuyerUuid: "9d7ce679-ccef-4bb9-9b01-7ee8b97516bc",
  telegramUserId: 22, identityResolved: true,
  decision: "PRESENT_OFFER", reasonCode: "NO_ACTIVE_OFFER",
  reasonSummary: "No offer is active and one live offering is available.",
  buyerStage: "FIRST_TIME_BUYER",
  commerceSignal: {
    lifetimeSpendMinor: 999, purchaseCount: 1,
    latestTransaction: "order-1", attributionState: "PENDING",
  },
  activePurchaseIntentId: null, activeOfferingId: null,
  activeOfferStatus: null, activeOfferConversionState: "NO_ACTIVE_OFFER",
  recommendedOfferingId: "offering-1",
  recommendedPublicationId: "publication-1",
  recommendedDeliveryUrl: "https://fanvue.com/link",
  sellAllowed: true, nudgeAllowed: false, upsellAllowed: false,
  crossSellAllowed: false, congratulateAllowed: false,
  cooldownUntil: null, evaluatedAt: "2026-07-26T00:00:00Z",
  decisionMetadata: {
    rulePriority: 9,
    configuration: { purchaseCooldownHours: 24, offerNudgeHours: 24 },
  },
};
const statistics = {
  total: 1, decisionDistribution: { PRESENT_OFFER: 1 },
  buyerStageDistribution: { FIRST_TIME_BUYER: 1 },
  currentActiveOffers: 0, pendingPayments: 0, unknownAttributions: 0,
};

function response(body: unknown) {
  return Promise.resolve({
    ok: true, json: () => Promise.resolve(body),
  } as Response);
}

afterEach(() => vi.unstubAllGlobals());

describe("CustomerSalesBrainPage", () => {
  it("renders distributions and opens the complete read-only decision", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
      String(input).endsWith("/statistics")
        ? response(statistics)
        : response({
          items: [decision], total: 1, page: 1,
          pageSize: 20, totalPages: 1,
        })
    ));
    render(<CustomerSalesBrainPage />);
    expect((await screen.findAllByText("First Time Buyer")).length).toBe(2);
    fireEvent.click(screen.getByRole("button", {
      name: `View ${decision.externalFanvueBuyerUuid}`,
    }));
    const detail = screen.getByLabelText("Complete CustomerSalesDecision");
    expect(detail).toHaveTextContent("NO_ACTIVE_OFFER");
    expect(detail).toHaveTextContent("offering-1");
    expect(detail).toHaveTextContent("purchaseCooldownHours");
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
  });

  it("searches through the read-only list", async () => {
    const fetch = vi.fn((input: RequestInfo | URL) =>
      String(input).endsWith("/statistics")
        ? response(statistics)
        : response({
          items: [], total: 0, page: 1,
          pageSize: 20, totalPages: 1,
        })
    );
    vi.stubGlobal("fetch", fetch);
    render(<CustomerSalesBrainPage />);
    await screen.findByText("No customer decisions found.");
    fireEvent.change(screen.getByLabelText("Search Customer Sales Brain"), {
      target: { value: "buyer-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(fetch.mock.calls.some(([input]) =>
      String(input).includes("search=buyer-1")
    )).toBe(true));
  });
});
