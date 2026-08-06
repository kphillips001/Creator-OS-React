import { useCallback, useEffect, useState } from "react";
import { Camera, Package } from "lucide-react";
import { useLocation } from "react-router-dom";
import { LibraryActionButton } from "../../shared/ui/LibraryActionButton";
import { ContainedMediaImage } from "../../shared/ui/ContainedMediaImage";
import { PhotoshootViewer, type RegistrationState } from "./PhotoshootViewer";
import "./photoshoot-gallery.css";

type GalleryItem = { deliverableId: string; name: string; description: string | null; completedAt: string; shotCount: number; imageUrl: string | null; registrationState: RegistrationState };

async function json<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null) as T | { detail?: string } | null;
  const detail = body && typeof body === "object" && "detail" in body ? String(body.detail || "") : "";
  if (!response.ok) throw new Error(detail || "Unable to load Photoshoot Gallery.");
  return body as T;
}

const registrationLabel = (state: RegistrationState) => state === "PHOTOSHOOT_COMPLETE" ? "Not Added" : state === "IN_ASSET_LIBRARY" ? "In Asset Library" : state === "REGISTERED" ? "Registered" : "Archived";

export function PhotoshootGalleryPage() {
  const location = useLocation();
  const newlyCompletedDeliverableId = (location.state as { newlyCompletedDeliverableId?: string | null } | null)?.newlyCompletedDeliverableId ?? null;
  const [items, setItems] = useState<GalleryItem[]>([]);
  const [openDeliverableId, setOpenDeliverableId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [registering, setRegistering] = useState<string | null>(null);
  const load = useCallback(() => fetch("/api/v1/photoshoot-gallery", { cache: "no-store" })
    .then((response) => json<{ items: GalleryItem[] }>(response)).then((value) => setItems(value.items)), []);

  useEffect(() => { void load().catch((reason: Error) => setError(reason.message)); }, [load, newlyCompletedDeliverableId]);
  useEffect(() => {
    if (!newlyCompletedDeliverableId || !items.some((item) => item.deliverableId === newlyCompletedDeliverableId)) return;
    document.getElementById(`photoshoot-gallery-${newlyCompletedDeliverableId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [items, newlyCompletedDeliverableId]);
  const open = (id: string) => { setError(""); setOpenDeliverableId(id); };
  const addToAssetLibrary = async (id: string) => {
    setRegistering(id); setError("");
    try {
      const added = await fetch(`/api/v1/photoshoot-gallery/${id}/add-to-asset-library`, { method: "POST" }).then((response) => json<GalleryItem>(response));
      await load();
      return added.registrationState;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to register Photoshoot.");
      throw reason;
    } finally { setRegistering(null); }
  };

  if (openDeliverableId) return <PhotoshootViewer deliverableId={openDeliverableId} onClose={() => setOpenDeliverableId(null)} onAddToAssetLibrary={addToAssetLibrary} />;

  return <section className="photoshoot-gallery-page">
    <header><p className="photoshoot-gallery-page__eyebrow">Library</p><h1>Photoshoot Gallery</h1><p>Completed multi-image Photoshoots preserved as cohesive sets.</p></header>
    {error && <div role="alert">{error}</div>}
    {!error && items.length === 0 && <div className="photoshoot-gallery-empty">No completed Photoshoots found.</div>}
    <div className="photoshoot-gallery-grid">{items.map((item) => <article id={`photoshoot-gallery-${item.deliverableId}`} key={item.deliverableId} className={item.deliverableId === newlyCompletedDeliverableId ? "photoshoot-gallery-card photoshoot-gallery-card--new" : "photoshoot-gallery-card"} tabIndex={0} aria-label={`Open completed Photoshoot with ${item.shotCount} images`} onClick={() => open(item.deliverableId)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") open(item.deliverableId); }}>
      {item.deliverableId === newlyCompletedDeliverableId && <span className="photoshoot-gallery-card__new-badge">Just completed</span>}
      {item.imageUrl && <ContainedMediaImage src={item.imageUrl} alt="" />}<div className="photoshoot-gallery-card__footer"><p><Camera aria-hidden="true" size={15} strokeWidth={2} />{item.shotCount} {item.shotCount === 1 ? "Image" : "Images"}</p>{item.registrationState === "PHOTOSHOOT_COMPLETE" ? <LibraryActionButton accent icon={Package} tooltip="Add to Asset Library" disabled={registering === item.deliverableId} onClick={(event) => { event.stopPropagation(); void addToAssetLibrary(item.deliverableId).catch(() => undefined); }} /> : <span className="photoshoot-gallery-card__registered">{registrationLabel(item.registrationState)}</span>}</div>
    </article>)}</div>
  </section>;
}
