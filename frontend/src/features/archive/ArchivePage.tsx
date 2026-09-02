import { ArchiveRestore, Camera, Images, RotateCw, ScrollText, Trash2, Upload, Video } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";

import { PageHeader } from "../../shared/ui/PageHeader";
import "./archive.css";

const imageTitle = (item: { displayName?: string | null; fileName: string | null }) => {
  const displayName = item.displayName?.trim();
  const looksGenerated = !displayName || displayName === item.fileName || /^Asset #\d+$/i.test(displayName) || /(?:^|[_ -])[0-9a-f]{16,}(?:\.[a-z0-9]+)?$/i.test(displayName);
  return looksGenerated ? "Archived Image" : displayName;
};

const destinations = [
  {
    title: "Regenerated Content",
    description: "Browse regenerated variations archived from Regeneration Studio.",
    button: "Open Regenerated Content",
    path: "/system/archive/regenerated",
    icon: RotateCw,
  },
  {
    title: "Prompt Workshop Archive",
    description: "Browse historical Prompt Workshop batches and previously generated prompts.",
    button: "Open Prompt Workshop Archive",
    path: "/system/archive/prompts",
    icon: ScrollText,
  },
  {
    title: "Edited Content",
    description: "View previous approved versions of Generation Library assets.",
    button: "Open Edited Content",
    path: "/system/archive/edited",
    icon: Images,
  },
  {
    title: "Published Content",
    description: "Browse media previously published to X, Telegram, Fanvue, and future platforms.",
    button: "Open Published Content",
    path: "/system/archive/published",
    icon: Upload,
  },
  {
    title: "Removed Content",
    description: "Restore removed Generation Library assets or delete them permanently.",
    button: "Open Removed Content",
    path: "/system/archive/removed",
    icon: Trash2,
  },
] as const;

export function ArchivePage() {
  type ArchivedItem = { libraryItemId: string; itemKind: "registered_asset" | "staged_generation" | "photoshoot"; assetId: number | null; displayName?: string | null; generationId: string | null; deliverableId?: string | null; fileName: string | null; mediaType: string; imageUrl: string | null; shotCount?: number | null; archivedAt?: string | null };
  const [items, setItems] = useState<ArchivedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [restoring, setRestoring] = useState("");
  const load = () => {
    setLoading(true); setError("");
    fetch("/api/v1/assets/archived", { cache: "no-store" })
      .then(async (response) => { const body = await response.json() as { items?: ArchivedItem[]; detail?: string }; if (!response.ok) throw new Error(body.detail || "Unable to load archived Assets."); setItems(body.items || []); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to load archived Assets."))
      .finally(() => setLoading(false));
  };
  useEffect(load, []);
  const restore = async (item: ArchivedItem) => {
    const identity = item.deliverableId || item.generationId || String(item.assetId || "");
    const kind = item.itemKind === "photoshoot" ? "photoshoots" : item.itemKind === "staged_generation" ? "staged" : "assets";
    setRestoring(item.libraryItemId); setError("");
    try {
      const response = await fetch(`/api/v1/assets/archived/${kind}/${encodeURIComponent(identity)}/restore`, { method: "POST" });
      const body = await response.json() as { detail?: string };
      if (!response.ok) throw new Error(body.detail || "Unable to restore Asset.");
      setItems((current) => current.filter(({ libraryItemId }) => libraryItemId !== item.libraryItemId));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to restore Asset."); }
    finally { setRestoring(""); }
  };
  const sections = [
    { title: "Images", icon: Images, items: items.filter((item) => item.mediaType === "image") },
    { title: "Photoshoots", icon: Camera, items: items.filter((item) => item.mediaType === "photoshoot") },
    { title: "Stories", icon: ScrollText, items: items.filter((item) => item.mediaType === "story") },
    { title: "Videos", icon: Video, items: items.filter((item) => item.mediaType === "video") },
  ];
  return (
    <section className="archive-page">
      <PageHeader title="Archive" description="Browse Creator_OS history and previously published content." />
      <div className="archive-page__cards">
        {destinations.map((destination) => {
          const Icon = destination.icon;
          return <article className="archive-page__card" key={destination.path}><Icon aria-hidden="true" size={30} /><h2>{destination.title}</h2><p>{destination.description}</p><Link to={destination.path}>{destination.button}</Link></article>;
        })}
      </div>
      <section className="asset-archive" aria-labelledby="asset-archive-title">
        <header><ArchiveRestore size={26} /><div><h2 id="asset-archive-title">Asset Library Archive</h2><p>Restore archived Assets without changing their identity or history.</p></div></header>
        {loading && <div className="asset-archive__state">Loading archived Assets…</div>}
        {error && <div className="asset-archive__state asset-archive__state--error" role="alert">{error}</div>}
        {!loading && !error && sections.map((section) => <section aria-labelledby={`asset-archive-${section.title.toLowerCase()}-title`} className="asset-archive__section" key={section.title}>
          <h3 id={`asset-archive-${section.title.toLowerCase()}-title`}><section.icon aria-hidden="true" size={19} />{section.title}</h3>
          {!section.items.length ? <p className="asset-archive__empty">No archived {section.title.toLowerCase()}.</p> : <div className="asset-archive__grid">{section.items.map((item) => <article className="asset-archive__card" key={item.libraryItemId}>
            <div className="asset-archive__preview">{item.imageUrl ? <img alt={item.fileName || section.title} src={item.imageUrl} loading="lazy" /> : <Images />}</div>
            <div className="asset-archive__body"><strong>{item.mediaType === "image" ? imageTitle(item) : item.displayName || item.fileName || section.title}</strong>{item.mediaType === "photoshoot" && <span>{item.shotCount || 0} Images</span>}<time>Archived {item.archivedAt ? new Date(item.archivedAt).toLocaleDateString() : "date unavailable"}</time><button disabled={Boolean(restoring)} onClick={() => void restore(item)} type="button"><ArchiveRestore size={16} />{restoring === item.libraryItemId ? "Restoring…" : "Restore"}</button></div>
          </article>)}</div>}
        </section>)}
      </section>
    </section>
  );
}
