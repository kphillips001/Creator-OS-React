import { useEffect, useState } from "react";

import { getActiveReference } from "../../infrastructure/api/referenceLibraryApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import type { ReferenceLibraryContext } from "./types";
import "./reference-library.css";

const dateLabel = (value: string | null) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not recorded";

export function ReferenceLibraryPage() {
  const [context, setContext] = useState<ReferenceLibraryContext | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    getActiveReference(controller.signal).then(setContext).catch((reason) => {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) setError(reason instanceof Error ? reason.message : "Unable to load Reference Library.");
    });
    return () => controller.abort();
  }, []);
  return <section className="reference-library-page"><PageHeader title="Reference Library" description="Your canonical creator identity reference." />
    {error && <div className="reference-library-state" role="alert">{error}</div>}
    {!error && !context && <div className="reference-library-state">Loading active reference…</div>}
    {context && !context.activeReference && <div className="reference-library-state">No active Reference Image selected for {context.creator.name}.</div>}
    {context?.activeReference && <article className="reference-library-active"><div className="reference-library-active__image"><img alt={`${context.creator.name} active canonical reference`} src={context.activeReference.imageUrl} /></div><div className="reference-library-active__details"><div className="reference-library-active__eyebrow">Active canonical reference</div><h2>{context.activeReference.fileName}</h2><div className="reference-library-active__badges"><span>Active</span>{context.activeReference.isCanonical && <span>Canonical</span>}{context.activeReference.isFavorite && <span>Favorite</span>}{context.activeReference.isProtected && <span>Protected</span>}</div><dl><div><dt>Creator</dt><dd>{context.creator.name} · Profile #{context.creator.id}</dd></div><div><dt>Asset ID</dt><dd>{context.activeReference.assetId}</dd></div><div><dt>Classification</dt><dd>{context.activeReference.classification}</dd></div><div><dt>Status</dt><dd>{context.activeReference.status}</dd></div><div><dt>Media type</dt><dd>{context.activeReference.mediaType}</dd></div><div><dt>Added</dt><dd>{dateLabel(context.activeReference.addedAt)}</dd></div><div><dt>Last used</dt><dd>{dateLabel(context.activeReference.lastUsedAt)}</dd></div></dl></div></article>}
  </section>;
}
