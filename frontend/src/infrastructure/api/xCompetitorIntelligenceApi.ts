import { environment } from "../config/environment";

export type XGrowth = {
  raw: number;
  percent: number;
  baselineObservedAt: string;
  currentObservedAt: string;
};
export type XTelegramIntelligence = {
  presence: "UNKNOWN" | "YES" | "NO";
  telegramUrl: string | null;
  audienceType: "SUBSCRIBERS" | "MEMBERS" | null;
  commentsAllowed: boolean | null;
  joined: boolean | null;
  scraped: boolean;
};
export type XRefreshSchedule = {
  lastSuccessfulAt: string | null;
  nextRefreshAt: string | null;
  due: boolean;
};
export type XCreatorPlatform = "FANVUE" | "ONLYFANS" | "OTHER";
export type XCompetitor = {
  id: string;
  xUserId: string | null;
  username: string;
  displayName: string | null;
  profileImageUrl: string | null;
  accountRole: "COMPETITOR" | "OWN_ACCOUNT";
  platform: XCreatorPlatform;
  trackingEnabled: boolean;
  telegramPresence: XTelegramIntelligence["presence"];
  telegramUrl: string | null;
  telegramAudienceType: XTelegramIntelligence["audienceType"];
  telegramCommentsAllowed: boolean | null;
  telegramJoined: boolean | null;
  telegramScraped: boolean;
  followersCount: number | null;
  createdAt: string;
  observedAt: string | null;
  lastActiveAt: string | null;
  lastAudienceScrapedAt: string | null;
  lastAudienceScrapeStatus:
    "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED" | null;
  lastAudienceRunId: string | null;
  posts7d: number | null;
  comments7d: number | null;
  retweets7d: number | null;
  quotes7d: number | null;
  engagementRate: number | null;
  audienceCount: number | null;
  growth7d: XGrowth | null;
  growth30d: XGrowth | null;
  refresh: XRefreshSchedule;
};
export type XAudienceSourceSummary = { requests: number; failed: number };
export type XAudienceCollection = {
  runId: string;
  status: "SUCCEEDED" | "PARTIAL" | "FAILED";
  completedAt: string;
  postsConsidered: number;
  postsProcessed: number;
  repliesReturned: number;
  retweetersReturned: number;
  quotesReturned: number;
  uniqueUsersObserved: number;
  newUsers: number;
  existingUsers: number;
  newSignals: number;
  existingSignals: number;
  providerRequests: number;
  failedSources: number;
  sourceBreakdown: {
    replies: XAudienceSourceSummary;
    retweets: XAudienceSourceSummary;
    quotes: XAudienceSourceSummary;
  };
};
export type XAudienceRunUser = {
  id: string;
  xUserId: string;
  username: string;
  displayName: string | null;
  profileImageUrl: string | null;
  signalTypes: ("REPLY" | "RETWEET" | "QUOTE")[];
  sourcePosts: number;
  previousCompetitors: number;
  knownFrom: string | null;
};
export type XAudienceRunUsers = {
  runId: string;
  classification: "NEW" | "EXISTING";
  count: number;
  users: XAudienceRunUser[];
};
export type XAudienceRunDiagnostics = {
  run: {
    id: string;
    competitorId: string;
    status: "RUNNING" | "SUCCEEDED" | "PARTIAL" | "FAILED";
    startedAt: string;
    completedAt: string | null;
    postsConsidered: number;
    postsProcessed: number;
    repliesReturned: number;
    retweetersReturned: number;
    quotesReturned: number;
    uniqueUsersObserved: number;
    newUsers: number;
    existingUsers: number;
    newSignals: number;
    existingSignals: number;
    providerRequests: number;
  };
  competitor: Pick<
    XCompetitor,
    "id" | "username" | "displayName" | "profileImageUrl"
  >;
  sourceStatus: {
    replies: XAudienceDiagnosticSource;
    retweets: XAudienceDiagnosticSource;
    quotes: XAudienceDiagnosticSource;
  };
  failures: {
    sourceType: "REPLY" | "RETWEET" | "QUOTE";
    sourceTweetId: string;
    postedAt: string;
    textPreview: string | null;
    pagesCompleted: number;
    reason: string | null;
  }[];
};
export type XAudienceDiagnosticSource = { complete: number; failed: number };
export type XCollectedLead = {
  id: string;
  xUserId: string;
  username: string;
  displayName: string | null;
  profileImageUrl: string | null;
  hasReply: boolean;
  hasRetweet: boolean;
  hasQuote: boolean;
  competitorCount: number;
};
export type XCollectedLeadsResponse = {
  items: XCollectedLead[];
  total: number;
  globalTotal: number;
  page: number;
  pageSize: number;
  search: string;
  sort: "account-asc" | "account-desc" | "competitors-desc" | "competitors-asc";
};
export type XImportResult = {
  competitorId?: string;
  submittedUsername: string;
  resolvedUsername: string | null;
  status: "ADDED" | "ALREADY_TRACKED" | "ARCHIVED" | "NOT_FOUND" | "FAILED";
  reason: string | null;
  activityStatus: "REFRESHED" | "UNCHANGED" | "NO_ACTIVITY" | "FAILED" | null;
};
export type XArchivedCompetitor = {
  id: string;
  xUserId: string | null;
  username: string;
  displayName: string | null;
  profileImageUrl: string | null;
  platform: XCreatorPlatform;
  followersCount: number | null;
  archivedAt: string;
};
export type XDashboard = {
  items: XCompetitor[];
  benchmark: XCompetitor | null;
  metrics: {
    commenters: number;
    retweeters: number;
    quotePosters: number;
    uniqueLeads: number;
  };
};
export type XCompetitorPost = {
  id: string;
  xTweetId: string;
  text: string | null;
  postedAt: string;
  language: string | null;
  conversationId: string | null;
  isQuote: boolean;
  hasMedia: boolean;
  mediaMetadata: Record<string, unknown>[];
  viewCount: number | null;
  likeCount: number | null;
  replyCount: number | null;
  retweetCount: number | null;
  quoteCount: number | null;
  bookmarkCount: number | null;
  lastMetricObservedAt: string | null;
};
export type XPosts7dResponse = {
  competitor: Pick<
    XCompetitor,
    "id" | "username" | "displayName" | "profileImageUrl"
  >;
  count: number;
  posts: XCompetitorPost[];
};
export type XArchivedPostsResponse = XPosts7dResponse & {
  page: number;
  pageSize: number;
};
type XMetricSummary = { median: number | null; average: number | null };
export type XEngagementResponse = {
  competitor: Pick<
    XCompetitor,
    "id" | "username" | "displayName" | "profileImageUrl"
  >;
  sampleSize: number;
  followersCount: number | null;
  medianFollowerEngagementRate: number | null;
  medianViewedEngagementRate: number | null;
  medianReachRatio: number | null;
  typical: {
    view: XMetricSummary;
    like: XMetricSummary;
    comments: XMetricSummary;
    retweet: XMetricSummary;
    quote: XMetricSummary;
    interactions: XMetricSummary;
  };
  mix: {
    like: number | null;
    comments: number | null;
    retweet: number | null;
    quote: number | null;
  };
  consistency: {
    minimum: number | null;
    q1: number | null;
    median: number | null;
    q3: number | null;
    maximum: number | null;
  };
  topPosts: (XCompetitorPost & { followerEngagementRate: number })[];
};
const base = `${environment.apiBaseUrl}/x-intelligence`;

export async function downloadXLeadsCsv(): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`${base}/audience/leads/export.csv`, { cache: "no-store" });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(body?.detail || "Unable to export collected leads.");
  }
  const disposition = response.headers.get("content-disposition") || "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || "creator_os_x_leads.csv";
  return { blob: await response.blob(), filename };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, init);
  const body = (await response.json().catch(() => null)) as T & {
    detail?: string;
  };
  if (!response.ok)
    throw new Error(
      body?.detail || "X Competitor Intelligence request failed.",
    );
  return body;
}

export const xCompetitorIntelligenceApi = {
  downloadCollectedLeadsCsv: downloadXLeadsCsv,
  dashboard: () => request<XDashboard>("/competitors", { cache: "no-store" }),
  importCompetitors: (usernames: string[], platform: XCreatorPlatform = "FANVUE") =>
    request<{ results: XImportResult[] }>("/competitors/import", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ usernames, platform }),
    }),
  archivedCompetitors: () =>
    request<{ items: XArchivedCompetitor[] }>("/competitors/archived", {
      cache: "no-store",
    }),
  archiveCompetitor: (competitorId: string) =>
    request<{ id: string; archivedAt: string }>(
      `/competitors/${encodeURIComponent(competitorId)}/archive`,
      { method: "POST" },
    ),
  restoreCompetitor: (competitorId: string) =>
    request<{ id: string; archivedAt: null }>(
      `/competitors/${encodeURIComponent(competitorId)}/restore`,
      { method: "POST" },
    ),
  updateTelegramIntelligence: (
    competitorId: string,
    value: XTelegramIntelligence,
  ) =>
    request<XTelegramIntelligence>(
      `/competitors/${encodeURIComponent(competitorId)}/telegram-intelligence`,
      {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(value),
      },
    ),
  posts7d: (competitorId: string) =>
    request<XPosts7dResponse>(
      `/competitors/${encodeURIComponent(competitorId)}/posts-7d`,
      { cache: "no-store" },
    ),
  engagement7d: (competitorId: string) =>
    request<XEngagementResponse>(
      `/competitors/${encodeURIComponent(competitorId)}/engagement-7d`,
      { cache: "no-store" },
    ),
  collectAudience7d: (competitorId: string) =>
    request<XAudienceCollection>(
      `/competitors/${encodeURIComponent(competitorId)}/audience-7d/collect`,
      { method: "POST" },
    ),
  audienceRunUsers: (runId: string, classification: "NEW" | "EXISTING") =>
    request<XAudienceRunUsers>(
      `/audience-runs/${encodeURIComponent(runId)}/users?classification=${classification}`,
      { cache: "no-store" },
    ),
  audienceRunDiagnostics: (runId: string) =>
    request<XAudienceRunDiagnostics>(
      `/audience-runs/${encodeURIComponent(runId)}/diagnostics`,
      { cache: "no-store" },
    ),
  collectedLeads: (
    page = 1,
    search = "",
    sort: XCollectedLeadsResponse["sort"] = "account-asc",
  ) =>
    request<XCollectedLeadsResponse>(
      `/audience/leads?page=${page}&page_size=25&search=${encodeURIComponent(search)}&sort=${sort}`,
      { cache: "no-store" },
    ),
  collectedLeadUsernames: () =>
    request<{ usernames: string[]; count: number }>(
      "/audience/leads/usernames",
      { cache: "no-store" },
    ),
  archivedPosts: (competitorId: string, page = 1) =>
    request<XArchivedPostsResponse>(
      `/competitors/${encodeURIComponent(competitorId)}/posts-archived?page=${page}&page_size=25`,
      { cache: "no-store" },
    ),
  refreshPostMetrics: (postId: string, idempotencyKey: string) =>
    request<{ post: XCompetitorPost; idempotentReplay: boolean }>(
      `/posts/${encodeURIComponent(postId)}/refresh-metrics`,
      { method: "POST", headers: { "Idempotency-Key": idempotencyKey } },
    ),
};
