import { ChevronLeft, ChevronRight, ImageOff, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { AssetLibraryItem, AssetLibraryResponse } from "./types";
import "./asset-library.css";

const emptyResponse: AssetLibraryResponse = {
  assets: [], total: 0, page: 1, pageSize: 18, totalPages: 1, classifications: [],
};

const dateLabel = (value: string | null) => value
  ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value))
  : "Not recorded";

export function AssetLibraryPage() {
  const [data, setData] = useState<AssetLibraryResponse>(emptyResponse);
  const [search, setSearch] = useState("");
  const [mediaType, setMediaType] = useState("");
  const [classification, setClassification] = useState("");
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<AssetLibraryItem | null>(null);
  const [preview, setPreview] = useState<AssetLibraryItem | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ page: String(page), page_size: "18" });
    if (search.trim()) params.set("search", search.trim());
    if (mediaType) params.set("media_type", mediaType);
    if (classification) params.set("classification", classification);
    setLoading(true); setError("");
    fetch(`/api/v1/assets?${params}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        const result = await response.json() as AssetLibraryResponse & { detail?: string };
        if (!response.ok) throw new Error(result.detail || "Unable to load Asset Library.");
        return result;
      })
      .then((result) => { setData(result); setLoading(false); })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Unable to load Asset Library.");
        setLoading(false);
      });
    return () => controller.abort();
  }, [classification, mediaType, page, search]);

  const openDetails = async (asset: AssetLibraryItem) => {
    setSelected(asset); setError("");
    try {
      const response = await fetch(`/api/v1/assets/${asset.assetId}`, { cache: "no-store" });
      const result = await response.json() as AssetLibraryItem & { detail?: string };
      if (!response.ok) throw new Error(result.detail || "Unable to load Asset details.");
      setSelected(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load Asset details.");
    }
  };

  const range = useMemo(() => {
    if (!data.total) return "0 assets";
    const first = (data.page - 1) * data.pageSize + 1;
    return `${first}-${Math.min(first + data.assets.length - 1, data.total)} of ${data.total}`;
  }, [data]);

  return <section className="asset-library-page">
    <PageHeader title="Asset Library" description="Canonical Creator Assets registered in Creator_OS." />
    <div className="asset-library-toolbar">
      <label className="asset-library-search"><Search size={16} /><span className="sr-only">Search assets</span><input aria-label="Search assets" onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder="Search assets" value={search} /></label>
      <label><span>Media type</span><select aria-label="Media type" onChange={(event) => { setMediaType(event.target.value); setPage(1); }} value={mediaType}><option value="">All media</option><option value="image">Images</option><option value="video">Videos</option></select></label>
      <label><span>Classification</span><select aria-label="Classification" onChange={(event) => { setClassification(event.target.value); setPage(1); }} value={classification}><option value="">All classifications</option>{data.classifications.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
      <span className="asset-library-range">{range}</span>
    </div>

    {error && <div className="asset-library-state asset-library-state--error" role="alert">{error}</div>}
    {loading && <div className="asset-library-state">Loading assets...</div>}
    {!loading && !error && data.assets.length === 0 && <div className="asset-library-state"><ImageOff size={24} /><strong>No assets found.</strong><span>Register an image from Generation Library or adjust the filters.</span></div>}
    {!loading && data.assets.length > 0 && <div className="asset-library-layout">
      <div className="asset-library-grid">
        {data.assets.map((asset) => <article className={selected?.assetId === asset.assetId ? "asset-card asset-card--selected" : "asset-card"} key={asset.assetId}>
          <button className="asset-card__image" disabled={!asset.mediaAvailable} onClick={() => setPreview(asset)} type="button" aria-label={`Preview Asset ${asset.assetId}`}>
            {asset.imageUrl ? <img alt={asset.fileName || `Asset ${asset.assetId}`} loading="lazy" src={asset.imageUrl} /> : <span><ImageOff /><small>Media unavailable</small></span>}
          </button>
          <button className="asset-card__summary" onClick={() => void openDetails(asset)} type="button">
            <span><strong>Asset #{asset.assetId}</strong>{asset.isCanonicalReference && <em>Canonical reference - Protected</em>}</span>
            <dl><div><dt>Type</dt><dd>{asset.mediaType}</dd></div><div><dt>Classification</dt><dd>{asset.classification || "Unclassified"}</dd></div><div><dt>Registered</dt><dd>{dateLabel(asset.createdAt)}</dd></div></dl>
          </button>
        </article>)}
      </div>
      {selected && <aside className="asset-details" aria-label="Selected asset details"><header><div><small>Selected Asset</small><h2>Asset #{selected.assetId}</h2></div><button aria-label="Close asset details" onClick={() => setSelected(null)} type="button"><X size={17} /></button></header><dl><div><dt>Filename</dt><dd>{selected.fileName || "Not recorded"}</dd></div><div><dt>Media type</dt><dd>{selected.mediaType}</dd></div><div><dt>Classification</dt><dd>{selected.classification || "Unclassified"}</dd></div><div><dt>Created</dt><dd>{dateLabel(selected.createdAt)}</dd></div><div><dt>Registration source</dt><dd>{selected.registrationSource || "Existing Creator Asset"}</dd></div><div><dt>Status</dt><dd>{selected.status || "Not recorded"}</dd></div><div><dt>Canonical reference</dt><dd>{selected.isCanonicalReference ? "Yes - Protected" : "No"}</dd></div><div><dt>Tags</dt><dd>{selected.tags.length ? selected.tags.join(", ") : "None"}</dd></div><div><dt>Themes</dt><dd>{selected.themes.length ? selected.themes.join(", ") : "None"}</dd></div></dl></aside>}
    </div>}

    {!loading && data.totalPages > 1 && <nav className="asset-pagination" aria-label="Asset Library pagination"><button disabled={data.page <= 1} onClick={() => setPage((current) => current - 1)} type="button"><ChevronLeft size={16} />Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={data.page >= data.totalPages} onClick={() => setPage((current) => current + 1)} type="button">Next<ChevronRight size={16} /></button></nav>}
    {preview && <div className="asset-preview" role="dialog" aria-modal="true" aria-label={`Asset ${preview.assetId} preview`} onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><button aria-label="Close preview" onClick={() => setPreview(null)} type="button"><X /></button><div>{preview.imageUrl ? <img alt={`${preview.fileName || `Asset ${preview.assetId}`} preview`} src={preview.imageUrl} /> : <span>Media unavailable</span>}<p>Asset #{preview.assetId}</p></div></div>}
  </section>;
}
