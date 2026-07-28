import { useMemo, useState } from "react";
import { Check, Copy, Search } from "lucide-react";

import type { JsonValue } from "./types";

const highlightedKeys = new Set([
  "uuid", "id", "username", "displayname", "mediauuid", "mediauuids",
  "medialinkuuid", "url", "purchasedat", "purchasedby", "purchasedbyfan",
  "purchasedate", "amount", "currency", "transactionid", "source", "earnings",
  "unlocks", "creatoruuid", "creatoruseruuid", "price", "clicks", "mediatype",
  "creator", "media", "metadata", "purchaser", "purchaserinformation", "buyer",
  "transaction", "transactioninformation", "owner", "pricing", "purchase",
  "purchaseinformation", "handle", "scopes", "account", "accountmetadata",
]);

function contains(value: JsonValue, key: string, query: string): boolean {
  if (!query) return true;
  if (key.toLowerCase().includes(query)) return true;
  if (value === null || typeof value !== "object") {
    return String(value).toLowerCase().includes(query);
  }
  return Object.entries(value).some(([childKey, child]) =>
    contains(child, childKey, query),
  );
}

function Primitive({ value }: { value: JsonValue }) {
  if (value === null) return <span className="fanvue-json__null">null</span>;
  if (typeof value === "string") return <span className="fanvue-json__string">"{value}"</span>;
  return <span className="fanvue-json__primitive">{String(value)}</span>;
}

function Node({
  name,
  value,
  query,
  depth = 0,
}: {
  name: string;
  value: JsonValue;
  query: string;
  depth?: number;
}) {
  if (!contains(value, name, query)) return null;
  const keyClass = highlightedKeys.has(name.toLowerCase())
    ? "fanvue-json__key fanvue-json__key--highlight"
    : "fanvue-json__key";
  if (value === null || typeof value !== "object") {
    return <div className="fanvue-json__row" style={{ paddingLeft: depth * 14 }}>
      {name && <><span className={keyClass}>{name}</span><span>: </span></>}
      <Primitive value={value} />
    </div>;
  }
  const entries = Object.entries(value);
  const kind = Array.isArray(value) ? "Array" : "Object";
  return <details className="fanvue-json__branch" open={depth < 2 || Boolean(query)}>
    <summary style={{ marginLeft: depth * 14 }}>
      {name && <span className={keyClass}>{name}</span>}
      <span className="fanvue-json__count">{kind} · {entries.length}</span>
    </summary>
    {entries.map(([key, child]) =>
      <Node depth={depth + 1} key={key} name={key} query={query} value={child} />,
    )}
  </details>;
}

export function FanvueJsonViewer({
  body,
  rawJson,
}: {
  body: JsonValue;
  rawJson: string;
}) {
  const [mode, setMode] = useState<"pretty" | "raw">("pretty");
  const [search, setSearch] = useState("");
  const [copied, setCopied] = useState(false);
  const query = search.trim().toLowerCase();
  const pretty = useMemo(() => JSON.stringify(body, null, 2), [body]);

  const copy = async () => {
    await navigator.clipboard.writeText(pretty);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return <section className="fanvue-json" aria-label="Fanvue JSON response">
    <header className="fanvue-json__toolbar">
      <div className="fanvue-json__tabs" role="tablist">
        <button aria-selected={mode === "pretty"} onClick={() => setMode("pretty")} role="tab" type="button">Pretty JSON</button>
        <button aria-selected={mode === "raw"} onClick={() => setMode("raw")} role="tab" type="button">Raw JSON</button>
      </div>
      <label><Search size={15} /><span className="sr-only">Search JSON</span>
        <input onChange={(event) => setSearch(event.target.value)} placeholder="Search JSON" value={search} />
      </label>
      <button className="fanvue-json__copy" onClick={() => void copy()} type="button">
        {copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copied" : "Copy JSON"}
      </button>
    </header>
    {mode === "pretty"
      ? <div className="fanvue-json__tree"><Node name="" query={query} value={body} /></div>
      : <pre>{rawJson}</pre>}
  </section>;
}
