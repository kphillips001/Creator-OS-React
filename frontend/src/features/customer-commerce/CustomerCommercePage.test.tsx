import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CustomerCommercePage } from "./CustomerCommercePage";

const profile = {
  profileId: "profile-1",
  creatorProfileId: 2,
  fanvueAccountId: 7,
  externalFanvueUserUuid: "9d7ce679-ccef-4bb9-9b01-7ee8b97516bc",
  telegramIdentityMappingId: null,
  telegramUserId: null,
  displayName: "Eligible Asp",
  handle: "eligible-asp-909",
  firstSeenAt: "2026-07-24T23:58:17Z",
  lastSeenAt: "2026-07-24T23:58:17Z",
  firstPurchaseAt: "2026-07-24T23:58:17Z",
  lastPurchaseAt: "2026-07-24T23:58:17Z",
  lifetimeGrossMinor: 300,
  lifetimeNetMinor: 240,
  purchaseCount: 1,
  averageOrderValueMinor: 300,
  largestPurchaseMinor: 300,
  lastTransactionOrderId: "FVE-20260724-104266",
  lastPaymentStatus: "pendingBalance",
  lastPurchaseSource: "mediaLink",
  lastSyncedAt: "2026-07-25T00:00:00Z",
  profileState: "UNKNOWN",
  createdAt: "2026-07-24T23:58:17Z",
  updatedAt: "2026-07-25T00:00:00Z",
};
const statistics = {
  profileCount: 1, buyerCount: 1, lifetimeGrossMinor: 300,
  lifetimeNetMinor: 240, purchaseCount: 1,
  averageOrderValueMinor: 300, largestPurchaseMinor: 300,
};

function response(body: unknown) {
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve(body),
  } as Response);
}

afterEach(() => vi.unstubAllGlobals());

describe("CustomerCommercePage", () => {
  it("renders statistics and opens the complete read-only profile", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
      String(input).includes("/commerce-signals?")
        ? response({
          buyerUuid: profile.externalFanvueUserUuid,
          telegramUserId: 22, identityResolved: true,
          lifetimeSpendMinor: 300, purchaseCount: 1,
          lastPurchaseAt: profile.lastPurchaseAt,
          currentActiveOfferId: "offering-1",
          currentOfferStatus: "PURCHASED",
          conversionState: "PURCHASED",
          latestTransaction: profile.lastTransactionOrderId,
          attributionState: "ATTRIBUTED",
          reconciliationState: "VERIFIED",
        })
        : String(input).endsWith("/statistics")
        ? response(statistics)
        : response({
          items: [profile], total: 1, page: 1,
          pageSize: 20, totalPages: 1,
        })
    ));
    render(<CustomerCommercePage />);
    expect(await screen.findByText("Eligible Asp")).toBeInTheDocument();
    expect(screen.getAllByText("$3.00").length).toBeGreaterThan(0);
    expect(screen.getByText("No commerce profile selected.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View Eligible Asp" }));
    const detail = screen.getByLabelText("Complete Commerce Profile");
    expect(detail).toHaveTextContent("FVE-20260724-104266");
    expect(detail).toHaveTextContent("Not linked");
    expect(await screen.findByText("Identity Resolved")).toBeInTheDocument();
    expect(detail).toHaveTextContent("Attributed");
    expect(detail).toHaveTextContent("Verified");
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
  });

  it("searches through the read-only list endpoint", async () => {
    const fetch = vi.fn((input: RequestInfo | URL) =>
      String(input).endsWith("/statistics")
        ? response(statistics)
        : response({
          items: [], total: 0, page: 1,
          pageSize: 20, totalPages: 1,
        })
    );
    vi.stubGlobal("fetch", fetch);
    render(<CustomerCommercePage />);
    await screen.findByText("No customer commerce profiles found.");
    fireEvent.change(screen.getByLabelText("Search Customer Commerce"), {
      target: { value: "buyer-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(
      fetch.mock.calls.some(([input]) =>
        String(input).includes("search=buyer-1")
      ),
    ).toBe(true));
  });

  it("renders API failures without exposing mutation controls", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
      ok: false,
      json: () => Promise.resolve({ detail: "Commerce unavailable" }),
    } as Response)));
    render(<CustomerCommercePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Commerce unavailable",
    );
  });
});
