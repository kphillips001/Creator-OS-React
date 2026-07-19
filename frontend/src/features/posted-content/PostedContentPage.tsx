import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getPostedContent } from "../../infrastructure/api/postedContentApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import { LibraryImage } from "../generation-library/LibraryImage";
import type { PostedContentItem } from "./types";
import "./posted-content.css";

const dateLabel = (value: string) => new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium", timeStyle: "short",
}).format(new Date(value));
const providerLabel = (value: string) => value
  ? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
  : "Unavailable";

export function PostedContentPage() {
  const [items, setItems] = useState<PostedContentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [platform, setPlatform] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const [preview, setPreview] = useState<PostedContentItem | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getPostedContent(controller.signal)
      .then(setItems)
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") {
          setError(reason instanceof Error ? reason.message : "Posted Content could not be loaded.");
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!preview) return undefined;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setPreview(null); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [preview]);

  const filtered = useMemo(() => items.filter((item) => {
    if (platform && item.platform !== platform) return false;
    const query = search.trim().toLowerCase();
    if (!query) return true;
    return [item.caption, item.creator, item.generationLibraryId, item.provider, item.prompt, item.platform]
      .join(" ").toLowerCase().includes(query);
  }).sort((left, right) => {
    const comparison = left.postedAt.localeCompare(right.postedAt);
    return sort === "oldest" ? comparison : -comparison;
  }), [items, platform, search, sort]);

  return (
    <section className="posted-content">
      <PageHeader title="Published Content" description="Browse media previously published by Creator_OS." />
      <div className="posted-content__toolbar" aria-label="Posted Content filters">
        <label><span>Platform</span><select aria-label="Platform" onChange={(event) => setPlatform(event.target.value)} value={platform}><option value="">All</option><option value="X">X</option><option value="Telegram">Telegram</option><option value="Fanvue">Fanvue (future)</option></select></label>
        <label className="posted-content__search"><Search size={16} /><span className="sr-only">Search</span><input onChange={(event) => setSearch(event.target.value)} placeholder="Search posted content" value={search} /></label>
        <label><span>Sort</span><select aria-label="Sort" onChange={(event) => setSort(event.target.value as "newest" | "oldest")} value={sort}><option value="newest">Newest</option><option value="oldest">Oldest</option></select></label>
      </div>

      {loading && <div className="posted-content__state" role="status">Loading Posted Content…</div>}
      {error && <div className="posted-content__state posted-content__state--error" role="alert">{error}</div>}
      {!loading && !error && items.length === 0 && <div className="posted-content__state"><strong>No posted content yet.</strong><span>Images posted through Creator_OS will automatically appear here.</span></div>}
      {!loading && !error && items.length > 0 && filtered.length === 0 && <div className="posted-content__state">No posted content matches these filters.</div>}

      <div className="posted-content__grid">
        {filtered.map((item) => <article className="posted-card" key={item.contentId}>
          <button className="posted-card__preview" aria-label={`Preview ${item.platform} post`} onClick={() => setPreview(item)} type="button"><LibraryImage alt={`${item.platform} posted content`} src={item.mediaUrl} /></button>
          <div className="posted-card__body"><div className="posted-card__meta"><strong>{item.platform}</strong><time>{dateLabel(item.postedAt)}</time></div><p>{item.caption || "No caption available."}</p><span>{item.creator}</span><details><summary>Developer details</summary><code>{item.generationLibraryId}</code></details></div>
        </article>)}
      </div>

      {preview && <div className="posted-preview" role="dialog" aria-modal="true" aria-label="Posted content preview" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><button className="posted-preview__close" aria-label="Close preview" onClick={() => setPreview(null)} type="button"><X /></button><div className="posted-preview__panel"><div className="posted-preview__image"><LibraryImage alt={`${preview.platform} posted content preview`} priority src={preview.mediaUrl} /></div><aside><h2>{preview.platform}</h2><dl><div><dt>Caption</dt><dd>{preview.caption || "No caption available."}</dd></div><div><dt>Posted</dt><dd>{dateLabel(preview.postedAt)}</dd></div><div><dt>Creator</dt><dd>{preview.creator}</dd></div><div><dt>Source Generation Library ID</dt><dd>{preview.generationLibraryId}</dd></div><div><dt>Provider</dt><dd>{providerLabel(preview.provider)}</dd></div></dl><details><summary>Prompt</summary><p>{preview.prompt || "Prompt unavailable."}</p></details><details><summary>Developer details</summary><code>{preview.fileLocation}</code></details></aside></div></div>}
    </section>
  );
}
