import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RelationshipsPage } from "./RelationshipsPage";

const base = {
  personKey: "telegram:2:2:1", telegramUserId: 1, displayName: "A deliberately long customer name",
  username: "long_customer_username", identityStatus: "UNMAPPED", buyerStatus: null,
  isBuyer: false, lifetimeVerifiedRevenueMinor: null, qualifyingPurchaseCount: null,
  latestActivityAt: "2026-09-17T18:00:00Z", latestMessagePreview: "latest preview remains visible",
  activePurchaseIntent: false, activeSalesSession: false, operationalStatus: "REPLY_SCHEDULED",
  nextAutomaticAttemptAt: "2026-09-17T18:05:00Z", marketTier: "MEDIUM", highValueProspect: true,
  timeWaster: true, failedPresentationCount: 8, verifiedPurchaseCount: 0,
};
const ok = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), {
  status: 200, headers: { "Content-Type": "application/json" },
}));

afterEach(() => vi.restoreAllMocks());

it("reserves the title for operational status and moves compact classifications below the preview", async () => {
  const buyer = { ...base, personKey: "telegram:2:2:2", telegramUserId: 2, displayName: "Buyer", username: "buyer", isBuyer: true, marketTier: "HIGH", highValueProspect: false, operationalStatus: "NONE", timeWaster: false, verifiedPurchaseCount: 1 };
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("/messages?")
    ? ok({ person: base, items: [], olderCursor: null, hasMoreOlder: false })
    : ok({ items: [base, buyer], nextCursor: null, hasMore: false, summary: { total: 2, needsAttention: 0, buyers: 1, prospects: 1, manual: 0 } }));
  render(<RelationshipsPage />);

  const scheduled = await screen.findByRole("button", { name: /deliberately long customer name/ });
  const title = scheduled.querySelector<HTMLElement>(".relationship-row-title")!;
  const metadata = scheduled.querySelector<HTMLElement>(".relationship-row-metadata")!;
  expect(within(title).getByText(/REPLY SCHEDULED/)).toHaveClass("is-operational");
  expect(within(title).queryByText("PROSPECT")).not.toBeInTheDocument();
  expect(within(metadata).getByText("PROSPECT")).toBeInTheDocument();
  expect(within(metadata).getByText("HVP")).toBeInTheDocument();
  expect(within(metadata).getByText("MED")).toBeInTheDocument();
  const tw = within(metadata).getByText("TW");
  expect(tw).toHaveAttribute("title", expect.stringContaining("8 failed PPVs"));
  expect(tw).toHaveAttribute("tabindex", "0");
  expect(scheduled).not.toHaveTextContent("Conversation prospect");
  expect(scheduled).toHaveTextContent("latest preview remains visible");

  const buyerRow = screen.getAllByRole("button").find((item) => item.classList.contains("relationship-row") && item.textContent?.includes("@buyer"))!;
  const buyerMetadata = buyerRow.querySelector<HTMLElement>(".relationship-row-metadata")!;
  expect(within(buyerMetadata).getByText("CUSTOMER")).toBeInTheDocument();
  expect(within(buyerMetadata).getByText("HIGH")).toBeInTheDocument();
  expect(within(buyerMetadata).queryByText("TW")).not.toBeInTheDocument();

  fireEvent.click(scheduled);
  const selectedTitle = await screen.findByRole("heading", { name: base.displayName });
  const selectedBadges = selectedTitle.closest<HTMLElement>(".selected-customer-title")!;
  expect(within(selectedBadges).getByText("TW")).toHaveAttribute(
    "aria-label",
    expect.stringContaining("Reduced investment active"),
  );
});
