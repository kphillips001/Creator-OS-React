import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Download,
  ExternalLink,
  Plus,
  UsersRound,
  X,
} from "lucide-react";
import { PageHeader } from "../../shared/ui/PageHeader";
import {
  xCompetitorIntelligenceApi,
  type XAudienceCollection,
  type XAudienceRunDiagnostics,
  type XAudienceRunUsers,
  type XArchivedCompetitor,
  type XCreatorPlatform,
  type XCollectedLeadsResponse,
  type XCompetitor,
  type XCompetitorPost,
  type XDashboard,
  type XEngagementResponse,
  type XImportResult,
  type XPosts7dResponse,
} from "../../infrastructure/api/xCompetitorIntelligenceApi";
import { normalizeXAccount } from "./xAccountInput";
import "./x-competitor-intelligence.css";

const columns = [
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
] as const;
const emptyDashboard: XDashboard = {
  items: [],
  benchmark: null,
  metrics: { commenters: 0, retweeters: 0, quotePosters: 0, uniqueLeads: 0 },
};

function PlatformBadge({ platform = "FANVUE" }: { platform?: XCreatorPlatform }) {
  const label = platform === "FANVUE" ? "FV" : platform === "ONLYFANS" ? "OF" : "OT";
  return (
    <span
      className={`x-intelligence-platform-badge x-intelligence-platform-badge--${platform.toLowerCase()}`}
    >
      {label}
    </span>
  );
}
const number = (value: number | null) =>
  value === null ? "—" : new Intl.NumberFormat("en-US").format(value);
const percent = (value: number | null | undefined) =>
  value == null ? "—" : `${value.toFixed(1)}%`;
export function buildCollectedLeadClipboardText(
  usernames: (string | null | undefined)[],
) {
  return usernames
    .map((value) => (value ?? "").trim().replace(/^@+/, ""))
    .filter(Boolean)
    .join("\n");
}
const escapeClipboardHtml = (value: string) =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
export async function writeCollectedLeadClipboardText(payload: string) {
  if (
    typeof ClipboardItem !== "undefined" &&
    typeof navigator.clipboard.write === "function"
  ) {
    const html = payload
      .split("\n")
      .map((username) => `<div>${escapeClipboardHtml(username)}</div>`)
      .join("");
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/plain": new Blob([payload], { type: "text/plain;charset=utf-8" }),
        "text/html": new Blob([html], { type: "text/html;charset=utf-8" }),
      }),
    ]);
    return;
  }
  await navigator.clipboard.writeText(payload);
}
export const formatLastActive = (value: string | null, now = new Date()) => {
  if (!value) return "—";
  const activity = new Date(value);
  if (Number.isNaN(activity.getTime())) return "—";
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const activityDay = new Date(
    activity.getFullYear(),
    activity.getMonth(),
    activity.getDate(),
  );
  const days = Math.floor(
    (today.getTime() - activityDay.getTime()) / 86_400_000,
  );
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days <= 30) return `${days}d ago`;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: activity.getFullYear() === now.getFullYear() ? undefined : "numeric",
  }).format(activity);
};
const formatRefreshDate = (value: string | null) =>
  value
    ? new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(new Date(value))
    : "Never";
export const formatLastRefreshDate = (value: string | null) => {
  if (!value) return null;
  const updated = new Date(value);
  if (Number.isNaN(updated.getTime())) return null;
  return `Last Refresh ${new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(updated)}`;
};
function CollectionResultDialog({
  item,
  summary,
  onClose,
}: {
  item: XCompetitor;
  summary: XAudienceCollection;
  onClose: () => void;
}) {
  const [users, setUsers] = useState<XAudienceRunUsers | null>(null);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [error, setError] = useState("");
  const source = summary.sourceBreakdown;
  const openUsers = async (classification: "NEW" | "EXISTING") => {
    setLoadingUsers(true);
    setError("");
    try {
      setUsers(
        await xCompetitorIntelligenceApi.audienceRunUsers(
          summary.runId,
          classification,
        ),
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to load collected users.",
      );
    } finally {
      setLoadingUsers(false);
    }
  };
  return (
    <div className="x-competitor-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="x-collection-result-title"
        aria-modal="true"
        className="x-competitor-dialog x-competitor-detail"
        role="dialog"
      >
        <header className="x-intelligence-card__header">
          <div className="x-intelligence-card__heading">
            <h2 id="x-collection-result-title">Audience Scrape Complete</h2>
            <p>
              {item.displayName || item.username} · @{item.username}
            </p>
          </div>
          <button
            aria-label="Close audience scrape result"
            className="x-competitor-dialog__close"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        {error && (
          <p
            className="x-intelligence-state x-intelligence-state--error"
            role="alert"
          >
            {error}
          </p>
        )}
        <section
          className="x-audience-summary"
          aria-label="7-Day Audience Collection summary"
        >
          <h3>Collection {summary.status.toLowerCase()}</h3>
          <dl>
            <SummaryRow
              label="Posts Processed"
              value={summary.postsProcessed}
            />
            <SummaryRow
              label="Replies Returned"
              value={summary.repliesReturned}
            />
            <SummaryRow
              label="Retweeters Returned"
              value={summary.retweetersReturned}
            />
            <SummaryRow
              label="Quotes Returned"
              value={summary.quotesReturned}
            />
            <SummaryRow
              label="Unique Users Found"
              value={summary.uniqueUsersObserved}
            />
            <SummaryRow
              interactive={summary.newUsers > 0}
              label="New Users Added"
              onClick={() => void openUsers("NEW")}
              value={summary.newUsers}
            />
            <SummaryRow
              interactive={summary.existingUsers > 0}
              label="Already in Database"
              onClick={() => void openUsers("EXISTING")}
              value={summary.existingUsers}
            />
            <SummaryRow label="New Signals" value={summary.newSignals} />
            <SummaryRow
              label="Existing Signals"
              value={summary.existingSignals}
            />
            <SummaryRow
              label="Provider Requests"
              value={summary.providerRequests}
            />
            <SummaryRow label="Failed Sources" value={summary.failedSources} />
          </dl>
          <p className="x-audience-summary__breakdown">
            Requests: Replies {source.replies.requests} · Retweets{" "}
            {source.retweets.requests} · Quotes {source.quotes.requests}
          </p>
          {summary.failedSources > 0 && (
            <p className="x-audience-summary__breakdown x-audience-summary__breakdown--error">
              Failures: Replies {source.replies.failed} · Retweets{" "}
              {source.retweets.failed} · Quotes {source.quotes.failed}
            </p>
          )}
        </section>
        <footer>
          <button onClick={onClose}>Close</button>
        </footer>
      </section>
      {users && (
        <AudienceRunUsersDialog
          data={users}
          loading={loadingUsers}
          onClose={() => setUsers(null)}
        />
      )}
    </div>
  );
}
export const formatLastScraped = (value: string | null, now = new Date()) => {
  if (!value) return "Never";
  const scraped = new Date(value);
  if (Number.isNaN(scraped.getTime())) return "Never";
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const scrapedDay = new Date(
    scraped.getFullYear(),
    scraped.getMonth(),
    scraped.getDate(),
  );
  const days = Math.floor(
    (today.getTime() - scrapedDay.getTime()) / 86_400_000,
  );
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: scraped.getFullYear() === now.getFullYear() ? undefined : "numeric",
  }).format(scraped);
};
const fullScrapeTimestamp = (value: string | null) =>
  value
    ? `${new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(value))} · ${new Intl.DateTimeFormat("en-US", { timeStyle: "short" }).format(new Date(value))}`
    : undefined;
export const formatGlobalRefresh = (value: string | null, now = new Date()) => {
  if (!value) return "Never";
  const refreshed = new Date(value);
  if (Number.isNaN(refreshed.getTime())) return "Never";
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const refreshedDay = new Date(
    refreshed.getFullYear(),
    refreshed.getMonth(),
    refreshed.getDate(),
  );
  const days = Math.floor(
    (today.getTime() - refreshedDay.getTime()) / 86_400_000,
  );
  const time = new Intl.DateTimeFormat("en-US", { timeStyle: "short" }).format(
    refreshed,
  );
  if (days <= 0) return `Today, ${time}`;
  if (days === 1) return `Yesterday, ${time}`;
  return `${new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: refreshed.getFullYear() === now.getFullYear() ? undefined : "numeric" }).format(refreshed)}, ${time}`;
};
type CompetitorSort =
  | "followers-desc"
  | "followers-asc"
  | "name-asc"
  | "name-desc"
  | "last-active-desc"
  | "last-active-asc"
  | "posts-desc"
  | "posts-asc"
  | "engagement-desc"
  | "engagement-asc"
  | "growth7-desc"
  | "growth7-asc"
  | "growth30-desc"
  | "growth30-asc"
  | "last-scraped-desc"
  | "last-scraped-asc"
  | "telegram-desc"
  | "telegram-asc"
  | "comments-desc"
  | "comments-asc"
  | "retweets-desc"
  | "retweets-asc"
  | "quotes-desc"
  | "quotes-asc";
type EngagementMetric = "comments" | "retweets" | "quotes";
type SortableColumn =
  | "Competitor"
  | "Followers"
  | "7D Growth"
  | "30D Growth"
  | "Last Active"
  | "Posts 7D"
  | "Engagement"
  | "TG"
  | "Last Scraped";
const sortDirections: Record<
  SortableColumn,
  readonly [CompetitorSort, CompetitorSort]
> = {
  Competitor: ["name-asc", "name-desc"],
  Followers: ["followers-desc", "followers-asc"],
  "7D Growth": ["growth7-desc", "growth7-asc"],
  "30D Growth": ["growth30-desc", "growth30-asc"],
  "Last Active": ["last-active-desc", "last-active-asc"],
  "Posts 7D": ["posts-desc", "posts-asc"],
  Engagement: ["engagement-desc", "engagement-asc"],
  TG: ["telegram-desc", "telegram-asc"],
  "Last Scraped": ["last-scraped-desc", "last-scraped-asc"],
};
const sortColumn = (sort: CompetitorSort): SortableColumn | null =>
  sort.startsWith("name")
    ? "Competitor"
    : sort.startsWith("followers")
      ? "Followers"
      : sort.startsWith("growth7")
        ? "7D Growth"
        : sort.startsWith("growth30")
          ? "30D Growth"
          : sort.startsWith("last-active")
            ? "Last Active"
            : sort.startsWith("last-scraped")
              ? "Last Scraped"
              : sort.startsWith("telegram")
                ? "TG"
              : sort.startsWith("posts")
                ? "Posts 7D"
                : sort.startsWith("engagement")
                  ? "Engagement"
                  : null;
const sortOrder = (sort: CompetitorSort): "ascending" | "descending" =>
  sort.endsWith("asc") ? "ascending" : "descending";
const identity = (item: XCompetitor) =>
  (item.displayName?.trim() || item.username).toLocaleLowerCase();
const stableIdentity = (left: XCompetitor, right: XCompetitor) =>
  identity(left).localeCompare(identity(right)) ||
  left.username
    .toLocaleLowerCase()
    .localeCompare(right.username.toLocaleLowerCase()) ||
  left.id.localeCompare(right.id);
const followers = (
  left: XCompetitor,
  right: XCompetitor,
  direction: 1 | -1,
) => {
  if (left.followersCount === null)
    return right.followersCount === null ? stableIdentity(left, right) : 1;
  if (right.followersCount === null) return -1;
  return (
    direction * (left.followersCount - right.followersCount) ||
    stableIdentity(left, right)
  );
};
const lastActive = (
  left: XCompetitor,
  right: XCompetitor,
  direction: 1 | -1,
) => {
  const leftTime =
    left.lastActiveAt === null ? null : Date.parse(left.lastActiveAt);
  const rightTime =
    right.lastActiveAt === null ? null : Date.parse(right.lastActiveAt);
  const leftKnown = leftTime !== null && !Number.isNaN(leftTime);
  const rightKnown = rightTime !== null && !Number.isNaN(rightTime);
  if (!leftKnown) return !rightKnown ? stableIdentity(left, right) : 1;
  if (!rightKnown) return -1;
  return direction * (leftTime - rightTime) || stableIdentity(left, right);
};
const lastScraped = (
  left: XCompetitor,
  right: XCompetitor,
  direction: 1 | -1,
) => {
  const leftTime =
    left.lastAudienceScrapedAt === null
      ? null
      : Date.parse(left.lastAudienceScrapedAt);
  const rightTime =
    right.lastAudienceScrapedAt === null
      ? null
      : Date.parse(right.lastAudienceScrapedAt);
  const leftKnown = leftTime !== null && !Number.isNaN(leftTime);
  const rightKnown = rightTime !== null && !Number.isNaN(rightTime);
  if (!leftKnown) return !rightKnown ? stableIdentity(left, right) : 1;
  if (!rightKnown) return -1;
  return direction * (leftTime - rightTime) || stableIdentity(left, right);
};
const posts7d = (left: XCompetitor, right: XCompetitor, direction: 1 | -1) => {
  if (left.posts7d === null)
    return right.posts7d === null ? stableIdentity(left, right) : 1;
  if (right.posts7d === null) return -1;
  return (
    direction * (left.posts7d - right.posts7d) || stableIdentity(left, right)
  );
};
const engagement = (
  left: XCompetitor,
  right: XCompetitor,
  direction: 1 | -1,
) => {
  if (left.engagementRate == null)
    return right.engagementRate == null ? stableIdentity(left, right) : 1;
  if (right.engagementRate == null) return -1;
  return (
    direction * (left.engagementRate - right.engagementRate) ||
    stableIdentity(left, right)
  );
};
const growth = (
  left: XCompetitor,
  right: XCompetitor,
  key: "growth7d" | "growth30d",
  direction: 1 | -1,
) => {
  const leftValue = left[key]?.percent;
  const rightValue = right[key]?.percent;
  if (leftValue == null)
    return rightValue == null ? stableIdentity(left, right) : 1;
  if (rightValue == null) return -1;
  return direction * (leftValue - rightValue) || stableIdentity(left, right);
};
const engagementTotal = (
  left: XCompetitor,
  right: XCompetitor,
  key: "comments7d" | "retweets7d" | "quotes7d",
  direction: 1 | -1,
) => {
  const leftValue = left[key];
  const rightValue = right[key];
  if (leftValue === null)
    return rightValue === null ? stableIdentity(left, right) : 1;
  if (rightValue === null) return -1;
  return direction * (leftValue - rightValue) || stableIdentity(left, right);
};
const telegramPresence = (
  left: XCompetitor,
  right: XCompetitor,
  direction: 1 | -1,
) =>
  direction *
    (Number(left.telegramPresence === "YES") -
      Number(right.telegramPresence === "YES")) ||
  stableIdentity(left, right);
export const sortCompetitors = (
  items: readonly XCompetitor[],
  sort: CompetitorSort,
) =>
  [...items].sort((left, right) => {
    if (sort === "followers-desc") return followers(left, right, -1);
    if (sort === "followers-asc") return followers(left, right, 1);
    if (sort === "name-asc") return stableIdentity(left, right);
    if (sort === "name-desc") return -stableIdentity(left, right);
    if (sort === "last-active-desc") return lastActive(left, right, -1);
    if (sort === "last-active-asc") return lastActive(left, right, 1);
    if (sort === "last-scraped-desc") return lastScraped(left, right, -1);
    if (sort === "last-scraped-asc") return lastScraped(left, right, 1);
    if (sort === "telegram-desc") return telegramPresence(left, right, -1);
    if (sort === "telegram-asc") return telegramPresence(left, right, 1);
    if (sort === "posts-desc") return posts7d(left, right, -1);
    if (sort === "posts-asc") return posts7d(left, right, 1);
    if (sort.startsWith("growth7"))
      return growth(left, right, "growth7d", sort.endsWith("desc") ? -1 : 1);
    if (sort.startsWith("growth30"))
      return growth(left, right, "growth30d", sort.endsWith("desc") ? -1 : 1);
    if (sort.startsWith("comments"))
      return engagementTotal(
        left,
        right,
        "comments7d",
        sort.endsWith("desc") ? -1 : 1,
      );
    if (sort.startsWith("retweets"))
      return engagementTotal(
        left,
        right,
        "retweets7d",
        sort.endsWith("desc") ? -1 : 1,
      );
    if (sort.startsWith("quotes"))
      return engagementTotal(
        left,
        right,
        "quotes7d",
        sort.endsWith("desc") ? -1 : 1,
      );
    return engagement(left, right, sort === "engagement-desc" ? -1 : 1);
  });
type PostSort =
  "newest" | "views" | "likes" | "comments" | "retweets" | "quotes";
const postMetric: Record<Exclude<PostSort, "newest">, keyof XCompetitorPost> = {
  views: "viewCount",
  likes: "likeCount",
  comments: "replyCount",
  retweets: "retweetCount",
  quotes: "quoteCount",
};
export const sortCompetitorPosts = (
  posts: readonly XCompetitorPost[],
  sort: PostSort,
) =>
  [...posts].sort((left, right) => {
    const tie = () =>
      Date.parse(right.postedAt) - Date.parse(left.postedAt) ||
      left.xTweetId.localeCompare(right.xTweetId);
    if (sort === "newest") return tie();
    const key = postMetric[sort];
    const leftValue = left[key] as number | null;
    const rightValue = right[key] as number | null;
    if (leftValue === null) return rightValue === null ? tie() : 1;
    if (rightValue === null) return -1;
    return rightValue - leftValue || tie();
  });

export function XCompetitorIntelligencePage() {
  const [dashboard, setDashboard] = useState<XDashboard>(emptyDashboard);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState("");
  const [sort, setSort] = useState<CompetitorSort>("followers-desc");
  const [competitorSearch, setCompetitorSearch] = useState("");
  const [postViewer, setPostViewer] = useState<XPosts7dResponse | null>(null);
  const [postViewerLoading, setPostViewerLoading] = useState(false);
  const [postViewerError, setPostViewerError] = useState("");
  const [engagementViewer, setEngagementViewer] =
    useState<XEngagementResponse | null>(null);
  const [engagementLoading, setEngagementLoading] = useState(false);
  const [competitorDetail, setCompetitorDetail] = useState<XCompetitor | null>(
    null,
  );
  const [scrapingIds, setScrapingIds] = useState<Set<string>>(() => new Set());
  const scrapingIdsRef = useRef(new Set<string>());
  const [collectionResult, setCollectionResult] = useState<{
    item: XCompetitor;
    summary: XAudienceCollection;
  } | null>(null);
  const [collectionError, setCollectionError] = useState("");
  const [scrapeDetails, setScrapeDetails] =
    useState<XAudienceRunDiagnostics | null>(null);
  const [scrapeDetailsLoading, setScrapeDetailsLoading] = useState(false);
  const [scrapeDetailsError, setScrapeDetailsError] = useState("");
  const [leadsOpen, setLeadsOpen] = useState(false);
  const [archivedOpen, setArchivedOpen] = useState(false);
  const [archivedItems, setArchivedItems] = useState<XArchivedCompetitor[]>([]);
  const [archivedLoading, setArchivedLoading] = useState(false);
  const [archivedError, setArchivedError] = useState("");
  const [downloadingLeads, setDownloadingLeads] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [competitorInput, setCompetitorInput] = useState("");
  const [creatorPlatform, setCreatorPlatform] =
    useState<XCreatorPlatform>("FANVUE");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [results, setResults] = useState<XImportResult[] | null>(null);
  const normalizedAccount = useMemo(
    () => normalizeXAccount(competitorInput),
    [competitorInput],
  );
  const username = normalizedAccount.username;
  const validationError = competitorInput.trim() ? normalizedAccount.error : null;
  const load = useCallback(async () => {
    try {
      setDashboard(await xCompetitorIntelligenceApi.dashboard());
      setPageError("");
    } catch (reason) {
      setPageError(
        reason instanceof Error
          ? reason.message
          : "Unable to load competitors.",
      );
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  const closeDialog = () => {
    setDialogOpen(false);
    setCompetitorInput("");
    setCreatorPlatform("FANVUE");
    setSubmitting(false);
    setSubmitError("");
    setResults(null);
  };
  useEffect(() => {
    if (!dialogOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) closeDialog();
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [dialogOpen, submitting]);
  const submit = async () => {
    if (!username || validationError || submitting) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      const response =
        await xCompetitorIntelligenceApi.importCompetitors(
          [username],
          creatorPlatform,
        );
      setResults(response.results);
      await load();
    } catch (reason) {
      setSubmitError(
        reason instanceof Error ? reason.message : "Unable to add competitors.",
      );
    } finally {
      setSubmitting(false);
    }
  };
  const openArchived = async () => {
    setArchivedOpen(true);
    setArchivedLoading(true);
    setArchivedError("");
    try {
      setArchivedItems((await xCompetitorIntelligenceApi.archivedCompetitors()).items);
    } catch (reason) {
      setArchivedError(reason instanceof Error ? reason.message : "Unable to load archived competitors.");
    } finally {
      setArchivedLoading(false);
    }
  };
  const restoreCompetitor = async (competitorId: string) => {
    await xCompetitorIntelligenceApi.restoreCompetitor(competitorId);
    setArchivedItems((current) => current.filter((item) => item.id !== competitorId));
    await load();
  };
  const downloadLeads = async () => {
    if (downloadingLeads) return;
    setDownloadingLeads(true);
    try {
      const { blob, filename } = await xCompetitorIntelligenceApi.downloadCollectedLeadsCsv();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setPageError("");
    } catch (reason) {
      setPageError(reason instanceof Error ? reason.message : "Unable to export collected leads.");
    } finally {
      setDownloadingLeads(false);
    }
  };
  const openPosts = async (item: XCompetitor) => {
    if (item.posts7d === null || postViewerLoading) return;
    setPostViewerLoading(true);
    setPostViewerError("");
    try {
      setPostViewer(await xCompetitorIntelligenceApi.posts7d(item.id));
    } catch (reason) {
      setPostViewerError(
        reason instanceof Error
          ? reason.message
          : "Unable to load competitor posts.",
      );
    } finally {
      setPostViewerLoading(false);
    }
  };
  const openEngagement = async (item: XCompetitor) => {
    if (item.engagementRate === null || engagementLoading) return;
    setEngagementLoading(true);
    setPostViewerError("");
    try {
      setEngagementViewer(
        await xCompetitorIntelligenceApi.engagement7d(item.id),
      );
    } catch (reason) {
      setPostViewerError(
        reason instanceof Error
          ? reason.message
          : "Unable to load engagement analytics.",
      );
    } finally {
      setEngagementLoading(false);
    }
  };
  const scrapeAudience = async (item: XCompetitor) => {
    if (scrapingIdsRef.current.has(item.id)) return;
    scrapingIdsRef.current.add(item.id);
    setScrapingIds(new Set(scrapingIdsRef.current));
    setCollectionError("");
    try {
      const summary = await xCompetitorIntelligenceApi.collectAudience7d(
        item.id,
      );
      await load();
      setCollectionResult({ item, summary });
    } catch (reason) {
      setCollectionError(
        reason instanceof Error
          ? reason.message
          : "Unable to collect audience.",
      );
    } finally {
      scrapingIdsRef.current.delete(item.id);
      setScrapingIds(new Set(scrapingIdsRef.current));
    }
  };
  const openScrapeDetails = async (item: XCompetitor) => {
    if (!item.lastAudienceRunId || scrapeDetailsLoading) return;
    setScrapeDetailsLoading(true);
    setScrapeDetailsError("");
    try {
      setScrapeDetails(
        await xCompetitorIntelligenceApi.audienceRunDiagnostics(
          item.lastAudienceRunId,
        ),
      );
    } catch (reason) {
      setScrapeDetailsError(
        reason instanceof Error
          ? reason.message
          : "Unable to load scrape details.",
      );
    } finally {
      setScrapeDetailsLoading(false);
    }
  };
  const leadsCollected = loading ? "—" : number(dashboard.metrics.uniqueLeads);
  const normalizedCompetitorSearch = competitorSearch
    .trim()
    .replace(/^@+/, "")
    .toLocaleLowerCase();
  const sortedCompetitors = useMemo(
    () =>
      sortCompetitors(
        dashboard.items.filter((item) => {
          if (!normalizedCompetitorSearch) return true;
          return (
            item.username
              .trim()
              .replace(/^@+/, "")
              .toLocaleLowerCase()
              .includes(normalizedCompetitorSearch) ||
            (item.displayName
              ?.trim()
              .toLocaleLowerCase()
              .includes(normalizedCompetitorSearch) ??
              false)
          );
        }),
        sort,
      ),
    [dashboard.items, normalizedCompetitorSearch, sort],
  );
  const activateSort = (column: SortableColumn) => {
    const directions = sortDirections[column];
    setSort((current) =>
      sortColumn(current) === column
        ? current === directions[0]
          ? directions[1]
          : directions[0]
        : directions[0],
    );
  };
  const activateEngagementMetricSort = (metric: EngagementMetric) => {
    const descending = `${metric}-desc` as CompetitorSort;
    const ascending = `${metric}-asc` as CompetitorSort;
    setSort((current) =>
      current === descending
        ? ascending
        : current === ascending
          ? descending
          : descending,
    );
  };
  return (
    <section className="x-intelligence-page">
      <PageHeader
        title="X Competitor Intelligence"
        description="Track competitors, audience growth, and X market intelligence over time."
      />
      <section
        aria-labelledby="competitors-title"
        className="x-intelligence-card"
      >
        <header>
          <div>
            <h2 id="competitors-title">Competitors</h2>
            <p>Track X accounts and build historical intelligence over time.</p>
          </div>
          <button
            aria-label="Browse Leads Collected"
            className="x-intelligence-card__leads"
            onClick={() => setLeadsOpen(true)}
          >
            <span>Leads Collected</span>
            <strong>{leadsCollected}</strong>
            <small>Unique · Deduplicated</small>
          </button>
        </header>
        <div
          aria-label="Competitor table controls"
          className="x-intelligence-toolbar"
          role="group"
        >
          <label className="x-intelligence-toolbar__search">
            <span>Search</span>
            <input
              disabled={loading && !dashboard.items.length}
              onChange={(event) => setCompetitorSearch(event.target.value)}
              placeholder="Search competitors..."
              type="search"
              value={competitorSearch}
            />
          </label>
          <div className="x-intelligence-card__actions">
            <button className="x-intelligence-card__archived" disabled={downloadingLeads} onClick={() => void downloadLeads()} type="button">
              <Download size={15} />
              {downloadingLeads ? "Downloading…" : "Download"}
            </button>
            <button aria-label="View Archived Competitors" className="x-intelligence-card__archived" onClick={() => void openArchived()}>
              Archived
            </button>
            <button
              className="x-intelligence-card__add"
              onClick={() => setDialogOpen(true)}
            >
              <Plus size={16} />
              Add Competitor
            </button>
          </div>
        </div>
        {pageError && (
          <p
            className="x-intelligence-state x-intelligence-state--error"
            role="alert"
          >
            {pageError}
          </p>
        )}
        {postViewerError && (
          <p
            className="x-intelligence-state x-intelligence-state--error"
            role="alert"
          >
            {postViewerError}
          </p>
        )}
        {collectionError && (
          <p
            className="x-intelligence-state x-intelligence-state--error"
            role="alert"
          >
            {collectionError}
          </p>
        )}
        {dashboard.benchmark && (
          <BenchmarkAccount
            item={dashboard.benchmark}
            onDetails={() => setCompetitorDetail(dashboard.benchmark)}
            onPosts={() => void openPosts(dashboard.benchmark!)}
            postsLoading={postViewerLoading}
          />
        )}
        <div
          className="x-intelligence-table"
          role="table"
          aria-label="Tracked X competitors"
        >
          <div className="x-intelligence-table__header" role="row">
            {columns.map((column) => {
              const sortable = column in sortDirections;
              const active = sortable && sortColumn(sort) === column;
              const order = active ? sortOrder(sort) : undefined;
              return (
                <span
                  aria-label={column}
                  aria-sort={order}
                  key={column}
                  role="columnheader"
                >
                  {sortable ? (
                    <button
                      aria-label={`Sort by ${column}${order ? `, currently ${order}` : ""}`}
                      className={active ? "is-active" : undefined}
                      onClick={() => activateSort(column as SortableColumn)}
                    >
                      {column}
                      {active ? (
                        order === "ascending" ? (
                          <ArrowUp aria-hidden="true" />
                        ) : (
                          <ArrowDown aria-hidden="true" />
                        )
                      ) : (
                        <ArrowUpDown aria-hidden="true" />
                      )}
                    </button>
                  ) : (
                    column
                  )}
                </span>
              );
            })}
          </div>
          {sortedCompetitors.map((item) => {
            const scraping = scrapingIds.has(item.id);
            const status = item.lastAudienceScrapeStatus;
            const diagnostic = status === "PARTIAL" || status === "FAILED";
            return (
              <div
                className="x-intelligence-table__row"
                key={item.id}
                role="row"
              >
                <span role="cell">
                  <div className="x-intelligence-competitor">
                    <button
                      aria-label="Open competitor details"
                      className="x-intelligence-competitor__avatar-action"
                      onClick={() => setCompetitorDetail(item)}
                      type="button"
                    >
                      {item.profileImageUrl ? (
                        <img alt="" src={item.profileImageUrl} />
                      ) : (
                        <span className="x-intelligence-competitor__avatar">
                          {(item.displayName || item.username)
                            .slice(0, 1)
                            .toUpperCase()}
                        </span>
                      )}
                    </button>
                    <span>
                      <span className="x-intelligence-competitor__name-line">
                        <button
                          className="x-intelligence-competitor__button"
                          onClick={() => setCompetitorDetail(item)}
                          type="button"
                        >
                          <strong>{item.displayName || item.username}</strong>
                        </button>
                        {item.accountRole === "COMPETITOR" && (
                          <PlatformBadge platform={item.platform} />
                        )}
                      </span>
                      <a
                        className="x-intelligence-competitor__profile-link"
                        href={`https://x.com/${encodeURIComponent(item.username.trim().replace(/^@+/, ""))}`}
                        onClick={(event) => event.stopPropagation()}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        @{item.username.trim().replace(/^@+/, "")}
                      </a>
                    </span>
                  </div>
                </span>
                <span role="cell">{number(item.followersCount)}</span>
                <GrowthValue value={item.growth7d} />
                <GrowthValue value={item.growth30d} />
                <span className="x-intelligence-table__last-active" role="cell">
                  <span title={item.lastActiveAt || undefined}>
                    {formatLastActive(item.lastActiveAt)}
                  </span>
                </span>
                <span role="cell">
                  {item.posts7d === null ? (
                    "—"
                  ) : (
                    <button
                      className="x-intelligence-post-count"
                      disabled={postViewerLoading}
                      onClick={() => void openPosts(item)}
                    >
                      {item.posts7d}
                    </button>
                  )}
                </span>
                <span role="cell">
                  {item.engagementRate == null ? (
                    "—"
                  ) : (
                    <button
                      className="x-intelligence-post-count"
                      disabled={engagementLoading}
                      onClick={() => void openEngagement(item)}
                    >
                      {percent(item.engagementRate)}
                    </button>
                  )}
                </span>
                <span
                  aria-label={
                    item.telegramPresence === "YES"
                      ? "Telegram: Yes"
                      : "Telegram: No or unknown"
                  }
                  className={`x-intelligence-telegram-status${item.telegramPresence === "YES" ? " is-present" : ""}`}
                  role="cell"
                >
                  {item.telegramPresence === "YES" ? (
                    item.telegramUrl ? (
                      <a
                        aria-label={`Open Telegram for @${item.username}`}
                        className="x-intelligence-telegram-status__link"
                        href={item.telegramUrl}
                        onClick={(event) => event.stopPropagation()}
                        rel="noopener noreferrer"
                        target="_blank"
                        title="Open Telegram"
                      >
                        ✓
                      </a>
                    ) : (
                      "✓"
                    )
                  ) : (
                    "—"
                  )}
                </span>
                <span
                  className="x-last-scraped"
                  role="cell"
                  title={fullScrapeTimestamp(item.lastAudienceScrapedAt)}
                >
                  <strong>
                    {formatLastScraped(item.lastAudienceScrapedAt)}
                  </strong>
                  {status &&
                    status !== "SUCCEEDED" &&
                    (diagnostic && item.lastAudienceRunId ? (
                      <button
                        className={`is-${status.toLowerCase()}`}
                        disabled={scrapeDetailsLoading}
                        onClick={() => void openScrapeDetails(item)}
                      >
                        {status.charAt(0) + status.slice(1).toLowerCase()}
                      </button>
                    ) : (
                      <small className={`is-${status.toLowerCase()}`}>
                        {status.charAt(0) + status.slice(1).toLowerCase()}
                      </small>
                    ))}
                </span>
                <span role="cell">
                  <button
                    className="x-intelligence-scrape"
                    disabled={scraping}
                    onClick={() => void scrapeAudience(item)}
                  >
                    {scraping
                      ? "Scraping…"
                      : item.lastAudienceScrapedAt
                        ? "Scrape Again"
                        : "Scrape"}
                  </button>
                </span>
                <span
                  aria-label={`Last 7 days: ${number(item.comments7d)} comments, ${number(item.retweets7d)} retweets, ${number(item.quotes7d)} quotes`}
                  className="x-intelligence-table__seven-day-summary"
                  role="cell"
                >
                  {(
                    [
                      ["comments", item.comments7d],
                      ["retweets", item.retweets7d],
                      ["quotes", item.quotes7d],
                    ] as const
                  ).map(([metric, value], index) => {
                    const active = sort.startsWith(`${metric}-`);
                    const direction = active ? sortOrder(sort) : undefined;
                    return (
                      <span key={metric}>
                        {index > 0 && (
                          <>
                            {" "}
                            <b aria-hidden="true">·</b>{" "}
                          </>
                        )}
                        <button
                          aria-label={`Sort by ${metric}${direction ? `, currently ${direction}` : ""}`}
                          aria-pressed={active}
                          className={active ? "is-active" : undefined}
                          onClick={() => activateEngagementMetricSort(metric)}
                          type="button"
                        >
                          {number(value)} {metric}
                          {direction === "descending" && (
                            <ArrowDown aria-hidden="true" />
                          )}
                          {direction === "ascending" && (
                            <ArrowUp aria-hidden="true" />
                          )}
                        </button>
                      </span>
                    );
                  })}
                </span>
                {formatLastRefreshDate(item.refresh?.lastSuccessfulAt ?? null) && (
                  <small
                    className="x-intelligence-refresh-metadata x-intelligence-table__refresh-position"
                    role="cell"
                  >
                    {formatLastRefreshDate(item.refresh?.lastSuccessfulAt ?? null)}
                  </small>
                )}
              </div>
            );
          })}
          {!loading &&
            !pageError &&
            dashboard.items.length > 0 &&
            !sortedCompetitors.length && (
              <div className="x-intelligence-table__empty" role="row">
                <div role="cell">
                  <UsersRound size={24} />
                  <strong>No matching competitors.</strong>
                </div>
              </div>
            )}
          {!loading && !pageError && !dashboard.items.length && (
            <div className="x-intelligence-table__empty" role="row">
              <div role="cell">
                <UsersRound size={24} />
                <strong>No competitors tracked yet.</strong>
                <p>
                  Add X competitors to begin building historical growth and
                  audience intelligence.
                </p>
              </div>
            </div>
          )}
        </div>
      </section>
      {postViewer && (
        <PostsViewer data={postViewer} onClose={() => setPostViewer(null)} />
      )}
      {engagementViewer && (
        <EngagementViewer
          data={engagementViewer}
          onClose={() => setEngagementViewer(null)}
        />
      )}
      {competitorDetail && (
        <TelegramCompetitorDetail
          item={competitorDetail}
          onClose={() => setCompetitorDetail(null)}
          onArchived={(competitorId) => {
            setCompetitorDetail(null);
            setDashboard((current) => ({
              ...current,
              items: current.items.filter((item) => item.id !== competitorId),
            }));
          }}
          onUpdated={(value) => {
            setCompetitorDetail((current) =>
              current?.id === value.id ? value : current,
            );
            setDashboard((current) => ({
              ...current,
              items: current.items.map((item) =>
                item.id === value.id ? value : item,
              ),
            }));
          }}
        />
      )}
      {collectionResult && (
        <CollectionResultDialog
          item={collectionResult.item}
          onClose={() => setCollectionResult(null)}
          summary={collectionResult.summary}
        />
      )}
      {scrapeDetails && (
        <ScrapeDetailsDialog
          data={scrapeDetails}
          onClose={() => setScrapeDetails(null)}
        />
      )}
      {scrapeDetailsError && (
        <p
          className="x-intelligence-state x-intelligence-state--error"
          role="alert"
        >
          {scrapeDetailsError}
        </p>
      )}
      {leadsOpen && (
        <CollectedLeadsDialog
          expectedTotal={dashboard.metrics.uniqueLeads}
          onClose={() => setLeadsOpen(false)}
        />
      )}
      {archivedOpen && (
        <ArchivedCompetitorsDialog
          error={archivedError}
          items={archivedItems}
          loading={archivedLoading}
          onClose={() => setArchivedOpen(false)}
          onRestore={restoreCompetitor}
        />
      )}
      {dialogOpen && (
        <div className="x-competitor-dialog-backdrop" role="presentation">
          <section
            aria-labelledby="add-competitor-title"
            aria-modal="true"
            className="x-competitor-dialog"
            role="dialog"
          >
            <header>
              <div>
                <h2 id="add-competitor-title">
                  {results ? "Competitor Added" : "Add Competitor"}
                </h2>
                <p>
                  {results
                    ? "Competitor result from canonical profile resolution."
                    : "Add one X account to Competitor Intelligence."}
                </p>
              </div>
              <button
                aria-label="Close Add Competitor"
                className="x-competitor-dialog__close"
                disabled={submitting}
                onClick={closeDialog}
              >
                <X size={18} />
              </button>
            </header>
            {results ? (
              <ImportResults
                onRestore={async (competitorId) => {
                  await restoreCompetitor(competitorId);
                  setResults((current) => current?.map((item) =>
                    item.competitorId === competitorId
                      ? { ...item, status: "ALREADY_TRACKED", reason: null }
                      : item,
                  ) ?? null);
                }}
                results={results}
              />
            ) : (
              <>
                <fieldset className="x-competitor-dialog__platform">
                  <legend>Creator Platform</legend>
                  {(["FANVUE", "ONLYFANS", "OTHER"] as const).map((platform) => (
                    <label key={platform}>
                      <input
                        checked={creatorPlatform === platform}
                        name="creator-platform"
                        onChange={() => setCreatorPlatform(platform)}
                        type="radio"
                        value={platform}
                      />
                      {platform === "FANVUE" ? "Fanvue" : platform === "ONLYFANS" ? "OnlyFans" : "Other"}
                    </label>
                  ))}
                </fieldset>
                <div className="x-competitor-dialog__field">
                  <label htmlFor="x-competitor-account">
                    X Username or Profile URL
                  </label>
                  <input
                    autoFocus
                    id="x-competitor-account"
                    onChange={(event) => setCompetitorInput(event.target.value)}
                    type="text"
                    value={competitorInput}
                  />
                  <small>Enter an X username or profile URL. No @ required.</small>
                  {validationError && (
                    <p className="x-competitor-dialog__error" role="alert">
                      {validationError}
                    </p>
                  )}
                </div>
                {submitError && (
                  <p className="x-competitor-dialog__error" role="alert">
                    {submitError}
                  </p>
                )}
                <footer>
                  <button disabled={submitting} onClick={closeDialog}>
                    Cancel
                  </button>
                  <button
                    disabled={!username || Boolean(validationError) || submitting}
                    onClick={() => void submit()}
                  >
                    {submitting ? "Adding Competitor…" : "Add Competitor"}
                  </button>
                </footer>
              </>
            )}
            {results && (
              <footer>
                <button onClick={closeDialog}>Done</button>
              </footer>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

function PostsViewer({
  data,
  onClose,
}: {
  data: XPosts7dResponse;
  onClose: () => void;
}) {
  const [sort, setSort] = useState<PostSort>("newest");
  const [view, setView] = useState<"recent" | "archived">("recent");
  const [archive, setArchive] = useState<
    (XPosts7dResponse & { page: number; pageSize: number }) | null
  >(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const current = view === "recent" ? data : archive;
  const posts = useMemo(
    () => sortCompetitorPosts(current?.posts || [], sort),
    [current?.posts, sort],
  );
  const loadArchive = async (page = 1) => {
    setLoading(true);
    setError("");
    try {
      setArchive(
        await xCompetitorIntelligenceApi.archivedPosts(
          data.competitor.id,
          page,
        ),
      );
      setView("archived");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to load archived posts.",
      );
    } finally {
      setLoading(false);
    }
  };
  const replacePost = (updated: XCompetitorPost) =>
    setArchive((value) =>
      value
        ? {
            ...value,
            posts: value.posts.map((post) =>
              post.id === updated.id ? updated : post,
            ),
          }
        : value,
    );
  return (
    <div className="x-competitor-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="x-post-viewer-title"
        aria-modal="true"
        className="x-competitor-dialog x-post-viewer"
        role="dialog"
      >
        <header>
          <div className="x-post-viewer__identity">
            {data.competitor.profileImageUrl && (
              <img alt="" src={data.competitor.profileImageUrl} />
            )}
            <div>
              <h2 id="x-post-viewer-title">
                {data.competitor.displayName || data.competitor.username}
              </h2>
              <p>@{data.competitor.username}</p>
              <strong>
                Posts — {view === "recent" ? "Last 7 Days" : "Archived"} ·{" "}
                {current?.count ?? 0}{" "}
                {(current?.count ?? 0) === 1 ? "post" : "posts"}
              </strong>
            </div>
          </div>
          <button
            aria-label="Close Posts viewer"
            className="x-competitor-dialog__close"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <div className="x-post-viewer__controls">
          <nav aria-label="Post history view" className="x-post-viewer__tabs">
            <button
              aria-pressed={view === "recent"}
              onClick={() => setView("recent")}
            >
              Last 7 Days
            </button>
            <button
              aria-pressed={view === "archived"}
              disabled={loading}
              onClick={() => void loadArchive()}
            >
              {loading ? "Loading…" : "Archived"}
            </button>
          </nav>
          <label className="x-post-viewer__sort">
            <span>Sort posts</span>
            <select
              aria-label="Sort competitor posts"
              onChange={(event) => setSort(event.target.value as PostSort)}
              value={sort}
            >
              <option value="newest">Newest</option>
              <option value="views">Most Views</option>
              <option value="likes">Most Likes</option>
              <option value="comments">Most Comments</option>
              <option value="retweets">Most Retweets</option>
              <option value="quotes">Most Quotes</option>
            </select>
          </label>
        </div>
        {error && (
          <p
            role="alert"
            className="x-intelligence-state x-intelligence-state--error"
          >
            {error}
          </p>
        )}
        <div className="x-post-viewer__list">
          {posts.map((post) => (
            <PostCard
              archived={view === "archived"}
              key={post.id}
              onUpdated={replacePost}
              post={post}
              username={data.competitor.username}
            />
          ))}
          {current && !posts.length && (
            <p className="x-intelligence-state">
              No qualifying{" "}
              {view === "recent"
                ? "posts in the trailing seven days"
                : "archived posts"}
              .
            </p>
          )}
        </div>
        {view === "archived" && archive && (
          <div className="x-post-viewer__pagination">
            <button
              disabled={archive.page <= 1 || loading}
              onClick={() => void loadArchive(archive.page - 1)}
            >
              Previous
            </button>
            <span>Page {archive.page}</span>
            <button
              disabled={
                archive.page * archive.pageSize >= archive.count || loading
              }
              onClick={() => void loadArchive(archive.page + 1)}
            >
              Next
            </button>
          </div>
        )}
        <footer>
          <button onClick={onClose}>Close</button>
        </footer>
      </section>
    </div>
  );
}

function CollectedLeadsDialog({
  expectedTotal,
  onClose,
}: {
  expectedTotal: number;
  onClose: () => void;
}) {
  const [data, setData] = useState<XCollectedLeadsResponse | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [sort, setSort] = useState<"account-asc" | "account-desc">(
    "account-asc",
  );
  const [loading, setLoading] = useState(true);
  const [copying, setCopying] = useState(false);
  const [copiedLeadId, setCopiedLeadId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    xCompetitorIntelligenceApi
      .collectedLeads(page, search, sort)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((reason) => {
        if (active)
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to load collected leads.",
          );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [page, search, sort]);
  const activate = () => {
    setPage(1);
    setSort((current) =>
      current === "account-asc" ? "account-desc" : "account-asc",
    );
  };
  const copyAll = async () => {
    if (copying) return;
    setCopying(true);
    setFeedback("");
    setError("");
    try {
      const result = await xCompetitorIntelligenceApi.collectedLeadUsernames();
      const payload = buildCollectedLeadClipboardText(result.usernames);
      await writeCollectedLeadClipboardText(payload);
      setFeedback(
        `Copied ${number(payload ? payload.split("\n").length : 0)} usernames`,
      );
    } catch {
      setError(
        "Unable to copy usernames. Check clipboard permission and try again.",
      );
    } finally {
      setCopying(false);
    }
  };
  const copyLead = async (lead: XCollectedLeadsResponse["items"][number]) => {
    const username = lead.username.trim().replace(/^@+/, "");
    if (!username) return;
    setError("");
    try {
      await navigator.clipboard.writeText(username);
      setCopiedLeadId(lead.id);
      window.setTimeout(
        () =>
          setCopiedLeadId((current) => (current === lead.id ? null : current)),
        1500,
      );
    } catch {
      setError(
        "Unable to copy username. Check clipboard permission and try again.",
      );
    }
  };
  return (
    <div className="x-competitor-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="x-collected-leads-title"
        aria-modal="true"
        className="x-competitor-dialog x-collected-leads"
        role="dialog"
      >
        <header>
          <div>
            <h2 id="x-collected-leads-title">Collected Leads</h2>
            <p>{number(data?.globalTotal ?? expectedTotal)} unique leads</p>
          </div>
          <button
            aria-label="Close Collected Leads"
            className="x-competitor-dialog__close"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <form
          className="x-collected-leads__search"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            setSearch(draft.trim());
          }}
        >
          <label htmlFor="x-collected-leads-search">Search leads...</label>
          <div>
            <input
              id="x-collected-leads-search"
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Search leads..."
              type="search"
              value={draft}
            />
            <button type="submit">Search</button>
            <button
              className="x-collected-leads__copy"
              disabled={copying}
              onClick={() => void copyAll()}
              type="button"
            >
              {copying ? "Copying…" : "Copy All"}
            </button>
          </div>
        </form>
        {search && data && (
          <p className="x-collected-leads__filtered">
            {number(data.total)} matching {data.total === 1 ? "lead" : "leads"}{" "}
            · {number(data.globalTotal)} total
          </p>
        )}
        {feedback && (
          <p className="x-collected-leads__feedback" role="status">
            {feedback}
          </p>
        )}
        {error && (
          <p
            className="x-intelligence-state x-intelligence-state--error"
            role="alert"
          >
            {error}
          </p>
        )}
        <div
          className="x-collected-leads__table"
          role="table"
          aria-label="Collected leads"
        >
          <div className="x-collected-leads__header" role="row">
            <span
              aria-sort={sort === "account-asc" ? "ascending" : "descending"}
              role="columnheader"
            >
              <button onClick={activate}>Account</button>
            </span>
          </div>
          {data?.items.map((lead) => {
            const username = lead.username.trim().replace(/^@+/, "");
            return (
              <div className="x-collected-leads__row" key={lead.id} role="row">
                <span className="x-intelligence-competitor" role="cell">
                  {lead.profileImageUrl ? (
                    <img alt="" src={lead.profileImageUrl} />
                  ) : (
                    <span className="x-intelligence-competitor__avatar">
                      {(lead.displayName || lead.username || "?")
                        .slice(0, 1)
                        .toUpperCase()}
                    </span>
                  )}
                  <span>
                    <strong>
                      {lead.displayName || username || "Unknown account"}
                    </strong>
                    <small>
                      {username ? `@${username}` : "Username unavailable"}
                    </small>
                  </span>
                </span>
                {username && (
                  <button
                    className="x-collected-leads__row-copy"
                    onClick={() => void copyLead(lead)}
                    type="button"
                  >
                    {copiedLeadId === lead.id ? "Copied" : "Copy"}
                  </button>
                )}
              </div>
            );
          })}
          {!loading && data && !data.items.length && (
            <p className="x-intelligence-state">No collected leads yet.</p>
          )}
          {loading && (
            <p className="x-intelligence-state">Loading collected leads…</p>
          )}
        </div>
        {data && data.total > data.pageSize && (
          <div className="x-post-viewer__pagination">
            <button
              disabled={loading || page <= 1}
              onClick={() => setPage((value) => value - 1)}
            >
              Previous
            </button>
            <span>
              Page {page} of {Math.ceil(data.total / data.pageSize)}
            </span>
            <button
              disabled={loading || page * data.pageSize >= data.total}
              onClick={() => setPage((value) => value + 1)}
            >
              Next
            </button>
          </div>
        )}
        <footer>
          <button onClick={onClose}>Close</button>
        </footer>
      </section>
    </div>
  );
}

type TelegramDetailState = {
  presence: XCompetitor["telegramPresence"];
  telegramUrl: string;
  audienceType: XCompetitor["telegramAudienceType"];
  commentsAllowed: boolean | null;
  joined: boolean | null;
  scraped: boolean;
};
function TelegramCompetitorDetail({
  item,
  onArchived,
  onClose,
  onUpdated,
}: {
  item: XCompetitor;
  onArchived: (competitorId: string) => void;
  onClose: () => void;
  onUpdated: (item: XCompetitor) => void;
}) {
  const normalizedUsername = item.username.trim().replace(/^@+/, "");
  const initial: TelegramDetailState = {
    presence: item.telegramPresence,
    telegramUrl: item.telegramUrl || "",
    audienceType: item.telegramAudienceType,
    commentsAllowed: item.telegramCommentsAllowed,
    joined: item.telegramJoined,
    scraped: item.telegramScraped,
  };
  const [value, setValue] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [confirmArchive, setConfirmArchive] = useState(false);
  const [archiving, setArchiving] = useState(false);
  useEffect(
    () =>
      setValue({
        presence: item.telegramPresence,
        telegramUrl: item.telegramUrl || "",
        audienceType: item.telegramAudienceType,
        commentsAllowed: item.telegramCommentsAllowed,
        joined: item.telegramJoined,
        scraped: item.telegramScraped,
      }),
    [
      item.id,
      item.telegramPresence,
      item.telegramUrl,
      item.telegramAudienceType,
      item.telegramCommentsAllowed,
      item.telegramJoined,
      item.telegramScraped,
    ],
  );
  const validTelegramUrl = (candidate: string) => {
    if (!candidate.trim()) return true;
    try {
      const parsed = new URL(candidate.trim());
      return (
        parsed.protocol === "https:" &&
        parsed.hostname.toLowerCase() === "t.me" &&
        parsed.pathname.replaceAll("/", "").length > 0
      );
    } catch {
      return false;
    }
  };
  const persist = async (next: TelegramDetailState) => {
    if (saving) return;
    const trimmed = next.telegramUrl.trim();
    if (!validTelegramUrl(trimmed)) {
      setError("Enter a valid full Telegram URL beginning with https://t.me/.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const saved = await xCompetitorIntelligenceApi.updateTelegramIntelligence(
        item.id,
        { ...next, telegramUrl: trimmed || null },
      );
      setValue({ ...next, telegramUrl: saved.telegramUrl || "" });
      onUpdated({
        ...item,
        telegramPresence: saved.presence,
        telegramUrl: saved.telegramUrl,
        telegramAudienceType: saved.audienceType,
        telegramCommentsAllowed: saved.commentsAllowed,
        telegramJoined: saved.joined,
        telegramScraped: saved.scraped ?? next.scraped,
      });
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to save Telegram intelligence.",
      );
    } finally {
      setSaving(false);
    }
  };
  const updateAndPersist = (next: TelegramDetailState) => {
    setValue(next);
    void persist(next);
  };
  const audience = (type: "SUBSCRIBERS" | "MEMBERS") =>
    updateAndPersist({
      ...value,
      audienceType: value.audienceType === type ? null : type,
    });
  const metrics = [
    ["Followers", number(item.followersCount)],
    ["7D Growth", percent(item.growth7d?.percent)],
    ["30D Growth", percent(item.growth30d?.percent)],
    ["Last Active", formatLastActive(item.lastActiveAt)],
    ["Posts 7D", number(item.posts7d)],
    ["Engagement", percent(item.engagementRate)],
  ];
  const archive = async () => {
    if (archiving) return;
    setArchiving(true);setError("");
    try {
      await xCompetitorIntelligenceApi.archiveCompetitor(item.id);
      onArchived(item.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to archive competitor.");
      setConfirmArchive(false);
    } finally {
      setArchiving(false);
    }
  };
  return (
    <div className="x-competitor-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="x-competitor-detail-title"
        aria-modal="true"
        className="x-competitor-dialog x-competitor-detail"
        role="dialog"
      >
        <header>
          <div className="x-post-viewer__identity">
            {item.profileImageUrl && <img alt="" src={item.profileImageUrl} />}
            <div>
              <h2 id="x-competitor-detail-title">
                {item.displayName || item.username}
              </h2>
              <p>
                <a
                  className="x-competitor-detail__profile-link"
                  href={`https://x.com/${encodeURIComponent(normalizedUsername)}`}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  @{normalizedUsername}
                </a>
              </p>
            </div>
          </div>
          <button
            aria-label="Close competitor detail"
            className="x-competitor-dialog__close"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <div className="x-competitor-detail__metrics">
          {metrics.map(([label, metric]) => (
            <article key={label}>
              <span>{label}</span>
              <strong>{metric}</strong>
            </article>
          ))}
        </div>
        <section aria-label="Refresh schedule" className="x-competitor-refresh">
          <h3>Refresh</h3>
          <div>
            <strong>Last Refresh</strong>
            <span>{formatRefreshDate(item.refresh.lastSuccessfulAt)}</span>
          </div>
          <div>
            <strong>Next Refresh</strong>
            <span>
              {item.refresh.due
                ? "Due"
                : formatRefreshDate(item.refresh.nextRefreshAt)}
            </span>
          </div>
        </section>
        {item.accountRole === "COMPETITOR" && <section
          aria-label="Telegram intelligence"
          className="x-competitor-telegram"
        >
          <h3>Telegram</h3>
          <fieldset className="x-competitor-telegram__presence">
            <legend>Do they have a Telegram?</legend>
            <div className="x-competitor-telegram__presence-row">
            <button
              aria-pressed={value.presence === "YES"}
              className={value.presence === "YES" ? "is-selected" : ""}
              disabled={saving}
              onClick={() => updateAndPersist({ ...value, presence: "YES" })}
              type="button"
            >
              Yes
            </button>
            <button
              aria-pressed={value.presence === "NO"}
              className={value.presence === "NO" ? "is-selected" : ""}
              disabled={saving}
              onClick={() => updateAndPersist({ ...value, presence: "NO" })}
              type="button"
            >
              No
            </button>
            {value.presence === "YES" && (
              <label className="x-competitor-telegram__link">
                <span>Telegram Link</span>
                <div>
                  <input
                    aria-label="Telegram Link"
                    aria-invalid={!validTelegramUrl(value.telegramUrl)}
                    disabled={saving}
                    onBlur={() => void persist(value)}
                    onChange={(event) => {
                      setError("");
                      setValue((current) => ({ ...current, telegramUrl: event.target.value }));
                    }}
                    type="url"
                    value={value.telegramUrl}
                  />
                  {value.telegramUrl && validTelegramUrl(value.telegramUrl) && (
                    <a aria-label="Open Telegram link" href={value.telegramUrl.trim()} rel="noopener noreferrer" target="_blank">
                      <ExternalLink size={16} />
                    </a>
                  )}
                </div>
              </label>
            )}
            </div>
          </fieldset>
          {value.presence === "YES" && (
            <>
              <div className="x-competitor-telegram__options">
                <span>Audience</span>
                <label>
                  <input
                    checked={value.joined === true}
                    disabled={saving}
                    onChange={() => updateAndPersist({ ...value, joined: value.joined !== true })}
                    type="checkbox"
                  />
                  Joined
                </label>
                <label>
                  <input
                    checked={value.audienceType === "SUBSCRIBERS"}
                    disabled={saving}
                    onChange={() => audience("SUBSCRIBERS")}
                    type="checkbox"
                  />
                  Subscribers
                </label>
                <label>
                  <input
                    checked={value.scraped}
                    disabled={saving}
                    onChange={() => updateAndPersist({ ...value, scraped: !value.scraped })}
                    type="checkbox"
                  />
                  Scraped
                </label>
              </div>
            </>
          )}
          {error && (
            <small className="x-competitor-telegram__error" role="alert">
              {error}
            </small>
          )}
        </section>}
        <footer className="x-competitor-detail__footer">
          {item.accountRole === "COMPETITOR" && <button className="x-competitor-detail__archive" onClick={() => setConfirmArchive(true)}>Archive</button>}
          <button onClick={onClose}>Close</button>
        </footer>
      </section>
      {confirmArchive && (
        <div className="x-competitor-dialog-backdrop x-competitor-dialog-backdrop--nested" role="presentation">
          <section aria-labelledby="archive-competitor-title" aria-modal="true" className="x-competitor-dialog x-competitor-archive-confirm" role="dialog">
            <h2 id="archive-competitor-title">Archive {item.displayName || item.username}?</h2>
            <p>{item.displayName || item.username} will be removed from your active X Competitor Intelligence list and will no longer be automatically refreshed or scraped. All previously collected intelligence will remain stored and can be restored later.</p>
            <footer><button disabled={archiving} onClick={() => setConfirmArchive(false)}>Cancel</button><button className="x-competitor-detail__archive" disabled={archiving} onClick={() => void archive()}>{archiving ? "Archiving…" : "Archive"}</button></footer>
          </section>
        </div>
      )}
    </div>
  );
}

function BenchmarkAccount({item,onDetails,onPosts,postsLoading}:{item:XCompetitor;onDetails:()=>void;onPosts:()=>void;postsLoading:boolean}) {
  const username=item.username.trim().replace(/^@+/,"");
  const metrics=[
    ["Followers",number(item.followersCount)],
    ["7D Growth",percent(item.growth7d?.percent)],
    ["30D Growth",percent(item.growth30d?.percent)],
    ["Last Active",formatLastActive(item.lastActiveAt)],
    ["Posts 7D",number(item.posts7d)],
    ["Engagement",percent(item.engagementRate)],
  ];
  return <section aria-label="Your benchmark account" className="x-benchmark-account">
    <span className="x-benchmark-account__label">Your Account</span>
    <div className="x-benchmark-account__identity">
      {item.profileImageUrl?<img alt="" src={item.profileImageUrl}/>:<span className="x-intelligence-competitor__avatar">{(item.displayName||username).slice(0,1).toUpperCase()}</span>}
      <span><button onClick={onDetails} type="button"><strong>{item.displayName||username}</strong></button><a href={`https://x.com/${encodeURIComponent(username)}`} onClick={event=>event.stopPropagation()} rel="noopener noreferrer" target="_blank">@{username}</a></span>
    </div>
    <div className="x-benchmark-account__metrics">{metrics.map(([label,value])=><span key={label}><small>{label}</small>{label==="Posts 7D"&&item.posts7d!==null?<button disabled={postsLoading} onClick={onPosts}>{value}</button>:<strong>{value}</strong>}</span>)}</div>
    <small className="x-benchmark-account__engagement">{number(item.comments7d)} comments · {number(item.retweets7d)} retweets · {number(item.quotes7d)} quotes</small>
    {formatLastRefreshDate(item.refresh?.lastSuccessfulAt ?? null)&&<small className="x-intelligence-refresh-metadata x-benchmark-account__refresh-position">{formatLastRefreshDate(item.refresh?.lastSuccessfulAt ?? null)}</small>}
  </section>;
}

function ScrapeDetailsDialog({
  data,
  onClose,
}: {
  data: XAudienceRunDiagnostics;
  onClose: () => void;
}) {
  const { run, competitor, sourceStatus, failures } = data;
  const completed = run.completedAt || run.startedAt;
  const sources: [
    [string, typeof sourceStatus.replies],
    [string, typeof sourceStatus.replies],
    [string, typeof sourceStatus.replies],
  ] = [
    ["Replies", sourceStatus.replies],
    ["Retweets", sourceStatus.retweets],
    ["Quotes", sourceStatus.quotes],
  ];
  return (
    <div className="x-competitor-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="x-scrape-details-title"
        aria-modal="true"
        className="x-competitor-dialog x-scrape-details"
        role="dialog"
      >
        <header>
          <div className="x-post-viewer__identity">
            {competitor.profileImageUrl ? (
              <img alt="" src={competitor.profileImageUrl} />
            ) : (
              <span className="x-intelligence-competitor__avatar">
                {(competitor.displayName || competitor.username)
                  .slice(0, 1)
                  .toUpperCase()}
              </span>
            )}
            <div>
              <h2 id="x-scrape-details-title">Scrape Details</h2>
              <strong>{competitor.displayName || competitor.username}</strong>
              <p>@{competitor.username}</p>
              <small>
                {formatGlobalRefresh(completed)} ·{" "}
                {run.status.charAt(0) + run.status.slice(1).toLowerCase()}
              </small>
            </div>
          </div>
          <button
            aria-label="Close scrape details"
            className="x-competitor-dialog__close"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <section
          className="x-audience-summary"
          aria-label="Collection run summary"
        >
          <h3>Run Summary</h3>
          <dl>
            <SummaryRow label="Posts Processed" value={run.postsProcessed} />
            <SummaryRow label="Replies Returned" value={run.repliesReturned} />
            <SummaryRow
              label="Retweeters Returned"
              value={run.retweetersReturned}
            />
            <SummaryRow label="Quotes Returned" value={run.quotesReturned} />
            <SummaryRow
              label="Unique Users Found"
              value={run.uniqueUsersObserved}
            />
            <SummaryRow label="New Users Added" value={run.newUsers} />
            <SummaryRow label="Already in Database" value={run.existingUsers} />
            <SummaryRow label="New Signals" value={run.newSignals} />
            <SummaryRow label="Existing Signals" value={run.existingSignals} />
            <SummaryRow
              label="Provider Requests"
              value={run.providerRequests}
            />
            <SummaryRow
              label="Successful Sources"
              value={sources.reduce(
                (total, [, value]) => total + value.complete,
                0,
              )}
            />
            <SummaryRow label="Failed Sources" value={failures.length} />
          </dl>
        </section>
        <section className="x-scrape-details__sources">
          <h3>Source Status</h3>
          {sources.map(([label, value]) => (
            <div key={label}>
              <strong>{label}</strong>
              <span>
                {value.complete} complete · {value.failed} failed
              </span>
            </div>
          ))}
        </section>
        <section className="x-scrape-details__failures">
          <h3>Failures</h3>
          {failures.length ? (
            failures.map((failure) => (
              <article key={`${failure.sourceType}-${failure.sourceTweetId}`}>
                <strong>
                  {failure.sourceType} · Post {failure.sourceTweetId}
                </strong>
                <span>
                  {new Intl.DateTimeFormat("en-US", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(failure.postedAt))}
                </span>
                {failure.textPreview && <p>{failure.textPreview}</p>}
                <span>
                  {failure.pagesCompleted}{" "}
                  {failure.pagesCompleted === 1 ? "page" : "pages"} completed
                  {failure.pagesCompleted > 0 ? " · Failed on next page" : ""}
                </span>
                <span>
                  Reason:{" "}
                  {failure.reason ||
                    "Detailed failure information is unavailable for this collection."}
                </span>
                <a
                  href={`https://x.com/${encodeURIComponent(competitor.username)}/status/${encodeURIComponent(failure.sourceTweetId)}`}
                  rel="noreferrer"
                  target="_blank"
                >
                  Open on X
                </a>
              </article>
            ))
          ) : (
            <p>
              Detailed failure information is unavailable for this collection.
            </p>
          )}
        </section>
        <footer>
          <button onClick={onClose}>Close</button>
        </footer>
      </section>
    </div>
  );
}

function SummaryRow({
  label,
  value,
  interactive = false,
  onClick,
}: {
  label: string;
  value: number;
  interactive?: boolean;
  onClick?: () => void;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>
        {interactive ? (
          <button
            className="x-audience-summary__count"
            disabled={!interactive}
            onClick={onClick}
          >
            {value}
          </button>
        ) : (
          value
        )}
      </dd>
    </div>
  );
}

function AudienceRunUsersDialog({
  data,
  onClose,
  loading,
}: {
  data: XAudienceRunUsers;
  onClose: () => void;
  loading: boolean;
}) {
  const title =
    data.classification === "NEW" ? "New Users Added" : "Already in Database";
  return (
    <div
      className="x-competitor-dialog-backdrop x-competitor-dialog-backdrop--nested"
      role="presentation"
    >
      <section
        aria-labelledby="x-audience-users-title"
        aria-modal="true"
        className="x-competitor-dialog x-audience-users"
        role="dialog"
      >
        <header>
          <div>
            <h2 id="x-audience-users-title">{title}</h2>
            <p>
              {data.count} {data.count === 1 ? "account" : "accounts"} in this
              collection run
            </p>
          </div>
          <button
            aria-label={`Close ${title}`}
            className="x-competitor-dialog__close"
            disabled={loading}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        <div className="x-audience-users__list">
          {data.users.map((user) => (
            <article key={user.id}>
              {user.profileImageUrl ? (
                <img alt="" src={user.profileImageUrl} />
              ) : (
                <span className="x-intelligence-competitor__avatar">
                  {(user.displayName || user.username)
                    .slice(0, 1)
                    .toUpperCase()}
                </span>
              )}
              <div>
                <strong>{user.displayName || user.username}</strong>
                <small>@{user.username}</small>
                <span>
                  {user.signalTypes.join(" · ")} · {user.sourcePosts} source{" "}
                  {user.sourcePosts === 1 ? "post" : "posts"}
                </span>
                {data.classification === "EXISTING" && (
                  <span>
                    {user.previousCompetitors > 0
                      ? `Previously seen with ${user.previousCompetitors} ${user.previousCompetitors === 1 ? "competitor" : "competitors"}`
                      : user.knownFrom
                        ? `Known from ${user.knownFrom}`
                        : "Previously stored in Audience"}
                  </span>
                )}
              </div>
            </article>
          ))}
        </div>
        <footer>
          <button onClick={onClose}>Close</button>
        </footer>
      </section>
    </div>
  );
}

function GrowthValue({ value }: { value: XCompetitor["growth7d"] }) {
  if (!value) return <span role="cell">—</span>;
  const sign = value.percent > 0 ? "+" : "";
  const rawSign = value.raw > 0 ? "+" : "";
  return (
    <span
      className={`x-growth-value ${value.percent > 0 ? "is-positive" : value.percent < 0 ? "is-negative" : "is-neutral"}`}
      role="cell"
      title={`Compared with ${new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(new Date(value.baselineObservedAt))}`}
    >
      <strong>
        {sign}
        {value.percent.toFixed(1)}%
      </strong>
      <small>
        {rawSign}
        {new Intl.NumberFormat("en-US").format(value.raw)}
      </small>
    </span>
  );
}

function EngagementViewer({
  data,
  onClose,
}: {
  data: XEngagementResponse;
  onClose: () => void;
}) {
  const metric = (label: string, value: number | null) => (
    <article>
      <span>{label}</span>
      <strong>{percent(value)}</strong>
    </article>
  );
  const typical = [
    ["Views", data.typical.view],
    ["Likes", data.typical.like],
    ["Comments", data.typical.comments],
    ["Retweets", data.typical.retweet],
    ["Quotes", data.typical.quote],
    ["Interactions", data.typical.interactions],
  ] as const;
  return (
    <div className="x-competitor-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="x-engagement-title"
        aria-modal="true"
        className="x-competitor-dialog x-engagement-viewer"
        role="dialog"
      >
        <header>
          <div className="x-post-viewer__identity">
            {data.competitor.profileImageUrl && (
              <img alt="" src={data.competitor.profileImageUrl} />
            )}
            <div>
              <h2 id="x-engagement-title">
                {data.competitor.displayName || data.competitor.username}
              </h2>
              <p>@{data.competitor.username}</p>
              <strong>
                Engagement — Last 7 Days · {data.sampleSize}{" "}
                {data.sampleSize === 1 ? "post" : "posts"} analyzed
              </strong>
            </div>
          </div>
          <button
            aria-label="Close Engagement viewer"
            className="x-competitor-dialog__close"
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </header>
        {data.sampleSize === 0 ? (
          <p className="x-intelligence-state">
            No qualifying posts in the last 7 days.
          </p>
        ) : (
          <>
            <section>
              <h3>Overall Analytics</h3>
              <div className="x-engagement-metrics">
                {metric(
                  "Median Follower Engagement",
                  data.medianFollowerEngagementRate,
                )}
                {metric(
                  "Median Viewed Engagement",
                  data.medianViewedEngagementRate,
                )}
                {metric("Median Reach Ratio", data.medianReachRatio)}
              </div>
            </section>
            <section>
              <h3>Typical Post</h3>
              <div className="x-engagement-typical">
                {typical.map(([label, value]) => (
                  <article key={label}>
                    <span>{label}</span>
                    <strong>{number(value.median)}</strong>
                    <small>Average {number(value.average)}</small>
                  </article>
                ))}
              </div>
            </section>
            <section>
              <h3>Engagement Mix</h3>
              <div className="x-engagement-mix">
                {(["like", "comments", "retweet", "quote"] as const).map(
                  (key) => (
                    <div key={key}>
                      <span>
                        {key === "like"
                          ? "Likes"
                          : key === "comments"
                            ? "Comments"
                            : key === "retweet"
                              ? "Retweets"
                              : "Quotes"}
                      </span>
                      <strong>{percent(data.mix[key])}</strong>
                    </div>
                  ),
                )}
              </div>
            </section>
            <section>
              <h3>Consistency</h3>
              <div className="x-engagement-consistency">
                <span>
                  Low <strong>{percent(data.consistency.minimum)}</strong>
                </span>
                <span>
                  Q1 <strong>{percent(data.consistency.q1)}</strong>
                </span>
                <span>
                  Median <strong>{percent(data.consistency.median)}</strong>
                </span>
                <span>
                  Q3 <strong>{percent(data.consistency.q3)}</strong>
                </span>
                <span>
                  High <strong>{percent(data.consistency.maximum)}</strong>
                </span>
              </div>
              <p>
                Typical Range: {percent(data.consistency.q1)} –{" "}
                {percent(data.consistency.q3)}
              </p>
            </section>
            <section>
              <h3>Top Recent Posts</h3>
              <div className="x-engagement-top-posts">
                {data.topPosts.map((post) => (
                  <article key={post.id}>
                    {(() => {
                      const media = post.mediaMetadata.find(
                        (item) =>
                          typeof item.media_url_https === "string" ||
                          typeof item.url === "string",
                      );
                      const source = media
                        ? String(media.media_url_https || media.url)
                        : null;
                      return source && /^https:\/\//i.test(source) ? (
                        <img alt="Post thumbnail" src={source} />
                      ) : null;
                    })()}
                    <div>
                      <p>{post.text || "—"}</p>
                      <time dateTime={post.postedAt}>
                        {new Intl.DateTimeFormat("en-US", {
                          dateStyle: "medium",
                        }).format(new Date(post.postedAt))}
                      </time>
                      <dl>
                        <div>
                          <dt>Follower ER</dt>
                          <dd>{percent(post.followerEngagementRate)}</dd>
                        </div>
                        <div>
                          <dt>Views</dt>
                          <dd>{number(post.viewCount)}</dd>
                        </div>
                        <div>
                          <dt>Likes</dt>
                          <dd>{number(post.likeCount)}</dd>
                        </div>
                        <div>
                          <dt>Comments</dt>
                          <dd>{number(post.replyCount)}</dd>
                        </div>
                        <div>
                          <dt>Retweets</dt>
                          <dd>{number(post.retweetCount)}</dd>
                        </div>
                        <div>
                          <dt>Quotes</dt>
                          <dd>{number(post.quoteCount)}</dd>
                        </div>
                      </dl>
                      <a
                        href={`https://x.com/${encodeURIComponent(data.competitor.username)}/status/${encodeURIComponent(post.xTweetId)}`}
                        rel="noopener noreferrer"
                        target="_blank"
                      >
                        Open on X
                      </a>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </>
        )}
        <footer>
          <button onClick={onClose}>Close</button>
        </footer>
      </section>
    </div>
  );
}

function PostCard({
  post,
  username,
  archived = false,
  onUpdated,
}: {
  post: XCompetitorPost;
  username: string;
  archived?: boolean;
  onUpdated?: (post: XCompetitorPost) => void;
}) {
  const [refreshing, setRefreshing] = useState(false);
  const [feedback, setFeedback] = useState("");
  const media = post.mediaMetadata.find(
    (item) =>
      typeof item.media_url_https === "string" || typeof item.url === "string",
  );
  const mediaUrl = media ? String(media.media_url_https || media.url) : null;
  const metric = (value: number | null) =>
    value === null ? "—" : number(value);
  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    setFeedback("");
    try {
      const result = await xCompetitorIntelligenceApi.refreshPostMetrics(
        post.id,
        crypto.randomUUID(),
      );
      onUpdated?.(result.post);
      setFeedback("Metrics refreshed");
    } catch (reason) {
      setFeedback(
        reason instanceof Error ? reason.message : "Unable to refresh metrics.",
      );
    } finally {
      setRefreshing(false);
    }
  };
  return (
    <article className="x-post-card">
      {mediaUrl && /^https:\/\//i.test(mediaUrl) && (
        <img alt="Post media" src={mediaUrl} />
      )}
      <p>{post.text || "—"}</p>
      <time dateTime={post.postedAt}>
        {new Intl.DateTimeFormat("en-US", {
          dateStyle: "medium",
          timeStyle: "short",
        }).format(new Date(post.postedAt))}
      </time>
      {archived && (
        <small>
          Metrics last observed{" "}
          {post.lastMetricObservedAt
            ? new Intl.DateTimeFormat("en-US", { dateStyle: "medium" }).format(
                new Date(post.lastMetricObservedAt),
              )
            : "—"}
        </small>
      )}
      <dl>
        <div>
          <dt>Views</dt>
          <dd>{metric(post.viewCount)}</dd>
        </div>
        <div>
          <dt>Likes</dt>
          <dd>{metric(post.likeCount)}</dd>
        </div>
        <div>
          <dt>Comments</dt>
          <dd>{metric(post.replyCount)}</dd>
        </div>
        <div>
          <dt>Retweets</dt>
          <dd>{metric(post.retweetCount)}</dd>
        </div>
        <div>
          <dt>Quotes</dt>
          <dd>{metric(post.quoteCount)}</dd>
        </div>
      </dl>
      {feedback && <small role="status">{feedback}</small>}
      <footer>
        {archived && (
          <button disabled={refreshing} onClick={() => void refresh()}>
            {refreshing ? "Refreshing…" : "Refresh Metrics"}
          </button>
        )}
        <a
          href={`https://x.com/${encodeURIComponent(username)}/status/${encodeURIComponent(post.xTweetId)}`}
          rel="noopener noreferrer"
          target="_blank"
        >
          Open on X
        </a>
      </footer>
    </article>
  );
}

function ImportResults({ results, onRestore }: { results: XImportResult[]; onRestore: (competitorId: string) => Promise<void> }) {
  const [restoreCandidate,setRestoreCandidate]=useState<XImportResult|null>(null);
  const [restoring,setRestoring]=useState(false);
  const [restoreError,setRestoreError]=useState("");
  const counts = (status: XImportResult["status"]) =>
    results.filter((item) => item.status === status).length;
  const notices = results.filter(
    (item) =>
      item.status === "NOT_FOUND" ||
      item.status === "FAILED" ||
      item.status === "ARCHIVED" ||
      item.activityStatus === "FAILED",
  );
  return (
    <div className="x-competitor-results">
      <dl>
        <div>
          <dt>Added</dt>
          <dd>{counts("ADDED")}</dd>
        </div>
        <div>
          <dt>Already Tracked</dt>
          <dd>{counts("ALREADY_TRACKED")}</dd>
        </div>
        <div>
          <dt>Not Found</dt>
          <dd>{counts("NOT_FOUND")}</dd>
        </div>
        <div>
          <dt>Failed</dt>
          <dd>{counts("FAILED")}</dd>
        </div>
      </dl>
      {notices.length > 0 && (
        <ul>
          {notices.map((item) => (
            <li key={item.submittedUsername}>
              <strong>@{item.submittedUsername}</strong>
              <span>
                {item.activityStatus === "FAILED"
                  ? "Added — Activity needs refresh"
                  : item.reason}
              </span>
              {item.status === "ARCHIVED" && item.competitorId && <button onClick={() => setRestoreCandidate(item)}>Restore</button>}
            </li>
          ))}
        </ul>
      )}
      {restoreError && <p role="alert">{restoreError}</p>}
      {restoreCandidate?.competitorId && <div className="x-competitor-dialog-backdrop x-competitor-dialog-backdrop--nested" role="presentation"><section aria-labelledby="restore-archived-title" aria-modal="true" className="x-competitor-dialog" role="dialog"><h2 id="restore-archived-title">This competitor is archived. Restore them?</h2><footer><button disabled={restoring} onClick={() => setRestoreCandidate(null)}>Cancel</button><button disabled={restoring} onClick={async()=>{setRestoring(true);setRestoreError("");try{await onRestore(restoreCandidate.competitorId!);setRestoreCandidate(null);}catch(reason){setRestoreError(reason instanceof Error?reason.message:"Unable to restore competitor.");}finally{setRestoring(false);}}}>{restoring?"Restoring…":"Restore"}</button></footer></section></div>}
    </div>
  );
}

function ArchivedCompetitorsDialog({items,loading,error,onClose,onRestore}:{items:XArchivedCompetitor[];loading:boolean;error:string;onClose:()=>void;onRestore:(competitorId:string)=>Promise<void>}) {
  const [restoring,setRestoring]=useState<string|null>(null);
  const [actionError,setActionError]=useState("");
  return <div className="x-competitor-dialog-backdrop" role="presentation"><section aria-labelledby="archived-competitors-title" aria-modal="true" className="x-competitor-dialog x-archived-competitors" role="dialog"><header><div><h2 id="archived-competitors-title">Archived Competitors</h2><p>Stored intelligence is preserved and can be restored.</p></div><button aria-label="Close Archived Competitors" className="x-competitor-dialog__close" onClick={onClose}><X size={18}/></button></header>{loading?<p>Loading archived competitors…</p>:error?<p role="alert">{error}</p>:items.length===0?<p>No archived competitors.</p>:<div className="x-archived-competitors__list">{items.map(item=><article key={item.id}><div><span className="x-archived-competitors__name"><strong>{item.displayName||item.username}</strong><PlatformBadge platform={item.platform}/></span><small>@{item.username}</small></div><span>{number(item.followersCount)} followers</span><time dateTime={item.archivedAt}>{new Intl.DateTimeFormat("en-US",{month:"short",day:"numeric",year:"numeric"}).format(new Date(item.archivedAt))}</time><button disabled={restoring===item.id} onClick={async()=>{setRestoring(item.id);setActionError("");try{await onRestore(item.id);}catch(reason){setActionError(reason instanceof Error?reason.message:"Unable to restore competitor.");}finally{setRestoring(null);}}}>{restoring===item.id?"Restoring…":"Restore"}</button></article>)}</div>}{actionError&&<p role="alert">{actionError}</p>}<footer><button onClick={onClose}>Close</button></footer></section></div>;
}
