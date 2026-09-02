import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { IgCompetitorIntelligencePage } from "./IgCompetitorIntelligencePage";

const competitor = { id: "ig-1", username: "ava", followers: 12345, profileImageUrl: null, archivedAt: null };
const response = (body: unknown, ok = true) => Promise.resolve({ ok, json: () => Promise.resolve(body) } as Response);
const phoneStatus = { available: true, state: "CONNECTED", serial: "SERIAL", model: "SM-G781U1", manufacturer: "samsung", adb_available: true, scrcpy_available: true, mirror_available: true, mirror_running: false, message: null };

describe("IgCompetitorIntelligencePage", () => {
  beforeEach(() => vi.stubGlobal("fetch", vi.fn((url: string | URL | Request) => String(url).includes("/device/android/status") ? response(phoneStatus) : response({ items: [competitor] }))));
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it("renders the X-parity columns, formatted followers, and disabled scrape placeholder", async () => {
    render(<IgCompetitorIntelligencePage />);
    expect(await screen.findByText("12,345")).toBeInTheDocument();
    for (const label of ["Competitor", "Followers", "7D Growth", "30D Growth", "Last Active", "Posts 7D", "Engagement", "TG", "Last Scraped"]) expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Scrape" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Scrape" })).toBeDisabled();
    const openPhone = screen.getByRole("button", { name: "Open Phone" });
    expect(screen.getByText("Competitors").closest("header")).toContainElement(openPhone);
    expect(screen.getByLabelText("Search competitors").closest(".x-intelligence-toolbar")).not.toContainElement(openPhone);
  });

  it("creates from only username and followers", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((url) => String(url).includes("/device/android/status") ? response(phoneStatus) : String(url).endsWith("/competitors") && fetchMock.mock.calls.filter(([value]) => String(value).endsWith("/competitors")).length > 1 ? response(competitor) : response({ items: [] }));
    render(<IgCompetitorIntelligencePage />);
    await screen.findByText("No competitors tracked yet.");
    fireEvent.click(screen.getByRole("button", { name: /Add Competitor/ }));
    fireEvent.change(screen.getByLabelText("IG Username"), { target: { value: "@ava" } });
    expect(screen.queryByLabelText("Display Name")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Followers"), { target: { value: "12345" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Add Competitor" }).at(-1)!);
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/competitors") && init?.method === "POST")).toBe(true));
    const createCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/competitors") && init?.method === "POST");
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall![1]?.body))).toEqual({ username: "@ava", followers: 12345 });
  });

  it("updates followers and archives without invoking scrape", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation((url) => String(url).includes("/device/android/status") ? response(phoneStatus) : String(url).includes("/followers") ? response({ ...competitor, followers: 13000 }) : String(url).includes("/archive") ? response({ ...competitor, archivedAt: "2026-08-21T00:00:00Z" }) : response({ items: [competitor] }));
    vi.stubGlobal("confirm", vi.fn(() => true));
    render(<IgCompetitorIntelligencePage />);
    fireEvent.click(await screen.findByRole("button", { name: /Edit followers/ }));
    fireEvent.change(screen.getByLabelText("Followers"), { target: { value: "13000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Followers" }));
    await screen.findByText("13,000");
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    await screen.findByText("No competitors tracked yet.");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("scrape"))).toBe(false);
  });

  it("opens the connected phone without navigation and prevents clicks while pending", async () => {
    const fetchMock = vi.mocked(fetch);
    let finishMirror: ((value: Response) => void) | undefined;
    let running = false;
    fetchMock.mockImplementation((url) => {
      if (String(url).endsWith("/device/android/mirror")) return new Promise((resolve) => { finishMirror = resolve; });
      return String(url).includes("/device/android/status") ? response({ ...phoneStatus, mirror_running: running }) : response({ items: [competitor] });
    });
    render(<IgCompetitorIntelligencePage />);
    const button = await screen.findByRole("button", { name: "Open Phone" });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(screen.getByRole("button", { name: "Opening..." })).toBeDisabled();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/device/android/mirror"))).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Opening..." }));
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/device/android/mirror"))).toHaveLength(1);
    running = true;
    finishMirror!(await response({ result: "STARTED", serial: "SERIAL" }));
    await screen.findByRole("button", { name: "Sleep" });
  });

  it("sleeps through the same button and returns it to Open Phone", async () => {
    const fetchMock = vi.mocked(fetch); let running=true;
    fetchMock.mockImplementation((url) => {
      if(String(url).endsWith("/device/android/sleep")){running=false;return response({result:"SLEPT",serial:"SERIAL",mirror_closed:true});}
      return String(url).includes("/device/android/status")?response({...phoneStatus,mirror_running:running}):response({items:[competitor]});
    });
    render(<IgCompetitorIntelligencePage/>);
    fireEvent.click(await screen.findByRole("button",{name:"Sleep"}));
    await screen.findByRole("button",{name:"Open Phone"});
    expect(fetchMock.mock.calls.some(([url])=>String(url).endsWith("/device/android/sleep"))).toBe(true);
  });

  it("polls backend mirror state at a lightweight interval", async () => {
    const interval=vi.spyOn(window,"setInterval");
    vi.mocked(fetch).mockImplementation((url)=>String(url).includes("/device/android/status")?response({...phoneStatus,mirror_running:true}):response({items:[competitor]}));
    render(<IgCompetitorIntelligencePage/>);
    await screen.findByRole("button",{name:"Sleep"});
    expect(interval).toHaveBeenCalledWith(expect.any(Function),5000);
  });

  it("disables Open Phone and exposes the scrcpy diagnostic when mirroring is unavailable", async () => {
    vi.mocked(fetch).mockImplementation((url) => String(url).includes("/device/android/status") ? response({ ...phoneStatus, scrcpy_available: false, mirror_available: false, message: "scrcpy unavailable" }) : response({ items: [competitor] }));
    render(<IgCompetitorIntelligencePage />);
    const button = await screen.findByRole("button", { name: "Open Phone" });
    await waitFor(() => expect(button).toHaveAttribute("title", "scrcpy unavailable"));
    expect(button).toBeDisabled();
  });
});
