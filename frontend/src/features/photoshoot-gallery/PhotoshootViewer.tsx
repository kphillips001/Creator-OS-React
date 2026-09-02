import { useEffect, useState, type ReactNode } from "react";
import { CheckSquare, Images, Pencil, Square, Video } from "lucide-react";

import { ContainedMediaImage } from "../../shared/ui/ContainedMediaImage";
import {
  BundleSellingPanel,
  SessionSellingPanel,
} from "../asset-library/PhotoshootSalePreparation";
import type {
  BundleSalesChannel,
  CommercialAsset,
  PhotoshootSellingMode,
  SalePreparationReadiness,
} from "../asset-library/types";
import "./photoshoot-gallery.css";
import { videoStudioLink } from "../../infrastructure/api/videoStudioApi";

export type RegistrationState =
  "PHOTOSHOOT_COMPLETE" | "IN_ASSET_LIBRARY" | "REGISTERED" | "ARCHIVED";
export type PhotoshootDetail = {
  deliverableId: string;
  name: string;
  description: string | null;
  completedAt: string;
  shotCount: number;
  imageUrl: string | null;
  registrationState: RegistrationState;
  sellingMode: PhotoshootSellingMode;
  bundleSalesChannel?: BundleSalesChannel | null;
  sourceKind?: "PHOTOSHOOT_STUDIO" | "GENERATION_LIBRARY_IMPORT" | string;
  intelligence: Record<string, unknown>;
  productionIntelligence: Record<string, unknown>;
  members: {
    assetId: number;
    shotOrder: number;
    isHero?: boolean;
    imageUrl: string;
    intelligence: Record<string, unknown>;
  }[];
  technical: Record<string, unknown>;
  commercialAssets?: CommercialAsset[];
  memberCuration?: {
    eligible: boolean;
    reason: string | null;
    memberCount: number;
    maximumExtractable: number;
  };
  sessionTeaser?: {
    eligible: boolean;
    reason: string | null;
    sourceAssetId: number | null;
    hasSessionTeaser: boolean;
  };
};

async function readJson<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as
    T | { detail?: string } | null;
  const detail =
    body && typeof body === "object" && "detail" in body
      ? String(body.detail || "")
      : "";
  if (!response.ok || !body)
    throw new Error(detail || `Request failed (${response.status}).`);
  return body as T;
}

const registrationLabel = (state: RegistrationState) =>
  state === "PHOTOSHOOT_COMPLETE"
    ? "Not Added"
    : state === "IN_ASSET_LIBRARY"
      ? "In Asset Library"
      : state === "REGISTERED"
        ? "Registered"
        : "Archived";
const productionFields = [
  ["theme", "Theme"],
  ["story", "Story"],
  ["experience", "Experience"],
  ["emotional_journey", "Emotional Journey"],
  ["hero_shot", "Hero Shot"],
  ["cover_shot", "Cover Shot"],
  ["teaser_shot", "Teaser Shot"],
  ["thumbnail_shot", "Thumbnail Shot"],
] as const;
const shotFields = [
  ["sequence_role", "Sequence Role"],
  ["summary", "Summary"],
  ["classification", "Classification"],
  ["suggested_content_uses", "Suggested Uses"],
  ["hero_suitability", "Hero Suitability"],
  ["cover_suitability", "Cover Suitability"],
  ["thumbnail_suitability", "Thumbnail Suitability"],
  ["teaser_suitability", "Teaser Suitability"],
] as const;

function conciseValue(value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (["string", "number"].includes(typeof value)) return String(value);
  if (Array.isArray(value)) {
    const items = value
      .filter((item) => ["string", "number", "boolean"].includes(typeof item))
      .map(String);
    return items.length ? items.join(", ") : null;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["rating", "score", "value", "recommended", "suitable"]) {
      const concise = conciseValue(record[key]);
      if (concise) return concise;
    }
  }
  return null;
}

function IntelligenceCard({
  title,
  intelligence,
  fields,
  actions,
}: {
  title: string;
  intelligence: Record<string, unknown>;
  fields: ReadonlyArray<readonly [string, string]>;
  actions?: ReactNode;
}) {
  const values = fields.flatMap(([key, fieldLabel]) => {
    const value = conciseValue(intelligence[key]);
    return value ? [{ key, label: fieldLabel, value }] : [];
  });
  return (
    <article className="photoshoot-intelligence-card">
      <header>
        <h2>{title}</h2>
      </header>
      {values.length > 0 && (
        <dl className="photoshoot-intelligence-fields">
          {values.map((field) => (
            <div key={field.key}>
              <dt>{field.label}</dt>
              <dd>{field.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {actions && (
        <div className="photoshoot-intelligence-card__actions">{actions}</div>
      )}
    </article>
  );
}

export function PhotoshootViewer({
  deliverableId,
  onClose,
  onAddToAssetLibrary,
  onCreateOffer,
  enableSessionSelling = false,
  initialSessionSellingDialog = null,
  onSessionSellingChange,
  onSellingModeChange,
  onMembersChanged,
}: {
  deliverableId: string;
  onClose: () => void;
  onAddToAssetLibrary?: (deliverableId: string) => Promise<RegistrationState>;
  onCreateOffer?: (
    deliverableId: string,
    selectedAssetId: number | null,
  ) => void;
  enableSessionSelling?: boolean;
  initialSessionSellingDialog?: "prepare" | "retry" | null;
  onSessionSellingChange?: (value: SalePreparationReadiness) => void;
  onSellingModeChange?: (value: PhotoshootSellingMode) => void;
  onMembersChanged?: (detail: PhotoshootDetail) => void;
}) {
  const [detail, setDetail] = useState<PhotoshootDetail | null>(null);
  const [selectedAssetId, setSelectedAssetId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [registering, setRegistering] = useState(false);
  const [savingMode, setSavingMode] = useState(false);
  const [savingChannel, setSavingChannel] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedForMove, setSelectedForMove] = useState<Set<number>>(
    new Set(),
  );
  const [confirmMove, setConfirmMove] = useState(false);
  const [movingMembers, setMovingMembers] = useState(false);
  const [curationMessage, setCurationMessage] = useState(() =>
    new URLSearchParams(window.location.search).has("teaserAdded")
      ? "Teaser added as Shot 1. Existing shots shifted forward."
      : "",
  );
  const [startingTeaser, setStartingTeaser] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setError("");
    setSelectedAssetId(null);
    setSelectMode(false);
    setSelectedForMove(new Set());
    setConfirmMove(false);
    setCurationMessage("");
    fetch(`/api/v1/photoshoot-gallery/${encodeURIComponent(deliverableId)}`, {
      cache: "no-store",
      signal: controller.signal,
    })
      .then((response) => readJson<PhotoshootDetail>(response))
      .then((result) => {
        setDetail({
          ...result,
          sellingMode: result.sellingMode || "SESSION",
          bundleSalesChannel:
            result.sellingMode === "BUNDLE"
              ? result.bundleSalesChannel ||
                (result.sourceKind === "GENERATION_LIBRARY_IMPORT"
                  ? null
                  : "CHAT")
              : null,
        });
        setSelectedAssetId(
          result.members.find((member) => member.isHero)?.assetId ??
            result.members[0]?.assetId ??
            null,
        );
      })
      .catch((reason: unknown) => {
        if ((reason as { name?: string }).name !== "AbortError")
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to load Photoshoot.",
          );
      });
    return () => controller.abort();
  }, [deliverableId]);

  const register = async () => {
    if (!onAddToAssetLibrary || registering) return;
    setRegistering(true);
    setError("");
    try {
      const registrationState = await onAddToAssetLibrary(deliverableId);
      setDetail((current) =>
        current ? { ...current, registrationState } : current,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to register Photoshoot.",
      );
    } finally {
      setRegistering(false);
    }
  };

  const changeSellingMode = async (sellingMode: PhotoshootSellingMode) => {
    if (!detail || detail.sellingMode === sellingMode || savingMode) return;
    setSavingMode(true);
    setError("");
    try {
      const result = await fetch(
        `/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/selling-mode`,
        {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ sellingMode }),
        },
      ).then((response) =>
        readJson<{ sellingMode: PhotoshootSellingMode }>(response),
      );
      setDetail((current) =>
        current
          ? {
              ...current,
              sellingMode: result.sellingMode,
              bundleSalesChannel:
                result.sellingMode === "BUNDLE"
                  ? current.bundleSalesChannel || "CHAT"
                  : current.bundleSalesChannel,
            }
          : current,
      );
      onSellingModeChange?.(result.sellingMode);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to change selling mode.",
      );
    } finally {
      setSavingMode(false);
    }
  };

  const changeBundleSalesChannel = async (
    bundleSalesChannel: BundleSalesChannel,
  ) => {
    if (
      !detail ||
      detail.sellingMode !== "BUNDLE" ||
      detail.bundleSalesChannel === bundleSalesChannel ||
      savingChannel
    )
      return;
    setSavingChannel(true);
    setError("");
    try {
      const result = await fetch(
        `/api/v1/assets/photoshoots/${encodeURIComponent(deliverableId)}/bundle-sales-channel`,
        {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ bundleSalesChannel }),
        },
      ).then((response) =>
        readJson<{ bundleSalesChannel: BundleSalesChannel }>(response),
      );
      setDetail((current) =>
        current
          ? { ...current, bundleSalesChannel: result.bundleSalesChannel }
          : current,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to change Bundle sales channel.",
      );
    } finally {
      setSavingChannel(false);
    }
  };

  const selectedMember =
    detail?.members.find((member) => member.assetId === selectedAssetId) ||
    null;
  const createTeaser = async () => {
    if (!detail || selectedMember?.shotOrder !== 1 || startingTeaser) return;
    setStartingTeaser(true);
    setError("");
    try {
      const result = await fetch(
        `/api/v1/photoshoot-gallery/${encodeURIComponent(deliverableId)}/session-teaser-intents`,
        { method: "POST" },
      ).then((response) => readJson<{ redirect: string }>(response));
      window.location.href = result.redirect;
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to open Session Teaser editing.",
      );
      setStartingTeaser(false);
    }
  };
  const maximumExtractable = detail?.memberCuration?.maximumExtractable ?? 0;
  const moveBlocked =
    selectedForMove.size === 0 || selectedForMove.size > maximumExtractable;
  const toggleMoveSelection = (assetId: number) =>
    setSelectedForMove((current) => {
      const next = new Set(current);
      if (next.has(assetId)) next.delete(assetId);
      else next.add(assetId);
      return next;
    });
  const refreshDetail = async () => {
    const result = await fetch(
      `/api/v1/photoshoot-gallery/${encodeURIComponent(deliverableId)}`,
      {
        cache: "no-store",
      },
    ).then((response) => readJson<PhotoshootDetail>(response));
    setDetail(result);
    setSelectedAssetId(
      result.members.find((member) => member.isHero)?.assetId ??
        result.members[0]?.assetId ??
        null,
    );
    onMembersChanged?.(result);
    return result;
  };
  const moveToImages = async () => {
    if (!detail || moveBlocked || movingMembers) return;
    const assetIds = [...selectedForMove];
    setMovingMembers(true);
    setError("");
    try {
      const result = await fetch(
        `/api/v1/photoshoot-gallery/${encodeURIComponent(deliverableId)}/members/move-to-images`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ assetIds }),
        },
      ).then((response) => readJson<{ movedCount: number }>(response));
      await refreshDetail();
      setSelectedForMove(new Set());
      setSelectMode(false);
      setConfirmMove(false);
      setCurationMessage(
        `${result.movedCount} ${result.movedCount === 1 ? "image" : "images"} moved to Asset Library → Images`,
      );
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Unable to move Photoshoot images.",
      );
      setConfirmMove(false);
    } finally {
      setMovingMembers(false);
    }
  };
  return (
    <section className="photoshoot-detail-page">
      <header className="photoshoot-detail-header">
        <div>
          <p className="photoshoot-gallery-page__eyebrow">Photoshoot</p>
          {detail && (
            <p>
              {new Date(detail.completedAt).toLocaleDateString()}{" "}
              <span aria-hidden="true">·</span> {detail.shotCount} images
            </p>
          )}
        </div>
        <div className="photoshoot-detail-header__actions">
          {detail?.memberCuration?.eligible && !selectMode && (
            <button
              type="button"
              className="photoshoot-detail-select"
              onClick={() => {
                setSelectMode(true);
                setSelectedForMove(new Set());
                setCurationMessage("");
              }}
            >
              <CheckSquare size={16} /> Select
            </button>
          )}
          {selectedMember && !selectMode && (
            <button
              type="button"
              onClick={() => {
                window.location.href = videoStudioLink({
                  type: "photoshoot_shot",
                  id: String(selectedMember.assetId),
                  previewUrl: selectedMember.imageUrl,
                  label: `Shot ${selectedMember.shotOrder}`,
                  context: `Production Photoshoot · Shot ${selectedMember.shotOrder}`,
                });
              }}
            >
              <Video size={16} /> Create Video
            </button>
          )}
          {detail && onCreateOffer && !selectMode && (
            <button
              type="button"
              onClick={() => onCreateOffer(deliverableId, selectedAssetId)}
            >
              Create Offer
            </button>
          )}
          <button
            type="button"
            className="photoshoot-detail-close"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </header>
      {error && <div role="alert">{error}</div>}
      {!detail && !error && (
        <div className="photoshoot-gallery-empty">Loading Photoshoot...</div>
      )}
      {detail && (
        <>
          {curationMessage && (
            <div className="photoshoot-curation-success" role="status">
              <strong>{curationMessage}</strong>
              <a href="/library/assets?assetType=images">View Images</a>
            </div>
          )}
          {selectMode && (
            <div
              className="photoshoot-curation-toolbar"
              role="toolbar"
              aria-label="Photoshoot member selection"
            >
              <strong>{selectedForMove.size} selected</strong>
              <button
                type="button"
                onClick={() =>
                  setSelectedForMove(
                    new Set(
                      detail.members
                        .slice(0, maximumExtractable)
                        .map((member) => member.assetId),
                    ),
                  )
                }
              >
                Select All Eligible
              </button>
              <button
                type="button"
                disabled={!selectedForMove.size}
                onClick={() => setSelectedForMove(new Set())}
              >
                Clear
              </button>
              <button
                type="button"
                className="photoshoot-curation-toolbar__move"
                disabled={moveBlocked || movingMembers}
                onClick={() => setConfirmMove(true)}
              >
                <Images size={16} /> Move to Images
              </button>
              <button
                type="button"
                onClick={() => {
                  setSelectMode(false);
                  setSelectedForMove(new Set());
                }}
              >
                Exit Select
              </button>
              {selectedForMove.size > maximumExtractable && (
                <span>A Photoshoot must retain at least 2 images.</span>
              )}
            </div>
          )}
          <div
            className="photoshoot-detail-filmstrip"
            aria-label="Photoshoot filmstrip"
          >
            {detail.members.map((member) => (
              <button
                type="button"
                className={`photoshoot-detail-shot${!selectMode && member.assetId === selectedAssetId ? " photoshoot-detail-shot--selected" : ""}${selectMode && selectedForMove.has(member.assetId) ? " photoshoot-detail-shot--curation-selected" : ""}`}
                key={member.assetId}
                onClick={() =>
                  selectMode
                    ? toggleMoveSelection(member.assetId)
                    : setSelectedAssetId(member.assetId)
                }
                aria-label={
                  selectMode
                    ? `${selectedForMove.has(member.assetId) ? "Deselect" : "Select"} Shot ${member.shotOrder} for moving`
                    : `Select shot ${member.shotOrder}`
                }
                aria-pressed={
                  selectMode
                    ? selectedForMove.has(member.assetId)
                    : member.assetId === selectedAssetId
                }
              >
                <span>Shot {member.shotOrder}</span>
                <div className="photoshoot-detail-shot__media">
                  {selectMode && (
                    <span
                      className="photoshoot-detail-shot__checkbox"
                      aria-hidden="true"
                    >
                      {selectedForMove.has(member.assetId) ? (
                        <CheckSquare />
                      ) : (
                        <Square />
                      )}
                    </span>
                  )}
                  <ContainedMediaImage
                    src={
                      selectedAssetId === member.assetId
                        ? member.imageUrl.replace("/thumbnail", "/preview")
                        : member.imageUrl
                    }
                    alt={`Shot ${member.shotOrder}`}
                  />
                </div>
              </button>
            ))}
          </div>
          <div
            className="photoshoot-intelligence-cards"
            aria-label="Intelligence Inspector"
          >
            <IntelligenceCard
              title="Photoshoot Summary"
              intelligence={detail.productionIntelligence || {}}
              fields={productionFields}
            />
            <IntelligenceCard
              title={`Selected Shot — Shot ${selectedMember?.shotOrder ?? 1}`}
              intelligence={selectedMember?.intelligence || {}}
              fields={shotFields}
              actions={
                selectedMember?.shotOrder === 1 &&
                detail.sellingMode === "SESSION" &&
                detail.sessionTeaser?.eligible &&
                !selectMode ? (
                  <button
                    type="button"
                    disabled={startingTeaser}
                    onClick={() => void createTeaser()}
                  >
                    <Pencil size={16} />{" "}
                    {detail.sessionTeaser.hasSessionTeaser
                      ? "Replace Teaser"
                      : "Create Teaser"}
                  </button>
                ) : undefined
              }
            />
          </div>
          {detail.commercialAssets && detail.commercialAssets.length > 0 && (
            <section
              className="commercial-assets"
              aria-labelledby="photoshoot-commercial-assets-title"
            >
              <header>
                <small>Supporting Media</small>
                <h2 id="photoshoot-commercial-assets-title">
                  Commercial Assets
                </h2>
              </header>
              <div>
                {detail.commercialAssets.map((asset) => (
                  <figure
                    key={`${asset.kind}-${asset.assetId || asset.previewUrl}`}
                  >
                    <ContainedMediaImage
                      src={asset.previewUrl}
                      alt={asset.label}
                    />
                    <figcaption>
                      <strong>{asset.label}</strong>
                      <span>{asset.status}</span>
                    </figcaption>
                  </figure>
                ))}
              </div>
            </section>
          )}
          {enableSessionSelling && detail.sellingMode === "SESSION" && (
            <SessionSellingPanel
              deliverableId={deliverableId}
              initialDialog={initialSessionSellingDialog}
              onReadinessChange={onSessionSellingChange}
              deferStrategyGeneration={Boolean(
                detail.sessionTeaser?.eligible &&
                  !detail.sessionTeaser.hasSessionTeaser,
              )}
            />
          )}
          {enableSessionSelling && (
            <section
              className="photoshoot-selling-mode"
              aria-labelledby="selling-mode-title"
            >
              <header>
                <div>
                  <small>Commercial Configuration</small>
                  <h2 id="selling-mode-title">Selling Mode</h2>
                </div>
              </header>
              <div className="photoshoot-selling-mode__options">
                {detail.sourceKind !== "GENERATION_LIBRARY_IMPORT" && (
                  <button
                    type="button"
                    aria-pressed={detail.sellingMode === "SESSION"}
                    disabled={savingMode}
                    onClick={() => void changeSellingMode("SESSION")}
                  >
                    <strong>Session</strong>
                    <span>
                      Sell this Photoshoot progressively, one asset at a time.
                    </span>
                  </button>
                )}
                <button
                  type="button"
                  aria-pressed={detail.sellingMode === "BUNDLE"}
                  disabled={savingMode}
                  onClick={() => void changeSellingMode("BUNDLE")}
                >
                  <strong>Bundle</strong>
                  <span>
                    Sell the complete Photoshoot together as one bundle.
                  </span>
                </button>
              </div>
              {savingMode && <p role="status">Saving selling mode...</p>}
            </section>
          )}
          {enableSessionSelling && detail.sellingMode === "BUNDLE" && (
            <section
              className="photoshoot-selling-mode"
              aria-labelledby="bundle-sales-channel-title"
            >
              <header>
                <div>
                  <small>Commercial Configuration</small>
                  <h2 id="bundle-sales-channel-title">Sell Bundle Through</h2>
                </div>
              </header>
              <div className="photoshoot-selling-mode__options">
                <button
                  type="button"
                  aria-pressed={detail.bundleSalesChannel === "CHAT"}
                  disabled={savingChannel}
                  onClick={() => void changeBundleSalesChannel("CHAT")}
                >
                  <strong>Chats</strong>
                  <span>
                    Sell this Bundle directly in customer conversations.
                  </span>
                </button>
                <button
                  type="button"
                  aria-pressed={detail.bundleSalesChannel === "CONTENT_WALL"}
                  disabled={savingChannel}
                  onClick={() => void changeBundleSalesChannel("CONTENT_WALL")}
                >
                  <strong>Ava&apos;s Content Wall</strong>
                  <span>Sell this Bundle through Ava&apos;s Content Wall.</span>
                </button>
              </div>
              {savingChannel && (
                <p role="status">Saving Bundle sales channel...</p>
              )}
            </section>
          )}
          {enableSessionSelling &&
            detail.sellingMode === "BUNDLE" &&
            !detail.bundleSalesChannel && (
              <p className="photoshoot-selling-mode__guidance">
                Choose Chats or Ava&apos;s Content Wall to configure sale
                preparation.
              </p>
            )}
          {enableSessionSelling &&
            detail.sellingMode === "BUNDLE" &&
            detail.bundleSalesChannel && (
              <BundleSellingPanel
                deliverableId={deliverableId}
                salesChannel={detail.bundleSalesChannel}
                onReadinessChange={onSessionSellingChange}
              />
            )}
          <div className="photoshoot-detail-sections">
            <details>
              <summary>Commerce</summary>
              <div className="photoshoot-detail-section-content">
                <p>
                  <strong>Asset Library status</strong>{" "}
                  {registrationLabel(detail.registrationState)}
                </p>
                {detail.registrationState === "PHOTOSHOOT_COMPLETE" &&
                  onAddToAssetLibrary && (
                    <button
                      type="button"
                      disabled={registering}
                      onClick={() => void register()}
                    >
                      Add to Asset Library
                    </button>
                  )}
              </div>
            </details>
            <details>
              <summary>Technical Details</summary>
              <div className="photoshoot-detail-section-content">
                <dl>
                  {Object.entries(detail.technical).map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{String(value ?? "")}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </details>
          </div>
          {confirmMove && (
            <div className="photoshoot-curation-confirm" role="presentation">
              <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="photoshoot-curation-confirm-title"
              >
                <h2 id="photoshoot-curation-confirm-title">
                  Move {selectedForMove.size}{" "}
                  {selectedForMove.size === 1 ? "Image" : "Images"}?
                </h2>
                <p>
                  These images will be removed from this Photoshoot and become
                  standalone Images in Asset Library.
                </p>
                <strong>
                  Photoshoot: {detail.members.length} →{" "}
                  {detail.members.length - selectedForMove.size} images
                </strong>
                {detail.members.some(
                  (member) =>
                    member.isHero && selectedForMove.has(member.assetId),
                ) && (
                  <p>A new Photoshoot cover will be selected automatically.</p>
                )}
                <footer>
                  <button
                    type="button"
                    disabled={movingMembers}
                    onClick={() => setConfirmMove(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="photoshoot-curation-confirm__move"
                    disabled={movingMembers}
                    onClick={() => void moveToImages()}
                  >
                    {movingMembers ? "Moving…" : "Move to Images"}
                  </button>
                </footer>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
