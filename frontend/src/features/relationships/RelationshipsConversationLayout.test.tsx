import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { RelationshipsPage } from "./RelationshipsPage";

const alex = {
  personKey: "telegram:7:8:1",
  telegramUserId: 1,
  displayName: "Alex",
  username: "alex",
  identityStatus: "UNMAPPED",
  buyerStatus: null,
  lifetimeVerifiedRevenueMinor: null,
  qualifyingPurchaseCount: null,
  latestActivityAt: "2026-09-13T20:00:00Z",
  latestMessagePreview: "latest",
  activePurchaseIntent: false,
  activeSalesSession: false,
  controlMode: "AVA_AUTO",
  operationalStatus: "REPLY_SCHEDULED",
  nextAutomaticAttemptAt: "2026-09-13T20:30:00Z",
};
const blair = {
  ...alex,
  personKey: "telegram:7:8:2",
  telegramUserId: 2,
  displayName: "Blair",
  username: "blair",
};
const intelligence = (person: typeof alex) => ({
  person,
  mappingStatus: "UNMAPPED",
  partial: true,
  operatorClassification: null,
  effectiveAttentionPriority: "HIGH",
  behavioralIntelligence: {
    buyingIntent: "NONE",
    currentSignal: "NONE",
    salesStage: "PROSPECT",
  },
  customerValue: {
    buyerStatus: "UNMAPPED_PROSPECT",
    valueTier: "ENGAGED_PROSPECT",
    attentionTier: "HIGH",
    lifetimeSpendMinor: null,
    purchaseCount: null,
    repeatBuyer: false,
    relationshipLifecycle: "PROSPECT",
    relationshipInvestment: "STANDARD",
    continuationValue: "HIGH",
    timeWasterRisk: "NONE",
    retention: "NONE",
  },
  salesPerformance: {
    offersPresented: 0,
    offersPurchased: 0,
    offersNotPurchased: 0,
    conversionRate: null,
    lastOffer: null,
    lastPurchase: null,
  },
  commercialState: {
    activePurchaseIntent: null,
    activeSalesSession: null,
    activeOffer: null,
  },
  purchaseHistory: [],
  relationshipIntelligence: {
    location: null,
    timezone: null,
    interests: [],
    pets: [],
    music: [],
    preferences: [],
  },
});
const message = (eventKey: string, content: string, timestamp: string) => ({
  eventKey,
  direction: "CUSTOMER",
  content,
  timestamp,
  telegramMessageId: Number(eventKey),
  messageType: "ORDINARY_CHAT",
  purchaseIntentId: null,
});
const reply = (body: unknown) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

function mockRelationships() {
  return vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    const person = url.includes(encodeURIComponent(blair.personKey))
      ? blair
      : alex;
    if (url.includes("/messages?"))
      return reply({
        person,
        items: [
          message("1", `${person.displayName} oldest`, `2026-09-12T14:00:00Z`),
          message("2", `${person.displayName} latest`, `2026-09-13T20:00:00Z`),
        ],
        olderCursor: null,
        hasMoreOlder: false,
      });
    if (url.includes("/intelligence")) return reply(intelligence(person));
    if (url.includes("/market-tier"))
      return reply({
        marketTier: "HIGH",
        effectiveProspectInvestment: "HIGH",
        highValueProspect: false,
        verifiedBuyer: false,
        repliesUsedToday: 0,
        dailyReplyBudget: "FULL",
        budgetStatus: "AVAILABLE",
        nextBudgetResetAt: null,
        prospectReplyLimit: null,
      });
    if (url.includes("/control"))
      return reply({
        mode: "AVA_AUTO",
        controlVersion: 0,
        activePurchaseIntent: false,
        activeSalesSession: false,
      });
    return reply({
      items: [alex, blair],
      nextCursor: null,
      hasMore: false,
      summary: {
        total: 2,
        needsAttention: 0,
        buyers: 0,
        prospects: 2,
        manual: 0,
      },
    });
  });
}

afterEach(() => vi.restoreAllMocks());

it("keeps intelligence out of the conversation flow while header controls and transcript remain available", async () => {
  const fetchMock = mockRelationships();
  render(<RelationshipsPage />);
  fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
  await screen.findByText("Alex latest");
  expect(
    screen
      .getByRole("region", { name: "Customer Intelligence summary" })
      .closest(".customer-intelligence-stack"),
  ).toHaveClass("customer-intelligence-stack");
  expect(
    screen
      .getByRole("region", { name: "Country Tier Intelligence" })
      .closest(".customer-intelligence-stack"),
  ).toHaveClass("customer-intelligence-stack");
  expect(
    screen.getByRole("button", { name: "Open Customer Intelligence" }),
  ).toBeInTheDocument();
  const transcript = screen
    .getByText("Alex latest")
    .closest(".relationship-transcript")!;
  expect(transcript).toHaveClass("relationship-transcript");
  expect(transcript).toHaveTextContent("Alex oldest");
  expect(transcript).toHaveTextContent("Alex latest");
  expect(
    screen.getByRole("region", { name: "Conversation operational status" }),
  ).toHaveTextContent("Reply Scheduled");
  expect(
    screen.queryByRole("button", { name: "Toggle High Value Prospect" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Market Tier")).not.toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "More conversation controls" }),
  );
  expect(
    screen.getByRole("menuitem", { name: /High Value Prospect/ }),
  ).toBeInTheDocument();
  expect(screen.getByRole("menuitem", { name: "HIGH" })).toBeInTheDocument();
  expect(
    fetchMock.mock.calls.every(
      ([, init]) => !init || !init.method || init.method === "GET",
    ),
  ).toBe(true);
});

it("opens intelligence in the drawer, preserves every field and transcript, then closes", async () => {
  mockRelationships();
  render(<RelationshipsPage />);
  fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
  await screen.findByText("Alex latest");
  fireEvent.click(
    screen.getByRole("button", { name: "Open Customer Intelligence" }),
  );
  expect(
    await screen.findByRole("complementary", { name: "Customer Intelligence" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "View Customer Intelligence" }));
  const dialog = screen.getByRole("dialog", { name: "Customer Intelligence" });
  const card = within(dialog).getByRole("region", { name: "Customer Intelligence" });
  const details = card.querySelector(".customer-intelligence-details")!;
  expect(details).toHaveClass("customer-intelligence-details");
  expect(details).toHaveTextContent("Lifecycle");
  expect(details).toHaveTextContent("Automatic Value");
  expect(details).toHaveTextContent("Operator Classification");
  expect(details).toHaveTextContent("Effective Attention");
  expect(details).toHaveTextContent("Buying Intent");
  expect(details).toHaveTextContent("Current Signal");
  expect(details).toHaveTextContent("Lifecycle");
  expect(details).not.toHaveTextContent("Sales Stage");
  expect(details).toHaveTextContent("Relationship Investment");
  expect(details).toHaveTextContent("Time-Waster Risk");
  expect(details).toHaveTextContent("Retention");
  expect(
    screen.getByRole("region", { name: "Country Tier Intelligence" }),
  ).toHaveTextContent("HIGH");
  expect(screen.getByText("Alex oldest")).toBeInTheDocument();
  expect(screen.getByText("Alex latest")).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole("button", { name: "Close Customer Intelligence details" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Close Customer Intelligence" }),
  );
  expect(
    screen.queryByRole("complementary", { name: "Customer Intelligence" }),
  ).not.toBeInTheDocument();
});

it("closes the drawer when another conversation is selected without truncating its history", async () => {
  mockRelationships();
  render(<RelationshipsPage />);
  fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
  await screen.findByText("Alex latest");
  fireEvent.click(
    screen.getByRole("button", { name: "Open Customer Intelligence" }),
  );
  expect(
    await screen.findByRole("complementary", { name: "Customer Intelligence" }),
  ).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Blair/ }));
  await screen.findByText("Blair latest");
  await waitFor(() =>
    expect(
      screen.queryByRole("complementary", { name: "Customer Intelligence" }),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByText("Blair oldest")).toBeInTheDocument();
  expect(screen.queryByText("Alex latest")).not.toBeInTheDocument();
});

it("renders valid message history when the secondary control request fails", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.includes("/messages?"))
      return reply({
        person: alex,
        items: [message("1", "Transcript survives", "2026-09-13T20:00:00Z")],
        olderCursor: null,
        hasMoreOlder: false,
      });
    if (url.includes("/control"))
      return Promise.resolve(
        new Response(
          JSON.stringify({ detail: "Relationship controls unavailable." }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        ),
      );
    if (url.includes("/intelligence")) return reply(intelligence(alex));
    if (url.includes("/market-tier"))
      return reply({
        marketTier: "UNCLASSIFIED",
        effectiveProspectInvestment: "STANDARD",
        highValueProspect: false,
        verifiedBuyer: false,
        repliesUsedToday: 0,
        dailyReplyBudget: "FULL",
        budgetStatus: "AVAILABLE",
        nextBudgetResetAt: null,
        prospectReplyLimit: null,
      });
    return reply({
      items: [alex],
      nextCursor: null,
      hasMore: false,
      summary: {
        total: 1,
        needsAttention: 0,
        buyers: 0,
        prospects: 1,
        manual: 0,
      },
    });
  });
  render(<RelationshipsPage />);
  fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
  expect(await screen.findByText("Transcript survives")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Relationship controls unavailable.",
  );
});

it.each(["intelligence", "market-tier"])(
  "keeps the transcript when %s fails",
  async (failedPath) => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/messages?"))
        return reply({
          person: alex,
          items: [message("1", "Still visible", "2026-09-13T20:00:00Z")],
          olderCursor: null,
          hasMoreOlder: false,
        });
      if (url.includes(`/${failedPath}`))
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Secondary unavailable" }), {
            status: 503,
            headers: { "Content-Type": "application/json" },
          }),
        );
      if (url.includes("/control"))
        return reply({
          mode: "AVA_AUTO",
          controlVersion: 0,
          activePurchaseIntent: false,
          activeSalesSession: false,
        });
      if (url.includes("/intelligence")) return reply(intelligence(alex));
      if (url.includes("/market-tier"))
        return reply({
          marketTier: "UNCLASSIFIED",
          effectiveProspectInvestment: "STANDARD",
          highValueProspect: false,
          verifiedBuyer: false,
          repliesUsedToday: 0,
          dailyReplyBudget: "FULL",
          budgetStatus: "AVAILABLE",
          nextBudgetResetAt: null,
          prospectReplyLimit: null,
        });
      return reply({
        items: [alex],
        nextCursor: null,
        hasMore: false,
        summary: {
          total: 1,
          needsAttention: 0,
          buyers: 0,
          prospects: 1,
          manual: 0,
        },
      });
    });
    render(<RelationshipsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
    expect(await screen.findByText("Still visible")).toBeInTheDocument();
  },
);

it("shows a bounded transcript error when messages genuinely do not resolve", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
    const url = String(input);
    if (url.includes("/messages?"))
      return Promise.resolve(
        new Response(JSON.stringify({ detail: "Relationship not found." }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      );
    if (url.includes("/control"))
      return reply({
        mode: "AVA_AUTO",
        controlVersion: 0,
        activePurchaseIntent: false,
        activeSalesSession: false,
      });
    if (url.includes("/intelligence")) return reply(intelligence(alex));
    if (url.includes("/market-tier"))
      return reply({
        marketTier: "UNCLASSIFIED",
        effectiveProspectInvestment: "STANDARD",
        highValueProspect: false,
        verifiedBuyer: false,
        repliesUsedToday: 0,
        dailyReplyBudget: "FULL",
        budgetStatus: "AVAILABLE",
        nextBudgetResetAt: null,
        prospectReplyLimit: null,
      });
    return reply({
      items: [alex],
      nextCursor: null,
      hasMore: false,
      summary: {
        total: 1,
        needsAttention: 0,
        buyers: 0,
        prospects: 1,
        manual: 0,
      },
    });
  });
  render(<RelationshipsPage />);
  fireEvent.click(await screen.findByRole("button", { name: /Alex/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Relationship not found.",
  );
});
