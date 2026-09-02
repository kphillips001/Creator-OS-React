import { ExternalLink, PackageOpen, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import "./bundle-library.css";

type Publication = { status: string; canPublish: boolean; readinessError?: string };
type Preparation = {
  status: string;
  statusLabel: string;
  contentVaultCaption?: { text: string; source: string };
  promotionalTeaser?: { status: string; previewUrl?: string };
};
type Bundle = {
  offeringId: string;
  title: string;
  source: string;
  sourceId: string;
  status: string;
  readinessStatus: string;
  destination: "CHAT" | "WALL";
  priceMinor: number;
  currency: string;
  memberCount: number;
  members: { assetId: number; position: number; imageUrl: string }[];
  heroImageUrl: string;
  deliveryUrl?: string;
  contentVaultPublication?: Publication;
  preparation?: Preparation;
};

const money = (value: number, currency: string) =>
  new Intl.NumberFormat(undefined, { style: "currency", currency }).format(value / 100);

export function BundleLibraryPage() {
  const [items, setItems] = useState<Bundle[]>([]);
  const [selected, setSelected] = useState<Bundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [manual, setManual] = useState("");
  const [guidance, setGuidance] = useState("");
  const [options, setOptions] = useState<{ text: string }[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/v1/bundle-studio/commercial-bundles", { cache: "no-store" });
      const value = (await response.json()) as { bundles: Bundle[]; detail?: string };
      if (!response.ok) throw new Error(value.detail);
      setItems(value.bundles);
      setSelected((current) => current
        ? value.bundles.find((item) => item.offeringId === current.offeringId) || null
        : current);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Bundle Library unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const call = async (path: string, init: RequestInit) => {
    if (!selected) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(
        `/api/v1/bundle-studio/commercial-bundles/${encodeURIComponent(selected.sourceId)}/content-vault/${path}`,
        init,
      );
      const value = (await response.json()) as { captions?: { text: string }[]; detail?: string };
      if (!response.ok) throw new Error(value.detail);
      if (path === "captions/generate") setOptions(value.captions || []);
      else {
        setOptions([]);
        setManual("");
        await load();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Content Wall action failed.");
    } finally {
      setBusy(false);
    }
  };

  return <section className="bundle-library">
    <header><p>Asset Library</p><h1>Bundles</h1><span>Canonical commercial image bundles from every Creator_OS workflow.</span></header>
    {loading && <div role="status">Loading Bundles…</div>}
    {error && <div role="alert">{error}</div>}
    {!loading && !items.length && <div className="bundle-library__empty"><PackageOpen /><h2>No commercial bundles</h2><p>Prepare a Photoshoot Bundle for sale to see it here.</p></div>}
    <div className="bundle-library__grid">{items.map((item) => <button className="bundle-library-card" key={item.offeringId} onClick={() => setSelected(item)}>
      <img src={item.heroImageUrl} alt="" />
      <div><h2>{item.title}</h2><p>{item.memberCount} images · {money(item.priceMinor, item.currency)}</p>
        <div className="bundle-library__badges">
          <span className={item.readinessStatus === "READY" ? "is-ready" : ""}>{item.readinessStatus.replaceAll("_", " ")}</span>
          <span>{item.destination === "WALL" && item.contentVaultPublication?.status === "PUBLISHED" ? "✓ WALL" : item.destination}</span>
          <span className="is-bundle">BUNDLE</span>
        </div>
      </div>
    </button>)}</div>
    {selected && <aside className="bundle-library-inspector">
      <button aria-label="Close bundle inspector" onClick={() => setSelected(null)}><X /></button>
      <h2>{selected.title}</h2>
      <dl>
        <div><dt>Classification</dt><dd>Bundle</dd></div><div><dt>Destination</dt><dd>{selected.destination}</dd></div>
        <div><dt>Preparation</dt><dd>{selected.readinessStatus.replaceAll("_", " ")}</dd></div>
        <div><dt>Price</dt><dd>{money(selected.priceMinor, selected.currency)}</dd></div>
        <div><dt>Paid images</dt><dd>{selected.memberCount}</dd></div>
        <div><dt>Publication</dt><dd>{selected.contentVaultPublication?.status || "Not applicable"}</dd></div>
      </dl>
      <div className="bundle-library-inspector__members">{selected.members.map((member) => <a href={`/api/v1/assets/${member.assetId}/media`} target="_blank" rel="noreferrer" key={member.assetId}><img src={member.imageUrl} alt={`Paid image ${member.position}`} /></a>)}</div>
      {selected.preparation?.promotionalTeaser?.previewUrl && <section><h3>Promotional teaser</h3><a href={selected.preparation.promotionalTeaser.previewUrl} target="_blank" rel="noreferrer"><img className="bundle-library-inspector__teaser" src={selected.preparation.promotionalTeaser.previewUrl} alt="Promotional teaser" /></a></section>}
      {selected.deliveryUrl && <a href={selected.deliveryUrl} target="_blank" rel="noreferrer"><ExternalLink /> Fanvue Media Link</a>}
      {selected.source === "BUNDLE_STUDIO" && selected.destination === "WALL" && <section className="bundle-library-caption">
        <h3>Content Vault Publishing</h3>
        {selected.preparation?.contentVaultCaption ? <blockquote>{selected.preparation.contentVaultCaption.text}</blockquote> : <p>No caption selected.</p>}
        <textarea aria-label="Write your own caption" value={manual} onChange={(event) => setManual(event.target.value)} placeholder="Write your own final caption" />
        <button disabled={busy || !manual.trim()} onClick={() => void call("caption", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: manual, source: "MANUAL" }) })}>Save Caption</button>
        <textarea aria-label="Caption guidance" value={guidance} onChange={(event) => setGuidance(event.target.value)} placeholder="Optional guidance for Grok" />
        <button disabled={busy} onClick={() => void call("captions/generate", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tone: "CLASSY", guidance: guidance.trim() || null }) })}>Generate Captions</button>
        {options.map((option) => <button className="bundle-library-caption__option" key={option.text} onClick={() => void call("caption", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: option.text, source: "GROK" }) })}>{option.text}</button>)}
        {selected.contentVaultPublication?.readinessError && <small>{selected.contentVaultPublication.readinessError}</small>}
        <button disabled={busy || !selected.contentVaultPublication?.canPublish} onClick={() => void call("publish", { method: "POST" })}>{selected.contentVaultPublication?.status === "PUBLISHED" ? "Published to Content Vault" : "Publish to Content Vault"}</button>
      </section>}
    </aside>}
  </section>;
}
