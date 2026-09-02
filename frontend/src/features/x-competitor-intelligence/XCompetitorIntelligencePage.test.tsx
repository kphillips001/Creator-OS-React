import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";

import {
  buildCollectedLeadClipboardText,
  formatGlobalRefresh,
  formatLastActive,
  formatLastScraped,
  formatLastRefreshDate,
  sortCompetitorPosts,
  sortCompetitors,
  writeCollectedLeadClipboardText,
  XCompetitorIntelligencePage,
} from "./XCompetitorIntelligencePage";
import type {
  XCompetitor,
  XCompetitorPost,
} from "../../infrastructure/api/xCompetitorIntelligenceApi";

const competitor = (
  overrides: Partial<XCompetitor> & Pick<XCompetitor, "id" | "username">,
): XCompetitor => ({
  xUserId: overrides.id,
  displayName: null,
  profileImageUrl: null,
  accountRole: "COMPETITOR",
  platform: "FANVUE",
  trackingEnabled: true,
  telegramPresence: "UNKNOWN",
  telegramUrl: null,
  telegramAudienceType: null,
  telegramCommentsAllowed: null,
  telegramJoined: null,
  telegramScraped: false,
  followersCount: null,
  createdAt: "2026-08-01T00:00:00Z",
  observedAt: null,
  lastActiveAt: null,
  posts7d: null,
  comments7d: 0,
  retweets7d: 0,
  quotes7d: 0,
  engagementRate: null,
  audienceCount: null,
  lastAudienceScrapedAt: null,
  lastAudienceScrapeStatus: null,
  lastAudienceRunId: null,
  growth7d: null,
  growth30d: null,
  refresh: {
    lastSuccessfulAt: null,
    nextRefreshAt: null,
    due: true,
  },
  ...overrides,
});
const post = (
  overrides: Partial<XCompetitorPost> &
    Pick<XCompetitorPost, "id" | "xTweetId">,
): XCompetitorPost => ({
  text: null,
  postedAt: "2026-08-16T10:00:00Z",
  language: null,
  conversationId: null,
  isQuote: false,
  hasMedia: false,
  mediaMetadata: [],
  viewCount: null,
  likeCount: null,
  replyCount: null,
  retweetCount: null,
  quoteCount: null,
  bookmarkCount: null,
  lastMetricObservedAt: null,
  ...overrides,
});
const writeText = vi.fn();

describe("XCompetitorIntelligencePage", () => {
  beforeEach(() => {
    writeText.mockReset();
    Reflect.deleteProperty(globalThis, "ClipboardItem");
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);
  });

  it("builds exact newline-delimited username-only clipboard text", () => {
    const value = buildCollectedLeadClipboardText([
      " alpha ",
      "@beta",
      null,
      " ",
      "gamma",
    ]);
    expect(value).toBe("alpha\nbeta\ngamma");
    expect(value).not.toBe("alpha beta gamma");
    expect(value).not.toBe("alpha,beta,gamma");
    expect(value).not.toContain("@");
    expect(value.split("\n")).toEqual(["alpha", "beta", "gamma"]);
  });

  it("publishes exact LF text/plain and a line-preserving Word-compatible representation", async () => {
    class TestClipboardItem {
      constructor(public readonly data: Record<string, Blob>) {}
    }
    const write = vi.fn();
    Object.defineProperty(globalThis, "ClipboardItem", {
      configurable: true,
      value: TestClipboardItem,
    });
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { write, writeText },
    });
    await writeCollectedLeadClipboardText("alpha\nbeta\ngamma");
    const item = (write.mock.calls[0]?.[0] as TestClipboardItem[])[0]!;
    const read = (blob: Blob) =>
      new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsText(blob);
      });
    expect(await read(item.data["text/plain"]!)).toBe("alpha\nbeta\ngamma");
    expect(await read(item.data["text/html"]!)).toBe(
      "<div>alpha</div><div>beta</div><div>gamma</div>",
    );
    expect(writeText).not.toHaveBeenCalled();
  });

  it("renders the competitor registry shell without fake data", async () => {
    render(<XCompetitorIntelligencePage />);
    expect(
      screen.getByRole("heading", { name: "X Competitor Intelligence" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("tablist", { name: "X intelligence sections" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Competitors" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Audience" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Insights" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add Competitor" }),
    ).toBeEnabled();
    await screen.findByText("No competitors tracked yet.");
    expect(screen.getByText("Leads Collected")).toBeInTheDocument();
    expect(screen.getByText("Unique · Deduplicated")).toBeInTheDocument();
    expect(screen.queryByText("Commenters")).not.toBeInTheDocument();
    expect(screen.queryByText("Retweeters")).not.toBeInTheDocument();
    expect(screen.queryByText("Quote Posters")).not.toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    const competitors = screen
      .getByRole("heading", { name: "Competitors" })
      .closest("section");
    expect(competitors).toContainElement(
      screen.getByRole("button", { name: "Browse Leads Collected" }),
    );
    expect(
      screen.queryByLabelText("Competitor summary"),
    ).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search competitors...")).toBeEnabled();
    expect(
      screen.queryByRole("combobox", { name: "Activity filter" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Tracking filter" }),
    ).not.toBeInTheDocument();
    const controls = screen.getByRole("group", {
      name: "Competitor table controls",
    });
    expect(
      screen.queryByLabelText("Global refresh freshness"),
    ).not.toBeInTheDocument();
    expect(controls).toContainElement(
      screen.getByPlaceholderText("Search competitors..."),
    );
    expect(
      screen.getByRole("heading", { name: "Competitors" }).parentElement
        ?.parentElement,
    ).toContainElement(
      screen.getByRole("button", { name: "Browse Leads Collected" }),
    );
    expect(
      within(controls).getByRole("button", { name: "Add Competitor" }),
    ).toBeInTheDocument();
    const actions = within(controls).getByRole("button", { name: "Download" }).parentElement!;
    expect(Array.from(actions.querySelectorAll("button")).map((button) => button.textContent?.trim())).toEqual([
      "Download", "Archived", "Add Competitor",
    ]);
    expect(
      within(controls).queryByRole("button", { name: "Refresh Profiles" }),
    ).not.toBeInTheDocument();
    expect(
      within(controls).queryByRole("button", { name: "Refresh Activity" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Sort competitors" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Followers" }),
    ).toHaveAttribute("aria-sort", "descending");
    for (const column of [
      "Competitor",
      "Followers",
      "7D Growth",
      "30D Growth",
      "Last Active",
      "Posts 7D",
      "Engagement",
      "TG",
      "Last Scraped",
      "Scrape",
    ]) {
      expect(
        screen.getByRole("columnheader", { name: column }),
      ).toBeInTheDocument();
    }
    const headers = screen
      .getAllByRole("columnheader")
      .map((header) => header.getAttribute("aria-label"));
    expect(headers.slice(-4)).toEqual([
      "Engagement",
      "TG",
      "Last Scraped",
      "Scrape",
    ]);
    expect(
      screen.queryByRole("columnheader", { name: "Audience" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Watchlist" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Sort by Audience" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sort by TG" }),
    ).toBeInTheDocument();
    for (const removed of ["24h", "Status", "Last Synced", "Actions"]) {
      expect(
        screen.queryByRole("columnheader", { name: removed }),
      ).not.toBeInTheDocument();
    }
    expect(screen.getByText("No competitors tracked yet.")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Add X competitors to begin building historical growth and audience intelligence.",
      ),
    ).toBeInTheDocument();
  });

  it("renders compact platform badges beside active competitor names while leaving the benchmark unbadged", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({ id: "fv", username: "fanvue", displayName: "A Very Long Fanvue Competitor Name", platform: "FANVUE" }),
          competitor({ id: "of", username: "onlyfans", displayName: "OnlyFans Competitor", platform: "ONLYFANS" }),
          competitor({ id: "other", username: "other", displayName: "Other Competitor", platform: "OTHER" }),
        ],
        benchmark: competitor({
          id: "ava",
          username: "ava",
          displayName: "Ava Blackthorne",
          accountRole: "OWN_ACCOUNT",
          platform: "FANVUE",
        }),
        metrics: { commenters: 0, retweeters: 0, quotePosters: 0, uniqueLeads: 0 },
      }),
    } as Response);

    render(<XCompetitorIntelligencePage />);

    const fanvueLine = (await screen.findByText("A Very Long Fanvue Competitor Name")).closest(
      ".x-intelligence-competitor__name-line",
    );
    expect(fanvueLine).not.toBeNull();
    expect(within(fanvueLine as HTMLElement).getByText("FV")).toHaveClass(
      "x-intelligence-platform-badge--fanvue",
    );
    expect(
      within(screen.getByText("OnlyFans Competitor").closest(".x-intelligence-competitor__name-line") as HTMLElement).getByText("OF"),
    ).toHaveClass("x-intelligence-platform-badge--onlyfans");
    expect(
      within(screen.getByText("Other Competitor").closest(".x-intelligence-competitor__name-line") as HTMLElement).getByText("OT"),
    ).toHaveClass("x-intelligence-platform-badge--other");
    expect(
      screen.getByRole("region", { name: "Your benchmark account" }).querySelector(
        ".x-intelligence-platform-badge",
      ),
    ).toBeNull();
  });

  it("downloads the backend CSV once and restores the control", async () => {
    let resolveBlob!: (blob: Blob) => void;
    const pendingBlob = new Promise<Blob>((resolve) => { resolveBlob = resolve; });
    vi.mocked(fetch)
      .mockResolvedValueOnce({ok:true,json:async()=>({items:[],metrics:{commenters:0,retweeters:0,quotePosters:0,uniqueLeads:1}})} as Response)
      .mockResolvedValueOnce({ok:true,headers:new Headers({"content-disposition":'attachment; filename="creator_os_x_leads_2026-08-30.csv"'}),blob:()=>pendingBlob} as Response);
    const createObjectURL=vi.fn(()=>"blob:test"),revokeObjectURL=vi.fn();
    Object.defineProperty(URL,"createObjectURL",{configurable:true,value:createObjectURL});
    Object.defineProperty(URL,"revokeObjectURL",{configurable:true,value:revokeObjectURL});
    const click=vi.spyOn(HTMLAnchorElement.prototype,"click").mockImplementation(()=>{});
    render(<XCompetitorIntelligencePage />);
    const button=await screen.findByRole("button",{name:"Download"});
    fireEvent.click(button);
    expect(await screen.findByRole("button",{name:"Downloading…"})).toBeDisabled();
    resolveBlob(new Blob(["x_user_id\r\n=\"42\"\r\n"],{type:"text/csv"}));
    await waitFor(()=>expect(screen.getByRole("button",{name:"Download"})).toBeEnabled());
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(String(vi.mocked(fetch).mock.calls[1]?.[0])).toContain("/audience/leads/export.csv");
    expect(click).toHaveBeenCalledTimes(1);expect(createObjectURL).toHaveBeenCalledTimes(1);expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");
  });

  it("renders the own account as a fixed benchmark without competitor-only actions", async () => {
    vi.mocked(fetch).mockResolvedValue({ok:true,json:async()=>({items:[competitor({id:"c1",username:"rival",followersCount:50})],benchmark:competitor({id:"own",username:"avablackthorne",displayName:"Ava Blackthorne",accountRole:"OWN_ACCOUNT",followersCount:100,posts7d:3,comments7d:12,retweets7d:4,quotes7d:1,refresh:{lastSuccessfulAt:"2026-08-19T12:00:00Z",nextRefreshAt:"2026-08-26T12:00:00Z",due:false}}),metrics:{commenters:0,retweeters:0,quotePosters:0,uniqueLeads:0}})} as Response);
    render(<XCompetitorIntelligencePage/>);
    const benchmark=await screen.findByRole("region",{name:"Your benchmark account"});
    expect(benchmark).toHaveTextContent("Ava Blackthorne");
    expect(benchmark).toHaveTextContent("12 comments · 4 retweets · 1 quotes");
    expect(within(benchmark).getByText("Last Refresh Aug 19")).toHaveClass("x-benchmark-account__refresh-position");
    expect(within(benchmark).getByText("12 comments · 4 retweets · 1 quotes")).not.toHaveTextContent("Last Refresh");
    expect(within(benchmark).getByText("7D Growth").parentElement).toHaveTextContent("7D Growth—");
    expect(within(benchmark).getByText("30D Growth").parentElement).toHaveTextContent("30D Growth—");
    fireEvent.click(within(benchmark).getByText("Ava Blackthorne"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("button",{name:"Archive"})).not.toBeInTheDocument();
    expect(screen.queryByRole("heading",{name:"Telegram"})).not.toBeInTheDocument();
  });

  it("keeps right-side headers distinct and shares one non-wrapping grid geometry with rows", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [competitor({ id: "c1", username: "AshleyPerkins89", displayName: "Ashley Perkins", followersCount: 118582, telegramPresence: "YES" })],
        metrics: { commenters: 0, retweeters: 0, quotePosters: 0, uniqueLeads: 0 },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("@AshleyPerkins89");

    const telegram = screen.getByRole("columnheader", { name: "TG" });
    const lastScraped = screen.getByRole("columnheader", { name: "Last Scraped" });
    const scrape = screen.getByRole("columnheader", { name: "Scrape" });
    expect(telegram).not.toBe(lastScraped);
    expect(lastScraped).not.toBe(scrape);
    const header = telegram.parentElement as HTMLElement;
    const bodyRow = screen.getAllByRole("row")[1] as HTMLElement;
    expect(header).toHaveClass("x-intelligence-table__header");
    expect(bodyRow).toHaveClass("x-intelligence-table__row");
    const css = readFileSync(
      "src/features/x-competitor-intelligence/x-competitor-intelligence.css",
      "utf8",
    );
    expect(css).toContain("white-space: nowrap;");
    expect(css).toContain("min-width: 930px;");
    expect(css).toContain('.x-intelligence-table__row > [role="cell"]');
    expect(css.match(/grid-template-columns: var\(--x-intelligence-table-columns\);/g)).toHaveLength(2);
    const cells = within(bodyRow).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("Ashley Perkins");
    expect(cells[1]).toHaveTextContent("118,582");
    expect(cells[0]).not.toBe(cells[1]);
    expect(screen.getByRole("button", { name: "Sort by TG" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sort by Last Scraped" })).toBeInTheDocument();
    expect(within(bodyRow).getByRole("button", { name: "Scrape" })).toBeInTheDocument();
  });

  it("renders positive, true-zero, and unavailable seven-day engagement totals distinctly", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "engaged",
            username: "engaged",
            comments7d: 84,
            retweets7d: 37,
            quotes7d: 12,
            refresh: {
              lastSuccessfulAt: "2026-08-24T12:00:00Z",
              nextRefreshAt: "2026-08-31T12:00:00Z",
              due: false,
            },
          }),
          competitor({ id: "quiet", username: "quiet", posts7d: 1 }),
          competitor({
            id: "unavailable",
            username: "unavailable",
            posts7d: 0,
            comments7d: null,
            retweets7d: null,
            quotes7d: null,
          }),
        ],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);

    render(<XCompetitorIntelligencePage />);

    expect(
      await screen.findByLabelText(
        "Last 7 days: 84 comments, 37 retweets, 12 quotes",
      ),
    ).toHaveTextContent(
      "84 comments · 37 retweets · 12 quotes",
    );
    expect(
      screen.getByLabelText(
        "Last 7 days: 84 comments, 37 retweets, 12 quotes",
      ),
    ).toHaveTextContent("84 comments · 37 retweets · 12 quotes");
    expect(
      screen.getByLabelText(
        "Last 7 days: 84 comments, 37 retweets, 12 quotes",
      ),
    ).not.toHaveTextContent("Last Refresh");
    expect(screen.getByText("Last Refresh Aug 24")).toHaveClass(
      "x-intelligence-refresh-metadata",
    );
    expect(
      screen.getByLabelText(
        "Last 7 days: 0 comments, 0 retweets, 0 quotes",
      ),
    ).toHaveTextContent(
      "0 comments · 0 retweets · 0 quotes",
    );
    expect(
      screen.getByLabelText(
        "Last 7 days: — comments, — retweets, — quotes",
      ),
    ).toHaveTextContent(
      "— comments · — retweets · — quotes",
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("formats canonical successful refresh dates without a year or time", () => {
    expect(formatLastRefreshDate("2026-08-24T12:00:00Z")).toBe("Last Refresh Aug 24");
    expect(formatLastRefreshDate(null)).toBeNull();
    expect(formatLastRefreshDate("not-a-date")).toBeNull();
  });

  it("sorts the complete competitor registry from the inline engagement metrics", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "alpha",
            username: "alpha",
            comments7d: 20,
            retweets7d: 90,
            quotes7d: 2,
          }),
          competitor({
            id: "beta",
            username: "beta",
            comments7d: 80,
            retweets7d: 10,
            quotes7d: 7,
          }),
          competitor({
            id: "gamma",
            username: "gamma",
            comments7d: 40,
            retweets7d: 30,
            quotes7d: 4,
          }),
        ],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("@alpha");
    const rowOrder = () =>
      screen
        .getAllByRole("row")
        .slice(1)
        .map((row) => row.querySelector(".x-intelligence-competitor strong")?.textContent);

    fireEvent.click(screen.getAllByRole("button", { name: "Sort by comments" })[0]!);
    expect(rowOrder()).toEqual(["beta", "gamma", "alpha"]);
    expect(
      screen.getAllByRole("button", {
        name: "Sort by comments, currently descending",
      })[0],
    ).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(
      screen.getAllByRole("button", {
        name: "Sort by comments, currently descending",
      })[0]!,
    );
    expect(rowOrder()).toEqual(["alpha", "gamma", "beta"]);
    expect(
      screen.getAllByRole("button", {
        name: "Sort by comments, currently ascending",
      })[0],
    ).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getAllByRole("button", { name: "Sort by retweets" })[0]!);
    expect(rowOrder()).toEqual(["alpha", "gamma", "beta"]);
    expect(
      screen.getAllByRole("button", {
        name: "Sort by retweets, currently descending",
      })[0],
    ).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Sort by quotes" })[0]!);
    expect(rowOrder()).toEqual(["beta", "gamma", "alpha"]);
    fireEvent.click(
      screen.getAllByRole("button", {
        name: "Sort by quotes, currently descending",
      })[0]!,
    );
    expect(rowOrder()).toEqual(["alpha", "gamma", "beta"]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not present a false empty competitor state when the dashboard request fails", async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error("read failed"));
    render(<XCompetitorIntelligencePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("read failed");
    expect(
      screen.queryByText("No competitors tracked yet."),
    ).not.toBeInTheDocument();
  });

  it("links Telegram status to exact canonical public and private URLs without opening competitor detail", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "public",
            username: "public",
            telegramPresence: "YES",
            telegramUrl: "https://t.me/public_channel",
          }),
          competitor({
            id: "private",
            username: "private",
            telegramPresence: "YES",
            telegramUrl: "https://t.me/+8pzjrgbAegIxMDA0",
          }),
          competitor({ id: "yes", username: "yes", telegramPresence: "YES" }),
          competitor({ id: "no", username: "no", telegramPresence: "NO" }),
          competitor({
            id: "unknown",
            username: "unknown",
            telegramPresence: "UNKNOWN",
            telegramAudienceType: "MEMBERS",
            telegramCommentsAllowed: true,
            telegramJoined: true,
          }),
        ],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("@yes");
    expect(screen.getAllByLabelText("Telegram: Yes")).toHaveLength(3);
    expect(screen.getAllByLabelText("Telegram: No or unknown")).toHaveLength(2);
    const publicLink = screen.getByRole("link", { name: "Open Telegram for @public" });
    const privateLink = screen.getByRole("link", { name: "Open Telegram for @private" });
    expect(publicLink).toHaveAttribute("href", "https://t.me/public_channel");
    expect(privateLink).toHaveAttribute("href", "https://t.me/+8pzjrgbAegIxMDA0");
    for (const link of [publicLink, privateLink]) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    publicLink.addEventListener("click", (event) => event.preventDefault());
    fireEvent.click(publicLink);
    expect(screen.queryByRole("dialog", { name: /public/i })).not.toBeInTheDocument();
    const yesWithoutUrlRow = screen.getByText("@yes").closest('[role="row"]');
    expect(
      within(yesWithoutUrlRow as HTMLElement).queryByRole("link", {
        name: /Open Telegram/,
      }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("Telegram: Yes")[2]).toHaveTextContent("✓");
    for (const cell of screen.getAllByLabelText("Telegram: No or unknown"))
      expect(cell).toHaveTextContent("—");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("links the detail username to the normalized persisted X profile", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "amanda",
            username: "@amandajuliiia",
            displayName: "Amanda Starlily",
          }),
        ],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    fireEvent.click(
      await screen.findByRole("button", { name: /Amanda Starlily/ }),
    );
    const detail = screen.getByRole("dialog", { name: "Amanda Starlily" });
    const profile = within(detail).getByRole("link", {
      name: "@amandajuliiia",
    });
    expect(profile).toHaveAttribute("href", "https://x.com/amandajuliiia");
    expect(profile).toHaveAttribute("target", "_blank");
    expect(profile).toHaveAttribute("rel", "noopener noreferrer");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("separates the registry display-name detail action from the X username link", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "evelyn",
            username: "@EvieDecker1686",
            displayName: "Evelyn Decker",
          }),
        ],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);

    const username = await screen.findByRole("link", {
      name: "@EvieDecker1686",
    });
    expect(username).toHaveAttribute(
      "href",
      "https://x.com/EvieDecker1686",
    );
    expect(username).toHaveAttribute("target", "_blank");
    expect(username).toHaveAttribute("rel", "noopener noreferrer");
    fireEvent.click(username);
    expect(
      screen.queryByRole("dialog", { name: "Evelyn Decker" }),
    ).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "Evelyn Decker" }),
    );
    expect(
      screen.getByRole("dialog", { name: "Evelyn Decker" }),
    ).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("confirms Archive, removes the active row, and restores the same archived competitor", async () => {
    const fetchMock=vi.mocked(fetch);const item=competitor({id:"c-archive",username:"maya",displayName:"MAYA",followersCount:123,telegramPresence:"YES",telegramUrl:"https://t.me/+preserved"});
    fetchMock
      .mockResolvedValueOnce({ok:true,json:async()=>({items:[item],metrics:{commenters:0,retweeters:0,quotePosters:0,uniqueLeads:0}})} as Response)
      .mockResolvedValueOnce({ok:true,json:async()=>({id:item.id,archivedAt:"2026-08-18T17:00:00Z"})} as Response)
      .mockResolvedValueOnce({ok:true,json:async()=>({items:[{id:item.id,xUserId:item.xUserId,username:item.username,displayName:item.displayName,profileImageUrl:null,followersCount:123,archivedAt:"2026-08-18T17:00:00Z"}]})} as Response)
      .mockResolvedValueOnce({ok:true,json:async()=>({id:item.id,archivedAt:null})} as Response)
      .mockResolvedValueOnce({ok:true,json:async()=>({items:[item],metrics:{commenters:0,retweeters:0,quotePosters:0,uniqueLeads:0}})} as Response);
    render(<XCompetitorIntelligencePage/>);fireEvent.click(await screen.findByRole("button",{name:/MAYA/}));
    fireEvent.click(screen.getByRole("button",{name:"Archive"}));
    let confirm=screen.getByRole("dialog",{name:"Archive MAYA?"});
    expect(confirm).toHaveTextContent("will no longer be automatically refreshed or scraped");
    fireEvent.click(within(confirm).getByRole("button",{name:"Cancel"}));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button",{name:"Archive"}));confirm=screen.getByRole("dialog",{name:"Archive MAYA?"});
    fireEvent.click(within(confirm).getByRole("button",{name:"Archive"}));
    await waitFor(()=>expect(screen.queryByText("@maya")).not.toBeInTheDocument());
    expect(fetchMock.mock.calls[1]?.[0]).toContain("/competitors/c-archive/archive");
    fireEvent.click(screen.getByRole("button",{name:"View Archived Competitors"}));
    const archived=await screen.findByRole("dialog",{name:"Archived Competitors"});
    expect(archived).toHaveTextContent("123 followers");expect(archived).toHaveTextContent("@maya");
    expect(within(archived).getByText("FV")).toHaveClass("x-intelligence-platform-badge--fanvue");
    fireEvent.click(within(archived).getByRole("button",{name:"Restore"}));
    await screen.findByText("@maya");
    expect(fetchMock.mock.calls[3]?.[0]).toContain("/competitors/c-archive/restore");
    expect(within(archived).queryByText("@maya")).not.toBeInTheDocument();
  });

  it("disables search only until the initial canonical competitor read completes", async () => {
    let resolveDashboard: (value: Response) => void = () => {};
    vi.mocked(fetch).mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveDashboard = resolve;
        }),
    );
    render(<XCompetitorIntelligencePage />);
    const search = screen.getByRole("searchbox", { name: "Search" });
    expect(search).toBeDisabled();
    resolveDashboard({
      ok: true,
      json: async () => ({
        items: [competitor({ id: "1", username: "ava" })],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);
    await screen.findByText("@ava");
    expect(search).toBeEnabled();
  });

  it("searches loaded competitors locally by normalized username and display name without requests", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "1",
            username: "BiaAzhelia",
            displayName: "Bia Zhelia",
            followersCount: 10,
          }),
          competitor({
            id: "2",
            username: "other",
            displayName: "Different Creator",
            followersCount: 20,
          }),
        ],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    const search = await screen.findByRole("searchbox", { name: "Search" });
    expect(search).toBeEnabled();
    for (const query of [
      "biaazhelia",
      "BIAAZHELIA",
      "  @biaazhelia  ",
      "Zhelia",
    ]) {
      fireEvent.change(search, { target: { value: query } });
      expect(screen.getByText("Bia Zhelia")).toBeInTheDocument();
      expect(screen.queryByText("Different Creator")).not.toBeInTheDocument();
    }
    fireEvent.change(search, { target: { value: "not tracked" } });
    expect(screen.getByText("No matching competitors.")).toBeInTheDocument();
    expect(
      screen.queryByText("No competitors tracked yet."),
    ).not.toBeInTheDocument();
    fireEvent.change(search, { target: { value: "" } });
    expect(screen.getByText("Bia Zhelia")).toBeInTheDocument();
    expect(screen.getByText("Different Creator")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.skip("obsolete separate profile and activity dashboard refresh controls", async () => {
    const fetchMock = vi.mocked(fetch);
    let resolveProfile: (value: Response) => void = () => {};
    let resolveActivity: (value: Response) => void = () => {};
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "alpha",
              displayName: "Alpha",
              followersCount: 1,
            }),
            competitor({
              id: "2",
              username: "zeta",
              displayName: "Zeta",
              followersCount: 2,
            }),
          ],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 0,
          },
        }),
      } as Response)
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveProfile = resolve;
          }),
      )
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "alpha",
              displayName: "Alpha",
              followersCount: 1,
            }),
            competitor({
              id: "2",
              username: "zeta",
              displayName: "Zeta",
              followersCount: 2,
            }),
          ],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 0,
          },
        }),
      } as Response)
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveActivity = resolve;
          }),
      )
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "alpha",
              displayName: "Alpha",
              followersCount: 1,
            }),
            competitor({
              id: "2",
              username: "zeta",
              displayName: "Zeta",
              followersCount: 2,
            }),
          ],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 0,
          },
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    const search = await screen.findByRole("searchbox", { name: "Search" });
    fireEvent.click(screen.getByRole("button", { name: "Sort by Competitor" }));
    fireEvent.click(screen.getByRole("button", { name: "Refresh Profiles" }));
    expect(search).toBeEnabled();
    fireEvent.change(search, { target: { value: "alpha" } });
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    resolveProfile({
      ok: true,
      json: async () => ({
        considered: 2,
        refreshed: 2,
        failed: 0,
        results: [],
      }),
    } as Response);
    await screen.findByText(/2 profiles refreshed/);
    expect(
      screen.getByRole("columnheader", { name: "Competitor" }),
    ).toHaveAttribute("aria-sort", "ascending");
    fireEvent.click(screen.getByRole("button", { name: "Refresh Activity" }));
    expect(search).toBeEnabled();
    resolveActivity({
      ok: true,
      json: async () => ({
        considered: 2,
        refreshed: 2,
        unchanged: 0,
        noActivity: 0,
        failed: 0,
        results: [],
      }),
    } as Response);
    await screen.findByText(/2 refreshed/);
    expect(search).toHaveValue("alpha");
    expect(
      screen.getByRole("columnheader", { name: "Competitor" }),
    ).toHaveAttribute("aria-sort", "ascending");
  });

  it("sorts canonical competitor values in every supported mode with deterministic null handling", () => {
    const items = [
      competitor({
        id: "3",
        username: "zulu",
        displayName: "Alex",
        followersCount: null,
        posts7d: null,
        comments7d: 8,
        retweets7d: 1,
        quotes7d: 4,
        createdAt: "2026-08-12T00:00:00Z",
      }),
      competitor({
        id: "2",
        username: "bravo",
        displayName: "Alex",
        followersCount: 20,
        posts7d: 0,
        comments7d: 2,
        retweets7d: 9,
        quotes7d: 3,
        createdAt: "2026-08-10T00:00:00Z",
      }),
      competitor({
        id: "1",
        username: "alpha",
        displayName: "Zoe",
        followersCount: 100,
        posts7d: 5,
        comments7d: 12,
        retweets7d: 4,
        quotes7d: 1,
        createdAt: "2026-08-11T00:00:00Z",
      }),
      competitor({
        id: "4",
        username: "charlie",
        displayName: null,
        followersCount: 20,
        posts7d: 2,
        comments7d: 2,
        retweets7d: 3,
        quotes7d: 7,
        createdAt: "2026-08-13T00:00:00Z",
      }),
    ];
    const usernames = (mode: Parameters<typeof sortCompetitors>[1]) =>
      sortCompetitors(items, mode).map((item) => item.username);
    expect(usernames("followers-desc")).toEqual([
      "alpha",
      "bravo",
      "charlie",
      "zulu",
    ]);
    expect(usernames("followers-asc")).toEqual([
      "bravo",
      "charlie",
      "alpha",
      "zulu",
    ]);
    expect(usernames("name-asc")).toEqual([
      "bravo",
      "zulu",
      "charlie",
      "alpha",
    ]);
    expect(usernames("name-desc")).toEqual([
      "alpha",
      "charlie",
      "zulu",
      "bravo",
    ]);
    expect(usernames("posts-desc")).toEqual([
      "alpha",
      "charlie",
      "bravo",
      "zulu",
    ]);
    expect(usernames("posts-asc")).toEqual([
      "bravo",
      "charlie",
      "alpha",
      "zulu",
    ]);
    expect(usernames("comments-desc")).toEqual([
      "alpha",
      "zulu",
      "bravo",
      "charlie",
    ]);
    expect(usernames("comments-asc")).toEqual([
      "bravo",
      "charlie",
      "zulu",
      "alpha",
    ]);
    expect(usernames("retweets-desc")).toEqual([
      "bravo",
      "alpha",
      "charlie",
      "zulu",
    ]);
    expect(usernames("retweets-asc")).toEqual([
      "zulu",
      "charlie",
      "alpha",
      "bravo",
    ]);
    expect(usernames("quotes-desc")).toEqual([
      "charlie",
      "zulu",
      "bravo",
      "alpha",
    ]);
    expect(usernames("quotes-asc")).toEqual([
      "alpha",
      "bravo",
      "zulu",
      "charlie",
    ]);
  });

  it("formats and sorts Last Scraped from canonical timestamps with unknowns always last", () => {
    const now = new Date("2026-08-17T15:00:00Z");
    expect(formatLastScraped(null, now)).toBe("Never");
    expect(formatLastScraped("2026-08-17T13:42:00Z", now)).toBe("Today");
    expect(formatLastScraped("2026-08-16T13:42:00Z", now)).toBe("Yesterday");
    const items = [
      competitor({ id: "never", username: "never" }),
      competitor({
        id: "old",
        username: "old",
        lastAudienceScrapedAt: "2026-08-08T10:00:00Z",
        lastAudienceScrapeStatus: "SUCCEEDED",
      }),
      competitor({
        id: "new",
        username: "new",
        lastAudienceScrapedAt: "2026-08-15T10:00:00Z",
        lastAudienceScrapeStatus: "PARTIAL",
      }),
    ];
    expect(
      sortCompetitors(items, "last-scraped-desc").map((item) => item.id),
    ).toEqual(["new", "old", "never"]);
    expect(
      sortCompetitors(items, "last-scraped-asc").map((item) => item.id),
    ).toEqual(["old", "new", "never"]);
  });

  it("sorts Telegram only from canonical presence with deterministic no and legacy ties", () => {
    const items = [
      competitor({
        id: "no",
        username: "bravo-no",
        telegramPresence: "NO",
        telegramUrl: "https://t.me/looks_present",
        telegramAudienceType: "SUBSCRIBERS",
        telegramJoined: true,
        telegramScraped: true,
        lastAudienceScrapedAt: "2026-08-20T12:00:00Z",
      }),
      competitor({
        id: "yes-zulu",
        username: "zulu-yes",
        telegramPresence: "YES",
        telegramUrl: null,
        telegramAudienceType: null,
        telegramJoined: false,
        telegramScraped: false,
        lastAudienceScrapedAt: null,
      }),
      competitor({
        id: "legacy",
        username: "charlie-legacy",
        telegramPresence: null as unknown as XCompetitor["telegramPresence"],
      }),
      competitor({
        id: "unknown",
        username: "delta-unknown",
        telegramPresence: "UNKNOWN",
      }),
      competitor({
        id: "yes-alpha",
        username: "alpha-yes",
        telegramPresence: "YES",
      }),
    ];

    expect(sortCompetitors(items, "telegram-desc").map((item) => item.id)).toEqual([
      "yes-alpha",
      "yes-zulu",
      "no",
      "legacy",
      "unknown",
    ]);
    expect(sortCompetitors(items, "telegram-asc").map((item) => item.id)).toEqual([
      "no",
      "legacy",
      "unknown",
      "yes-alpha",
      "yes-zulu",
    ]);
  });

  it("formats global freshness as Today, Yesterday, older date, and Never", () => {
    const now = new Date("2026-08-17T15:00:00Z");
    expect(formatGlobalRefresh(null, now)).toBe("Never");
    expect(formatGlobalRefresh("2026-08-17T13:42:00Z", now)).toBe(
      "Today, 8:42 AM",
    );
    expect(formatGlobalRefresh("2026-08-16T13:42:00Z", now)).toBe(
      "Yesterday, 8:42 AM",
    );
    expect(formatGlobalRefresh("2026-08-15T20:14:00Z", now)).toBe(
      "Aug 15, 3:14 PM",
    );
  });

  it("renders persisted global refresh freshness independently of competitor timestamps without provider calls", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "1",
            username: "ava",
            observedAt: "2026-08-17T14:59:00Z",
            lastActiveAt: "2026-08-17T14:59:00Z",
          }),
        ],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
        globalRefreshes: {
          profiles: { completedAt: "2026-08-15T20:14:00Z", status: "PARTIAL" },
          activity: { completedAt: "2026-08-14T20:14:00Z", status: "FAILED" },
        },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    expect(
      screen.queryByLabelText("Global refresh freshness"),
    ).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sorts Last Active by canonical timestamps with missing values last and deterministic ties", () => {
    const items = [
      competitor({
        id: "4",
        username: "missing",
        displayName: "Missing",
        lastActiveAt: null,
      }),
      competitor({
        id: "3",
        username: "beta",
        displayName: "Same",
        lastActiveAt: "2026-08-15T10:00:00Z",
      }),
      competitor({
        id: "2",
        username: "alpha",
        displayName: "Same",
        lastActiveAt: "2026-08-15T10:00:00Z",
      }),
      competitor({
        id: "1",
        username: "old",
        displayName: "Old",
        lastActiveAt: "2026-05-04T10:00:00Z",
      }),
      competitor({
        id: "5",
        username: "today",
        displayName: "Today",
        lastActiveAt: "2026-08-16T10:00:00Z",
      }),
    ];
    expect(
      sortCompetitors(items, "last-active-desc").map((item) => item.username),
    ).toEqual(["today", "alpha", "beta", "old", "missing"]);
    expect(
      sortCompetitors(items, "last-active-asc").map((item) => item.username),
    ).toEqual(["old", "alpha", "beta", "today", "missing"]);
  });

  it("formats canonical Last Active timestamps without substituting sync activity", () => {
    const now = new Date("2026-08-16T18:00:00");
    expect(formatLastActive("2026-08-16T01:00:00", now)).toBe("Today");
    expect(formatLastActive("2026-08-15T01:00:00", now)).toBe("Yesterday");
    expect(formatLastActive("2026-08-14T01:00:00", now)).toBe("2d ago");
    expect(formatLastActive("2026-06-01T01:00:00", now)).toBe("Jun 1");
    expect(formatLastActive(null, now)).toBe("—");
  });

  it("sorts persisted posts locally by newest and each canonical numeric metric with missing values last", () => {
    const posts = [
      post({
        id: "1",
        xTweetId: "old",
        postedAt: "2026-08-14T10:00:00Z",
        viewCount: 100,
        likeCount: 9,
        replyCount: 1,
        retweetCount: 4,
        quoteCount: 2,
      }),
      post({
        id: "2",
        xTweetId: "new",
        postedAt: "2026-08-16T10:00:00Z",
        viewCount: 50,
        likeCount: 20,
        replyCount: 8,
        retweetCount: 3,
        quoteCount: 5,
      }),
      post({ id: "3", xTweetId: "missing", postedAt: "2026-08-15T10:00:00Z" }),
    ];
    const ids = (mode: Parameters<typeof sortCompetitorPosts>[1]) =>
      sortCompetitorPosts(posts, mode).map((item) => item.xTweetId);
    expect(ids("newest")).toEqual(["new", "missing", "old"]);
    expect(ids("views")).toEqual(["old", "new", "missing"]);
    expect(ids("likes")).toEqual(["new", "old", "missing"]);
    expect(ids("comments")).toEqual(["new", "old", "missing"]);
    expect(ids("retweets")).toEqual(["old", "new", "missing"]);
    expect(ids("quotes")).toEqual(["new", "old", "missing"]);
  });

  it("sorts from accessible headers, toggles directions, keeps unknowns last, and makes no extra request", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "1",
            username: "large",
            displayName: "Zulu",
            followersCount: 100,
            lastActiveAt: "2026-08-15T10:00:00Z",
            posts7d: 0,
            engagementRate: 1,
            growth7d: {
              raw: -2,
              percent: -2,
              baselineObservedAt: "2026-08-09T00:00:00Z",
              currentObservedAt: "2026-08-16T00:00:00Z",
            },
            growth30d: {
              raw: 0,
              percent: 0,
              baselineObservedAt: "2026-07-17T00:00:00Z",
              currentObservedAt: "2026-08-16T00:00:00Z",
            },
          }),
          competitor({
            id: "2",
            username: "small",
            displayName: "Alpha",
            followersCount: 9,
            lastActiveAt: "2026-08-16T10:00:00Z",
            posts7d: 4,
            engagementRate: 5,
            growth7d: {
              raw: 2,
              percent: 20,
              baselineObservedAt: "2026-08-09T00:00:00Z",
              currentObservedAt: "2026-08-16T00:00:00Z",
            },
            growth30d: {
              raw: 1,
              percent: 10,
              baselineObservedAt: "2026-07-17T00:00:00Z",
              currentObservedAt: "2026-08-16T00:00:00Z",
            },
          }),
          competitor({
            id: "3",
            username: "unknown",
            displayName: "Missing",
            followersCount: null,
            lastActiveAt: null,
            posts7d: null,
            engagementRate: null,
          }),
        ],
        metrics: {
          tracked: 3,
          totalFollowers: 109,
          active: null,
          strongEngagement: null,
        },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Zulu");
    const first = () => screen.getAllByRole("row")[1];
    expect(first()).toHaveTextContent("Zulu");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Sort by Followers, currently descending/,
      }),
    );
    expect(first()).toHaveTextContent("Alpha");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Competitor" }));
    expect(first()).toHaveTextContent("Alpha");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Sort by Competitor, currently ascending/,
      }),
    );
    expect(first()).toHaveTextContent("Zulu");
    fireEvent.click(
      screen.getByRole("button", { name: "Sort by Last Active" }),
    );
    expect(first()).toHaveTextContent("Alpha");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Sort by Last Active, currently descending/,
      }),
    );
    expect(first()).toHaveTextContent("Zulu");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Posts 7D" }));
    expect(first()).toHaveTextContent("Alpha");
    expect(screen.getAllByRole("row")[2]).toHaveTextContent("0");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Sort by Posts 7D, currently descending/,
      }),
    );
    expect(first()).toHaveTextContent("Zulu");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    fireEvent.click(screen.getByRole("button", { name: "Sort by Engagement" }));
    expect(first()).toHaveTextContent("Alpha");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Sort by Engagement, currently descending/,
      }),
    );
    expect(first()).toHaveTextContent("Zulu");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    fireEvent.click(screen.getByRole("button", { name: "Sort by 7D Growth" }));
    expect(first()).toHaveTextContent("Alpha");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Sort by 7D Growth, currently descending/,
      }),
    );
    expect(first()).toHaveTextContent("Zulu");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    fireEvent.click(screen.getByRole("button", { name: "Sort by 30D Growth" }));
    expect(first()).toHaveTextContent("Alpha");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Sort by 30D Growth, currently descending/,
      }),
    );
    expect(first()).toHaveTextContent("Zulu");
    expect(screen.getAllByRole("row")[3]).toHaveTextContent("Missing");
    expect(
      screen.queryByRole("button", { name: /Sort by Watchlist/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "30D Growth" }),
    ).toHaveAttribute("aria-sort", "ascending");
    expect(
      screen.getByRole("columnheader", { name: "Engagement" }),
    ).not.toHaveAttribute("aria-sort");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("toggles Telegram sorting, composes with search, and switches to other headers", async () => {
    vi.mocked(fetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({ id: "no", username: "group-bravo", displayName: "Bravo", followersCount: 30, telegramPresence: "NO", telegramUrl: "https://t.me/not_a_proxy", telegramJoined: true, telegramAudienceType: "SUBSCRIBERS", telegramScraped: true }),
          competitor({ id: "yes-zulu", username: "group-zulu", displayName: "Zulu", followersCount: 20, telegramPresence: "YES" }),
          competitor({ id: "unknown", username: "group-charlie", displayName: "Charlie", followersCount: 10, telegramPresence: "UNKNOWN" }),
          competitor({ id: "yes-alpha", username: "group-alpha", displayName: "Alpha", followersCount: 40, telegramPresence: "YES" }),
        ],
        metrics: { commenters: 0, retweeters: 0, quotePosters: 0, uniqueLeads: 0 },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Alpha");
    const rowNames = () => screen.getAllByRole("row").slice(1).map((row) => row.textContent);

    expect(rowNames()[0]).toContain("Alpha");
    fireEvent.click(screen.getByRole("button", { name: "Sort by TG" }));
    expect(rowNames().map((row) => row?.match(/Alpha|Bravo|Charlie|Zulu/)?.[0])).toEqual([
      "Alpha",
      "Zulu",
      "Bravo",
      "Charlie",
    ]);
    expect(screen.getByRole("columnheader", { name: "TG" })).toHaveAttribute("aria-sort", "descending");

    fireEvent.click(screen.getByRole("button", { name: /Sort by TG, currently descending/ }));
    expect(rowNames().map((row) => row?.match(/Alpha|Bravo|Charlie|Zulu/)?.[0])).toEqual([
      "Bravo",
      "Charlie",
      "Alpha",
      "Zulu",
    ]);
    expect(screen.getByRole("columnheader", { name: "TG" })).toHaveAttribute("aria-sort", "ascending");

    fireEvent.change(screen.getByPlaceholderText("Search competitors..."), { target: { value: "group-a" } });
    expect(rowNames()).toHaveLength(1);
    expect(rowNames()[0]).toContain("Alpha");
    fireEvent.change(screen.getByPlaceholderText("Search competitors..."), { target: { value: "" } });

    fireEvent.click(screen.getByRole("button", { name: "Sort by Followers" }));
    expect(screen.getByRole("columnheader", { name: "Followers" })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getByRole("columnheader", { name: "TG" })).not.toHaveAttribute("aria-sort");
    fireEvent.click(screen.getByRole("button", { name: "Sort by TG" }));
    expect(screen.getByRole("columnheader", { name: "TG" })).toHaveAttribute("aria-sort", "descending");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.skip("obsolete separate Activity dashboard refresh control", async () => {
    const fetchMock = vi.mocked(fetch);
    let resolveRefresh: (value: Response) => void = () => {};
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "ava",
              displayName: "Ava",
              followersCount: 10,
            }),
          ],
          metrics: {
            tracked: 1,
            totalFollowers: 10,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response)
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveRefresh = resolve;
          }),
      )
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "ava",
              displayName: "Ava",
              followersCount: 10,
              lastActiveAt: new Date().toISOString(),
            }),
          ],
          metrics: {
            tracked: 1,
            totalFollowers: 10,
            active: null,
            strongEngagement: null,
          },
          globalRefreshes: {
            profiles: null,
            activity: {
              completedAt: new Date().toISOString(),
              status: "SUCCEEDED",
            },
          },
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Ava");
    fireEvent.click(screen.getByRole("button", { name: "Refresh Activity" }));
    expect(
      screen.getByRole("button", { name: "Refreshing Activity…" }),
    ).toBeDisabled();
    resolveRefresh({
      ok: true,
      json: async () => ({
        considered: 1,
        refreshed: 1,
        unchanged: 0,
        noActivity: 0,
        failed: 0,
        results: [],
      }),
    } as Response);
    expect(await screen.findByText("Today")).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Global refresh freshness"),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "1 refreshed · 0 unchanged · 0 no activity · 0 failed",
    );
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it.skip("obsolete separate Profile dashboard refresh control", async () => {
    const fetchMock = vi.mocked(fetch);
    let resolveRefresh: (value: Response) => void = () => {};
    const grown = {
      raw: 10,
      percent: 10,
      baselineObservedAt: "2026-08-09T00:00:00Z",
      currentObservedAt: "2026-08-16T00:00:00Z",
    };
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "ava",
              displayName: "Ava",
              followersCount: 100,
            }),
          ],
          metrics: {
            tracked: 1,
            totalFollowers: 100,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response)
      .mockImplementationOnce(
        () =>
          new Promise<Response>((resolve) => {
            resolveRefresh = resolve;
          }),
      )
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "ava",
              displayName: "Ava",
              followersCount: 110,
              growth7d: grown,
            }),
          ],
          metrics: {
            tracked: 1,
            totalFollowers: 110,
            active: null,
            strongEngagement: null,
          },
          globalRefreshes: {
            profiles: {
              completedAt: new Date().toISOString(),
              status: "SUCCEEDED",
            },
            activity: null,
          },
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Ava");
    fireEvent.click(screen.getByRole("button", { name: "Refresh Profiles" }));
    expect(
      screen.getByRole("button", { name: "Refreshing Profiles…" }),
    ).toBeDisabled();
    resolveRefresh({
      ok: true,
      json: async () => ({
        considered: 1,
        refreshed: 1,
        failed: 0,
        results: [],
      }),
    } as Response);
    expect(
      await screen.findByText("1 profiles refreshed · 0 failed"),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Global refresh freshness"),
    ).not.toBeInTheDocument();
    expect(screen.getByText("+10.0%")).toBeInTheDocument();
    expect(screen.getByText("+10")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("profiles/refresh");
  });

  it("distinguishes unknown from confirmed zero and opens persisted Posts 7D in the viewer", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "ava",
              displayName: "Ava",
              posts7d: 2,
            }),
            competitor({
              id: "2",
              username: "unknown",
              displayName: "Unknown",
              posts7d: null,
            }),
          ],
          metrics: {
            tracked: 2,
            totalFollowers: 0,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          competitor: {
            id: "1",
            username: "ava",
            displayName: "Ava",
            profileImageUrl: null,
          },
          count: 2,
          posts: [
            post({
              id: "p1",
              xTweetId: "111",
              text: "First",
              viewCount: 10,
              likeCount: 2,
              replyCount: 1,
              retweetCount: 0,
              quoteCount: null,
            }),
            post({
              id: "p2",
              xTweetId: "222",
              text: "Second",
              postedAt: "2026-08-15T10:00:00Z",
              viewCount: null,
              likeCount: 5,
            }),
          ],
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Ava");
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
    fireEvent.click(screen.getByRole("button", { name: "2" }));
    const dialog = await screen.findByRole("dialog", { name: "Ava" });
    expect(dialog).toHaveTextContent("Posts — Last 7 Days · 2 posts");
    expect(dialog).toHaveTextContent("Views");
    expect(dialog).toHaveTextContent("First");
    expect(screen.getByRole("button", { name: "Last 7 Days" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Archived" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(
      screen.getAllByRole("link", { name: "Open on X" })[0],
    ).toHaveAttribute("href", "https://x.com/ava/status/111");
    expect(
      screen.getAllByRole("link", { name: "Open on X" })[0],
    ).toHaveAttribute("target", "_blank");
    const sort = screen.getByRole("combobox", {
      name: "Sort competitor posts",
    });
    expect(sort).toHaveDisplayValue("Newest");
    expect(
      within(sort)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual([
      "Newest",
      "Most Views",
      "Most Likes",
      "Most Comments",
      "Most Retweets",
      "Most Quotes",
    ]);
    fireEvent.change(sort, { target: { value: "likes" } });
    expect(sort).toHaveDisplayValue("Most Likes");
    expect(
      within(dialog).getAllByText(/^(First|Second)$/)[0],
    ).toHaveTextContent("Second");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("loads Archived from persistence and refreshes only the selected post metrics", async () => {
    const archived = post({
      id: "archived",
      xTweetId: "900",
      text: "Archived post",
      postedAt: "2026-07-01T10:00:00Z",
      viewCount: 10,
      lastMetricObservedAt: "2026-07-09T10:00:00Z",
    });
    const updated = {
      ...archived,
      viewCount: 20,
      lastMetricObservedAt: "2026-08-16T10:00:00Z",
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "ava",
              displayName: "Ava",
              posts7d: 1,
            }),
          ],
          metrics: {
            tracked: 1,
            totalFollowers: 0,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          competitor: {
            id: "1",
            username: "ava",
            displayName: "Ava",
            profileImageUrl: null,
          },
          count: 1,
          posts: [post({ id: "recent", xTweetId: "1", text: "Recent" })],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          competitor: {
            id: "1",
            username: "ava",
            displayName: "Ava",
            profileImageUrl: null,
          },
          count: 1,
          page: 1,
          pageSize: 25,
          posts: [archived],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ post: updated, idempotentReplay: false }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Ava");
    fireEvent.click(screen.getByRole("button", { name: "1" }));
    await screen.findByText("Recent");
    fireEvent.click(screen.getByRole("button", { name: "Archived" }));
    expect(await screen.findByText("Archived post")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archived" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Last 7 Days" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByText(/Metrics last observed/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh Metrics" }));
    expect(await screen.findByText("Metrics refreshed")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain("posts-archived");
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain("refresh-metrics");
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("opens persisted Engagement analytics with objective sections and top posts without provider requests", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "1",
              username: "ava",
              displayName: "Ava",
              followersCount: 100,
              posts7d: 2,
              engagementRate: 2.5,
            }),
          ],
          metrics: {
            tracked: 1,
            totalFollowers: 100,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          competitor: {
            id: "1",
            username: "ava",
            displayName: "Ava",
            profileImageUrl: null,
          },
          sampleSize: 2,
          followersCount: 100,
          medianFollowerEngagementRate: 2.5,
          medianViewedEngagementRate: 5,
          medianReachRatio: 50,
          typical: {
            view: { median: 50, average: 60 },
            like: { median: 2, average: 2 },
            comments: { median: 1, average: 1 },
            retweet: { median: 0, average: 0 },
            quote: { median: 0, average: 0 },
            interactions: { median: 3, average: 3 },
          },
          mix: { like: 66.666, comments: 33.333, retweet: 0, quote: 0 },
          consistency: { minimum: 2, q1: 2, median: 2.5, q3: 3, maximum: 3 },
          topPosts: [
            {
              ...post({
                id: "p",
                xTweetId: "99",
                text: "Top post",
                viewCount: 50,
                likeCount: 2,
                replyCount: 1,
                retweetCount: 0,
                quoteCount: 0,
              }),
              followerEngagementRate: 3,
            },
          ],
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Ava");
    fireEvent.click(screen.getByRole("button", { name: "2.5%" }));
    const dialog = await screen.findByRole("dialog", { name: "Ava" });
    expect(dialog).toHaveTextContent(
      "Engagement — Last 7 Days · 2 posts analyzed",
    );
    expect(dialog).toHaveTextContent("Median Follower Engagement");
    expect(dialog).toHaveTextContent("Median Viewed Engagement");
    expect(dialog).toHaveTextContent("Median Reach Ratio");
    expect(dialog).toHaveTextContent("Typical Post");
    expect(dialog).toHaveTextContent("Engagement Mix");
    expect(dialog).toHaveTextContent("Typical Range: 2.0% – 3.0%");
    expect(dialog).toHaveTextContent("Top post");
    expect(screen.getByRole("link", { name: "Open on X" })).toHaveAttribute(
      "href",
      "https://x.com/ava/status/99",
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("opens a single-account input with Fanvue selected and cancels without adding a row", async () => {
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("No competitors tracked yet.");
    fireEvent.click(screen.getByRole("button", { name: "Add Competitor" }));
    expect(
      screen.getByRole("dialog", { name: "Add Competitor" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Single" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Multiple" })).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Fanvue" })).toBeChecked();
    expect(
      screen.getByLabelText("X Username or Profile URL"),
    ).toHaveAttribute("type", "text");
    expect(
      screen.getByText("Enter an X username or profile URL. No @ required."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "X Usernames or Profile URLs" })).not.toBeInTheDocument();
    expect(screen.queryByText(/accounts? detected/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("X Username or Profile URL"), {
      target: { value: "https://twitter.com/AshleyReed" },
    });
    expect(
      within(screen.getByRole("dialog", { name: "Add Competitor" })).getByRole("button", { name: "Add Competitor" }),
    ).toBeEnabled();
    fireEvent.click(screen.getByRole("radio", { name: "Other" }));
    expect(screen.getByRole("radio", { name: "Other" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("No competitors tracked yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add Competitor" }));
    expect(screen.getByLabelText("X Username or Profile URL")).toHaveValue("");
    expect(screen.getByRole("radio", { name: "Fanvue" })).toBeChecked();
  });

  it("accepts one username, @username, or profile URL and rejects batch input", () => {
    render(<XCompetitorIntelligencePage />);
    fireEvent.click(screen.getByRole("button", { name: "Add Competitor" }));
    expect(
      screen.getByLabelText("X Username or Profile URL"),
    ).toHaveAttribute("type", "text");
    const input = screen.getByLabelText("X Username or Profile URL");
    const submit = within(screen.getByRole("dialog", { name: "Add Competitor" })).getByRole("button", { name: "Add Competitor" });
    for (const value of ["AshleyReed", "@AshleyReed", "https://x.com/AshleyReed"]) {
      fireEvent.change(input, { target: { value } });
      expect(submit).toBeEnabled();
    }
    fireEvent.change(input, { target: { value: "AshleyReed\nmissing" } });
    expect(submit).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Usernames must contain 1–15 letters, numbers, or underscores.",
    );
    expect(screen.queryByText(/accounts? detected/)).not.toBeInTheDocument();
  });

  it("closes on Escape", () => {
    render(<XCompetitorIntelligencePage />);
    fireEvent.click(screen.getByRole("button", { name: "Add Competitor" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it.skip("obsolete close-time Telegram draft persistence", async () => {
    const fetchMock = vi.mocked(fetch);
    const item = competitor({
      id: "c1",
      username: "vicki",
      displayName: "Vicki",
      followersCount: 100,
      posts7d: 2,
      engagementRate: 3.2,
      telegramPresence: "UNKNOWN",
      telegramAudienceType: "SUBSCRIBERS",
      telegramCommentsAllowed: null,
      telegramJoined: false,
      refresh: {
        lastSuccessfulAt: "2026-08-17T10:00:00Z",
        nextRefreshAt: "2026-08-24T10:00:00Z",
        due: false,
      },
    });
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [item],
          metrics: {
            commenters: 0,
            retweeters: 4,
            quotePosters: 1,
            uniqueLeads: 4,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          presence: "YES",
          audienceType: "MEMBERS",
          commentsAllowed: true,
          joined: true,
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Vicki");
    fireEvent.click(screen.getByRole("button", { name: /Vicki/ }));
    const detail = screen.getByRole("dialog", { name: "Vicki" });
    expect(within(detail).queryByText("Last Scraped")).not.toBeInTheDocument();
    expect(
      within(detail).queryByRole("button", { name: /Scrape/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Scrape" })).toBeInTheDocument();
    const refresh = within(detail).getByLabelText("Refresh schedule");
    expect(refresh).toHaveTextContent("Last RefreshAug 17, 2026");
    expect(refresh).toHaveTextContent("Next RefreshAug 24, 2026");
    expect(refresh).not.toHaveTextContent("Profile");
    expect(refresh).not.toHaveTextContent("Activity");
    expect(within(detail).queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(within(detail).getByRole("button", { name: "Yes" }));
    const telegramOptions = within(detail)
      .getByRole("checkbox", { name: "Subscribers" })
      .closest("div");
    expect(telegramOptions).toContainElement(
      within(detail).getByRole("checkbox", { name: "Members" }),
    );
    expect(telegramOptions).toContainElement(
      within(detail).getByRole("checkbox", { name: "Comments Allowed" }),
    );
    expect(telegramOptions).toContainElement(
      within(detail).getByRole("checkbox", { name: "Joined" }),
    );
    expect(
      within(telegramOptions as HTMLElement).getAllByRole("checkbox").map(
        (checkbox) => checkbox.getAttribute("aria-label") || checkbox.parentElement?.textContent?.trim(),
      ),
    ).toEqual(["Joined", "Subscribers", "Comments Allowed", "Members"]);
    const members = within(detail).getByRole("checkbox", { name: "Members" });
    fireEvent.click(members);
    fireEvent.click(
      within(detail).getByRole("checkbox", { name: "Comments Allowed" }),
    );
    fireEvent.click(within(detail).getByRole("checkbox", { name: "Joined" }));
    fireEvent.click(within(detail).getByRole("button", { name: "No" }));
    expect(within(detail).queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(within(detail).getByRole("button", { name: "Yes" }));
    expect(members).toBeChecked();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(within(detail).getByRole("button", { name: "Close" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Vicki" }),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Telegram: Yes")).toHaveTextContent("✓");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      presence: "YES",
      audienceType: "MEMBERS",
      commentsAllowed: true,
      joined: true,
    });
  });

  it.skip("obsolete top-right close-time Telegram persistence", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({ id: "c1", username: "vicki", displayName: "Vicki" }),
          ],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 0,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          presence: "NO",
          audienceType: null,
          commentsAllowed: null,
          joined: null,
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Vicki");
    fireEvent.click(screen.getByRole("button", { name: /Vicki/ }));
    const detail = screen.getByRole("dialog", { name: "Vicki" });
    fireEvent.click(within(detail).getByRole("button", { name: "No" }));
    fireEvent.click(
      within(detail).getByRole("button", { name: "Close competitor detail" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Vicki" }),
      ).not.toBeInTheDocument(),
    );
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      presence: "NO",
      audienceType: null,
      commentsAllowed: null,
      joined: null,
    });
  });

  it.skip("obsolete close-time Telegram failure handling", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "c1",
              username: "vicki",
              displayName: "Vicki",
              telegramPresence: "YES",
              telegramAudienceType: "MEMBERS",
              telegramCommentsAllowed: true,
              telegramJoined: true,
            }),
          ],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 0,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: "Save failed" }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Vicki");
    fireEvent.click(screen.getByRole("button", { name: /Vicki/ }));
    const detail = screen.getByRole("dialog", { name: "Vicki" });
    expect(
      within(detail).getByRole("checkbox", { name: "Members" }),
    ).toBeChecked();
    expect(
      within(detail).getByRole("checkbox", { name: "Comments Allowed" }),
    ).toBeChecked();
    expect(
      within(detail).getByRole("checkbox", { name: "Joined" }),
    ).toBeChecked();
    fireEvent.click(within(detail).getByRole("checkbox", { name: "Joined" }));
    fireEvent.click(within(detail).getByRole("button", { name: "Close" }));
    expect(await within(detail).findByRole("alert")).toHaveTextContent(
      "Save failed",
    );
    expect(
      within(detail).getByRole("checkbox", { name: "Joined" }),
    ).not.toBeChecked();
  });

  it.skip("obsolete close-time Telegram serialization", async () => {
    let resolveFirst!: (value: Response) => void;
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "c1",
              username: "vicki",
              displayName: "Vicki",
              telegramPresence: "YES",
            }),
          ],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 0,
          },
        }),
      } as Response)
      .mockReturnValueOnce(
        new Promise<Response>((resolve) => {
          resolveFirst = resolve;
        }),
      );
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Vicki");
    fireEvent.click(screen.getByRole("button", { name: /Vicki/ }));
    const detail = screen.getByRole("dialog", { name: "Vicki" });
    fireEvent.click(within(detail).getByRole("checkbox", { name: "Members" }));
    fireEvent.click(
      within(detail).getByRole("checkbox", { name: "Comments Allowed" }),
    );
    fireEvent.click(within(detail).getByRole("checkbox", { name: "Joined" }));
    fireEvent.click(within(detail).getByRole("button", { name: "Close" }));
    fireEvent.click(within(detail).getByRole("button", { name: "Saving…" }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      presence: "YES",
      audienceType: "MEMBERS",
      commentsAllowed: true,
      joined: true,
    });
    resolveFirst({
      ok: true,
      json: async () => ({
        presence: "YES",
        audienceType: "MEMBERS",
        commentsAllowed: true,
        joined: true,
      }),
    } as Response);
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Vicki" }),
      ).not.toBeInTheDocument(),
    );
  });

  it.skip("obsolete close-time Telegram reconciliation", async () => {
    let resolveSave!: (value: Response) => void;
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "c1",
              username: "vicki",
              displayName: "Vicki",
              telegramPresence: "YES",
            }),
          ],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 0,
          },
        }),
      } as Response)
      .mockReturnValueOnce(
        new Promise<Response>((resolve) => {
          resolveSave = resolve;
        }),
      );
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Vicki");
    fireEvent.click(screen.getByRole("button", { name: /Vicki/ }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Members" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.getByRole("dialog", { name: "Vicki" })).toBeInTheDocument();
    await act(async () => {
      resolveSave({
        ok: true,
        json: async () => ({
          presence: "YES",
          audienceType: "MEMBERS",
          commentsAllowed: null,
          joined: null,
        }),
      } as Response);
      await Promise.resolve();
    });
    expect(
      screen.queryByRole("dialog", { name: "Vicki" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Vicki/ }));
    expect(screen.getByRole("checkbox", { name: "Members" })).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: "Subscribers" }),
    ).not.toBeChecked();
  });

  it("shows Joined, Subscribers, and persistent Scraped controls in that order", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [competitor({
            id: "c1",
            username: "ashley",
            displayName: "Ashley",
            telegramPresence: "YES",
            telegramAudienceType: "SUBSCRIBERS",
            telegramCommentsAllowed: true,
            telegramJoined: true,
            telegramScraped: false,
          })],
          metrics: { commenters: 0, retweeters: 0, quotePosters: 0, uniqueLeads: 0 },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          presence: "YES",
          telegramUrl: null,
          audienceType: "SUBSCRIBERS",
          commentsAllowed: true,
          joined: true,
          scraped: true,
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          presence: "YES",
          telegramUrl: null,
          audienceType: "SUBSCRIBERS",
          commentsAllowed: true,
          joined: true,
          scraped: false,
        }),
      } as Response);

    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Ashley");
    fireEvent.click(screen.getByRole("button", { name: /Ashley/ }));
    const detail = screen.getByRole("dialog", { name: "Ashley" });
    const checkboxes = within(detail).getAllByRole("checkbox");
    expect(checkboxes.map((checkbox) => checkbox.parentElement?.textContent?.trim())).toEqual([
      "Joined",
      "Subscribers",
      "Scraped",
    ]);
    expect(within(detail).queryByRole("checkbox", { name: "Comments Allowed" })).not.toBeInTheDocument();
    expect(within(detail).queryByRole("checkbox", { name: "Members" })).not.toBeInTheDocument();

    const scraped = within(detail).getByRole("checkbox", { name: "Scraped" });
    expect(scraped).not.toBeChecked();
    fireEvent.click(scraped);
    await waitFor(() => expect(scraped).toBeChecked());
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      presence: "YES",
      telegramUrl: null,
      audienceType: "SUBSCRIBERS",
      commentsAllowed: true,
      joined: true,
      scraped: true,
    });

    fireEvent.click(within(detail).getByRole("button", { name: "Close" }));
    fireEvent.click(screen.getByRole("button", { name: /Ashley/ }));
    const reopenedScraped = screen.getByRole("checkbox", { name: "Scraped" });
    expect(reopenedScraped).toBeChecked();
    fireEvent.click(reopenedScraped);
    await waitFor(() => expect(reopenedScraped).not.toBeChecked());
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({
      scraped: false,
    });
  });

  it("persists an exact private Telegram URL on blur and exposes a safe external link", async () => {
    const fetchMock = vi.mocked(fetch);
    const privateUrl = "https://t.me/+8pzjrgbAegIxMDA0";
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [competitor({ id: "c1", username: "vicki", displayName: "Vicki" })],
          metrics: { commenters: 0, retweeters: 0, quotePosters: 0, uniqueLeads: 0 },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ presence: "YES", telegramUrl: null, audienceType: null, commentsAllowed: null, joined: null }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ presence: "YES", telegramUrl: privateUrl, audienceType: null, commentsAllowed: null, joined: null }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Vicki");
    fireEvent.click(screen.getByRole("button", { name: /Vicki/ }));
    const detail = screen.getByRole("dialog", { name: "Vicki" });
    fireEvent.click(within(detail).getByRole("button", { name: "Yes" }));
    const input = await within(detail).findByRole("textbox", { name: "Telegram Link" });
    await waitFor(() => expect(input).toBeEnabled());
    fireEvent.change(input, { target: { value: `  ${privateUrl}  ` } });
    fireEvent.blur(input);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toMatchObject({ telegramUrl: privateUrl });
    const link = within(detail).getByRole("link", { name: "Open Telegram link" });
    expect(link).toHaveAttribute("href", privateUrl);
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    fireEvent.click(within(detail).getByRole("button", { name: "Close" }));
    fireEvent.click(screen.getByRole("button", { name: /Vicki/ }));
    expect(screen.getByRole("textbox", { name: "Telegram Link" })).toHaveValue(privateUrl);
  });

  it("scrapes from the table, prevents duplicate submission, refreshes canonical data, and opens the result summary", async () => {
    let resolveCollection!: (value: Response) => void;
    const collectionResponse = new Promise<Response>((resolve) => {
      resolveCollection = resolve;
    });
    const initial = competitor({
      id: "c1",
      username: "vicki",
      displayName: "Vicki",
    });
    const updated = {
      ...initial,
      lastAudienceScrapedAt: "2026-08-17T13:42:00Z",
      lastAudienceScrapeStatus: "SUCCEEDED" as const,
    };
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [initial],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 4,
          },
        }),
      } as Response)
      .mockReturnValueOnce(collectionResponse)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [updated],
          metrics: {
            commenters: 3,
            retweeters: 4,
            quotePosters: 1,
            uniqueLeads: 6,
          },
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Vicki");
    const row = screen.getAllByRole("row")[1]!;
    expect(within(row).getByText("Never")).toBeInTheDocument();
    const scrape = within(row).getByRole("button", { name: "Scrape" });
    fireEvent.click(scrape);
    expect(
      within(row).getByRole("button", { name: "Scraping…" }),
    ).toBeDisabled();
    fireEvent.click(within(row).getByRole("button", { name: "Scraping…" }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    resolveCollection({
      ok: true,
      json: async () => ({
        runId: "r1",
        status: "SUCCEEDED",
        completedAt: "2026-08-17T13:42:00Z",
        postsConsidered: 2,
        postsProcessed: 2,
        repliesReturned: 3,
        retweetersReturned: 4,
        quotesReturned: 1,
        uniqueUsersObserved: 6,
        newUsers: 5,
        existingUsers: 1,
        newSignals: 7,
        existingSignals: 1,
        providerRequests: 6,
        failedSources: 0,
        sourceBreakdown: {
          replies: { requests: 2, failed: 0 },
          retweets: { requests: 2, failed: 0 },
          quotes: { requests: 2, failed: 0 },
        },
      }),
    } as Response);
    expect(
      await screen.findByRole("dialog", { name: "Audience Scrape Complete" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Unique Users Found").nextSibling,
    ).toHaveTextContent("6");
    expect(screen.getByText("Leads Collected").parentElement).toHaveTextContent(
      "6",
    );
    expect(screen.getByRole("button", { name: "Scrape Again" })).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("renders prior scrape dates and non-success statuses directly in table rows without provider calls", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          competitor({
            id: "p",
            username: "partial",
            lastAudienceScrapedAt: "2026-08-15T10:00:00Z",
            lastAudienceScrapeStatus: "PARTIAL",
          }),
          competitor({
            id: "f",
            username: "failed",
            lastAudienceScrapedAt: "2026-08-08T10:00:00Z",
            lastAudienceScrapeStatus: "FAILED",
          }),
        ],
        metrics: {
          commenters: 0,
          retweeters: 0,
          quotePosters: 0,
          uniqueLeads: 0,
        },
      }),
    } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("@partial");
    expect(screen.getByText("Partial")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Scrape Again" }),
    ).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("opens database-only diagnostics for the exact Partial run while successful status stays inert", async () => {
    const partial = competitor({
      id: "p",
      username: "partial",
      displayName: "Partial Person",
      lastAudienceScrapedAt: "2026-08-17T15:42:00Z",
      lastAudienceScrapeStatus: "PARTIAL",
      lastAudienceRunId: "run-exact",
    });
    const succeeded = competitor({
      id: "s",
      username: "success",
      lastAudienceScrapedAt: "2026-08-17T14:00:00Z",
      lastAudienceScrapeStatus: "SUCCEEDED",
      lastAudienceRunId: "run-success",
    });
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [partial, succeeded],
          metrics: {
            commenters: 0,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 0,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          run: {
            id: "run-exact",
            competitorId: "p",
            status: "PARTIAL",
            startedAt: "2026-08-17T15:40:00Z",
            completedAt: "2026-08-17T15:42:00Z",
            postsConsidered: 2,
            postsProcessed: 1,
            uniqueUsersObserved: 8,
            newUsers: 5,
            existingUsers: 3,
            newSignals: 7,
            existingSignals: 2,
            providerRequests: 6,
          },
          competitor: {
            id: "p",
            username: "partial",
            displayName: "Partial Person",
            profileImageUrl: null,
          },
          sourceStatus: {
            replies: { complete: 1, failed: 1 },
            retweets: { complete: 2, failed: 0 },
            quotes: { complete: 0, failed: 1 },
          },
          failures: [
            {
              sourceType: "REPLY",
              sourceTweetId: "tweet-1",
              postedAt: "2026-08-17T10:00:00Z",
              textPreview: "Local persisted post",
              pagesCompleted: 3,
              reason: "Provider request timed out",
            },
            {
              sourceType: "QUOTE",
              sourceTweetId: "tweet-2",
              postedAt: "2026-08-16T10:00:00Z",
              textPreview: null,
              pagesCompleted: 0,
              reason: "Safe provider failure",
            },
          ],
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    const partialButton = await screen.findByRole("button", {
      name: "Partial",
    });
    expect(
      screen.queryByRole("button", { name: "Succeeded" }),
    ).not.toBeInTheDocument();
    fireEvent.click(partialButton);
    const dialog = await screen.findByRole("dialog", {
      name: "Scrape Details",
    });
    expect(within(dialog).getByText("Partial Person")).toBeInTheDocument();
    expect(within(dialog).getByText("@partial")).toBeInTheDocument();
    expect(within(dialog).getByText("Replies").parentElement).toHaveTextContent(
      "1 complete · 1 failed",
    );
    expect(
      within(dialog).getByText("Retweets").parentElement,
    ).toHaveTextContent("2 complete · 0 failed");
    expect(within(dialog).getByText("Quotes").parentElement).toHaveTextContent(
      "0 complete · 1 failed",
    );
    expect(
      within(dialog).getByText("REPLY · Post tweet-1"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText("Local persisted post"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText("3 pages completed · Failed on next page"),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText("Reason: Provider request timed out"),
    ).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain(
      "/audience-runs/run-exact/diagnostics",
    );
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ cache: "no-store" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("opens the paginated database-backed Collected Leads viewer and supports search and sorting", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [],
          metrics: {
            commenters: 1,
            retweeters: 2,
            quotePosters: 1,
            uniqueLeads: 2,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "u1",
              xUserId: "42",
              username: "fan",
              displayName: "Fan",
              profileImageUrl: null,
              hasReply: true,
              hasRetweet: true,
              hasQuote: false,
              competitorCount: 2,
            },
          ],
          total: 2,
          globalTotal: 2,
          page: 1,
          pageSize: 25,
          search: "",
          sort: "account-asc",
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "u1",
              xUserId: "42",
              username: "fan",
              displayName: "Fan",
              profileImageUrl: null,
              hasReply: true,
              hasRetweet: true,
              hasQuote: false,
              competitorCount: 2,
            },
          ],
          total: 1,
          globalTotal: 2,
          page: 1,
          pageSize: 25,
          search: "fan",
          sort: "account-asc",
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "u1",
              xUserId: "42",
              username: "fan",
              displayName: "Fan",
              profileImageUrl: null,
              hasReply: true,
              hasRetweet: true,
              hasQuote: false,
              competitorCount: 2,
            },
          ],
          total: 1,
          globalTotal: 2,
          page: 1,
          pageSize: 25,
          search: "fan",
          sort: "competitors-desc",
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("No competitors tracked yet.");
    fireEvent.click(
      screen.getByRole("button", { name: "Browse Leads Collected" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Collected Leads",
    });
    expect(within(dialog).getByText("2 unique leads")).toBeInTheDocument();
    expect(within(dialog).getByText("@fan")).toBeInTheDocument();
    for (const heading of [
      "Commenter",
      "Retweeter",
      "Quote Poster",
      "Competitors",
    ])
      expect(
        within(dialog).queryByRole("columnheader", { name: heading }),
      ).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText("Search leads..."), {
      target: { value: "fan" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Search" }));
    expect(
      await within(dialog).findByText("1 matching lead · 2 total"),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Account" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain("sort=account-desc");
  });

  it("copies all canonical usernames rather than the current page or active search", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [],
          metrics: {
            commenters: 1,
            retweeters: 2,
            quotePosters: 1,
            uniqueLeads: 3,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "u1",
              xUserId: "42",
              username: "fan",
              displayName: "Fan",
              profileImageUrl: null,
              hasReply: true,
              hasRetweet: true,
              hasQuote: false,
              competitorCount: 2,
            },
          ],
          total: 3,
          globalTotal: 3,
          page: 1,
          pageSize: 1,
          search: "",
          sort: "account-asc",
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "u1",
              xUserId: "42",
              username: "fan",
              displayName: "Fan",
              profileImageUrl: null,
              hasReply: true,
              hasRetweet: true,
              hasQuote: false,
              competitorCount: 2,
            },
          ],
          total: 1,
          globalTotal: 3,
          page: 1,
          pageSize: 25,
          search: "fan",
          sort: "account-asc",
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: false,
        json: async () => ({ detail: "Not Found" }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          usernames: [" alpha ", "@fan", " ", "Zeta"],
          count: 4,
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("No competitors tracked yet.");
    fireEvent.click(
      screen.getByRole("button", { name: "Browse Leads Collected" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Collected Leads",
    });
    fireEvent.change(within(dialog).getByLabelText("Search leads..."), {
      target: { value: "fan" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Search" }));
    await within(dialog).findByText("1 matching lead · 3 total");
    fireEvent.click(within(dialog).getByRole("button", { name: "Copy All" }));
    expect(
      await within(dialog).findByText(
        "Unable to copy usernames. Check clipboard permission and try again.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Copy All" }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith("alpha\nfan\nZeta"),
    );
    expect(within(dialog).getByText("Copied 3 usernames")).toBeInTheDocument();
    expect(
      within(dialog).queryByText(
        "Unable to copy usernames. Check clipboard permission and try again.",
      ),
    ).not.toBeInTheDocument();
    expect(
      String(fetchMock.mock.calls[4]?.[0]).endsWith(
        "/audience/leads/usernames",
      ),
    ).toBe(true);
    expect(String(fetchMock.mock.calls[4]?.[0])).not.toContain("search=");
  });

  it("copies one row username locally and omits the action for a missing username", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [],
          metrics: {
            commenters: 1,
            retweeters: 0,
            quotePosters: 0,
            uniqueLeads: 2,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "u1",
              xUserId: "1",
              username: "@fan",
              displayName: "Fan Name",
              profileImageUrl: null,
              hasReply: true,
              hasRetweet: false,
              hasQuote: false,
              competitorCount: 1,
            },
            {
              id: "u2",
              xUserId: "2",
              username: "",
              displayName: "Unknown",
              profileImageUrl: null,
              hasReply: true,
              hasRetweet: false,
              hasQuote: false,
              competitorCount: 1,
            },
          ],
          total: 2,
          globalTotal: 2,
          page: 1,
          pageSize: 25,
          search: "",
          sort: "account-asc",
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("No competitors tracked yet.");
    fireEvent.click(
      screen.getByRole("button", { name: "Browse Leads Collected" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Collected Leads",
    });
    const rows = within(dialog).getAllByRole("row");
    expect(
      within(rows[1]!).getByRole("button", { name: "Copy" }),
    ).toBeInTheDocument();
    expect(
      within(rows[2]!).queryByRole("button", { name: "Copy" }),
    ).not.toBeInTheDocument();
    fireEvent.click(within(rows[1]!).getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("fan"));
    expect(
      within(rows[1]!).getByRole("button", { name: "Copied" }),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByRole("heading", { name: "Collected Leads" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("keeps collected-lead browsing backend paginated", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [],
          metrics: {
            commenters: 0,
            retweeters: 26,
            quotePosters: 0,
            uniqueLeads: 26,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "u1",
              xUserId: "1",
              username: "alpha",
              displayName: null,
              profileImageUrl: null,
              hasReply: false,
              hasRetweet: true,
              hasQuote: false,
              competitorCount: 1,
            },
          ],
          total: 26,
          globalTotal: 26,
          page: 1,
          pageSize: 25,
          search: "",
          sort: "account-asc",
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "u2",
              xUserId: "2",
              username: "zeta",
              displayName: null,
              profileImageUrl: null,
              hasReply: false,
              hasRetweet: true,
              hasQuote: false,
              competitorCount: 1,
            },
          ],
          total: 26,
          globalTotal: 26,
          page: 2,
          pageSize: 25,
          search: "",
          sort: "account-asc",
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("No competitors tracked yet.");
    fireEvent.click(
      screen.getByRole("button", { name: "Browse Leads Collected" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Collected Leads",
    });
    fireEvent.click(
      await within(dialog).findByRole("button", { name: "Next" }),
    );
    expect(await within(dialog).findByText("@zeta")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain("page=2");
  });

  it("submits one normalized account with the selected platform and refreshes canonical dashboard data", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [],
          metrics: {
            tracked: 0,
            totalFollowers: 0,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          results: [
            {
              submittedUsername: "AshleyReed",
              resolvedUsername: "AshleyReed",
              status: "ADDED",
              reason: null,
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              id: "1",
              xUserId: "42",
              username: "AshleyReed",
              displayName: "Ashley Reed",
              profileImageUrl: null,
              trackingEnabled: true,
              followersCount: 1234,
              observedAt: "2026-08-16T00:00:00Z",
            },
          ],
          metrics: {
            tracked: 1,
            totalFollowers: 1234,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("No competitors tracked yet.");
    fireEvent.click(screen.getByRole("button", { name: "Add Competitor" }));
    fireEvent.click(screen.getByRole("radio", { name: "OnlyFans" }));
    fireEvent.change(screen.getByLabelText("X Username or Profile URL"), {
      target: { value: "@AshleyReed" },
    });
    fireEvent.click(within(screen.getByRole("dialog", { name: "Add Competitor" })).getByRole("button", { name: "Add Competitor" }));
    expect(
      await screen.findByRole("heading", { name: "Competitor Added" }),
    ).toBeInTheDocument();
    expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
      usernames: ["AshleyReed"],
      platform: "ONLYFANS",
    });
    expect(await screen.findByText("Ashley Reed")).toBeInTheDocument();
    expect(screen.getAllByText("1,234").length).toBeGreaterThanOrEqual(1);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
  });

  it("waits for initial activity, reports repairable failure, refreshes once, and preserves active sorting", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "old",
              username: "old",
              displayName: "Old",
              followersCount: 100,
            }),
          ],
          metrics: {
            tracked: 1,
            totalFollowers: 100,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          results: [
            {
              submittedUsername: "newone",
              resolvedUsername: "newone",
              status: "ADDED",
              reason: "Activity needs refresh.",
              activityStatus: "FAILED",
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            competitor({
              id: "old",
              username: "old",
              displayName: "Old",
              followersCount: 100,
            }),
            competitor({
              id: "new",
              username: "newone",
              displayName: "New One",
              followersCount: 5,
            }),
          ],
          metrics: {
            tracked: 2,
            totalFollowers: 105,
            active: null,
            strongEngagement: null,
          },
        }),
      } as Response);
    render(<XCompetitorIntelligencePage />);
    await screen.findByText("Old");
    fireEvent.click(
      screen.getByRole("button", {
        name: /Sort by Followers, currently descending/,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Add Competitor" }));
    fireEvent.change(screen.getByLabelText("X Username or Profile URL"), {
      target: { value: "newone" },
    });
    fireEvent.click(within(screen.getByRole("dialog", { name: "Add Competitor" })).getByRole("button", { name: "Add Competitor" }));
    expect(
      await screen.findByText("Added — Activity needs refresh"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(3);
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(
      screen.getByRole("columnheader", { name: "Followers" }),
    ).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getAllByRole("row")[1]).toHaveTextContent("New One");
  });
});
