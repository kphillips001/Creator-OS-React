import type { ReactElement } from "react";
import { fireEvent, render as renderLibrary, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PerformanceSnapshot } from "./PerformanceSnapshot";

function LocationProbe() { const location = useLocation(); return <output data-testid="location">{location.pathname}{location.search}</output>; }
const render = (ui: ReactElement) => renderLibrary(<MemoryRouter>{ui}<LocationProbe /></MemoryRouter>);

const metric = (value: number | null, status: "AVAILABLE" | "UNAVAILABLE" = "AVAILABLE") => ({ status, value, recordIds: [] });
const snapshot = {
  period: { key: "TODAY", timezone: "America/Chicago", start: "2026-09-06T05:00:00Z", end: "2026-09-07T05:00:00Z", generatedAt: "2026-09-06T12:00:00Z", interval: "[start,end)" },
  commerce: {
    totalVerifiedRevenueMinor: metric(12345), contentMediaRevenueMinor: metric(12345), tipsRevenueMinor: metric(0),
    subscriptionRenewalRevenueMinor: metric(0), unclassifiedRevenueMinor: metric(0), qualifyingPurchases: metric(2),
    uniqueBuyers: metric(1), newBuyers: metric(1), repeatBuyers: metric(0), averagePurchaseValueMinor: metric(6173),
    offersPresented: metric(3), offersPurchased: metric(1), offerConversion: metric(33.3),
    wouldHaveSold: metric(null, "UNAVAILABLE"),
  },
  peopleActivity: { activePeople: metric(1), newPeople: metric(1), returningPeople: metric(0), customerMessages: metric(8), avaMessages: metric(7) },
  dataQuality: {},
};
const response = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

afterEach(() => vi.restoreAllMocks());

describe("Performance Snapshot", () => {
  it("loads Today by default, formats money and zero, and distinguishes unavailable", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(snapshot));
    render(<PerformanceSnapshot />);
    expect(screen.getByRole("button", { name: "Today" })).toHaveAttribute("aria-pressed", "true");
    expect((await screen.findAllByText("$123.45")).length).toBe(2);
    expect(screen.getByRole("button", { name: /Tips \$0\.00/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Would Have Sold/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Customers" })).toHaveAttribute("href", "/business/customers");
    expect(screen.getByRole("link", { name: "Buyers" })).toHaveAttribute("href", "/business/customers?filter=buyers");
    expect(screen.getByRole("link", { name: "Active Subscribers" })).toHaveAttribute("href", "/business/customers?filter=subscribers");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/creator-intelligence/snapshot?period=TODAY", expect.objectContaining({ cache: "no-store" }));
  });

  it("uses SPA navigation for every contextual deep link and preserves query parameters", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("current-sales-status")
      ? response({ activeSalesSessions: 1, activePurchaseIntents: 2, commercialFailures: 3 })
      : response(snapshot));
    render(<PerformanceSnapshot />);
    await screen.findAllByText("$123.45");
    const links: Array<[string, string]> = [
      ["Customers", "/business/customers"],
      ["Buyers", "/business/customers?filter=buyers"],
      ["Active Subscribers", "/business/customers?filter=subscribers"],
      ["Offer Activity", "/business/sales?tab=offers"],
      ["Active Sales Sessions", "/business/relationships?filter=active-sessions"],
      ["Active PurchaseIntents", "/business/relationships?filter=active-intents"],
      ["Commercial Failures", "/business/operations?tab=failures"],
    ];
    for (const [name, expected] of links) {
      fireEvent.click(screen.getByRole("link", { name }));
      expect(screen.getByTestId("location")).toHaveTextContent(expected);
    }
  });

  it("requests the selected uppercase period without polling", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(snapshot));
    render(<PerformanceSnapshot />);
    await screen.findAllByText("$123.45");
    fireEvent.click(screen.getByRole("button", { name: "30 Days" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/creator-intelligence/snapshot?period=LAST_30_DAYS", expect.anything()));
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("opens authoritative drill-down records for a metric", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("drill-down")
      ? response({ period: snapshot.period, metric: "active_people", count: 1, amountMinor: null, items: [{ personKey: "telegram:42", displayName: "Jordan", buyerStatus: "NONBUYER" }] })
      : response(snapshot));
    render(<PerformanceSnapshot />);
    const peopleChatted = await screen.findByRole("button", { name: /People Chatted 1/ });
    expect(peopleChatted).toHaveAttribute("title", "Unique people who chatted with Ava during this period.");
    fireEvent.click(peopleChatted);
    expect(await screen.findByRole("dialog", { name: "People Chatted" })).toHaveTextContent("Jordan");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("period=TODAY&metric=ACTIVE_PEOPLE"), expect.anything());
  });

  it("renders the offer funnel separately from paid-period purchases", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("drill-down")
      ? response({ period: snapshot.period, metric: "OFFERS_PURCHASED", count: 1, amountMinor: 5000, items: [{ record_id: "intent-1", offerConversionStatus: "PURCHASED" }] })
      : response(snapshot));
    render(<PerformanceSnapshot />);
    expect(await screen.findByRole("button", { name: /Offers Purchased 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Offer Conversion 33\.3%/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Purchases 2/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Offers Purchased 1/ }));
    expect(await screen.findByRole("dialog", { name: "Offers Purchased" })).toHaveTextContent("intent-1");
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("metric=OFFERS_PURCHASED"), expect.anything());
  });

  it("uses an em dash when offer conversion has no denominator", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ ...snapshot, commerce: { ...snapshot.commerce, offersPresented: metric(0), offersPurchased: metric(0), offerConversion: metric(null, "UNAVAILABLE") } }));
    render(<PerformanceSnapshot />);
    expect(await screen.findByRole("button", { name: /Offer Conversion —/ })).toBeInTheDocument();
  });

  it("carries the selected period into offer conversion drill-down", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("drill-down")
      ? response({ period: { ...snapshot.period, key: "YESTERDAY" }, metric: "OFFER_CONVERSION", count: 3, amountMinor: 5000, items: [] })
      : response({ ...snapshot, period: { ...snapshot.period, key: "YESTERDAY" } }));
    render(<PerformanceSnapshot />);
    await screen.findByRole("button", { name: /Offer Conversion/ });
    fireEvent.click(screen.getByRole("button", { name: "Yesterday" }));
    const conversion = await screen.findByRole("button", { name: /Offer Conversion 33\.3%/ });
    fireEvent.click(conversion);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("period=YESTERDAY&metric=OFFER_CONVERSION"), expect.anything()));
  });

  it("contains snapshot errors and offers retry", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ detail: "Snapshot unavailable." }, 503));
    render(<PerformanceSnapshot />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Snapshot unavailable.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
  it("shows current commercial state with contextual destinations", async () => {
    vi.spyOn(globalThis,"fetch").mockImplementation(input=>String(input).includes("sales-status")?response({activeSalesSessions:2,activePurchaseIntents:3,commercialFailures:1,asOf:"CURRENT"}):response(snapshot));
    render(<PerformanceSnapshot/>);
    expect(await screen.findByRole("region",{name:"Current sales state"})).toHaveTextContent("Active Sales Sessions2");
    expect(screen.getByRole("link",{name:/Active Sales Sessions/})).toHaveAttribute("href","/business/relationships?filter=active-sessions");
    expect(screen.getByRole("link",{name:/Active PurchaseIntents/})).toHaveAttribute("href","/business/relationships?filter=active-intents");
    expect(screen.getByRole("link",{name:/Commercial Failures/})).toHaveAttribute("href","/business/operations?tab=failures");
    expect(screen.getByRole("link",{name:"Offer Activity"})).toHaveAttribute("href","/business/sales?tab=offers");
  });
});
