import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";

import { BusinessControlsPage, effectiveMode } from "./BusinessControlsPage";
import type { CustomerControls, GlobalControls } from "./api";

const globalState: GlobalControls = {
  avaBot: { desired: "OFF", effective: "OFF", reason: "Ava Bot is off." },
  contentSellingEnabled: true,
  sessionSellingEnabled: false,
};
const person = {
  personKey: "telegram:7:8:1", telegramUserId: 1, displayName: "Alex", username: "alex",
  identityStatus: "VERIFIED", buyerStatus: "VERIFIED_BUYER", lifetimeVerifiedRevenueMinor: 5000,
  qualifyingPurchaseCount: 2, latestActivityAt: "2026-09-11T12:00:00Z", latestMessagePreview: "hello",
  activePurchaseIntent: true, activeSalesSession: true, isBuyer: true,
};
const customerState = (overrides: Partial<CustomerControls["configured"]> = {}, globalOverrides: Partial<CustomerControls["global"]> = {}): CustomerControls => {
  const configured = { avaChatEnabled: true, contentSellingEnabled: false, sessionSellingEnabled: false, relationshipMode: "AVA_AUTO" as const, controlVersion: 3, ...overrides };
  const global = { avaBotDesired: "ON" as const, avaBotEffective: "ON" as const, contentSellingEnabled: true, sessionSellingEnabled: true, ...globalOverrides };
  return {
    identity: { telegramUserId: 1, telegramChatId: 1 }, configured, global,
    effective: {
      chatAllowed: configured.avaChatEnabled && global.avaBotEffective === "ON", chatReason: null,
      contentSellingAllowed: configured.contentSellingEnabled && global.contentSellingEnabled,
      contentSellingReason: configured.contentSellingEnabled && !global.contentSellingEnabled ? "GLOBAL_CONTENT_SELLING_DISABLED" : configured.contentSellingEnabled ? null : "CUSTOMER_CONTENT_SELLING_DISABLED",
      sessionSellingAllowed: configured.sessionSellingEnabled && global.sessionSellingEnabled,
      sessionSellingReason: configured.sessionSellingEnabled && !global.sessionSellingEnabled ? "GLOBAL_SESSION_SELLING_DISABLED" : configured.sessionSellingEnabled ? null : "CUSTOMER_SESSION_SELLING_DISABLED",
    },
  };
};
const response = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

afterEach(() => vi.restoreAllMocks());

describe("Business Controls", () => {
  it("loads authoritative global controls and preserves stored selling settings while Ava is off", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(globalState));
    render(<MemoryRouter><BusinessControlsPage/></MemoryRouter>);
    expect(await screen.findByText("AVA BOT")).toBeInTheDocument();
    expect(screen.getByLabelText("CONTENT SELLING control").querySelector('[aria-pressed="true"]')).toHaveTextContent("ON");
    expect(screen.getAllByText("Will apply when Ava Bot is turned on.")).toHaveLength(2);
  });

  it("shows ATTENTION without falsely presenting Ava Bot as on and links to technical details", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response({ ...globalState, avaBot: { desired: "ON", effective: "ATTENTION", reason: "Worker unavailable." } }));
    render(<MemoryRouter><BusinessControlsPage/></MemoryRouter>);
    expect(await screen.findByText("ATTENTION")).toBeInTheDocument();
    expect(screen.getByText("Ava is not fully operational.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View technical details/ })).toHaveAttribute("href", "/business/operations");
  });

  it("uses authoritative post-write global state and blocks duplicate logical mutations", async () => {
    let resolveWrite!: (value: Response) => void;
    const write = new Promise<Response>((resolve) => { resolveWrite = resolve; });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => init?.method === "PATCH" ? write : response(globalState));
    render(<MemoryRouter><BusinessControlsPage/></MemoryRouter>);
    const off = (await screen.findByLabelText("CONTENT SELLING control")).querySelectorAll("button")[0]!;
    fireEvent.click(off); fireEvent.click(off);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    resolveWrite(await response({ state: { ...globalState, contentSellingEnabled: false } }));
    await waitFor(() => expect(off).toHaveAttribute("aria-pressed", "true"));
  });

  it("does not display a failed global mutation as successful", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_input, init) => init?.method === "PATCH" ? response({ detail: "Write rejected." }, 409) : response(globalState));
    render(<MemoryRouter><BusinessControlsPage/></MemoryRouter>);
    const control = await screen.findByLabelText("CONTENT SELLING control");
    fireEvent.click(control.querySelectorAll("button")[0]!);
    expect(await screen.findByRole("alert")).toHaveTextContent("Write rejected.");
    expect(control.querySelector('[aria-pressed="true"]')).toHaveTextContent("ON");
  });

  it("loads, searches, selects, and mutates customer controls through canonical APIs", async () => {
    const initial = customerState();
    const enabled = customerState({ contentSellingEnabled: true });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = String(input);
      if (url.includes("/api/v1/relationships?") ) return response({ items: [person], nextCursor: null, hasMore: false, sort: "LATEST_ACTIVITY" });
      if (init?.method === "PATCH") return response({ state: enabled });
      return response(initial);
    });
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    const search = await screen.findByLabelText("Search customers");
    fireEvent.change(search, { target: { value: "alex" } }); fireEvent.submit(search.closest("form")!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("search=alex"), expect.anything()));
    fireEvent.click(await screen.findByRole("row", { name: /Alex/ }));
    fireEvent.click(screen.getByLabelText("CONTENT SELLING customer control").querySelectorAll("button")[1]!);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/automation-controls/content-selling"), expect.objectContaining({ method: "PATCH", body: JSON.stringify({ value: true }) })));
    expect(screen.getAllByText("CONTENT SALES")).toHaveLength(2);
  });

  it("distinguishes customer configuration from a global ceiling", async () => {
    const blocked = customerState({ contentSellingEnabled: true }, { contentSellingEnabled: false });
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("/api/v1/relationships?") ? response({ items: [person], nextCursor: null, hasMore: false }) : response(blocked));
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    expect(await screen.findByText("Blocked globally")).toBeInTheDocument();
    expect(screen.getByText("CHAT ONLY")).toBeInTheDocument();
  });

  it("deep-links to a selected customer and back to the same Chat conversation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("/api/v1/relationships?") ? response({ items: [person], nextCursor: null, hasMore: false }) : response(customerState()));
    function Location() { return <output data-testid="location">{useLocation().pathname}{useLocation().search}</output>; }
    render(<MemoryRouter initialEntries={[`/business/controls?tab=customers&relationship=${encodeURIComponent(person.personKey)}`]}><BusinessControlsPage/><Location/></MemoryRouter>);
    const link = await screen.findByRole("link", { name: /View Conversation/ });
    fireEvent.click(link);
    expect(screen.getByTestId("location")).toHaveTextContent(`/business/relationships?relationship=${encodeURIComponent(person.personKey)}`);
  });

  it("warns accurately before disabling selling around existing obligations", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => String(input).includes("/api/v1/relationships?") ? response({ items: [person], nextCursor: null, hasMore: false }) : response(customerState({ sessionSellingEnabled: true })));
    render(<MemoryRouter initialEntries={["/business/controls?tab=customers"]}><BusinessControlsPage/></MemoryRouter>);
    fireEvent.click(await screen.findByRole("row", { name: /Alex/ }));
    fireEvent.click(screen.getByLabelText("SESSION SELLING customer control").querySelectorAll("button")[0]!);
    expect(screen.getByRole("dialog")).toHaveTextContent("current purchased or active session is preserved");
    expect(screen.getByRole("dialog")).toHaveTextContent("existing presented offer may still settle");
  });

  it("derives every operator effective-mode label", () => {
    expect(effectiveMode(customerState({ avaChatEnabled: false }))).toBe("MANUAL");
    expect(effectiveMode(customerState())).toBe("CHAT ONLY");
    expect(effectiveMode(customerState({ contentSellingEnabled: true }))).toBe("CONTENT SALES");
    expect(effectiveMode(customerState({ sessionSellingEnabled: true }))).toBe("SESSION SALES");
    expect(effectiveMode(customerState({ contentSellingEnabled: true, sessionSellingEnabled: true }))).toBe("ALL SALES");
  });
});
