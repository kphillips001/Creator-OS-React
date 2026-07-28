import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PurchaseIntentsPage } from "./PurchaseIntentsPage";

const item = {
  purchaseIntentId: "11111111-1111-4111-8111-111111111111",
  creatorProfileId: 2, fanvueAccountId: 7,
  telegramIdentityMappingId: 11, telegramUserId: 22, telegramChatId: 33,
  externalFanvueUserUuid: null,
  commercialOfferingId: "22222222-2222-4222-8222-222222222222",
  commercialPublicationId: "33333333-3333-4333-8333-333333333333",
  provider: "FANVUE", providerResourceId: "media-link-1",
  deliveryUrl: "https://fanvue.com/link", telegramMessageId: 91,
  conversationId: "conversation-1",
  correlationId: "44444444-4444-4444-8444-444444444444",
  expectedPriceMinor: 999, expectedCurrency: "USD", status: "PRESENTED",
  createdAt: "2026-07-25T00:00:00Z", presentedAt: "2026-07-25T00:01:00Z",
  clickedAt: null, expiresAt: "2026-07-25T01:00:00Z",
  abandonedAt: null, purchasedAt: null,
  providerTransactionOrderId: "order-1", providerPaymentId: null,
  providerEventId: "event-1", attributionResult: "PENDING",
  attributionReason: null, createdMetadata: { source: "test" },
  updatedAt: "2026-07-25T00:01:00Z",
};
const stats = {
  total: 1, active: 1, purchased: 0, expired: 0,
  abandoned: 0, unknown: 0, superseded: 0,
};

afterEach(() => vi.unstubAllGlobals());

describe("PurchaseIntentsPage", () => {
  it("renders a read-only master/detail lifecycle view", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(String(input).endsWith("/statistics")
          ? stats
          : { items: [item], total: 1, page: 1, pageSize: 20, totalPages: 1 }),
      } as Response)
    ));
    render(<PurchaseIntentsPage />);
    expect(await screen.findByText("22")).toBeInTheDocument();
    expect(screen.getByText("No Purchase Intent selected.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", {
      name: `View Purchase Intent ${item.purchaseIntentId}`,
    }));
    const detail = screen.getByLabelText("Complete Purchase Intent");
    expect(detail).toHaveTextContent("order-1");
    expect(detail).toHaveTextContent("$9.99");
    expect(detail).toHaveTextContent('"source": "test"');
    expect(screen.queryByRole("button", { name: /edit/i })).not.toBeInTheDocument();
  });

  it("sends search and status filters to the read-only endpoint", async () => {
    const fetch = vi.fn((input: RequestInfo | URL) => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(String(input).endsWith("/statistics")
        ? stats
        : { items: [], total: 0, page: 1, pageSize: 20, totalPages: 1 }),
    } as Response));
    vi.stubGlobal("fetch", fetch);
    render(<PurchaseIntentsPage />);
    await screen.findByText("No Purchase Intents found.");
    fireEvent.change(screen.getByLabelText("Search Purchase Intents"), {
      target: { value: "order-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.change(screen.getByLabelText("Status"), {
      target: { value: "PRESENTED" },
    });
    await waitFor(() => expect(fetch.mock.calls.some(([input]) =>
      String(input).includes("search=order-1")
      || String(input).includes("status=PRESENTED")
    )).toBe(true));
  });
});
