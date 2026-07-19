import { Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { getVersionHistories, restoreAssetVersion } from "../../infrastructure/api/versionHistoryApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import { LibraryImage } from "../generation-library/LibraryImage";
import type { AssetVersion, AssetVersionHistory } from "./types";
import "./version-history.css";

const titleCase = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const dateLabel = (value: string | null) => value
  ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value))
  : "Original generation";

function metadataSummary(metadata: Record<string, unknown>) {
  const keys = ["workflow_type", "source", "model", "edit_mode", "creative_mode"];
  const values = keys.flatMap((key) => {
    const value = metadata[key];
    return typeof value === "string" && value ? [`${titleCase(key)}: ${titleCase(value)}`] : [];
  });
  return values.slice(0, 3).join(" · ") || "Generation metadata preserved";
}

function VersionImage({ version, onOpen }: { version: AssetVersion; onOpen: () => void }) {
  return (
    <button className="version-history__image" onClick={onOpen} type="button" aria-label={`Preview Version ${version.versionNumber}`}>
      <LibraryImage alt={`Version ${version.versionNumber}`} src={version.imageUrl} />
    </button>
  );
}

export function VersionHistoryPage() {
  const [histories, setHistories] = useState<AssetVersionHistory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<"newest" | "oldest">("newest");
  const [provider, setProvider] = useState("");
  const [creator, setCreator] = useState("");
  const [preview, setPreview] = useState<AssetVersion | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<AssetVersion | null>(null);
  const [restoringAsset, setRestoringAsset] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getVersionHistories(controller.signal)
      .then(setHistories)
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError") {
          setError(reason instanceof Error ? reason.message : "Version History could not be loaded.");
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

  const providers = useMemo(() => [...new Set(histories.flatMap((history) => history.versions.map((version) => version.providerId)))].sort(), [histories]);
  const creators = useMemo(() => [...new Set(histories.map((history) => String(history.creatorProfileId ?? "current")))].sort(), [histories]);
  const filtered = useMemo(() => histories.filter((history) => {
    const versions = history.versions;
    const haystack = [history.generationLibraryRecordId, ...versions.flatMap((version) => [version.prompt, version.providerId, version.promptPlanId])].join(" ").toLowerCase();
    if (search.trim() && !haystack.includes(search.trim().toLowerCase())) return false;
    if (provider && !versions.some((version) => version.providerId === provider)) return false;
    return !creator || String(history.creatorProfileId ?? "current") === creator;
  }).sort((left, right) => {
    const stamp = (history: AssetVersionHistory) => history.versions.find((version) => version.isCurrent)?.approvalTimestamp || "";
    return sort === "oldest" ? stamp(left).localeCompare(stamp(right)) : stamp(right).localeCompare(stamp(left));
  }), [creator, histories, provider, search, sort]);

  const confirmRestore = async () => {
    if (!restoreTarget || restoringAsset) return;
    const imageId = restoreTarget.generationLibraryRecordId;
    const versionNumber = restoreTarget.versionNumber;
    setRestoringAsset(imageId);
    setError("");
    setNotice("");
    try {
      const refreshed = await restoreAssetVersion(imageId, versionNumber);
      setHistories((current) => current.map((history) => history.generationLibraryRecordId === imageId
        ? { ...refreshed, creatorProfileId: history.creatorProfileId }
        : history));
      setNotice(`Version ${versionNumber} restored as Version ${refreshed.currentVersion}.`);
      setRestoreTarget(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Version restore failed.");
    } finally {
      setRestoringAsset("");
    }
  };

  return (
    <section className="version-history">
      <PageHeader title="Edited Content" description="View previous approved versions of Generation Library assets." />
      <div className="version-history__toolbar" aria-label="Version History filters">
        <label className="version-history__search"><Search size={16} /><span className="sr-only">Search</span><input onChange={(event) => setSearch(event.target.value)} placeholder="Search versions" value={search} /></label>
        <label><span className="sr-only">Sort</span><select aria-label="Sort" onChange={(event) => setSort(event.target.value as "newest" | "oldest")} value={sort}><option value="newest">Newest First</option><option value="oldest">Oldest First</option></select></label>
        <label><span className="sr-only">Provider</span><select aria-label="Provider" onChange={(event) => setProvider(event.target.value)} value={provider}><option value="">All providers</option>{providers.map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label>
        <label><span className="sr-only">Creator</span><select aria-label="Creator" onChange={(event) => setCreator(event.target.value)} value={creator}><option value="">All creators</option>{creators.map((value) => <option key={value} value={value}>{value === "current" ? "Current Creator" : `Creator #${value}`}</option>)}</select></label>
      </div>

      {notice && <div className="version-history__notice" role="status">{notice}</div>}

      {loading && <div className="version-history__state" role="status">Loading Version History…</div>}
      {error && <div className="version-history__state version-history__state--error" role="alert">{error}</div>}
      {!loading && !error && histories.length === 0 && <div className="version-history__state"><strong>No archived versions yet.</strong><span>Approved edits will automatically appear here.</span></div>}
      {!loading && !error && histories.length > 0 && filtered.length === 0 && <div className="version-history__state">No version history matches these filters.</div>}

      <div className="version-history__assets">
        {filtered.map((history) => {
          const current = history.versions.find((version) => version.isCurrent);
          const previous = history.versions.filter((version) => !version.isCurrent).sort((a, b) => b.versionNumber - a.versionNumber);
          if (!current) return null;
          return (
            <article className="version-asset" key={history.generationLibraryRecordId}>
              <header><div><span>Generation Library image</span><h2>{history.generationLibraryRecordId}</h2></div><strong>Version {history.currentVersion}</strong></header>
              <section className="version-current" aria-label={`Current Version ${history.generationLibraryRecordId}`}>
                <h3>Current Version</h3><div className="version-current__grid"><VersionImage version={current} onOpen={() => setPreview(current)} /><div className="version-history__details">{typeof current.generationMetadata.restored_from_version === "number" && <span className="version-history__restored">Restored from Version {current.generationMetadata.restored_from_version}</span>}<dl><div><dt>Provider</dt><dd>{titleCase(current.providerId)}</dd></div><div><dt>Prompt</dt><dd>{current.prompt}</dd></div><div><dt>Approval date</dt><dd>{dateLabel(current.approvalTimestamp)}</dd></div><div><dt>Version number</dt><dd>Version {current.versionNumber}</dd></div></dl></div></div>
              </section>
              <section className="version-previous"><h3>Previous Versions</h3><div className="version-timeline">
                {previous.map((version) => <article className="version-timeline__item" key={version.versionNumber}>
                  <span className="version-timeline__marker" aria-hidden="true" />
                  <VersionImage version={version} onOpen={() => setPreview(version)} />
                  <div className="version-history__details"><div className="version-timeline__heading"><h4>Version {version.versionNumber}</h4><button disabled={Boolean(restoringAsset)} onClick={() => setRestoreTarget(version)} type="button">{restoringAsset === history.generationLibraryRecordId ? "Restoring…" : "Restore"}</button></div><dl><div><dt>Approval date</dt><dd>{dateLabel(version.approvalTimestamp)}</dd></div><div><dt>Provider</dt><dd>{titleCase(version.providerId)}</dd></div><div><dt>Prompt</dt><dd>{version.prompt}</dd></div>{version.promptPlanId && <div><dt>Prompt plan</dt><dd>{version.promptPlanId}</dd></div>}<div><dt>Generation metadata</dt><dd>{metadataSummary(version.generationMetadata)}</dd></div></dl><details><summary>Developer details</summary><code>{version.archivedFilePath}</code></details></div>
                </article>)}
              </div></section>
            </article>
          );
        })}
      </div>

      {preview && <div className="version-preview" role="dialog" aria-modal="true" aria-label={`Version ${preview.versionNumber} preview`} onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><button aria-label="Close preview" onClick={() => setPreview(null)} type="button"><X /></button><div><LibraryImage alt={`Version ${preview.versionNumber}`} priority src={preview.imageUrl} /><p>Version {preview.versionNumber}</p></div></div>}
      {restoreTarget && <div className="version-restore-dialog" role="dialog" aria-modal="true" aria-labelledby="restore-version-title"><div><h2 id="restore-version-title">Restore Version {restoreTarget.versionNumber}?</h2><p>This will create a new current version based on Version {restoreTarget.versionNumber}. Your current image and all previous versions will remain in Version History.</p><footer><button disabled={Boolean(restoringAsset)} onClick={() => setRestoreTarget(null)} type="button">Cancel</button><button className="version-restore-dialog__confirm" disabled={Boolean(restoringAsset)} onClick={confirmRestore} type="button">{restoringAsset ? "Restoring…" : "Restore Version"}</button></footer></div></div>}
    </section>
  );
}
