import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { loadXLinkPerformance } from "./api";
import type { SnapshotPeriod, XLinkPerformance as XLinkReport, XLinkPerformanceItem } from "./types";

const PERIODS: Array<[SnapshotPeriod, string]> = [
  ["TODAY", "Today"], ["YESTERDAY", "Yesterday"], ["LAST_7_DAYS", "7 Days"],
  ["LAST_30_DAYS", "30 Days"], ["THIS_MONTH", "This Month"], ["ALL_TIME", "All Time"],
];
const TIMEZONE = "America/New_York";
const dayKey = (value: string) => new Intl.DateTimeFormat("en-CA", { timeZone: TIMEZONE, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));
const dayLabel = (value: string) => new Intl.DateTimeFormat(undefined, { timeZone: TIMEZONE, weekday: "long", month: "long", day: "numeric" }).format(new Date(value));
const timeLabel = (value: string) => new Intl.DateTimeFormat(undefined, { timeZone: TIMEZONE, hour: "numeric", minute: "2-digit" }).format(new Date(value));

function TrackingValue({ item }: { item: XLinkPerformanceItem }) {
  if (item.trackingState === "TRACKED") return <div className="x-link-card__clicks"><strong>{item.linkClicks ?? 0}</strong><span>Link Clicks</span></div>;
  const label = item.trackingState === "NO_CTA" ? "No CTA" : item.trackingState === "FAILED_CTA" ? "CTA failed" : "Tracking unavailable";
  return <div className="x-link-card__state"><strong>{label}</strong></div>;
}

export function XLinkPerformance() {
  const [period, setPeriod] = useState<SnapshotPeriod>("TODAY");
  const [report, setReport] = useState<XLinkReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void loadXLinkPerformance(period, controller.signal).then(setReport)
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load X Link Performance."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [period, refreshKey]);
  const groups = useMemo(() => {
    const result = new Map<string, XLinkPerformanceItem[]>();
    for (const item of report?.items ?? []) {
      const key = dayKey(item.publishedAt);
      result.set(key, [...(result.get(key) ?? []), item]);
    }
    return [...result.values()];
  }, [report]);

  return <section className="x-link-performance" aria-labelledby="x-link-performance-heading">
    <header><div><span>Owned attribution</span><h2 id="x-link-performance-heading">X Link Performance</h2>{report && <p>{report.period.timezone}</p>}</div><button aria-label="Refresh X Link Performance" className="snapshot-refresh" onClick={() => setRefreshKey((value) => value + 1)} type="button"><RefreshCw size={15} />Refresh</button></header>
    <div className="snapshot-periods" role="group" aria-label="X Link Performance period">{PERIODS.map(([key, label]) => <button aria-pressed={period === key} className={period === key ? "is-active" : ""} key={key} onClick={() => { if (key !== period) { setReport(null); setLoading(true); setPeriod(key); } }} type="button">{label}</button>)}</div>
    {loading && !report && <div className="snapshot-state" role="status">Loading X link performance…</div>}
    {error && <div className="snapshot-state snapshot-state--error" role="alert"><span>{error}</span><button onClick={() => setRefreshKey((value) => value + 1)} type="button">Retry</button></div>}
    {report && !report.items.length && <div className="snapshot-state">No Creator-OS X posts were published during this period.</div>}
    {report && groups.length > 0 && <div className={loading ? "x-link-days is-refreshing" : "x-link-days"}>{groups.map((items) => <section className="x-link-day" key={dayKey(items[0]!.publishedAt)}><h3>{dayLabel(items[0]!.publishedAt)}</h3><div>{items.map((item) => <article className="x-link-card" key={item.primaryPostId}><img alt="Published X post" src={item.thumbnailUrl} /><div className="x-link-card__content"><p>{item.caption || "No caption"}</p><small>Published {timeLabel(item.publishedAt)}{item.accountName ? ` · @${item.accountName}` : ""}</small></div><TrackingValue item={item} /></article>)}</div></section>)}</div>}
  </section>;
}
