import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { RelationshipsPage } from "./RelationshipsPage";

const person = { personKey: "telegram:7:8:1", telegramUserId: 1, displayName: "Alex", username: "alex", identityStatus: "UNMAPPED", buyerStatus: null, lifetimeVerifiedRevenueMinor: null, qualifyingPurchaseCount: null, latestActivityAt: "2026-09-06T14:00:00Z", latestMessagePreview: "hello", activePurchaseIntent: false, activeSalesSession: false };
const response = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
afterEach(() => vi.restoreAllMocks());

it("links a selected canonical relationship to customer training without mutation", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("/messages?")
    ? response({ person, items: [], olderCursor: null, hasMoreOlder: false })
    : String(input).includes("/control")
      ? response({ mode: "AVA_AUTO", controlVersion: 1, changedAt: null, changedBy: "SYSTEM", reason: null, lastManualActivityAt: null, activePurchaseIntent: false, activeSalesSession: false })
      : response({ items: [person], nextCursor: null, hasMore: false }));
  render(<MemoryRouter><RelationshipsPage /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
  expect(await screen.findByRole("link", { name: "Train Ava for this customer" })).toHaveAttribute("href", "/training/ai-training?tab=queue&scope=customer&customer=telegram%3A7%3A8%3A1");
  expect(fetchMock.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
});
