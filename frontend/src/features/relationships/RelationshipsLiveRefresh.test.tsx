import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RelationshipsPage } from "./RelationshipsPage";

const person = {
  personKey: "telegram:7:8:1",
  telegramUserId: 1,
  displayName: "Alex",
  username: "alex",
  identityStatus: "VERIFIED",
  buyerStatus: "PROSPECT",
  lifetimeVerifiedRevenueMinor: 0,
  qualifyingPurchaseCount: 0,
  latestActivityAt: "2026-09-17T18:00:00Z",
  latestMessagePreview: "old message",
  activePurchaseIntent: false,
  activeSalesSession: false,
  isBuyer: false,
  operationalStatus: "NONE",
  needsAttention: false,
};
const message = (eventKey: string, content: string, direction = "CUSTOMER") => ({
  eventKey,
  direction,
  content,
  timestamp: `2026-09-17T18:00:0${eventKey}Z`,
  telegramMessageId: Number(eventKey),
  messageType: "ORDINARY_CHAT",
  purchaseIntentId: null,
});
const response = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
const list = (items = [person], total = items.length) => ({
  items,
  nextCursor: null,
  hasMore: false,
  summary: { total, needsAttention: 0, buyers: 0, prospects: total, manual: 0 },
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
});

describe("Business Chat live refresh", () => {
  it("keeps the newest rapid selection when older requests finish out of order", async () => {
    const people = ["A", "B", "C"].map((name, index) => ({
      ...person, personKey: `telegram:7:8:${index + 1}`,
      telegramUserId: index + 1, displayName: name, username: name.toLowerCase(),
    }));
    const pending = new Map<string, (value: Response) => void>();
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url=String(input);
      if (url.includes("/messages?")) {
        const key=decodeURIComponent(url).match(/telegram:7:8:(\d+)/)?.[1] || "";
        return new Promise<Response>((resolve) => pending.set(key,resolve));
      }
      if (url.endsWith("/control")) return response({ mode:"AVA_AUTO",controlVersion:0 });
      if (url.includes("/intelligence") || url.includes("/market-tier"))
        return response({});
      return response(list(people));
    });
    render(<RelationshipsPage />);
    await screen.findByText("A");
    fireEvent.click(screen.getByText("A").closest("button")!);
    fireEvent.click(screen.getByText("B").closest("button")!);
    fireEvent.click(screen.getByText("C").closest("button")!);
    await act(async () => pending.get("3")?.(await response({items:[message("3","C newest")],olderCursor:null,hasMoreOlder:false})));
    await screen.findByText("C newest");
    await act(async () => pending.get("1")?.(await response({items:[message("1","A stale")],olderCursor:null,hasMoreOlder:false})));
    await act(async () => pending.get("2")?.(await response({items:[message("2","B stale")],olderCursor:null,hasMoreOlder:false})));
    expect(screen.getByText("C newest")).toBeInTheDocument();
    expect(screen.queryByText("A stale")).not.toBeInTheDocument();
    expect(screen.queryByText("B stale")).not.toBeInTheDocument();
  });
  it("silently refreshes the list, summary, and selected customer/Ava messages", async () => {
    vi.useFakeTimers();
    let listReads = 0, messageReads = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/control"))
        return response({ mode: "AVA_AUTO", controlVersion: 0, activePurchaseIntent: false, activeSalesSession: false });
      if (url.includes("/messages?")) {
        messageReads += 1;
        const items = messageReads === 1
          ? [message("1", "old message")]
          : [message("1", "old message"), message("2", "new inbound"), message("3", "new Ava reply", "AVA")];
        return response({ person, items, olderCursor: null, hasMoreOlder: false });
      }
      listReads += 1;
      const newcomer = { ...person, personKey: "telegram:7:8:2", telegramUserId: 2, displayName: "Blair", username: "blair" };
      return response(list(listReads === 1 ? [person] : [newcomer, { ...person, isBuyer: true, latestMessagePreview: "new inbound" }], listReads === 1 ? 1 : 2));
    });
    render(<RelationshipsPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(screen.getByRole("button", { name: /Alex/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getAllByText("old message").length).toBeGreaterThan(0);

    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(screen.getAllByText("new inbound").length).toBeGreaterThan(0);
    expect(screen.getByText("new Ava reply")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Blair/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Alex/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByRole("button", { name: /Alex/ })).getByText("CUSTOMER")).toBeInTheDocument();
    expect(screen.queryByText("Loading conversation…")).not.toBeInTheDocument();
    expect(screen.getByText("Total Chats").closest("button")).toHaveTextContent("2");
  });

  it("reconciles an externally changed relationship control mode", async () => {
    vi.useFakeTimers();
    let controlReads = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.endsWith("/control")) {
        controlReads += 1;
        return response({
          mode: controlReads === 1 ? "AVA_AUTO" : "HUMAN_OPERATOR",
          controlVersion: controlReads,
          activePurchaseIntent: false,
          activeSalesSession: false,
        });
      }
      if (url.includes("/messages?"))
        return response({ person, items: [], olderCursor: null, hasMoreOlder: false });
      return response(list());
    });
    render(<RelationshipsPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(screen.getByRole("button", { name: /Alex/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("button", { name: "TAKE OVER" })).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(screen.getByRole("button", { name: "RETURN TO AVA" })).toBeInTheDocument();
    expect(screen.getByLabelText("Write a message")).toBeInTheDocument();
  });

  it("pauses while hidden and immediately revalidates on return", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => response(list()));
    render(<RelationshipsPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const initial = fetchMock.mock.calls.length;
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "hidden" });
    await act(async () => { await vi.advanceTimersByTimeAsync(9000); });
    expect(fetchMock).toHaveBeenCalledTimes(initial);
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); await vi.advanceTimersByTimeAsync(0); });
    expect(fetchMock.mock.calls.length).toBeGreaterThan(initial);
  });

  it("deduplicates an in-flight list poll and keeps stale data on failure", async () => {
    vi.useFakeTimers();
    let finish: ((value: Response) => void) | undefined;
    let reads = 0;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => {
      reads += 1;
      if (reads === 1) return response(list());
      if (reads === 2) return new Promise<Response>((resolve) => { finish = resolve; });
      return response({ detail: "temporary" }, 500);
    });
    render(<RelationshipsPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("button", { name: /Alex/ })).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () => { finish?.(new Response(JSON.stringify({ detail: "temporary" }), { status: 500, headers: { "Content-Type": "application/json" } })); await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("button", { name: /Alex/ })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("temporary");
  });
});
