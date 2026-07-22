import { useCallback, useEffect, useState } from "react";
import "./photoshoot-gallery.css";

type RegistrationState = "PHOTOSHOOT_COMPLETE" | "IN_ASSET_LIBRARY" | "REGISTERED" | "ARCHIVED";
type GalleryItem = { deliverableId: string; name: string; description: string | null; completedAt: string; shotCount: number; imageUrl: string | null; registrationState: RegistrationState };
type Detail = GalleryItem & { intelligence: Record<string, unknown>; members: { assetId: number; shotOrder: number; imageUrl: string }[]; technical: Record<string, unknown> };

async function json<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { detail?: string } | null;
  const detail = body && typeof body === "object" && "detail" in body ? String(body.detail || "") : "";
  if (!response.ok) throw new Error(detail || "Unable to load Photoshoot Gallery.");
  return body as T;
}

const displayValue = (value: unknown) => Array.isArray(value) ? value.join(", ") : String(value);

export function PhotoshootGalleryPage() {
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [registering, setRegistering] = useState<string | null>(null);
  const load = useCallback(() => fetch("/api/v1/photoshoot-gallery", { cache: "no-store" })
    .then((response) => json<{ items: GalleryItem[] }>(response)).then((value) => setItems(value.items)), []);
  useEffect(() => { void load().catch((reason: Error) => setError(reason.message)); }, [load]);
  const open = (id: string) => { void fetch(`/api/v1/photoshoot-gallery/${id}`, { cache: "no-store" })
    .then((response) => json<Detail>(response)).then(setDetail).catch((reason: Error) => setError(reason.message)); };
  const addToAssetLibrary = async (id: string) => {
    setRegistering(id); setError("");
    try {
      const added = await fetch(`/api/v1/photoshoot-gallery/${id}/add-to-asset-library`, { method: "POST" })
        .then((response) => json<GalleryItem>(response));
      await load();
      setDetail((current) => current?.deliverableId === id ? { ...current, registrationState: added.registrationState } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to register Photoshoot.");
    } finally { setRegistering(null); }
  };
  return <section className="photoshoot-gallery-page">
    <header><p className="photoshoot-gallery-page__eyebrow">Library</p><h1>Photoshoot Gallery</h1><p>Completed multi-image Photoshoots preserved as cohesive sets.</p></header>
    {error && <div role="alert">{error}</div>}
    {!error && items.length === 0 && <div className="photoshoot-gallery-empty">No completed Photoshoots found.</div>}
    <div className="photoshoot-gallery-grid">{items.map((item) => <article key={item.deliverableId} className="photoshoot-gallery-card" tabIndex={0} aria-label={`Open ${item.name}`} onClick={() => open(item.deliverableId)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") open(item.deliverableId); }}>
      {item.imageUrl && <img src={item.imageUrl} alt="" />}<div><h2>{item.name}</h2>{item.description && <p className="photoshoot-gallery-card__description">{item.description}</p>}<p>{item.shotCount} images · {new Date(item.completedAt).toLocaleDateString()}</p>{item.registrationState === "PHOTOSHOOT_COMPLETE" ? <button type="button" disabled={registering === item.deliverableId} onClick={(event) => { event.stopPropagation(); void addToAssetLibrary(item.deliverableId); }}>⭐ Add to Asset Library</button> : item.registrationState === "IN_ASSET_LIBRARY" ? <span className="photoshoot-gallery-card__registered">✓ In Asset Library</span> : item.registrationState === "REGISTERED" ? <span className="photoshoot-gallery-card__registered">✓ Registered</span> : <span className="photoshoot-gallery-card__registered">Archived</span>}</div>
    </article>)}</div>
    {detail && <aside className="photoshoot-gallery-detail" aria-label="Photoshoot details"><button type="button" onClick={() => setDetail(null)}>Close</button><h2>{detail.name}</h2>{detail.description && <p>{detail.description}</p>}<p>{detail.shotCount} images · {new Date(detail.completedAt).toLocaleDateString()}</p><section className="photoshoot-gallery-registration"><h3>Asset Library</h3><p><strong>Status</strong> {detail.registrationState === "PHOTOSHOOT_COMPLETE" ? "Not Added" : detail.registrationState === "IN_ASSET_LIBRARY" ? "In Asset Library" : detail.registrationState === "REGISTERED" ? "Registered" : "Archived"}</p>{detail.registrationState === "PHOTOSHOOT_COMPLETE" && <button type="button" disabled={registering === detail.deliverableId} onClick={() => void addToAssetLibrary(detail.deliverableId)}>⭐ Add to Asset Library</button>}</section><h3>Timeline</h3><div className="photoshoot-gallery-shots">{detail.members.map((member) => <figure key={member.assetId}><img src={member.imageUrl} alt={`Shot ${member.shotOrder}`} /><figcaption>Shot {member.shotOrder}</figcaption></figure>)}</div><h3>Photoshoot Intelligence</h3><dl>{Object.entries(detail.intelligence).filter(([, value]) => value).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{displayValue(value)}</dd></div>)}</dl><details><summary>Advanced / Technical</summary><dl>{Object.entries(detail.technical).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value ?? "")}</dd></div>)}</dl></details></aside>}
  </section>;
}
