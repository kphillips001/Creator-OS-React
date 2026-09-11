import { AlertTriangle, Archive, ExternalLink, Pencil, Send } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

type OfferingDetail = {
  offeringId: string;
  title: string;
  description: string | null;
  priceMinor: number | null;
  currency: string;
  primarySalesChannel: string;
  status: string;
  publicationStatus: string | null;
  providerResourceStatus: string | null;
  deliveryUrl: string | null;
  lastError: string | null;
};

const money = (minor: number | null, currency: string) =>
  minor == null
    ? "Not priced"
    : new Intl.NumberFormat(undefined, { style: "currency", currency }).format(minor / 100);

const label = (value: string | null) => value
  ? value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (part) => part.toUpperCase())
  : "Not published";

const operatorStatus = (offering: OfferingDetail) => {
  if (offering.status === "ARCHIVED" || offering.publicationStatus === "ARCHIVED") return "Archived";
  if (offering.publicationStatus === "FAILED" || offering.lastError) return "Attention Needed";
  if (offering.publicationStatus === "LIVE" && offering.providerResourceStatus === "PRESENT") return "Live · Ready to Sell";
  if (offering.publicationStatus === "PUBLISHING") return "Publishing";
  if (offering.status === "READY") return "Ready";
  return "Not Prepared";
};

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => null) as (T & { detail?: string | { message?: string } }) | null;
  if (!response.ok || !body) {
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || "Unable to update selling details.");
  }
  return body;
}

export function OfferingSellingControls({ offeringId, onChanged }: {
  offeringId: string;
  onChanged?: () => void | Promise<void>;
}) {
  const [offering, setOffering] = useState<OfferingDetail | null>(null);
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const value = await request<OfferingDetail>(`/api/v1/commerce-authoring/${offeringId}`);
      setOffering(value);
      setTitle(value.title);
      setDescription(value.description || "");
      setPrice(value.priceMinor == null ? "" : (value.priceMinor / 100).toFixed(2));
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load selling details.");
    }
  }, [offeringId]);
  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    const priceMinor = Math.round(Number(price) * 100);
    if (!title.trim() || !Number.isSafeInteger(priceMinor) || priceMinor < 300 || priceMinor > 50000) {
      setError("Enter a title and a price between $3.00 and $500.00.");
      return;
    }
    setBusy(true); setError("");
    try {
      await request(`/api/v1/commerce-authoring/${offeringId}`, {
        method: "PATCH", headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: title.trim(), description: description.trim() || null, priceMinor, currency: "USD" }),
      });
      setEditing(false); await load(); await onChanged?.();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save selling details."); }
    finally { setBusy(false); }
  };
  const act = async (action: "publish" | "archive") => {
    if (action === "archive" && !window.confirm(`Archive ${offering?.title || "this offering"}?`)) return;
    setBusy(true); setError("");
    try {
      await request(`/api/v1/commerce-authoring/${offeringId}/${action}`, {
        method: "POST", headers: { "content-type": "application/json" }, body: "{}",
      });
      await load(); await onChanged?.();
    } catch (reason) { setError(reason instanceof Error ? reason.message : `Unable to ${action} offering.`); }
    finally { setBusy(false); }
  };

  return <section className="asset-offering-controls" aria-label="Selling">
    <header><div><small>Selling</small><h3>{offering ? operatorStatus(offering) : "Loading…"}</h3></div>
      <Link to="/commerce" aria-label="Open Offering Catalog">Offering Catalog <ExternalLink size={14} /></Link></header>
    {error && <p className="sale-preparation-error" role="alert"><AlertTriangle size={16} />{error}</p>}
    {offering && (editing ? <div className="asset-offering-editor">
      <label>Offering Title<input aria-label="Offering Title" maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <label>Offering Description<textarea aria-label="Offering Description" maxLength={2000} value={description} onChange={(event) => setDescription(event.target.value)} /></label>
      <label>Price (USD)<input aria-label="Offering Price" min="3" max="500" step=".01" type="number" value={price} onChange={(event) => setPrice(event.target.value)} /></label>
      <div><button disabled={busy} onClick={() => void save()} type="button">Save Selling Details</button><button disabled={busy} onClick={() => setEditing(false)} type="button">Cancel</button></div>
    </div> : <>
      <dl><div><dt>Title</dt><dd>{offering.title}</dd></div><div><dt>Description</dt><dd>{offering.description || "Not set"}</dd></div>
        <div><dt>Price</dt><dd>{money(offering.priceMinor, offering.currency)}</dd></div><div><dt>Destination</dt><dd>{offering.primarySalesChannel === "TELEGRAM_WALL" ? "TG Wall / Content Vault" : "Chat"}</dd></div>
        <div><dt>Publication</dt><dd>{label(offering.publicationStatus)}</dd></div><div><dt>Provider</dt><dd>{offering.providerResourceStatus === "PRESENT" ? "Ready" : label(offering.providerResourceStatus || "PENDING")}</dd></div></dl>
      <div className="asset-offering-actions"><button disabled={busy || offering.publicationStatus === "PUBLISHING"} onClick={() => setEditing(true)} type="button"><Pencil size={15} />Edit</button>
        <button disabled={busy || offering.status === "ARCHIVED" || ["LIVE", "PUBLISHING", "ARCHIVED"].includes(offering.publicationStatus || "")} onClick={() => void act("publish")} type="button"><Send size={15} />Publish</button>
        <button disabled={busy || offering.status === "ARCHIVED" || offering.publicationStatus === "PUBLISHING"} onClick={() => void act("archive")} type="button"><Archive size={15} />Archive</button></div>
      {offering.lastError && <p className="sale-preparation-error">Publication needs attention. Open Offering Catalog for diagnostics.</p>}
    </>)}
  </section>;
}
