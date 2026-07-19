import { X } from "lucide-react";
import { useEffect, useState } from "react";

import { LibraryImage } from "./LibraryImage";
import type { CaptionTheme, GenerationRecord, PublishContext, PublishDestination } from "./types";

export function PublishDialog({ record, onClose, onPublished }: {
  record: GenerationRecord;
  onClose: () => void;
  onPublished: (message: string) => void;
}) {
  const [context, setContext] = useState<PublishContext | null>(null);
  const [destination, setDestination] = useState<PublishDestination>("x");
  const [themes, setThemes] = useState<CaptionTheme[]>([]);
  const [captionResultId, setCaptionResultId] = useState<string | null>(null);
  const [selectedGeneratedCaption, setSelectedGeneratedCaption] = useState("");
  const [caption, setCaption] = useState("");
  const [ideaSeed, setIdeaSeed] = useState(0);
  const [ctaEnabled, setCtaEnabled] = useState(false);
  const [ctaLabel, setCtaLabel] = useState("");
  const [ctaUrl, setCtaUrl] = useState("");
  const [pending, setPending] = useState<"load" | "captions" | "publish" | "">("load");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/v1/generation-library/${encodeURIComponent(record.image_id)}/publish`, { signal: controller.signal })
      .then(async (response) => {
        const result = (await response.json()) as PublishContext;
        if (!response.ok || !result.success) throw new Error(result.error || "Publish dialog failed to load.");
        return result;
      })
      .then((result) => { setContext(result); setDestination(result.defaultDestination); setPending(""); })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") return;
        setError(reason instanceof Error ? reason.message : "Publish dialog failed to load.");
        setPending("");
      });
    return () => controller.abort();
  }, [record.image_id]);

  const chooseDestination = (value: PublishDestination) => {
    setDestination(value); setThemes([]); setCaptionResultId(null);
    setSelectedGeneratedCaption(""); setCaption(""); setIdeaSeed(0); setError("");
  };

  const generateCaptions = async (regenerate: boolean) => {
    const nextSeed = regenerate ? ideaSeed + 1 : ideaSeed;
    setPending("captions"); setError("");
    try {
      const response = await fetch(`/api/v1/generation-library/${encodeURIComponent(record.image_id)}/publish/captions`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ destination, ideaSeed: nextSeed }),
      });
      const result = (await response.json()) as { success: boolean; captionResultId?: string; themes?: CaptionTheme[]; error?: string };
      if (!response.ok || !result.success) throw new Error(result.error || "Caption generation failed.");
      setIdeaSeed(nextSeed); setThemes(result.themes || []); setCaptionResultId(result.captionResultId || null);
      setSelectedGeneratedCaption(""); setCaption("");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Caption generation failed.");
    } finally { setPending(""); }
  };

  const selectCaption = (value: string) => { setSelectedGeneratedCaption(value); setCaption(value); };
  const destinationLabel = context?.destinations.find(({ value }) => value === destination)?.label || "";
  const busy = pending === "captions" || pending === "publish";
  const destinationAvailable = Boolean(context?.destinations.some((option) => option.value === destination && option.available));
  const canPublish = Boolean(context && destinationAvailable && destination && caption.trim() && !busy);

  const publish = async () => {
    if (!canPublish) return;
    setPending("publish"); setError("");
    const endpoint = `/api/v1/generation-library/${encodeURIComponent(record.image_id)}/publish`;
    const payload = {
      destination, caption, captionResultId, selectedGeneratedCaption,
      ctaEnabled, ctaLabel, ctaUrl,
    };
    try {
      console.info("[Generation Library Publish] Request", { endpoint, payload });
      const response = await fetch(endpoint, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const responseBody = await response.text();
      let result: { success?: boolean; message?: string; error?: string; detail?: unknown; exceptionType?: string } = {};
      try {
        result = responseBody ? JSON.parse(responseBody) as typeof result : {};
      } catch {
        result = {};
      }
      console.info("[Generation Library Publish] Response", {
        endpoint, payload, status: response.status, responseBody,
      });
      if (!response.ok || !result.success) {
        const detail = typeof result.detail === "string"
          ? result.detail
          : result.detail
            ? JSON.stringify(result.detail)
            : "";
        const message = result.error || detail || responseBody || `HTTP ${response.status} ${response.statusText}`;
        throw new Error(result.exceptionType ? `${result.exceptionType}: ${message}` : message);
      }
      onPublished(result.message || `Published to ${destinationLabel}.`);
    } catch (reason: unknown) {
      const exceptionType = reason instanceof Error ? reason.name : typeof reason;
      const exceptionMessage = reason instanceof Error ? reason.message : String(reason);
      console.error("[Generation Library Publish] Exception", {
        endpoint, payload, exceptionType, exceptionMessage, exception: reason,
      });
      setError(
        reason instanceof Error
          ? (reason.name === "Error" ? reason.message : `${reason.name}: ${reason.message}`)
          : `${exceptionType}: ${exceptionMessage}`,
      );
      setPending("");
    }
  };

  return <div className="publish-dialog" role="dialog" aria-modal="true" aria-labelledby="publish-dialog-title" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
    <div className="publish-dialog__panel">
      <header><div><small>Generation Library</small><h2 id="publish-dialog-title">Publish</h2></div><button aria-label="Close publish dialog" disabled={busy} onClick={onClose} type="button"><X size={18} /></button></header>
      {pending === "load" && <p className="publish-dialog__notice">Loading publishing options…</p>}
      {context && <>
        <div className="publish-dialog__workspace">
          <aside className="publish-dialog__image" aria-label="Selected image preview">
            <LibraryImage priority record={record} />
          </aside>
          <div className="publish-dialog__controls">
            <section className="publish-dialog__destination"><h3>Destination</h3><div className="publish-dialog__radios">
              {context.destinations.map((option) => <label key={option.value}><input checked={destination === option.value} disabled={busy} name="publish-destination" onChange={() => chooseDestination(option.value)} type="radio" /><span>{option.label}</span></label>)}
            </div></section>
            <section><h3>Caption controls</h3><p>Generate image-aware captions with Caption Studio, or enter your own caption below.</p><div className="publish-dialog__actions">
              <button disabled={busy} onClick={() => generateCaptions(false)} type="button">Generate Captions</button>
              <button disabled={busy || !captionResultId} onClick={() => generateCaptions(true)} type="button">Regenerate Captions</button>
            </div>{pending === "captions" && <p className="publish-dialog__notice">Generating captions…</p>}
              {themes.length > 0 && <div className="publish-dialog__captions" aria-label="Generated captions">{themes.map((theme) => <div key={theme.theme}><h4>{theme.theme}</h4>{theme.captions.map((value, index) => <button aria-pressed={selectedGeneratedCaption === value} key={`${theme.theme}-${index}`} onClick={() => selectCaption(value)} type="button">{value}</button>)}</div>)}</div>}
            </section>
            <section><label className="publish-dialog__editor"><span>Enter Your Own Caption</span><textarea disabled={busy} onChange={(event) => setCaption(event.target.value)} placeholder={`Type or paste your own ${destination === "x" ? "X" : "Telegram"} caption here.`} rows={5} value={caption} /></label>
              {selectedGeneratedCaption && caption !== selectedGeneratedCaption && <button className="publish-dialog__restore" disabled={busy} onClick={() => setCaption(selectedGeneratedCaption)} type="button">Restore Original</button>}
            </section>
            {destination !== "x" && <section className="publish-dialog__telegram-options"><label><input checked={ctaEnabled} disabled={busy} onChange={(event) => setCtaEnabled(event.target.checked)} type="checkbox" /> Include CTA button</label>{ctaEnabled && <div><label><span>Button Text</span><input disabled={busy} onChange={(event) => setCtaLabel(event.target.value)} value={ctaLabel} /></label><label><span>Button URL</span><input disabled={busy} onChange={(event) => setCtaUrl(event.target.value)} value={ctaUrl} /></label></div>}</section>}
          </div>
        </div>
        <section className="publish-dialog__preview"><h3>Caption preview</h3><p>{caption || "Your caption preview will appear here."}</p></section>
      </>}
      {error && <div className="publish-dialog__error" role="alert">{error}</div>}
      <footer><button disabled={busy} onClick={onClose} type="button">Cancel</button><button className="publish-dialog__publish" disabled={!canPublish} onClick={publish} type="button">{pending === "publish" ? "Publishing…" : `Publish to ${destinationLabel}`}</button></footer>
    </div>
  </div>;
}
