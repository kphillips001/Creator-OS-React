import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Radio } from "lucide-react";
import { developerFetch } from "../../infrastructure/api/developerFetch";

import { PageHeader } from "../../shared/ui/PageHeader";
import { FanvueJsonViewer } from "../fanvue-api-explorer/FanvueJsonViewer";
import type {
  FanvueWebhookMonitorItem,
  FanvueWebhookMonitorResponse,
} from "./types";
import "./fanvue-webhook-monitor.css";

type MonitorFilter =
  | "all" | "success" | "failed" | "unknown" | "purchase"
  | "subscription" | "message" | "payment" | "refund";

const empty: FanvueWebhookMonitorResponse = {
  items: [],
  lastWebhookReceived: null,
  storage: "process-memory",
  limit: 100,
};

function matchesFilter(item: FanvueWebhookMonitorItem, filter: MonitorFilter) {
  const event = item.eventName.toLowerCase();
  const content = `${event} ${JSON.stringify(item.payload).toLowerCase()}`;
  if (filter === "all") return true;
  if (filter === "success") return item.httpStatus < 400 && !item.exception;
  if (filter === "failed") return item.httpStatus >= 400 || Boolean(item.exception);
  if (filter === "unknown") return event === "unknown"
    || JSON.stringify(item.processingResult).toLowerCase().includes("unhandled");
  if (filter === "purchase") return content.includes("purchase") || content.includes("unlock");
  if (filter === "subscription") return content.includes("subscription");
  if (filter === "message") return content.includes("message");
  if (filter === "payment") {
    return content.includes("payment") || content.includes("transaction") || content.includes("tip");
  }
  return content.includes("refund");
}

function processingLabel(item: FanvueWebhookMonitorItem) {
  if (item.exception) return "Failed";
  if (
    item.persistenceResult
    && typeof item.persistenceResult === "object"
    && !Array.isArray(item.persistenceResult)
    && item.persistenceResult.duplicate
  ) return "Duplicate";
  if (
    JSON.stringify(item.processingResult).toLowerCase().includes("unhandled")
  ) return "Unhandled";
  return item.httpStatus < 400 ? "Completed" : "Rejected";
}

function reconciliationLabel(item: FanvueWebhookMonitorItem) {
  const serialized = JSON.stringify(item.processingResult);
  const match = serialized.match(/"state"\s*:\s*"(VERIFIED|PENDING|FAILED)"/i);
  return match?.[1] ? match[1].toUpperCase() : "—";
}

function when(value: string) {
  return new Date(value).toLocaleString();
}

export function FanvueWebhookMonitorPage() {
  const [data, setData] = useState(empty);
  const [selectedMonitorId, setSelectedMonitorId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<MonitorFilter>("all");
  const [error, setError] = useState("");

  useEffect(() => {
    let disposed = false;
    const load = async () => {
      try {
        const response = await developerFetch("/api/v1/developer/fanvue-webhook-monitor", {
          cache: "no-store",
        });
        const body = await response.json() as FanvueWebhookMonitorResponse & { detail?: string };
        if (!response.ok) throw new Error(body.detail || "Unable to load webhook monitor.");
        if (!disposed) {
          setData({
            ...body,
            items: [...body.items].sort(
              (left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp),
            ),
          });
          setError("");
        }
      } catch (reason) {
        if (!disposed) {
          setError(reason instanceof Error ? reason.message : "Unable to load webhook monitor.");
        }
      }
    };
    void load();
    const interval = window.setInterval(() => void load(), 2000);
    return () => {
      disposed = true;
      window.clearInterval(interval);
    };
  }, []);

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return data.items.filter((item) => {
      if (!matchesFilter(item, filter)) return false;
      if (!normalized) return true;
      return `${item.eventName} ${item.eventId || ""} ${JSON.stringify(item.payload)}`
        .toLowerCase()
        .includes(normalized);
    });
  }, [data.items, filter, query]);

  const selected = useMemo(
    () => data.items.find((item) => item.monitorId === selectedMonitorId) ?? null,
    [data.items, selectedMonitorId],
  );

  return <section className="webhook-monitor">
    <PageHeader
      title="Fanvue Webhook Monitor"
      description="Developer Tool — Live, read-only visibility into this FastAPI process."
    />
    <div className="webhook-monitor__status">
      <Radio size={17} />
      <strong>Last webhook received:</strong>
      <span>{data.lastWebhookReceived ? when(data.lastWebhookReceived) : "No webhook received"}</span>
      <small>Polling every 2 seconds · Last 100 · Memory only</small>
    </div>
    <div className="webhook-monitor__toolbar">
      <input
        aria-label="Search webhooks"
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search payload, event, buyer, transaction, media, or Media Link UUID"
        value={query}
      />
      <select
        aria-label="Webhook filter"
        onChange={(event) => setFilter(event.target.value as MonitorFilter)}
        value={filter}
      >
        <option value="all">All</option>
        <option value="success">Success</option>
        <option value="failed">Failed</option>
        <option value="unknown">Unknown</option>
        <option value="purchase">Purchase</option>
        <option value="subscription">Subscription</option>
        <option value="message">Message</option>
        <option value="payment">Payment</option>
        <option value="refund">Refund</option>
      </select>
    </div>
    {error && <div className="webhook-monitor__error" role="alert"><AlertTriangle size={17} />{error}</div>}
    {!error && data.items.length === 0 && <div className="webhook-monitor__empty">
      <Radio size={28} /><strong>Waiting for Fanvue webhook...</strong>
      <span>No webhook received</span>
    </div>}
    {!error && data.items.length > 0 && visible.length === 0 && <div className="webhook-monitor__empty">
      <strong>No webhooks match the current search and filter.</strong>
    </div>}
    {data.items.length > 0 && <div className="webhook-monitor__workspace">
      <div className="webhook-monitor__table-wrap">
        <table>
          <thead><tr>
            <th>Timestamp</th><th>HTTP Status</th><th>Event Name</th><th>Event ID</th>
            <th>Signature Valid</th><th>Processing Result</th><th>Reconciliation</th><th>Duration</th>
            <th>Payload Size</th><th>Retry Count</th>
          </tr></thead>
          <tbody>{visible.map((item) => <tr
            aria-selected={selectedMonitorId === item.monitorId}
            className="webhook-monitor__row"
            key={item.monitorId}
            onClick={() => setSelectedMonitorId(item.monitorId)}
          >
            <td>
              <button
                aria-label={`View ${item.eventName} webhook ${item.eventId || item.monitorId}`}
                className="webhook-monitor__select"
                onClick={() => setSelectedMonitorId(item.monitorId)}
                type="button"
              >
                {when(item.timestamp)}
              </button>
            </td>
            <td>{item.httpStatus}</td><td>{item.eventName}</td><td>{item.eventId || "—"}</td>
            <td>{item.signatureValid === null ? "Unknown" : item.signatureValid ? "Yes" : "No"}</td>
            <td>{processingLabel(item)}</td><td>{reconciliationLabel(item)}</td><td>{item.durationMs} ms</td>
            <td>{item.payloadSize} B</td><td>{item.retryCount ?? "—"}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <aside className="webhook-monitor__detail" aria-label="Selected webhook details">
        {!selected && <div className="webhook-monitor__no-selection">No webhook selected.</div>}
        {selected && <>
        <header><div><small>{when(selected.timestamp)}</small><h2>{selected.eventName}</h2></div></header>
        <dl>
          <div><dt>Request path</dt><dd>{selected.requestPath}</dd></div>
          <div><dt>Event ID</dt><dd>{selected.eventId || "—"}</dd></div>
          <div><dt>HTTP status</dt><dd>{selected.httpStatus}</dd></div>
          <div><dt>Duration</dt><dd>{selected.durationMs} ms</dd></div>
          <div><dt>Retry count</dt><dd>{selected.retryCount ?? "Not present"}</dd></div>
          <div><dt>Reconciliation</dt><dd>{reconciliationLabel(selected)}</dd></div>
        </dl>
        <h3>Payload</h3>
        <FanvueJsonViewer body={selected.payload} rawJson={selected.rawJson} />
        {([
          ["Headers", selected.headers],
          ["Signature headers", selected.signatureHeaders],
          ["Delivery metadata", selected.deliveryMetadata],
          ["Processing metadata", selected.processingResult],
          ["Normalization result", selected.normalizationResult],
          ["Persistence result", selected.persistenceResult],
        ] as const).map(([label, value]) => <details key={label}>
          <summary>{label}</summary><pre>{JSON.stringify(value, null, 2)}</pre>
        </details>)}
        <section className="webhook-monitor__exception"><h3>Exception</h3><pre>{selected.exception || "None"}</pre></section>
        </>}
      </aside>
    </div>}
  </section>;
}
