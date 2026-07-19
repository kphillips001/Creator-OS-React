import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "../../shared/ui/PageHeader";
import { LibraryImage } from "../generation-library/LibraryImage";
import type { RemovedContentItem } from "./types";
import "./removed-content.css";

const dateLabel = (value: string) => new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium", timeStyle: "short",
}).format(new Date(value));
const providerLabel = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

export function RemovedContentPage() {
  const [items, setItems] = useState<RemovedContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState("");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const [preview, setPreview] = useState<RemovedContentItem | null>(null);
  const [confirming, setConfirming] = useState<RemovedContentItem | null>(null);
  const [pending, setPending] = useState("");

  const load = () => {
    setLoading(true);
    setError("");
    fetch("/api/v1/generation-library/removed/items", { cache: "no-store" })
      .then(async (response) => {
        const result = await response.json() as { items?: RemovedContentItem[]; detail?: string };
        if (!response.ok) throw new Error(result.detail || "Removed Content could not be loaded.");
        setItems(result.items || []);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Removed Content could not be loaded."))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const providers = useMemo(() => [...new Set(items.map((item) => item.provider))].sort(), [items]);
  const filtered = useMemo(() => items.filter((item) => {
    if (provider && item.provider !== provider) return false;
    const query = search.trim().toLowerCase();
    return !query || [item.generationLibraryId, item.provider, item.prompt].join(" ").toLowerCase().includes(query);
  }).sort((left, right) => sort === "oldest"
    ? left.removedAt.localeCompare(right.removedAt)
    : right.removedAt.localeCompare(left.removedAt)), [items, provider, search, sort]);

  const act = async (item: RemovedContentItem, action: "restore" | "permanent-delete") => {
    setPending(`${item.generationLibraryId}:${action}`);
    setError("");
    try {
      const response = await fetch(`/api/v1/generation-library/removed/${encodeURIComponent(item.generationLibraryId)}/${action}`, {
        method: "POST",
        headers: action === "permanent-delete" ? { "Content-Type": "application/json" } : undefined,
        body: action === "permanent-delete" ? JSON.stringify({ confirmed: true }) : undefined,
      });
      const result = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Action failed.");
      setItems((current) => current.filter(({ archiveId }) => archiveId !== item.archiveId));
      setPreview(null);
      setConfirming(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Action failed.");
    } finally {
      setPending("");
    }
  };

  return <section className="removed-content">
    <PageHeader title="Removed Content" description="Restore removed assets or explicitly delete them permanently." />
    <div className="removed-content__toolbar" aria-label="Removed Content filters">
      <label className="removed-content__search"><Search size={16} /><span className="sr-only">Search</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search prompts, providers, or IDs" /></label>
      <label><span>Provider</span><select aria-label="Provider" value={provider} onChange={(event) => setProvider(event.target.value)}><option value="">All</option>{providers.map((value) => <option key={value} value={value}>{providerLabel(value)}</option>)}</select></label>
      <label><span>Sort</span><select aria-label="Sort" value={sort} onChange={(event) => setSort(event.target.value as "newest" | "oldest")}><option value="newest">Newest</option><option value="oldest">Oldest</option></select></label>
    </div>
    {loading && <div className="removed-content__state" role="status">Loading Removed Content…</div>}
    {error && <div className="removed-content__state removed-content__state--error" role="alert">{error}</div>}
    {!loading && !error && items.length === 0 && <div className="removed-content__state"><strong>No removed content.</strong><span>Content you remove from the Generation Library will appear here.</span></div>}
    {!loading && !error && items.length > 0 && filtered.length === 0 && <div className="removed-content__state">No removed content matches these filters.</div>}
    <div className="removed-content__grid">{filtered.map((item) => <article className="removed-card" key={item.archiveId}>
      <button className="removed-card__preview" aria-label={`Preview removed content ${item.generationLibraryId}`} onClick={() => setPreview(item)} type="button"><LibraryImage alt="Removed content" src={item.mediaUrl} /></button>
      <div className="removed-card__body"><div className="removed-card__meta"><time>Removed {dateLabel(item.removedAt)}</time><strong>{providerLabel(item.provider)}</strong></div><div className="removed-card__actions"><button disabled={Boolean(pending)} onClick={() => act(item, "restore")} type="button">Restore</button><button className="removed-card__delete" disabled={Boolean(pending)} onClick={() => setConfirming(item)} type="button">Delete Permanently</button></div><details className="removed-card__details"><summary>Image Details</summary><dl><div><dt>Generation Library ID</dt><dd><code>{item.generationLibraryId}</code></dd></div><div><dt>Prompt</dt><dd>{item.prompt || "Prompt unavailable."}</dd></div></dl></details></div>
    </article>)}</div>
    {preview && <div className="removed-preview" role="dialog" aria-modal="true" aria-label="Removed content preview" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><button className="removed-preview__close" aria-label="Close preview" onClick={() => setPreview(null)} type="button"><X /></button><div className="removed-preview__panel"><div><LibraryImage alt="Removed content preview" priority src={preview.mediaUrl} /></div><aside><h2>Removed Content</h2><dl><div><dt>Removed</dt><dd>{dateLabel(preview.removedAt)}</dd></div><div><dt>Provider</dt><dd>{providerLabel(preview.provider)}</dd></div><div><dt>Generation Library ID</dt><dd>{preview.generationLibraryId}</dd></div><div><dt>Prompt</dt><dd>{preview.prompt || "Prompt unavailable."}</dd></div></dl></aside></div></div>}
    {confirming && <div className="removed-confirm" role="dialog" aria-modal="true" aria-labelledby="permanent-delete-title"><div className="removed-confirm__panel"><h2 id="permanent-delete-title">Delete Permanently?</h2><p>This permanently removes the selected content from Creator_OS.</p><strong>This action cannot be undone.</strong><div><button disabled={Boolean(pending)} onClick={() => setConfirming(null)} type="button">Cancel</button><button className="removed-card__delete" disabled={Boolean(pending)} onClick={() => act(confirming, "permanent-delete")} type="button">Delete Permanently</button></div></div></div>}
  </section>;
}
