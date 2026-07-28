import { useMemo, useState, type FormEvent } from "react";
import { AlertTriangle, Database, LockKeyhole } from "lucide-react";
import { developerFetch } from "../../infrastructure/api/developerFetch";

import { PageHeader } from "../../shared/ui/PageHeader";
import { FanvueJsonViewer } from "./FanvueJsonViewer";
import { sortEarningsForDisplay } from "./earningsDisplay";
import type { FanvueExplorerResponse, JsonValue } from "./types";
import "./fanvue-api-explorer.css";

type Operation = "earnings" | "media-links" | "media" | "current-user";

const operations: Array<{ value: Operation; label: string; endpoint: string }> = [
  { value: "earnings", label: "Earnings", endpoint: "GET /insights/earnings" },
  { value: "media-links", label: "Media Links", endpoint: "GET /media-links" },
  { value: "media", label: "Media", endpoint: "GET /media/{uuid}" },
  { value: "current-user", label: "Current User", endpoint: "GET /users/me" },
];

function findMediaUuids(
  value: JsonValue,
  key = "",
  insideMedia = false,
): string[] {
  const normalizedKey = key.toLowerCase();
  if (
    typeof value === "string"
    && (["mediauuid", "mediauuids"].includes(normalizedKey)
      || (insideMedia && normalizedKey === "uuid"))
  ) return [value];
  if (
    Array.isArray(value)
    && ["mediauuid", "mediauuids"].includes(normalizedKey)
  ) {
    return value.filter((item): item is string => typeof item === "string");
  }
  if (value === null || typeof value !== "object") return [];
  const childInsideMedia = insideMedia || ["media", "mediaitems"].includes(normalizedKey);
  return Object.entries(value).flatMap(([childKey, child]) =>
    findMediaUuids(child, childKey, childInsideMedia),
  );
}

function displayDiagnostic(value: JsonValue | number | null): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function FanvueApiExplorerPage() {
  const [operation, setOperation] = useState<Operation>("earnings");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [pageSize, setPageSize] = useState("25");
  const [mediaUuid, setMediaUuid] = useState("");
  const [knownMediaUuids, setKnownMediaUuids] = useState<string[]>([]);
  const [result, setResult] = useState<FanvueExplorerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const selected = operations.find((item) => item.value === operation)!;
  const scopes = useMemo(() => result?.oauthScopes.join(" ") || "—", [result]);
  const displayResult = useMemo(
    () => result
      ? sortEarningsForDisplay(result.endpoint, result.body)
      : null,
    [result],
  );

  const run = async (event: FormEvent) => {
    event.preventDefault();
    const params = new URLSearchParams();
    if (operation === "earnings") {
      if (startDate) params.set("start_date", startDate);
      if (endDate) params.set("end_date", endDate);
      if (pageSize) params.set("page_size", pageSize);
    }
    if (operation === "media" && mediaUuid) params.set("media_uuid", mediaUuid);
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const response = await developerFetch(
        `/api/v1/developer/fanvue-api-explorer/${operation}?${params}`,
        { cache: "no-store" },
      );
      const body = await response.json() as FanvueExplorerResponse & { detail?: string };
      if (!response.ok) throw new Error(body.detail || `Explorer request failed (${response.status}).`);
      setResult(body);
      if (operation === "media-links") {
        const discovered = [...new Set(findMediaUuids(body.body))];
        setKnownMediaUuids(discovered);
        setMediaUuid((current) => current || discovered[0] || "");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to inspect Fanvue.");
    } finally {
      setLoading(false);
    }
  };

  return <section className="fanvue-explorer">
    <PageHeader title="Fanvue API Explorer" description="Inspect allowlisted official Fanvue API responses through the authenticated creator connection." />
    <div className="fanvue-explorer__notice"><LockKeyhole size={18} /><div><strong>Developer Tool — Read Only</strong><span>No responses are persisted and no provider state can be changed.</span></div></div>
    <form className="fanvue-explorer__controls" onSubmit={(event) => void run(event)}>
      <label>Endpoint<select aria-label="Endpoint" onChange={(event) => { setOperation(event.target.value as Operation); setResult(null); setError(""); }} value={operation}>
        {operations.map((item) => <option key={item.value} value={item.value}>{item.endpoint}</option>)}
      </select></label>
      {operation === "earnings" && <>
        <label>Start date<input onChange={(event) => setStartDate(event.target.value)} type="date" value={startDate} /></label>
        <label>End date<input onChange={(event) => setEndDate(event.target.value)} type="date" value={endDate} /></label>
        <label>Page size<input max="100" min="1" onChange={(event) => setPageSize(event.target.value)} type="number" value={pageSize} /></label>
      </>}
      {operation === "media" && <label>Media UUID
        <select aria-label="Media UUID" disabled={knownMediaUuids.length === 0} onChange={(event) => setMediaUuid(event.target.value)} required value={mediaUuid}>
          <option value="">Select a Media UUID</option>
          {knownMediaUuids.map((uuid) => <option key={uuid} value={uuid}>{uuid}</option>)}
        </select>
      </label>}
      <button disabled={loading || (operation === "media" && !mediaUuid)} type="submit">{loading ? "Loading…" : `Run ${selected.endpoint}`}</button>
    </form>
    {operation === "media" && knownMediaUuids.length === 0 && <p className="fanvue-explorer__hint">Run GET /media-links first to populate Media UUID choices.</p>}
    {error && <div className="fanvue-explorer__error" role="alert"><AlertTriangle size={18} />{error}</div>}
    {result && <>
      {result.error && <div className="fanvue-explorer__error" role="alert"><AlertTriangle size={18} />Provider response: {result.error}</div>}
      <section className="fanvue-explorer__diagnostics" aria-label="Request diagnostics">
        <div><span>Endpoint</span><strong>{result.endpoint}</strong></div>
        <div><span>HTTP Status</span><strong>{result.httpStatus || "Network error"}</strong></div>
        <div><span>Elapsed Time</span><strong>{result.elapsedMs} ms</strong></div>
        <div><span>Record Count</span><strong>{displayDiagnostic(result.recordCount)}</strong></div>
        <div><span>Cursor</span><strong>{displayDiagnostic(result.cursor)}</strong></div>
        <div><span>Next Page</span><strong>{displayDiagnostic(result.nextPage)}</strong></div>
        <div><span>Current API Version</span><strong>{result.apiVersion}</strong></div>
        <div className="fanvue-explorer__diagnostics-wide"><span>OAuth scopes currently granted</span><strong>{scopes}</strong></div>
      </section>
      <details className="fanvue-explorer__metadata">
        <summary><Database size={16} />Response headers and pagination metadata</summary>
        <h3>Response headers</h3><pre>{JSON.stringify(result.headers, null, 2)}</pre>
        <h3>Pagination metadata</h3><pre>{JSON.stringify(result.pagination, null, 2)}</pre>
      </details>
      {displayResult?.sortingApplied && <div className="fanvue-explorer__sort-badge">Sorted by newest transaction</div>}
      <FanvueJsonViewer
        body={displayResult?.body ?? result.body}
        rawJson={displayResult?.sortingApplied
          ? JSON.stringify(displayResult.body)
          : result.rawJson}
      />
    </>}
  </section>;
}
