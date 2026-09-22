import { DeliveryUncertainBadge, DeliveryUncertainDismissModal } from "./DeliveryUncertainDismissal";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  ArrowLeft,
  MoreHorizontal,
  RefreshCw,
  Search,
  Users,
  X,
} from "lucide-react";
import { Link, useInRouterContext } from "react-router-dom";
import {
  relationshipsApi,
  type MarketTier,
  type MarketTierProjection,
  type Relationship,
  type RelationshipControl,
  type RelationshipFilter,
  type RelationshipIntelligence,
  type RelationshipMessage,
  type RelationshipSort,
  type RelationshipSummary,
} from "./api";
import "./relationships.css";
import "./chat-polish.css";
import "./inspect-resolve.css";
import { RelationshipOfferDrawer } from "./RelationshipOfferDrawer";
import { InspectResolveDialog } from "./InspectResolveDialog";
import { ConversationAnalysisDialog } from "./ConversationAnalysisDialog";
import {
  buildChatTranscript,
  saveChatTranscript,
  transcriptFilename,
} from "./chatTranscriptDownload";
import {
  formatChatCalendarDate,
  formatChatDay,
  formatChatTime,
} from "./chatTime";

const CHAT_REFRESH_INTERVAL_MS = 3000;
const TRANSCRIPT_BOTTOM_THRESHOLD_PX = 80;

const money = (minor: number) =>
  new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
  }).format(minor / 100);
const time = (value: string) => formatChatTime(value);
const day = (value: string) => formatChatDay(value);
const title = (value: string | null | undefined) =>
  value
    ? value
        .replaceAll("_", " ")
        .toLowerCase()
        .replace(/\b\w/g, (letter) => letter.toUpperCase())
    : "—";
const calendarDate = (value: string | null | undefined) =>
  value ? formatChatCalendarDate(value) : "—";
const overdue = (value: string | null | undefined) =>
  value
    ? `${Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))}m`
    : "";
const operationalBadge = (person: Relationship) => {
  switch (person.operationalStatus) {
    case "IGNORED":
      return "IGNORED";
    case "MANUAL_MODE":
      return "MANUAL MODE";
    case "SYSTEM_INCIDENT":
      return "SYSTEM INCIDENT";
    case "DELIVERY_UNCERTAIN":
      return "DELIVERY UNCERTAIN";
    case "RECOVERY_PENDING":
      return "RECOVERY PENDING";
    case "NEEDS_ATTENTION":
      return "NEEDS ATTENTION";
    case "MEDIUM_MARKET_LIMIT":
      return "MED MARKET LIMIT";
    case "LOW_MARKET_LIMIT":
      return "LOW MARKET LIMIT";
    case "OVERDUE":
      return `OVERDUE · ${overdue(person.overdueSince)}`;
    case "REPLY_SCHEDULED":
      return `REPLY SCHEDULED · ${person.nextAutomaticAttemptAt ? time(person.nextAutomaticAttemptAt) : ""}`;
    case "REPLY_READY":
      return `REPLY READY · ${person.nextAutomaticAttemptAt ? time(person.nextAutomaticAttemptAt) : ""}`;
    default:
      return null;
  }
};
function ReplyReadyBadge({ person, onCancel }: { person: Relationship; onCancel: () => void }) {
  const anchor = useRef<HTMLSpanElement>(null);
  const tooltip = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tooltipId = useId();
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 8, top: 8 });
  const cancelClose = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = null;
  };
  const show = () => {
    cancelClose();
    setOpen(true);
  };
  const scheduleClose = () => {
    cancelClose();
    closeTimer.current = setTimeout(() => setOpen(false), 80);
  };
  useEffect(() => {
    if (!open) return;
    const place = () => {
      const trigger = anchor.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const width = Math.min(360, window.innerWidth - 16);
      const measuredHeight = tooltip.current?.offsetHeight || 180;
      const below = window.innerHeight - rect.bottom;
      setPosition({
        left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
        top:
          below >= Math.min(measuredHeight, 280) + 8
            ? rect.bottom + 6
            : Math.max(8, rect.top - Math.min(measuredHeight, 280) - 6),
      });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);
  useEffect(() => () => cancelClose(), []);

  return (
    <>
      <span
        aria-describedby={open ? tooltipId : undefined}
        className="chat-badge is-operational is-reply_ready"
        onBlur={scheduleClose}
        onFocus={show}
        onMouseEnter={show}
        onMouseLeave={scheduleClose}
        ref={anchor}
        tabIndex={0}
      >
        {operationalBadge(person)}
      </span>
      {open &&
        createPortal(
          <div
            className="reply-ready-preview"
            id={tooltipId}
            onFocus={show}
            onMouseEnter={show}
            onMouseLeave={scheduleClose}
            ref={tooltip}
            role="tooltip"
            style={position}
            tabIndex={0}
          >
            <strong>Ava&apos;s scheduled reply</strong>
            <p>{person.pendingReplyPreview}</p>
            <button className="cancel-reply-button" onClick={onCancel} type="button">Cancel Reply</button>
          </div>,
          document.body,
        )}
    </>
  );
}
const lifecycleBadge = (person: Relationship) =>
  person.isBuyer ? "CUSTOMER" : "PROSPECT";
const tierLabel = (tier: MarketTier | undefined) =>
  tier === "MEDIUM" ? "MED" : tier;
function MarketBadge({ tier }: { tier: MarketTier | undefined }) {
  return tier && tier !== "UNCLASSIFIED" ? (
    <span
      aria-label={`Country Tier: ${title(tier)}`}
      className={`chat-badge is-market-tier is-${tier.toLowerCase()}`}
      title={`Country Tier: ${title(tier)}`}
    >
      {tierLabel(tier)}
    </span>
  ) : null;
}
function TimeWasterBadge({
  active,
  failedPresentationCount,
  verifiedPurchaseCount,
}: {
  active: boolean | undefined;
  failedPresentationCount: number | undefined;
  verifiedPurchaseCount: number | undefined;
}) {
  if (!active) return null;
  const explanation = `Time-Waster · ${failedPresentationCount ?? 0} failed PPVs · ${verifiedPurchaseCount ?? 0} purchases · Reduced investment active`;
  return (
    <span
      aria-label={explanation}
      className="chat-badge is-time-waster"
      data-tooltip={explanation}
      tabIndex={0}
      title={explanation}
    >
      TW
    </span>
  );
}
type PopupPosition = {
  left: number;
  top: number;
  maxHeight: number;
  placement: "top" | "bottom";
};
function FloatingMenu({
  anchor,
  open,
  onClose,
  label,
  className = "",
  children,
}: {
  anchor: React.RefObject<HTMLButtonElement | null>;
  open: boolean;
  onClose: () => void;
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  const menu = useRef<HTMLDivElement>(null),
    [position, setPosition] = useState<PopupPosition>({
      left: 8,
      top: 8,
      maxHeight: 320,
      placement: "bottom",
    });
  useEffect(() => {
    if (!open) return;
    const place = () => {
      const trigger = anchor.current,
        node = menu.current;
      if (!trigger || !node) return;
      const gap = 6,
        margin = 8,
        rect = trigger.getBoundingClientRect(),
        width = Math.min(
          Math.max(node.offsetWidth, 220),
          window.innerWidth - margin * 2,
        ),
        availableBelow = window.innerHeight - rect.bottom - margin,
        availableAbove = rect.top - margin,
        placeAbove =
          availableBelow < Math.min(node.scrollHeight, 240) &&
          availableAbove > availableBelow,
        maxHeight = Math.max(
          120,
          placeAbove ? availableAbove - gap : availableBelow - gap,
        ),
        top = placeAbove
          ? Math.max(
              margin,
              rect.top - Math.min(node.scrollHeight, maxHeight) - gap,
            )
          : Math.min(window.innerHeight - margin, rect.bottom + gap),
        left = Math.min(
          Math.max(margin, rect.right - width),
          window.innerWidth - width - margin,
        );
      setPosition({
        left,
        top,
        maxHeight,
        placement: placeAbove ? "top" : "bottom",
      });
    };
    const frame = requestAnimationFrame(() => {
      place();
      menu.current
        ?.querySelector<HTMLButtonElement>("button:not(:disabled)")
        ?.focus();
    });
    const closeOnOutside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!menu.current?.contains(target) && !anchor.current?.contains(target))
        onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        anchor.current?.focus();
      }
    };
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      document.removeEventListener("pointerdown", closeOnOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [anchor, onClose, open]);
  if (!open) return null;
  return createPortal(
    <div
      aria-label={label}
      className={`conversation-popup-menu ${className}`.trim()}
      data-placement={position.placement}
      ref={menu}
      role="menu"
      style={{
        left: position.left,
        top: position.top,
        maxHeight: position.maxHeight,
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
function ClassificationTriggerPortal({
  buttonRef,
  expanded,
  onToggle,
}: {
  buttonRef: React.RefObject<HTMLButtonElement | null>;
  expanded: boolean;
  onToggle: () => void;
}) {
  const [target, setTarget] = useState<Element | null>(null);
  useEffect(() => {
    setTarget(document.querySelector(".selected-customer-title"));
  }, []);
  return target
    ? createPortal(
        <button
          aria-expanded={expanded}
          aria-haspopup="menu"
          aria-label="Classify relationship"
          className="classify-trigger"
          onClick={onToggle}
          ref={buttonRef}
          type="button"
        >
          CLASSIFY
        </button>,
        target,
      )
    : null;
}
function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value ?? "—"}</dd>
    </div>
  );
}
function OfferSummary({
  label,
  item,
}: {
  label: string;
  item: RelationshipIntelligence["salesPerformance"]["lastOffer"];
}) {
  return (
    <div className="intelligence-summary">
      <strong>{label}</strong>
      {item ? (
        <>
          <span>{item.title}</span>
          <small>
            {[
              item.type,
              item.priceMinor != null ? money(item.priceMinor) : null,
              calendarDate(item.presentedAt || item.purchasedAt),
            ]
              .filter(Boolean)
              .join(" · ")}
          </small>
        </>
      ) : (
        <span>—</span>
      )}
    </div>
  );
}
function PPVEscalationCard({
  data,
  onReadiness,
}: {
  data: RelationshipIntelligence["ppvEscalation"] | null | undefined;
  onReadiness?: (trigger: HTMLButtonElement) => void;
}) {
  if (!data)
    return (
      <section aria-label="PPV Escalation" className="ppv-escalation">
        <header>
          <h3>PPV Escalation</h3>
        </header>
        <p>Commercial projection unavailable.</p>
      </section>
    );
  return (
    <section
      aria-label="PPV Escalation"
      className={`ppv-escalation is-${data.stage.toLowerCase().replaceAll("_", "-")}`}
    >
      <header>
        <h3>PPV Escalation</h3>
      </header>
      <dl className="ppv-escalation-primary">
        <Metric label="Stage" value={title(data.stage)} />
        <Metric label="Next Action" value={title(data.nextAction)} />
      </dl>
      <dl className="ppv-escalation-support">
        <Metric label="Warmup" value={title(data.warmupStatus)} />
        <Metric
          label="Commercial Signal"
          value={title(data.commercialSignal)}
        />
        <Metric
          label="Current Offer"
          value={data.currentOffer?.title || "None"}
        />
        <Metric label="Last Offer" value={data.lastOffer?.title || "None"} />
      </dl>
      <p className="ppv-escalation-why">
        <strong>Why</strong>
        {data.why}
      </p>
      {data.conversationPolicy && (
        <dl className="ppv-escalation-support" aria-label="Nonbuyer conversation policy">
          <Metric label="Conversation Policy" value={title(data.conversationPolicy.responsePurpose || "BACKOFF")} />
          <Metric label="Supporter Boundary" value={data.conversationPolicy.supporterBoundaryCommunicated ? "Communicated" : "Not Yet Communicated"} />
          <Metric label="Time-Waster" value={data.conversationPolicy.timeWaster ? "Active" : "No"} />
          <Metric label="Optional Replies Today" value={data.conversationPolicy.optionalReplyAllowance == null ? "—" : `${data.conversationPolicy.optionalRepliesUsedToday || 0} / ${data.conversationPolicy.optionalReplyAllowance}`} />
          <Metric label="Sexual Access" value={data.conversationPolicy.sexualAccessGated ? "Gated" : "Open"} />
          <Metric label="Relationship" value={data.conversationPolicy.relationshipActive ? "Active" : "Unknown"} />
        </dl>
      )}
      {data.offerReadiness && onReadiness && (
        <button
          className="offer-readiness-trigger"
          onClick={(event) => onReadiness(event.currentTarget)}
          type="button"
        >
          Offer Readiness
          <span>{data.offerReadiness.distance}</span>
        </button>
      )}
      <details>
        <summary>Details</summary>
        <dl className="intelligence-metrics">
          <Metric
            label="Commercial Intent"
            value={title(data.commercialIntent)}
          />
          <Metric
            label="Offer Eligibility"
            value={title(data.offerEligibility)}
          />
          <Metric
            label="PurchaseIntent"
            value={title(data.purchaseIntentState)}
          />
          <Metric
            label="Paid Offers Presented"
            value={data.paidOffersPresented}
          />
          <Metric
            label="Verified Purchases"
            value={data.verifiedPurchases ?? "Unverified"}
          />
          <Metric
            label="Messages Since Last Offer"
            value={data.messagesSinceLastOffer ?? "—"}
          />
          <Metric label="Follow-Up" value={title(data.followUpStatus)} />
          <Metric label="Nudge" value={title(data.nudgeStatus)} />
          <Metric label="Backoff" value={title(data.backoffStatus)} />
          <Metric
            label="Sales Brain"
            value={title(data.evidence.salesBrainDecision)}
          />
          <Metric
            label="Decision Reason"
            value={title(data.evidence.salesBrainReason)}
          />
        </dl>
      </details>
    </section>
  );
}
function OfferReadinessModal({
  data,
  person,
  close,
}: {
  data: NonNullable<RelationshipIntelligence["ppvEscalation"]>["offerReadiness"];
  person: Relationship;
  close: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeButton.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [close]);
  return createPortal(
    <div
      aria-label="Offer Readiness dialog"
      className="offer-readiness-modal"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      role="presentation"
    >
      <section
        aria-labelledby="offer-readiness-title"
        aria-modal="true"
        className="offer-readiness-panel"
        role="dialog"
      >
        <header>
          <div>
            <small>PPV Escalation</small>
            <h2 id="offer-readiness-title">Offer Readiness</h2>
            <span>{person.displayName}</span>
          </div>
          <button aria-label="Close Offer Readiness" onClick={close} ref={closeButton} type="button">
            <X size={18} />
          </button>
        </header>
        <div className="offer-readiness-distance">
          <small>Current distance</small>
          <strong>{data.distance}</strong>
          <p>{data.summary}</p>
        </div>
        <div className="offer-readiness-requirements">
          {data.hotPath && (
            <article className={`is-${data.hotPath.status.toLowerCase()}`}>
              <header>
                <strong>{data.hotPath.label}</strong>
                <span>{title(data.hotPath.status)}</span>
              </header>
              <dl>
                <Metric
                  label="Sustained Conversation"
                  value={
                    data.hotPath.sustainedConversationCount == null
                      ? "Unavailable"
                      : `${data.hotPath.sustainedConversationCount} / ${data.hotPath.sustainedConversationRequired}`
                  }
                />
                <Metric
                  label="Sexual Receptiveness"
                  value={
                    data.hotPath.sexualEngagementCount == null
                      ? "Unavailable"
                      : `${data.hotPath.sexualEngagementCount} / ${data.hotPath.sexualEngagementRequired}`
                  }
                />
                <Metric
                  label="Current Hot Tone"
                  value={data.hotPath.currentHotToneQualified ? "Satisfied" : "Not satisfied"}
                />
                <Metric
                  label="No Prior Offer Exposure"
                  value={data.hotPath.noPriorPaidOfferExposure ? "Satisfied" : "Blocked"}
                />
                <Metric
                  label="Commercial Safeguards"
                  value={data.hotPath.commercialSafeguardsPassed ? "Passed" : "Blocked"}
                />
              </dl>
              <p>{data.hotPath.note}</p>
            </article>
          )}
          {data.requirements.map((requirement) => (
            <article className={`is-${requirement.status.toLowerCase()}`} key={requirement.key}>
              <header>
                <strong>{requirement.label}</strong>
                <span>{title(requirement.status)}</span>
              </header>
              <dl>
                <Metric label="Current" value={requirement.current == null ? "Unavailable" : String(requirement.current)} />
                <Metric label="Required" value={requirement.required == null ? "Unavailable" : String(requirement.required)} />
              </dl>
              <p>{requirement.explanation}</p>
              {!requirement.blocking && <small>Qualifying signal; not an independent offer authorization.</small>}
            </article>
          ))}
        </div>
        <aside className={`offer-readiness-bypass${data.bypass.available ? " is-available" : ""}`}>
          <strong>Direct commercial intent</strong>
          <p>{data.bypass.note}</p>
        </aside>
      </section>
    </div>,
    document.body,
  );
}
function IntelligenceDrawer({
  data,
  error,
  loading,
  person,
  onReadiness,
}: {
  data: RelationshipIntelligence | null;
  error: string;
  loading: boolean;
  person: Relationship;
  onReadiness: (trigger: HTMLButtonElement) => void;
}) {
  const memory = data?.relationshipIntelligence;
  return (
    <aside
      aria-label="Customer Intelligence"
      className="customer-intelligence-drawer"
    >
      <div aria-hidden="true" className="customer-intelligence-body" hidden>
        {loading && (
          <div className="relationships-state" role="status">
            Loading Customer Intelligence…
          </div>
        )}
        {error && (
          <div className="relationships-state is-error" role="alert">
            {error}
          </div>
        )}
        {!loading && !error && data && (
          <>
            {data.partial && (
              <p className="intelligence-notice">
                This Telegram prospect is not yet mapped to a verified customer.
                Available relationship memory is shown; verified commerce values
                remain unknown.
              </p>
            )}
            <PPVEscalationCard data={data.ppvEscalation} onReadiness={onReadiness} />
            <section>
              <h3>Communication</h3>
              <dl className="intelligence-metrics">
                <Metric
                  label="Communication Status"
                  value={person.ignored ? "Ignored" : "Active"}
                />
              </dl>
            </section>
            <section>
              <h3>Customer Value</h3>
              <dl className="intelligence-metrics">
                <Metric
                  label="Status"
                  value={title(data.customerValue.buyerStatus)}
                />
                <Metric
                  label="Value"
                  value={title(data.customerValue.valueTier)}
                />
                <Metric
                  label="Attention"
                  value={title(data.customerValue.attentionTier)}
                />
                <Metric
                  label="Lifetime Spend"
                  value={
                    data.customerValue.lifetimeSpendMinor == null
                      ? "—"
                      : money(data.customerValue.lifetimeSpendMinor)
                  }
                />
                <Metric
                  label="Purchases"
                  value={data.customerValue.purchaseCount ?? "—"}
                />
                <Metric
                  label="Lifecycle"
                  value={title(data.customerValue.relationshipLifecycle)}
                />
              </dl>
            </section>
            <section>
              <h3>Sales Performance</h3>
              <dl className="intelligence-metrics">
                <Metric
                  label="Presented"
                  value={data.salesPerformance.offersPresented}
                />
                <Metric
                  label="Purchased"
                  value={data.salesPerformance.offersPurchased}
                />
                <Metric
                  label="Not Purchased"
                  value={data.salesPerformance.offersNotPurchased}
                />
                <Metric
                  label="Conversion"
                  value={
                    data.salesPerformance.conversionRate == null
                      ? "—"
                      : `${Math.round(data.salesPerformance.conversionRate * 100)}%`
                  }
                />
              </dl>
              <OfferSummary
                label="Last Offer"
                item={data.salesPerformance.lastOffer}
              />
              <OfferSummary
                label="Last Purchase"
                item={data.salesPerformance.lastPurchase}
              />
            </section>
            <section>
              <h3>Commercial State</h3>
              <dl className="intelligence-metrics">
                <Metric
                  label="Intent"
                  value={
                    data.commercialState.activePurchaseIntent
                      ? title(data.commercialState.activePurchaseIntent.status)
                      : "None"
                  }
                />
                <Metric
                  label="Session"
                  value={
                    data.commercialState.activeSalesSession
                      ? `${title(data.commercialState.activeSalesSession.state)} · ${title(data.commercialState.activeSalesSession.stage)}`
                      : "None"
                  }
                />
                <Metric
                  label="Active Offer"
                  value={data.commercialState.activeOffer?.title || "None"}
                />
              </dl>
            </section>
            {data.purchaseHistory.length > 0 && (
              <section>
                <h3>Purchase History</h3>
                <div className="intelligence-history">
                  {data.purchaseHistory.map((item, index) => (
                    <article key={`${item.purchasedAt}-${index}`}>
                      <strong>{item.title}</strong>
                      <span>{item.type || "Content"}</span>
                      <small>
                        {[
                          calendarDate(item.purchasedAt),
                          item.priceMinor != null
                            ? money(item.priceMinor)
                            : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </small>
                    </article>
                  ))}
                </div>
              </section>
            )}
            <section>
              <h3>Relationship Intelligence</h3>
              <dl className="intelligence-facts">
                <Metric label="Location" value={memory?.location || "—"} />
                <Metric label="Timezone" value={memory?.timezone || "—"} />
              </dl>
              {[
                ["Interests", memory?.interests],
                ["Pets", memory?.pets],
                ["Music", memory?.music],
                ["Preferences", memory?.preferences],
              ].map(([label, values]) =>
                Array.isArray(values) && values.length ? (
                  <div className="intelligence-tags" key={String(label)}>
                    <strong>{label}</strong>
                    <div>
                      {values.map((value) => (
                        <span key={value}>{value}</span>
                      ))}
                    </div>
                  </div>
                ) : null,
              )}
            </section>
          </>
        )}
      </div>
    </aside>
  );
}

function IntelligenceCard({
  data,
  loading,
  error,
}: {
  data: RelationshipIntelligence | null;
  loading: boolean;
  error: string;
}) {
  if (loading)
    return (
      <section
        className="customer-intelligence-card"
        aria-label="Customer Intelligence"
      >
        <h3>Customer Intelligence</h3>
        <span>Loading…</span>
      </section>
    );
  if (error || !data || !data.customerValue || !data.behavioralIntelligence)
    return (
      <section
        className="customer-intelligence-card"
        aria-label="Customer Intelligence"
      >
        <h3>Customer Intelligence</h3>
        <span>{error || "Unavailable"}</span>
      </section>
    );
  const commerce = data.mappingStatus === "VERIFIED";
  return (
    <section
      className="customer-intelligence-card"
      aria-label="Customer Intelligence"
    >
      <header>
        <h3>Customer Intelligence</h3>
        {!commerce && <span>Commerce unverified</span>}
      </header>
      <div className="customer-intelligence-details">
        <dl>
          <Metric
            label="Lifecycle"
            value={title(data.customerValue.relationshipLifecycle)}
          />
          <Metric
            label="Automatic Value"
            value={title(data.customerValue.valueTier)}
          />
          <Metric
            label="Operator Classification"
            value={data.operatorClassification ? "High Value Prospect" : "—"}
          />
          <Metric
            label="Effective Attention"
            value={title(data.effectiveAttentionPriority)}
          />
          <Metric
            label="Attention"
            value={title(data.customerValue.attentionTier)}
          />
          <Metric
            label="Buying Intent"
            value={title(data.behavioralIntelligence.buyingIntent)}
          />
          <Metric
            label="Current Signal"
            value={title(data.behavioralIntelligence.currentSignal)}
          />
          <Metric
            label="Buyer"
            value={
              commerce ? title(data.customerValue.buyerStatus) : "Unverified"
            }
          />
          <Metric
            label="Purchases"
            value={commerce ? data.customerValue.purchaseCount : "Unverified"}
          />
          <Metric
            label="Spend"
            value={
              commerce && data.customerValue.lifetimeSpendMinor != null
                ? money(data.customerValue.lifetimeSpendMinor)
                : "Unverified"
            }
          />
          <Metric
            label="Relationship Investment"
            value={title(data.customerValue.relationshipInvestment)}
          />
          <Metric
            label="Time-Waster Risk"
            value={title(data.customerValue.timeWasterRisk)}
          />
          <Metric
            label="Retention"
            value={title(data.customerValue.retention)}
          />
        </dl>
      </div>
    </section>
  );
}

function CustomerIntelligenceModal({
  data,
  error,
  loading,
  person,
  close,
}: {
  data: RelationshipIntelligence | null;
  error: string;
  loading: boolean;
  person: Relationship;
  close: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeButton.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [close]);
  return createPortal(
    <div
      className="customer-intelligence-modal"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
      role="presentation"
    >
      <section
        aria-labelledby="customer-intelligence-modal-title"
        aria-modal="true"
        className="customer-intelligence-panel"
        role="dialog"
      >
        <header>
          <div>
            <h2 id="customer-intelligence-modal-title">Customer Intelligence</h2>
            <span>{person.displayName}</span>
          </div>
          <button
            aria-label="Close Customer Intelligence details"
            onClick={close}
            ref={closeButton}
            type="button"
          >
            <X size={18} />
          </button>
        </header>
        <IntelligenceCard data={data} error={error} loading={loading} />
        {!loading && !error && data && (
          <div className="customer-intelligence-extended">
            <section>
              <h3>Operational Context</h3>
              <dl className="intelligence-metrics">
                <Metric label="Communication Status" value={person.ignored ? "Ignored" : "Active"} />
                <Metric label="Offers Presented" value={data.salesPerformance.offersPresented} />
                <Metric label="Offers Purchased" value={data.salesPerformance.offersPurchased} />
                <Metric label="Offers Not Purchased" value={data.salesPerformance.offersNotPurchased} />
                <Metric label="Conversion" value={data.salesPerformance.conversionRate == null ? "—" : `${Math.round(data.salesPerformance.conversionRate * 100)}%`} />
                <Metric label="Active Intent" value={data.commercialState.activePurchaseIntent ? title(data.commercialState.activePurchaseIntent.status) : "None"} />
                <Metric label="Active Session" value={data.commercialState.activeSalesSession ? title(data.commercialState.activeSalesSession.state) : "None"} />
                <Metric label="Active Offer" value={data.commercialState.activeOffer?.title || "None"} />
              </dl>
              <OfferSummary label="Last Offer" item={data.salesPerformance.lastOffer} />
              <OfferSummary label="Last Purchase" item={data.salesPerformance.lastPurchase} />
            </section>
            {data.purchaseHistory.length > 0 && (
              <section>
                <h3>Purchase History</h3>
                <div className="intelligence-history">
                  {data.purchaseHistory.map((item, index) => (
                    <article key={`${item.purchasedAt}-${index}`}>
                      <strong>{item.title}</strong>
                      <span>{item.type || "Content"}</span>
                      <small>{[calendarDate(item.purchasedAt), item.priceMinor != null ? money(item.priceMinor) : null].filter(Boolean).join(" Â· ")}</small>
                    </article>
                  ))}
                </div>
              </section>
            )}
            <section>
              <h3>Relationship Intelligence</h3>
              <dl className="intelligence-facts">
                <Metric label="Location" value={data.relationshipIntelligence.location || "—"} />
                <Metric label="Timezone" value={data.relationshipIntelligence.timezone || "—"} />
              </dl>
              {(["interests", "pets", "music", "preferences"] as const).map((key) => data.relationshipIntelligence[key].length ? (
                <div className="intelligence-tags" key={key}><strong>{title(key)}</strong><div>{data.relationshipIntelligence[key].map((value) => <span key={value}>{value}</span>)}</div></div>
              ) : null)}
            </section>
          </div>
        )}
      </section>
    </div>,
    document.body,
  );
}

function CustomerIntelligenceTrigger({
  open,
  error,
}: {
  open: (trigger: HTMLButtonElement) => void;
  error?: string;
}) {
  return (
    <section
      aria-label="Customer Intelligence summary"
      className="customer-intelligence-launcher"
    >
      <h3>Customer Intelligence</h3>
      {error && <span role="alert">{error}</span>}
      <button onClick={(event) => open(event.currentTarget)} type="button">
        View Customer Intelligence <span aria-hidden="true">→</span>
      </button>
    </section>
  );
}

function MarketPolicyCard({ market }: { market: MarketTierProjection | null }) {
  const limited =
    market?.marketTier === "MEDIUM" || market?.marketTier === "LOW";
  const opportunity = market?.activeSalesOpportunity;
  return (
    <section
      className="market-policy-card"
      aria-label="Country Tier Intelligence"
    >
      <dl>
        <Metric
          label="Country Tier"
          value={market?.marketTier || "UNCLASSIFIED"}
        />
        <Metric
          label="Effective Prospect Investment"
          value={title(market?.effectiveProspectInvestment || "STANDARD")}
        />
        {market?.verifiedBuyer ? (
          <Metric label="Prospect Reply Limit" value="NOT APPLICABLE" />
        ) : market?.marketTier === "HIGH" ? (
          <Metric label="Prospect Nurture" value="FULL" />
        ) : limited ? (
          <>
            <Metric
              label="Prospect Nurture"
              value={`${market?.repliesUsedToday ?? 0} / ${market?.dailyReplyBudget ?? "—"}`}
            />
            <Metric
              label="Nurture Budget"
              value={market?.budgetStatus || "AVAILABLE"}
            />
            {market?.effectiveResourceStatus === "SALES_OVERRIDE" && (
              <Metric label="Effective Status" value="Sales Override" />
            )}
            {opportunity?.active && (
              <>
                <Metric
                  label="Active Offer"
                  value={opportunity.offer_title || "Current PPV offer"}
                />
                <Metric
                  label="Offer Status"
                  value={opportunity.offer_status || "—"}
                />
              </>
            )}
            {market?.budgetStatus === "EXHAUSTED" &&
              market.effectiveResourceStatus !== "SALES_OVERRIDE" && (
                <Metric
                  label="Next Budget Reset"
                  value={
                    market.nextBudgetResetAt
                      ? time(market.nextBudgetResetAt)
                      : "—"
                  }
                />
              )}
          </>
        ) : null}
      </dl>
    </section>
  );
}

export function RelationshipsPage() {
  const inRouter = useInRouterContext();
  const legacyFilter = useRef(
    new URLSearchParams(window.location.search).get("filter"),
  );
  const deepLinkKey = useRef(
    new URLSearchParams(window.location.search).get("relationship"),
  );
  const deepLinkOpened = useRef(false);
  const [people, setPeople] = useState<Relationship[]>([]),
    [selected, setSelected] = useState<Relationship | null>(null),
    [messages, setMessages] = useState<RelationshipMessage[]>([]);
  const initialFilter: RelationshipFilter =
    legacyFilter.current === "active-sessions"
      ? "ACTIVE_SESSION"
      : legacyFilter.current === "active-intents"
        ? "ACTIVE_INTENT"
        : "ALL";
  const [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [sort, setSort] = useState<RelationshipSort>("LATEST_ACTIVITY"),
    [filter, setFilter] = useState<RelationshipFilter>(initialFilter),
    [countryTiers, setCountryTiers] = useState<MarketTier[]>([]),
    [filtersOpen, setFiltersOpen] = useState(false),
    [summary, setSummary] = useState<RelationshipSummary>({
      total: 0,
      needsAttention: 0,
      buyers: 0,
      prospects: 0,
      manual: 0,
    }),
    [next, setNext] = useState<string | null>(null),
    [older, setOlder] = useState<string | null>(null);
  const [loading, setLoading] = useState(true),
    [chatLoading, setChatLoading] = useState(false),
    [error, setError] = useState(""),
    [chatError, setChatError] = useState("");
  const transcript = useRef<HTMLDivElement>(null);
  const selectedRef = useRef<Relationship | null>(null);
  const messageRequest = useRef(false);
  const olderRequest = useRef(false);
  const selectionVersion = useRef(0);
  const initialBottomPending = useRef(false);
  const controlRefreshRequest = useRef<string | null>(null);
  const transcriptNearBottom = useRef(true);
  const [newMessagesAvailable, setNewMessagesAvailable] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false),
    [moreOpen, setMoreOpen] = useState(false),
    [classifyOpen, setClassifyOpen] = useState(false),
    [intelligence, setIntelligence] = useState<RelationshipIntelligence | null>(
      null,
    ),
    [market, setMarket] = useState<MarketTierProjection | null>(null),
    [intelligenceLoading, setIntelligenceLoading] = useState(false),
    [intelligenceError, setIntelligenceError] = useState("");
  const moreTrigger = useRef<HTMLButtonElement>(null),
    classifyTrigger = useRef<HTMLButtonElement>(null),
    filtersTrigger = useRef<HTMLButtonElement>(null);
  const closeMore = useCallback(() => setMoreOpen(false), []),
    closeClassify = useCallback(() => setClassifyOpen(false), []),
    closeFilters = useCallback(() => setFiltersOpen(false), []);
  useEffect(() => {
    moreTrigger.current = document.querySelector<HTMLButtonElement>(
      'button[aria-label="More conversation controls"]',
    );
    document
      .querySelector(".conversation-more-menu")
      ?.setAttribute("aria-hidden", "true");
  }, [moreOpen, selected]);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [downloadingChat, setDownloadingChat] = useState(false),
    [downloadError, setDownloadError] = useState("");
  const [valueChanging, setValueChanging] = useState(false),
    [marketChanging, setMarketChanging] = useState(false);
  const [confirmHvpRemoval, setConfirmHvpRemoval] = useState(false);
  const [control, setControl] = useState<RelationshipControl | null>(null),
    [confirmAction, setConfirmAction] = useState<
      "takeover" | "return" | "ignore" | "unignore" | null
    >(null),
    [controlError, setControlError] = useState("");
  const [cancelTarget, setCancelTarget] = useState<Relationship | null>(null),
    [cancellingReply, setCancellingReply] = useState(false),
    [cancelReplyError, setCancelReplyError] = useState("");
  const [uncertainTarget, setUncertainTarget] = useState<Relationship | null>(null);
  const [uncertainBusy, setUncertainBusy] = useState(false);
  const [uncertainError, setUncertainError] = useState("");
  const [acknowledging, setAcknowledging] = useState(false),
    [attentionError, setAttentionError] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({}),
    [sendingKey, setSendingKey] = useState<string | null>(null),
    [sendErrors, setSendErrors] = useState<Record<string, string>>({}),
    sendKeys = useRef(new Map<string, string>());
  const selectedKey = selected?.personKey ?? "";
  const draft = selectedKey ? drafts[selectedKey] ?? "" : "";
  const sending = Boolean(selectedKey && sendingKey === selectedKey);
  const sendError = selectedKey ? sendErrors[selectedKey] ?? "" : "";
  const setRelationshipDraft = (key: string, value: string) =>
    setDrafts((current) => ({ ...current, [key]: value }));
  const setRelationshipSendError = (key: string, value: string) =>
    setSendErrors((current) => ({ ...current, [key]: value }));
  const [offerOpen, setOfferOpen] = useState(false);
  const [readinessOpen, setReadinessOpen] = useState(false);
  const readinessTrigger = useRef<HTMLButtonElement | null>(null);
  const openReadiness = useCallback((trigger: HTMLButtonElement) => {
    readinessTrigger.current = trigger;
    setReadinessOpen(true);
  }, []);
  const closeReadiness = useCallback(() => {
    setReadinessOpen(false);
    requestAnimationFrame(() => readinessTrigger.current?.focus());
  }, []);
  const [customerIntelligenceOpen, setCustomerIntelligenceOpen] = useState(false);
  const customerIntelligenceTrigger = useRef<HTMLButtonElement | null>(null);
  const openCustomerIntelligence = useCallback((trigger: HTMLButtonElement) => {
    customerIntelligenceTrigger.current = trigger;
    setCustomerIntelligenceOpen(true);
  }, []);
  const closeCustomerIntelligence = useCallback(() => {
    setCustomerIntelligenceOpen(false);
    requestAnimationFrame(() => customerIntelligenceTrigger.current?.focus());
  }, []);
  const [inspectionTarget, setInspectionTarget] = useState<{
    person: Relationship;
    occurrenceId: string;
  } | null>(null);
  const listRequest = useRef(false);
  const loadList = (append = false, silent = false) => {
    if (listRequest.current) return Promise.resolve();
    listRequest.current = true;
    if (!silent) setLoading(true);
    setError("");
    return relationshipsApi
      .list(query, sort, filter, append ? next : null, undefined, countryTiers)
      .then((data) => {
        setPeople((current) =>
          append ? [...current, ...data.items] : data.items,
        );
        setNext(data.nextCursor);
        if (data.summary) setSummary(data.summary);
        if (!append && selected) {
          const refreshed = data.items.find(
            (item) => item.personKey === selected.personKey,
          );
          if (refreshed) setSelected(refreshed);
        }
      })
      .catch((reason) =>
        setError(
          reason instanceof Error ? reason.message : "Unable to load Chat.",
        ),
      )
      .finally(() => {
        listRequest.current = false;
        if (!silent) setLoading(false);
      });
  };
  useEffect(() => {
    void loadList();
  }, [query, sort, filter, countryTiers]);
  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);
  useLayoutEffect(() => {
    if (!initialBottomPending.current || !messages.length || !transcript.current)
      return;
    transcript.current.scrollTop = transcript.current.scrollHeight;
    transcriptNearBottom.current = true;
    initialBottomPending.current = false;
  }, [messages, selected?.personKey]);
  const refreshSelectedMessages = (silent = true) => {
    const person = selectedRef.current;
    if (!person || messageRequest.current) return Promise.resolve();
    messageRequest.current = true;
    if (!silent) setChatLoading(true);
    const wasNearBottom = transcriptNearBottom.current;
    return relationshipsApi
      .messages(person.personKey)
      .then((data) => {
        if (selectedRef.current?.personKey !== person.personKey) return;
        setMessages((current) => {
          const known = new Set(current.map((item) => item.eventKey));
          const hasNew = data.items.some((item) => !known.has(item.eventKey));
          const merged = new Map(current.map((item) => [item.eventKey, item]));
          for (const item of data.items) merged.set(item.eventKey, item);
          if (hasNew) {
            if (wasNearBottom) {
              requestAnimationFrame(() => {
                if (transcript.current)
                  transcript.current.scrollTop = transcript.current.scrollHeight;
              });
            } else setNewMessagesAvailable(true);
          }
          return [...merged.values()].sort(
            (a, b) =>
              new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
          );
        });
        setOlder(data.olderCursor);
        setChatError("");
      })
      .catch((reason) =>
        setChatError(
          reason instanceof Error
            ? reason.message
            : "Conversation refresh unavailable.",
        ),
      )
      .finally(() => {
        messageRequest.current = false;
        if (!silent) setChatLoading(false);
      });
  };
  const refreshSelectedControl = () => {
    const person = selectedRef.current;
    if (!person || controlRefreshRequest.current === person.personKey)
      return Promise.resolve();
    controlRefreshRequest.current = person.personKey;
    return relationshipsApi
      .control(person.personKey)
      .then((current) => {
        if (selectedRef.current?.personKey === person.personKey)
          setControl(current);
      })
      .catch(() => undefined)
      .finally(() => {
        if (controlRefreshRequest.current === person.personKey)
          controlRefreshRequest.current = null;
      });
  };
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      void loadList(false, true);
      void refreshSelectedMessages(true);
      void refreshSelectedControl();
    };
    const visibilityChanged = () => {
      if (document.visibilityState === "visible") refresh();
    };
    const timer = window.setInterval(refresh, CHAT_REFRESH_INTERVAL_MS);
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visibilityChanged);
    };
  }, [query, sort, filter, countryTiers, selected?.personKey]);
  const select = (person: Relationship) => {
    const version = ++selectionVersion.current;
    selectedRef.current = person;
    setDrawerOpen(false);
    setMoreOpen(false);
    setClassifyOpen(false);
    setOfferOpen(false);
    setIntelligence(null);
    setMarket(null);
    setSelected(person);
    setMessages([]);
    setControl(null);
    setRelationshipSendError(person.personKey, "");
    setDownloadError("");
    setChatError("");
    setNewMessagesAvailable(false);
    transcriptNearBottom.current = true;
    initialBottomPending.current = true;
    setControlError("");
    setChatLoading(true);
    setIntelligenceLoading(true);
    setIntelligenceError("");
    messageRequest.current = true;
    relationshipsApi
      .messages(person.personKey)
      .then((data) => {
        if (selectionVersion.current !== version ||
            selectedRef.current?.personKey !== person.personKey) return;
        setMessages(data.items);
        setOlder(data.olderCursor);
      })
      .catch((reason) => {
        if (selectionVersion.current !== version) return;
        setChatError(
          reason instanceof Error
            ? reason.message
            : "Unable to load conversation.",
        );
      })
      .finally(() => {
        if (selectionVersion.current !== version) return;
        messageRequest.current = false;
        setChatLoading(false);
      });
    relationshipsApi
      .control(person.personKey)
      .then((value) => {
        if (selectionVersion.current === version) setControl(value);
      })
      .catch((reason) => {
        if (selectionVersion.current !== version) return;
        setControlError(
          reason instanceof Error
            ? reason.message
            : "Relationship controls unavailable.",
        );
      });
    Promise.allSettled([
      relationshipsApi.intelligence(person.personKey),
      relationshipsApi.marketTier(person.personKey),
    ])
      .then(([value, tier]) => {
        if (selectionVersion.current !== version) return;
        if (value.status === "fulfilled")
          setIntelligence(value.value.customerValue ? value.value : null);
        else
          setIntelligenceError(
            value.reason instanceof Error
              ? value.reason.message
              : "Unable to load Customer Intelligence.",
          );
        if (tier.status === "fulfilled") setMarket(tier.value);
        else
          setIntelligenceError(
            (current) =>
              current ||
              (tier.reason instanceof Error
                ? tier.reason.message
                : "Market Tier unavailable."),
          );
      })
      .finally(() => {
        if (selectionVersion.current === version) setIntelligenceLoading(false);
      });
  };
  useEffect(() => {
    const key = deepLinkKey.current;
    if (!key || deepLinkOpened.current || !people.length) return;
    const person = people.find((item) => item.personKey === key);
    if (person) {
      deepLinkOpened.current = true;
      select(person);
    }
  }, [people]);
  const changeControl = () => {
    if (!selected || !confirmAction || !control) return;
    setControlError("");
    const request =
      confirmAction === "takeover"
        ? relationshipsApi.takeover(selected.personKey)
        : confirmAction === "return"
          ? relationshipsApi.returnToAva(selected.personKey)
          : confirmAction === "ignore"
            ? relationshipsApi.ignore(
                selected.personKey,
                control.controlVersion,
              )
            : relationshipsApi.unignore(
                selected.personKey,
                control.controlVersion,
              );
    request
      .then((current) => {
        setControl(current);
        const ignored = Boolean(current.ignored);
        const projection = {
          controlMode: current.mode,
          communicationDisposition: current.communicationDisposition,
          ignored,
          operationalStatus: ignored ? ("IGNORED" as const) : ("NONE" as const),
          operationalStatusReason: ignored
            ? "Automatic communication disabled for this relationship."
            : null,
          nextAutomaticAttemptAt: null,
        };
        setSelected((value) => (value ? { ...value, ...projection } : value));
        setPeople((values) => {
          const updated = values.map((value) =>
            value.personKey === selected.personKey
              ? { ...value, ...projection }
              : value,
          );
          const belongs = filter === "IGNORED" ? ignored : !ignored;
          return belongs
            ? updated
            : updated.filter((value) => value.personKey !== selected.personKey);
        });
        setConfirmAction(null);
        void loadList(false, true);
        if (current.mode === "AVA_AUTO") {
          setRelationshipDraft(selected.personKey, "");
          setRelationshipSendError(selected.personKey, "");
          sendKeys.current.delete(selected.personKey);
        }
      })
      .catch((reason) =>
        setControlError(
          reason instanceof Error
            ? reason.message
            : "Unable to change Manual Mode.",
        ),
      );
  };
  const cancelReply = () => {
    const target = cancelTarget;
    if (!target?.operationId || !target.inboundMessageId || cancellingReply) return;
    setCancellingReply(true);
    setCancelReplyError("");
    relationshipsApi.cancelReply(target.personKey, target.operationId, target.inboundMessageId)
      .then(() => {
        const projection = {
          operationalStatus: "NONE" as const,
          operationalStatusReason: null,
          nextAutomaticAttemptAt: null,
          pendingReplyPreview: null,
          overdueSince: null,
          operationState: "SUPPRESSED",
          operationId: null,
          inboundMessageId: null,
          hasActiveClaim: false,
        };
        setPeople((values) => values.map((value) =>
          value.personKey === target.personKey ? { ...value, ...projection } : value));
        setSelected((value) => value?.personKey === target.personKey
          ? { ...value, ...projection } : value);
        setCancelTarget(null);
        void loadList(false, true);
      })
      .catch((reason) => {
        setCancelReplyError(reason instanceof Error ? reason.message : "Reply could not be canceled.");
        void loadList(false, true);
      })
      .finally(() => setCancellingReply(false));
  };
  const send = () => {
    if (
      !selected ||
      !control ||
      control.mode !== "HUMAN_OPERATOR" ||
      !draft.trim() ||
      sending
    )
      return;
    const text = draft.trim();
    const relationshipKey = selected.personKey;
    const idempotencyKey =
      sendKeys.current.get(relationshipKey) ?? crypto.randomUUID();
    sendKeys.current.set(relationshipKey, idempotencyKey);
    setSendingKey(relationshipKey);
    setRelationshipSendError(relationshipKey, "");
    relationshipsApi
      .send(relationshipKey, text, idempotencyKey, control.controlVersion)
      .then((message) => {
        setRelationshipDraft(relationshipKey, "");
        sendKeys.current.delete(relationshipKey);
        if (selectedRef.current?.personKey === relationshipKey) {
          setMessages((current) =>
            current.some((item) => item.eventKey === message.eventKey)
              ? current
              : [...current, message],
          );
          requestAnimationFrame(() => {
            if (transcript.current)
              transcript.current.scrollTop = transcript.current.scrollHeight;
          });
        }
      })
      .catch((reason) =>
        setRelationshipSendError(
          relationshipKey,
          reason instanceof Error ? reason.message : "Message was not sent.",
        ),
      )
      .finally(() =>
        setSendingKey((current) =>
          current === relationshipKey ? null : current,
        ),
      );
  };
  const loadOlder = () => {
    if (!selected || !older || olderRequest.current) return;
    const relationshipKey=selected.personKey;
    const version=selectionVersion.current;
    const node = transcript.current,
      previous = node?.scrollHeight ?? 0,
      previousTop = node?.scrollTop ?? 0;
    olderRequest.current=true;
    setChatLoading(true);
    relationshipsApi
      .messages(relationshipKey, older)
      .then((data) => {
        if (selectionVersion.current !== version ||
            selectedRef.current?.personKey !== relationshipKey) return;
        setMessages((current) => {
          const merged=new Map<string,RelationshipMessage>();
          for (const item of data.items) merged.set(item.eventKey,item);
          for (const item of current) merged.set(item.eventKey,item);
          return [...merged.values()].sort((a,b) =>
            new Date(a.timestamp).getTime()-new Date(b.timestamp).getTime() ||
            a.eventKey.localeCompare(b.eventKey));
        });
        setOlder(data.olderCursor);
        requestAnimationFrame(() => {
          if (node) node.scrollTop = previousTop + node.scrollHeight - previous;
        });
      })
      .catch((reason) => {
        if (selectionVersion.current === version)
          setChatError(reason instanceof Error ? reason.message : "Older messages unavailable.");
      })
      .finally(() => {
        olderRequest.current=false;
        if (selectionVersion.current === version) setChatLoading(false);
      });
  };
  const downloadChat = async () => {
    if (!selected || downloadingChat || (!messages.length && !older)) return;
    setMoreOpen(false);
    setDownloadingChat(true);
    setDownloadError("");
    try {
      const complete = await relationshipsApi.completeMessages(
        selected.personKey,
      );
      if (!complete.length) return;
      saveChatTranscript(
        transcriptFilename(selected.displayName),
        buildChatTranscript(selected, complete),
      );
    } catch (reason) {
      setDownloadError(
        reason instanceof Error
          ? reason.message
          : "Unable to download chat transcript.",
      );
    } finally {
      setDownloadingChat(false);
    }
  };
  const openIntelligence = () => {
    if (!selected) return;
    setDrawerOpen(true);
    setIntelligenceLoading(true);
    setIntelligenceError("");
    relationshipsApi
      .intelligence(selected.personKey)
      .then(setIntelligence)
      .catch((reason) =>
        setIntelligenceError(
          reason instanceof Error
            ? reason.message
            : "Unable to load Customer Intelligence.",
        ),
      )
      .finally(() => setIntelligenceLoading(false));
  };
  const changeHighValue = (removalConfirmed = false) => {
    if (!selected || valueChanging) return;
    const isActive = Boolean(
      intelligence?.operatorClassification ?? selected.operatorClassification,
    );
    if (isActive && !removalConfirmed) {
      setConfirmHvpRemoval(true);
      return;
    }
    setValueChanging(true);
    setControlError("");
    const request = isActive
      ? relationshipsApi.removeHighValueProspect(selected.personKey)
      : relationshipsApi.setHighValueProspect(selected.personKey);
    request
      .then((result) => {
        setIntelligence(result.intelligence);
        const active = Boolean(result.intelligence.operatorClassification);
        setSelected((current) =>
          current
            ? {
                ...current,
                operatorClassification:
                  result.intelligence.operatorClassification,
                highValueProspect: active,
                effectiveAttentionPriority:
                  result.intelligence.effectiveAttentionPriority,
                nextAutomaticAttemptAt:
                  result.scheduling.advancedOperation?.next_retry_at ??
                  current.nextAutomaticAttemptAt,
              }
            : current,
        );
        setPeople((current) =>
          current.map((person) =>
            person.personKey === selected.personKey
              ? {
                  ...person,
                  operatorClassification:
                    result.intelligence.operatorClassification,
                  highValueProspect: active,
                  effectiveAttentionPriority:
                    result.intelligence.effectiveAttentionPriority,
                  nextAutomaticAttemptAt:
                    result.scheduling.advancedOperation?.next_retry_at ??
                    person.nextAutomaticAttemptAt,
                }
              : person,
          ),
        );
        setConfirmHvpRemoval(false);
      })
      .catch((reason) =>
        setControlError(
          reason instanceof Error
            ? reason.message
            : "Unable to change customer priority.",
        ),
      )
      .finally(() => setValueChanging(false));
  };
  const dismissUncertainty = async () => {
    if (!uncertainTarget?.attentionOccurrenceId || uncertainBusy) return;
    const target = uncertainTarget;
    setUncertainBusy(true); setUncertainError("");
    try {
      const projection = await relationshipsApi.acknowledgeAttention(target.personKey, target.attentionOccurrenceId!);
      setSelected(current => current?.personKey === target.personKey ? {...current, ...projection} : current);
      setPeople(current => current.map(person => person.personKey === target.personKey ? {...person, ...projection} : person));
      setUncertainTarget(null);
    } catch (error) {
      setUncertainError(error instanceof Error ? error.message : "Unable to dismiss warning.");
    } finally { setUncertainBusy(false); }
  };
  const openUncertainty = (person: Relationship) => { setUncertainError(""); setUncertainTarget(person); };
  const acknowledgeAttention = () => {
    if (!selected?.attentionOccurrenceId || acknowledging) return;
    setAcknowledging(true);
    setAttentionError("");
    relationshipsApi
      .acknowledgeAttention(selected.personKey, selected.attentionOccurrenceId)
      .then((projection) => {
        setSelected((current) =>
          current ? { ...current, ...projection } : current,
        );
        setPeople((current) => {
          const updated = current.map((person) =>
            person.personKey === selected.personKey
              ? { ...person, ...projection }
              : person,
          );
          return filter === "NEEDS_ATTENTION"
            ? updated.filter(
                (person) => person.operationalStatus === "NEEDS_ATTENTION",
              )
            : updated;
        });
        setSummary((current) => ({
          ...current,
          needsAttention: Math.max(0, current.needsAttention - (selected.operationalStatus === "NEEDS_ATTENTION" ? 1 : 0)),
        }));
      })
      .catch((reason) =>
        setAttentionError(
          reason instanceof Error
            ? reason.message
            : "Unable to acknowledge attention.",
        ),
      )
      .finally(() => setAcknowledging(false));
  };
  const changeMarketTier = (tier: Exclude<MarketTier, "UNCLASSIFIED">) => {
    if (!selected || marketChanging) return;
    setMarketChanging(true);
    setControlError("");
    const request =
      market?.marketTier === tier
        ? relationshipsApi.removeMarketTier(selected.personKey)
        : relationshipsApi.setMarketTier(selected.personKey, tier);
    request
      .then(async (result) => {
        setMarket(result);
        await Promise.all([
          loadList(false, true),
          relationshipsApi
            .intelligence(selected.personKey)
            .then(setIntelligence),
          relationshipsApi.marketTier(selected.personKey).then(setMarket),
        ]);
      })
      .catch((reason) =>
        setControlError(
          reason instanceof Error
            ? reason.message
            : "Unable to change Market Tier.",
        ),
      )
      .finally(() => setMarketChanging(false));
  };
  const clearMarketTier = () => {
    if (!selected || marketChanging || market?.marketTier === "UNCLASSIFIED")
      return;
    setMarketChanging(true);
    setControlError("");
    relationshipsApi
      .removeMarketTier(selected.personKey)
      .then(async (result) => {
        setMarket(result);
        await Promise.all([
          loadList(false, true),
          relationshipsApi
            .intelligence(selected.personKey)
            .then(setIntelligence),
          relationshipsApi.marketTier(selected.personKey).then(setMarket),
        ]);
      })
      .catch((reason) =>
        setControlError(
          reason instanceof Error
            ? reason.message
            : "Unable to change Market Tier.",
        ),
      )
      .finally(() => setMarketChanging(false));
  };
  useEffect(() => {
    if (!drawerOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [drawerOpen]);
  const visiblePeople = people;
  const setInboxFilter = (value: RelationshipFilter) => {
    setFilter(value);
    setNext(null);
  };
  const toggleCountryTier = (tier: MarketTier) => {
    setCountryTiers((current) =>
      current.includes(tier)
        ? current.filter((value) => value !== tier)
        : [...current, tier],
    );
    setNext(null);
  };
  return (
    <main className="relationships-page">
      {selected && (
        <>
          <ClassificationTriggerPortal
            buttonRef={classifyTrigger}
            expanded={classifyOpen}
            onToggle={() => {
              setMoreOpen(false);
              setClassifyOpen((value) => !value);
            }}
          />
          <FloatingMenu
            anchor={classifyTrigger}
            className="classify-menu"
            label="Classify relationship"
            onClose={closeClassify}
            open={classifyOpen}
          >
            <section>
              <strong>Country Tier</strong>
              <div className="classify-tier-options">
                {(["HIGH", "MEDIUM", "LOW"] as const).map((tier) => (
                  <button
                    aria-pressed={market?.marketTier === tier}
                    disabled={marketChanging || intelligenceLoading}
                    key={tier}
                    onClick={() => {
                      closeClassify();
                      changeMarketTier(tier);
                    }}
                    role="menuitem"
                    type="button"
                  >
                    {tierLabel(tier)}
                  </button>
                ))}
              </div>
              <button
                aria-pressed={market?.marketTier === "UNCLASSIFIED"}
                className="classify-unclassified"
                disabled={
                  marketChanging ||
                  intelligenceLoading ||
                  market?.marketTier === "UNCLASSIFIED"
                }
                onClick={() => {
                  closeClassify();
                  clearMarketTier();
                }}
                role="menuitem"
                type="button"
              >
                UNCLASSIFIED
              </button>
            </section>
            <section>
              <strong>Priority</strong>
              <button
                aria-pressed={Boolean(intelligence?.operatorClassification)}
                disabled={valueChanging || intelligenceLoading}
                onClick={() => {
                  closeClassify();
                  changeHighValue();
                }}
                role="menuitem"
                type="button"
              >
                High Value Prospect:{" "}
                {intelligence?.operatorClassification ? "ON" : "OFF"}
              </button>
            </section>
          </FloatingMenu>
          <FloatingMenu
            anchor={moreTrigger}
            label="More conversation controls"
            onClose={closeMore}
            open={moreOpen}
          >
            <section>
              <strong>Country Tier</strong>
              {(["HIGH", "MEDIUM", "LOW"] as const).map((tier) => (
                <button
                  aria-pressed={market?.marketTier === tier}
                  disabled={marketChanging || intelligenceLoading}
                  key={tier}
                  onClick={() => {
                    closeMore();
                    changeMarketTier(tier);
                  }}
                  role="menuitem"
                  type="button"
                >
                  {tierLabel(tier)}
                </button>
              ))}
              <button
                aria-pressed={market?.marketTier === "UNCLASSIFIED"}
                disabled={
                  marketChanging ||
                  intelligenceLoading ||
                  market?.marketTier === "UNCLASSIFIED"
                }
                onClick={() => {
                  closeMore();
                  clearMarketTier();
                }}
                role="menuitem"
                type="button"
              >
                Unclassified
              </button>
            </section>
            <section>
              <strong>Priority</strong>
              <button
                aria-pressed={Boolean(intelligence?.operatorClassification)}
                disabled={valueChanging || intelligenceLoading}
                onClick={() => {
                  closeMore();
                  changeHighValue();
                }}
                role="menuitem"
                type="button"
              >
                High Value Prospect{" "}
                {intelligence?.operatorClassification ? "On" : "Off"}
              </button>
            </section>
            <section>
              <strong>Communication</strong>
              {control && (
                <button
                  onClick={() => {
                    closeMore();
                    setConfirmAction(control.ignored ? "unignore" : "ignore");
                  }}
                  role="menuitem"
                  type="button"
                >
                  {control.ignored
                    ? "Unignore Relationship"
                    : "Ignore Relationship"}
                </button>
              )}
            </section>
            <section>
              <strong>Transcript</strong>
              <button
                disabled={downloadingChat || (!messages.length && !older)}
                onClick={() => void downloadChat()}
                role="menuitem"
                type="button"
              >
                {downloadingChat ? "Preparing Downloadâ€¦" : "Download Chat"}
              </button>
            </section>
          </FloatingMenu>
        </>
      )}
      <FloatingMenu
        anchor={filtersTrigger}
        className="chat-filter-menu"
        label="More chat filters"
        onClose={closeFilters}
        open={filtersOpen}
      >
        <section>
          <strong>Additional filters</strong>
          {(
            [
              ["ACTIVE_SESSION", "Active Session"],
              ["ACTIVE_INTENT", "Active Offer"],
              ["IGNORED", "Ignored"],
            ] as const
          ).map(([value, label]) => (
            <button
              aria-checked={filter === value}
              key={value}
              onClick={() => setInboxFilter(filter === value ? "ALL" : value)}
              role="menuitemradio"
              type="button"
            >
              {label}
            </button>
          ))}
        </section>
        <section>
          <strong>Country Tier</strong>
          {(
            [
              ["HIGH", "HIGH"],
              ["MEDIUM", "MED"],
              ["LOW", "LOW"],
              ["UNCLASSIFIED", "UNCLASSIFIED"],
            ] as const
          ).map(([value, label]) => (
            <button
              aria-checked={countryTiers.includes(value)}
              key={value}
              onClick={() => toggleCountryTier(value)}
              role="menuitemcheckbox"
              type="button"
            >
              <span aria-hidden="true">
                {countryTiers.includes(value) ? "☑" : "☐"}
              </span>
              {label}
            </button>
          ))}
        </section>
        {(filter !== "ALL" || countryTiers.length > 0) && (
          <section>
            <button
              className="clear-chat-filters"
              onClick={() => {
                setInboxFilter("ALL");
                setCountryTiers([]);
                setNext(null);
              }}
              role="menuitem"
              type="button"
            >
              Clear filters
            </button>
          </section>
        )}
      </FloatingMenu>
      <header>
        <div>
          <span>Business</span>
          <h1>Chat</h1>
          <p>Ava&apos;s Telegram conversations.</p>
        </div>
        <div className="chat-header-actions">
          {selected && inRouter && (
            <Link
              to={`/business/controls?tab=customers&relationship=${encodeURIComponent(selected.personKey)}`}
            >
              Customer Controls
            </Link>
          )}
          {selected && inRouter && (
            <Link
              to={`/training/ai-training?tab=queue&scope=customer&customer=${encodeURIComponent(selected.personKey)}`}
            >
              Train Ava for this customer
            </Link>
          )}
          {inRouter ? (
            <Link to="/agents/ava-coach">Ava Coach</Link>
          ) : (
            <a href="/agents/ava-coach">Ava Coach</a>
          )}
          <button onClick={() => void loadList()} type="button">
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
      </header>
      <section aria-label="Chat summary" className="chat-summary">
        <button
          className={filter === "ALL" ? "is-active" : ""}
          onClick={() => setInboxFilter("ALL")}
          type="button"
        >
          <span>Total Chats</span>
          <strong>{summary.total}</strong>
        </button>
        <button
          className={filter === "NEEDS_ATTENTION" ? "is-active" : ""}
          onClick={() => setInboxFilter("NEEDS_ATTENTION")}
          type="button"
        >
          <span>Needs Attention</span>
          <strong>{summary.needsAttention}</strong>
        </button>
        <button
          className={filter === "BUYERS" ? "is-active" : ""}
          onClick={() => setInboxFilter("BUYERS")}
          type="button"
        >
          <span>Buyers</span>
          <strong>{summary.buyers}</strong>
        </button>
        <button
          className={filter === "MANUAL" ? "is-active" : ""}
          onClick={() => setInboxFilter("MANUAL")}
          type="button"
        >
          <span>Manual Mode</span>
          <strong>{summary.manual}</strong>
        </button>
      </section>
      <div className="relationships-inbox">
        <aside className="relationships-list">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              setQuery(search.trim());
            }}
          >
            <Search size={15} />
            <input
              aria-label="Search chats"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search name, username, or ID"
              value={search}
            />
          </form>
          <label className="relationships-sort">
            <span>Sort:</span>
            <select
              aria-label="Sort chats"
              onChange={(event) =>
                setSort(event.target.value as RelationshipSort)
              }
              value={sort}
            >
              <option value="LATEST_ACTIVITY">Latest Activity</option>
              <option value="COUNTRY_TIER_HIGH_TO_LOW">
                Country Tier — High to Low
              </option>
              <option value="COUNTRY_TIER_LOW_TO_HIGH">
                Country Tier — Low to High
              </option>
              <option value="LIFETIME_SPEND">Lifetime Spend</option>
            </select>
          </label>
          <nav aria-label="Chat filters" className="chat-filters">
            {[
              ["ALL", "All"],
              ["NEEDS_ATTENTION", "Needs Attention"],
              ["BUYERS", "Buyers"],
              ["PROSPECTS", "Prospects"],
              ["MANUAL", "Manual"],
            ].map(([value, label]) => (
              <button
                aria-pressed={filter === value}
                key={value}
                onClick={() => setInboxFilter(value as RelationshipFilter)}
                type="button"
              >
                {label}
              </button>
            ))}
            <button
              aria-expanded={filtersOpen}
              aria-haspopup="menu"
              aria-label="More chat filters"
              className={
                filter === "ACTIVE_SESSION" ||
                filter === "ACTIVE_INTENT" ||
                filter === "IGNORED" ||
                countryTiers.length
                  ? "is-active"
                  : ""
              }
              onClick={() => setFiltersOpen((value) => !value)}
              ref={filtersTrigger}
              type="button"
            >
              More filters
              {countryTiers.length ? ` (${countryTiers.length})` : ""}
            </button>
          </nav>
          {loading && !people.length && (
            <div className="relationships-state" role="status">
              Loading chats…
            </div>
          )}
          {error && (
            <div className="relationships-state is-error" role="alert">
              {error}
              <button onClick={() => void loadList()} type="button">
                Retry
              </button>
            </div>
          )}
          {!loading && !error && !people.length && (
            <div className="relationships-state">
              <Users />
              <strong>No Telegram conversations yet.</strong>
              <span>
                When people begin chatting with Ava, their conversations will
                appear here.
              </span>
            </div>
          )}
          {filter !== "ALL" && (
            <div className="relationships-filter-note">
              Showing {filter.replaceAll("_", " ").toLowerCase()}
            </div>
          )}
          {visiblePeople.map((person) => (
            <button
              aria-pressed={selected?.personKey === person.personKey}
              className={
                selected?.personKey === person.personKey
                  ? "relationship-row is-selected"
                  : "relationship-row"
              }
              key={person.personKey}
              onClick={() => select(person)}
              type="button"
            >
              <div className="relationship-row-title">
                <strong>{person.displayName}</strong>
                {person.ignored ? (
                  <span className="chat-badge is-ignored">IGNORED</span>
                ) : person.operationalStatus === "DELIVERY_UNCERTAIN" && person.attentionOccurrenceId ? (
                  <DeliveryUncertainBadge onClick={() => openUncertainty(person)} />
                ) : person.operationalStatus === "REPLY_READY" &&
                  person.pendingReplyPreview ? (
                  <ReplyReadyBadge person={person} onCancel={() => setCancelTarget(person)} />
                ) : person.operationalStatus !== "LOW_MARKET_LIMIT" &&
                  operationalBadge(person) ? (
                    <span
                      className={`chat-badge is-operational is-${(person.operationalStatus || "none").toLowerCase()}`}
                    >
                      {operationalBadge(person)}
                    </span>
                  ) : null}
              </div>
              {person.username && <span>@{person.username}</span>}
              <p>{person.latestMessagePreview || "Telegram conversation"}</p>
              <div className="relationship-row-metadata">
                <span className="chat-badge">{lifecycleBadge(person)}</span>
                {person.highValueProspect && (
                  <span
                    className="chat-badge is-high-value-prospect"
                    title="High Value Prospect"
                  >
                    HVP
                  </span>
                )}
                <MarketBadge tier={person.marketTier} />
                <TimeWasterBadge
                  active={person.timeWaster}
                  failedPresentationCount={person.failedPresentationCount}
                  verifiedPurchaseCount={person.verifiedPurchaseCount}
                />
              </div>
              <time>{time(person.latestActivityAt)}</time>
            </button>
          ))}
          {next && (
            <button
              className="load-more"
              disabled={loading}
              onClick={() => void loadList(true)}
              type="button"
            >
              Load more chats
            </button>
          )}
        </aside>
        <section className="relationship-conversation">
          {!selected ? (
            <div className="relationships-state">
              Chat at a glance — select a conversation to see customer-visible
              messages and details.
            </div>
          ) : (
            <>
              <header>
                <div>
                  <button
                    className="back-to-relationships"
                    onClick={() => {
                      setDrawerOpen(false);
                      setMoreOpen(false);
                      setOfferOpen(false);
                      setSelected(null);
                      setMessages([]);
                      setOlder(null);
                      setControl(null);
                      setChatLoading(false);
                    }}
                    type="button"
                  >
                    <ArrowLeft size={14} />
                    Back to Chat
                  </button>
                  <div className="selected-customer-title">
                    <h2>{selected.displayName}</h2>
                    <span className="chat-badge">
                      {lifecycleBadge(selected)}
                    </span>
                    <MarketBadge tier={market?.marketTier} />
                    <TimeWasterBadge
                      active={intelligence?.customerValue.timeWaster ?? selected.timeWaster}
                      failedPresentationCount={intelligence?.customerValue.failedPresentationCount ?? selected.failedPresentationCount}
                      verifiedPurchaseCount={intelligence?.customerValue.verifiedPurchaseCount ?? selected.verifiedPurchaseCount}
                    />
                    {intelligence?.operatorClassification && (
                      <span
                        className="chat-badge is-high-value-prospect"
                        title="High Value Prospect"
                      >
                        HVP
                      </span>
                    )}
                    {control?.mode === "HUMAN_OPERATOR" && (
                      <span className="chat-badge is-manual">
                        MANUAL TAKEOVER
                      </span>
                    )}
                    {control?.ignored && (
                      <span className="chat-badge is-ignored">IGNORED</span>
                    )}
                  </div>
                  {selected.username && <span>@{selected.username}</span>}
                </div>
                <div className="conversation-header-actions">
                  {control && (
                    <button
                      className={`header-control-button${control.mode === "HUMAN_OPERATOR" ? " is-manual" : ""}`}
                      onClick={() =>
                        setConfirmAction(
                          control.mode === "HUMAN_OPERATOR"
                            ? "return"
                            : "takeover",
                        )
                      }
                      type="button"
                    >
                      {control.mode === "HUMAN_OPERATOR"
                        ? "RETURN TO AVA"
                        : "TAKE OVER"}
                    </button>
                  )}
                  <button
                    aria-label="Analyze conversation"
                    className="analysis-header-button"
                    onClick={() => setAnalysisOpen(true)}
                    type="button"
                  >
                    ANALYZE
                  </button>
                  <button
                    aria-label="Open Customer Intelligence"
                    className="intelligence-button"
                    onClick={openIntelligence}
                    type="button"
                  >
                    INTELLIGENCE
                  </button>
                  <div className="conversation-more">
                    <button
                      aria-expanded={moreOpen}
                      aria-haspopup="menu"
                      aria-label="More conversation controls"
                      className="conversation-more-trigger"
                      onClick={() => setMoreOpen((value) => !value)}
                      type="button"
                    >
                      <MoreHorizontal size={18} />
                      <span>MORE</span>
                    </button>
                    {moreOpen && (
                      <div className="conversation-more-menu" role="menu">
                        <section>
                          <strong>Market Tier</strong>
                          {(["HIGH", "MEDIUM", "LOW"] as const).map((tier) => (
                            <button
                              aria-pressed={market?.marketTier === tier}
                              disabled={marketChanging || intelligenceLoading}
                              key={tier}
                              onClick={() => {
                                setMoreOpen(false);
                                changeMarketTier(tier);
                              }}
                              role="menuitem"
                              type="button"
                            >
                              {tierLabel(tier)}
                            </button>
                          ))}
                          <button
                            aria-pressed={market?.marketTier === "UNCLASSIFIED"}
                            disabled={
                              marketChanging ||
                              intelligenceLoading ||
                              market?.marketTier === "UNCLASSIFIED"
                            }
                            onClick={() => {
                              setMoreOpen(false);
                              clearMarketTier();
                            }}
                            role="menuitem"
                            type="button"
                          >
                            Unclassified
                          </button>
                        </section>
                        <section>
                          <strong>Priority</strong>
                          <button
                            aria-pressed={Boolean(
                              intelligence?.operatorClassification,
                            )}
                            disabled={valueChanging || intelligenceLoading}
                            onClick={() => {
                              setMoreOpen(false);
                              changeHighValue();
                            }}
                            role="menuitem"
                            type="button"
                          >
                            High Value Prospect{" "}
                            {intelligence?.operatorClassification
                              ? "On"
                              : "Off"}
                          </button>
                        </section>
                        <section>
                          <strong>Communication</strong>
                          {control && (
                            <button
                              onClick={() => {
                                setMoreOpen(false);
                                setConfirmAction(
                                  control.ignored ? "unignore" : "ignore",
                                );
                              }}
                              role="menuitem"
                              type="button"
                            >
                              {control.ignored
                                ? "Unignore Relationship"
                                : "Ignore Relationship"}
                            </button>
                          )}
                        </section>
                      </div>
                    )}
                  </div>
                </div>
              </header>
              <section
                className="chat-operational-detail"
                aria-label={
                  selected.operationalStatus === "LOW_MARKET_LIMIT"
                    ? "Conversation operational status: Reply Limit Reached"
                    : "Conversation operational status"
                }
              >
                <dl>
                  <div>
                    <dt>Automation</dt>
                    <dd>
                      {selected.controlMode === "HUMAN_OPERATOR"
                        ? "Manual Mode"
                        : "Ava Auto"}
                    </dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>
                      {selected.operationalStatus === "DELIVERY_UNCERTAIN" && selected.attentionOccurrenceId
                        ? <DeliveryUncertainBadge onClick={() => openUncertainty(selected)} />
                        : selected.operationalStatus === "LOW_MARKET_LIMIT"
                        ? "Reply Limit Reached"
                        : selected.operationalStatus === "MEDIUM_MARKET_LIMIT"
                          ? "MED MARKET LIMIT"
                          : title(selected.operationalStatus)}
                    </dd>
                  </div>
                  {selected.deliveryUncertaintyAcknowledged && <div><dt>Delivery history</dt><dd>Delivery Uncertain — Acknowledged</dd></div>}
                  {selected.nextAutomaticAttemptAt && (
                    <div>
                      <dt>
                        {selected.operationalStatus === "OVERDUE"
                          ? "Expected"
                          : "Next reply"}
                      </dt>
                      <dd>{time(selected.nextAutomaticAttemptAt)}</dd>
                    </div>
                  )}
                  {selected.operationalStatus === "OVERDUE" && (
                    <div>
                      <dt>Overdue by</dt>
                      <dd>{overdue(selected.overdueSince)}</dd>
                    </div>
                  )}
                  {selected.operationalCategory && <><dt>Conversation lifecycle</dt><dd>{title(selected.operationalCategory)}</dd></>}
                  {selected.responseObligation && <><dt>Response owed</dt><dd>{selected.responseObligation.required ? "Yes" : "No"}</dd></>}
                  {selected.candidateBudgetRemaining != null && <><dt>Remaining candidates</dt><dd>{selected.candidateBudgetRemaining}</dd></>}
                  {selected.deliveryCertainty && <><dt>Delivery certainty</dt><dd>{title(selected.deliveryCertainty)}</dd></>}
                  {selected.operationalStatusReason &&
                    selected.operationalStatus !== "LOW_MARKET_LIMIT" && (
                    <div>
                      <dt>Reason</dt>
                      <dd>{selected.operationalStatusReason}</dd>
                    </div>
                  )}
                  {selected.operationalStatus === "REPLY_SCHEDULED" &&
                    selected.operationId && selected.inboundMessageId && (
                    <button className="cancel-reply-action" onClick={() => setCancelTarget(selected)} type="button">
                      Cancel Reply
                    </button>
                  )}
                  {(selected.operationalStatus === "MEDIUM_MARKET_LIMIT" ||
                    selected.operationalStatus === "LOW_MARKET_LIMIT") && (
                    <>
                      <div>
                        <dt>Next eligible</dt>
                        <dd>
                          {selected.nextResetAt
                            ? time(selected.nextResetAt)
                            : "—"}
                        </dd>
                      </div>
                      <div>
                        <dt>Usage</dt>
                        <dd>
                          {selected.repliesUsedToday} of{" "}
                          {selected.dailyReplyBudget} ordinary replies used
                          today
                        </dd>
                      </div>
                    </>
                  )}
                </dl>
                {(selected.operationalStatus === "NEEDS_ATTENTION" || selected.operationalStatus === "SYSTEM_INCIDENT") &&
                  selected.attentionOccurrenceId && (
                    <div className="attention-actions">
                      <button
                        onClick={() =>
                          setInspectionTarget({
                            person: selected,
                            occurrenceId: selected.attentionOccurrenceId!,
                          })
                        }
                        type="button"
                      >
                        Inspect &amp; Resolve
                      </button>
                      <button
                        disabled={acknowledging}
                        onClick={acknowledgeAttention}
                        type="button"
                      >
                        {acknowledging ? "Acknowledging…" : "Acknowledge"}
                      </button>
                    </div>
                  )}
                {attentionError && <span role="alert">{attentionError}</span>}
              </section>
              {selected.operationalStatus === "REPLY_READY" &&
                selected.pendingReplyPreview && (
                  <section className="pending-reply-card" aria-label="Ava pending reply">
                    <header>
                      <div>
                        <strong>AVA · PENDING REPLY</strong>
                        {selected.nextAutomaticAttemptAt && (
                          <span>Scheduled for {time(selected.nextAutomaticAttemptAt)}</span>
                        )}
                      </div>
                      {selected.operationId && selected.inboundMessageId && (
                        <button onClick={() => setCancelTarget(selected)} type="button">
                          Cancel Reply
                        </button>
                      )}
                    </header>
                    <p>{selected.pendingReplyPreview}</p>
                  </section>
                )}
              <div className="customer-intelligence-layout">
                {drawerOpen && (
                  <button
                    aria-label="Close Customer Intelligence"
                    className="intelligence-drawer-close"
                    onClick={() => setDrawerOpen(false)}
                    type="button"
                  >
                    <X size={18} />
                  </button>
                )}
                <PPVEscalationCard data={intelligence?.ppvEscalation} onReadiness={openReadiness} />
                <div className="customer-intelligence-stack">
                  <MarketPolicyCard market={market} />
                  <CustomerIntelligenceTrigger
                    error={intelligenceError}
                    open={openCustomerIntelligence}
                  />
                </div>
              </div>
              {analysisOpen && (
                <ConversationAnalysisDialog
                  personKey={selected.personKey}
                  displayName={selected.displayName}
                  username={selected.username}
                  transcript={messages}
                  onClose={() => setAnalysisOpen(false)}
                />
              )}{" "}
              {drawerOpen && (
                <IntelligenceDrawer
                  data={intelligence}
                  error={intelligenceError}
                  loading={intelligenceLoading}
                  person={selected}
                  onReadiness={openReadiness}
                />
              )}
              {readinessOpen && intelligence?.ppvEscalation?.offerReadiness && (
                <OfferReadinessModal
                  close={closeReadiness}
                  data={intelligence.ppvEscalation.offerReadiness}
                  person={selected}
                />
              )}
              {customerIntelligenceOpen && (
                <CustomerIntelligenceModal
                  close={closeCustomerIntelligence}
                  data={intelligence}
                  error={intelligenceError}
                  loading={intelligenceLoading}
                  person={selected}
                />
              )}
              {inspectionTarget && (
                <InspectResolveDialog
                  target={inspectionTarget.person}
                  occurrenceId={inspectionTarget.occurrenceId}
                  targetCurrent={people.some(
                    (item) =>
                      item.personKey === inspectionTarget.person.personKey &&
                      item.attentionOccurrenceId === inspectionTarget.occurrenceId,
                  )}
                  onClose={() => setInspectionTarget(null)}
                  onResolved={() => void loadList(false, true)}
                  onSelectSimilar={(key) => {
                    const person = people.find(
                      (item) => item.personKey === key,
                    );
                    setInspectionTarget(null);
                    if (person) select(person);
                  }}
                />
              )}
              {offerOpen && control && (
                <RelationshipOfferDrawer
                  personKey={selected.personKey}
                  control={control}
                  onClose={() => setOfferOpen(false)}
                  onSent={(message) =>
                    setMessages((current) =>
                      current.some((item) => item.eventKey === message.eventKey)
                        ? current
                        : [...current, message],
                    )
                  }
                />
              )}
              {confirmAction && (
                <div
                  className="takeover-modal"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="takeover-title"
                >
                  <div>
                    <h3 id="takeover-title">
                      {confirmAction === "takeover"
                        ? "Take over this conversation?"
                        : confirmAction === "return"
                          ? "Return this conversation to Ava?"
                          : confirmAction === "ignore"
                            ? "Ignore this relationship?"
                            : "Unignore this relationship?"}
                    </h3>
                    <p>
                      {confirmAction === "takeover"
                        ? "Ava will stop automatically replying to this customer until you return control."
                        : confirmAction === "return"
                          ? "Ava may respond to the next legitimate inbound or authorized automation event. Old inbound messages will not receive a new reply."
                          : confirmAction === "ignore"
                            ? "Ava will stop communicating with this relationship. Pending unsent work will be neutralized; new messages remain visible but unanswered."
                            : "Old messages received while ignored will not receive automatic responses. Ava waits for a new inbound."}
                    </p>
                    {(control?.activePurchaseIntent ||
                      control?.activeSalesSession) && (
                      <p className="control-warning">
                        This relationship has{" "}
                        {control.activePurchaseIntent
                          ? "an unresolved PurchaseIntent"
                          : ""}
                        {control.activePurchaseIntent &&
                        control.activeSalesSession
                          ? " and "
                          : ""}
                        {control.activeSalesSession
                          ? "an active Sales Session"
                          : ""}
                        . Neither will be reset.
                      </p>
                    )}
                    {controlError && <p role="alert">{controlError}</p>}
                    <footer>
                      <button
                        onClick={() => setConfirmAction(null)}
                        type="button"
                      >
                        Cancel
                      </button>
                      <button onClick={changeControl} type="button">
                        {confirmAction === "takeover"
                          ? "Take Over"
                          : confirmAction === "return"
                            ? "Return to Ava"
                            : confirmAction === "ignore"
                              ? "Ignore"
                              : "Unignore"}
                      </button>
                    </footer>
                  </div>
                </div>
              )}
              {confirmHvpRemoval && selected && (
                <div
                  className="takeover-modal"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="remove-hvp-title"
                >
                  <div>
                    <h3 id="remove-hvp-title">Remove HVP?</h3>
                    <p>
                      {selected.displayName} will no longer receive High Value
                      Prospect treatment. {selected.displayName}&apos;s HIGH market
                      tier will not change.
                    </p>
                    {controlError && <p role="alert">{controlError}</p>}
                    <footer>
                      <button
                        disabled={valueChanging}
                        onClick={() => setConfirmHvpRemoval(false)}
                        type="button"
                      >
                        Cancel
                      </button>
                      <button
                        disabled={valueChanging}
                        onClick={() => changeHighValue(true)}
                        type="button"
                      >
                        {valueChanging ? "Removing…" : "Remove HVP"}
                      </button>
                    </footer>
                  </div>
                </div>
              )}
              {cancelTarget && (
                <div className="takeover-modal" role="dialog" aria-modal="true" aria-labelledby="cancel-reply-title">
                  <div>
                    <h3 id="cancel-reply-title">Cancel Ava&apos;s reply?</h3>
                    <p>This prepared reply will not be sent. Ava Auto will remain on and will respond normally when the customer sends a new message.</p>
                    {cancelReplyError && <p role="alert">{cancelReplyError}</p>}
                    <footer>
                      <button disabled={cancellingReply} onClick={() => setCancelTarget(null)} type="button">Keep Reply</button>
                      <button disabled={cancellingReply} onClick={cancelReply} type="button">
                        {cancellingReply ? "Canceling…" : "Cancel Reply"}
                      </button>
                    </footer>
                  </div>
                </div>
              )}
              <div
                className="relationship-transcript"
                onScroll={(event) => {
                  const node = event.currentTarget;
                  transcriptNearBottom.current =
                    node.scrollHeight - node.scrollTop - node.clientHeight <=
                    TRANSCRIPT_BOTTOM_THRESHOLD_PX;
                  if (transcriptNearBottom.current)
                    setNewMessagesAvailable(false);
                  if (node.scrollTop <= TRANSCRIPT_BOTTOM_THRESHOLD_PX && older &&
                      !olderRequest.current) void loadOlder();
                }}
                ref={transcript}
              >
                {newMessagesAvailable && (
                  <button
                    className="new-message-indicator"
                    onClick={() => {
                      if (transcript.current)
                        transcript.current.scrollTop = transcript.current.scrollHeight;
                      transcriptNearBottom.current = true;
                      setNewMessagesAvailable(false);
                    }}
                    type="button"
                  >
                    New message
                  </button>
                )}
                {older && (
                  <button
                    className="load-older"
                    disabled={chatLoading}
                    onClick={() => void loadOlder()}
                    type="button"
                  >
                    Load older messages
                  </button>
                )}
                {chatLoading && !messages.length && (
                  <div className="relationships-state" role="status">
                    Loading conversation…
                  </div>
                )}
                {chatError && (
                  <div className="relationships-state is-error" role="alert">
                    {chatError}
                  </div>
                )}
                {downloadError && (
                  <div className="relationships-state is-error" role="alert">
                    {downloadError}
                  </div>
                )}
                {controlError && (
                  <div className="relationships-state is-error" role="alert">
                    {controlError}
                  </div>
                )}
                {messages.map((message, index) => {
                  const separator =
                    index === 0 ||
                    day(messages[index - 1]!.timestamp) !==
                      day(message.timestamp);
                  return (
                    <div key={message.eventKey}>
                      {separator && (
                        <div className="date-separator">
                          {day(message.timestamp)}
                        </div>
                      )}
                      <article
                        className={`message-bubble is-${message.direction.toLowerCase()}`}
                      >
                        <span>{message.direction}</span>
                        <p>{message.content}</p>
                        <time>{time(message.timestamp)}</time>
                        {message.messageType === "COMMERCIAL_OFFER" && (
                          <small>Offer Presented</small>
                        )}
                      </article>
                    </div>
                  );
                })}
              </div>
              {control?.mode === "HUMAN_OPERATOR" && (
                <form
                  className="manual-composer"
                  onSubmit={(event) => {
                    event.preventDefault();
                    send();
                  }}
                >
                  <header className="manual-composer-status">
                    <div>
                      <strong>MANUAL TAKEOVER</strong>
                      <span>You’re replying as Ava</span>
                    </div>
                    <button
                      className="return-to-ava-button"
                      onClick={() => setConfirmAction("return")}
                      type="button"
                    >
                      Return to Ava Auto
                    </button>
                  </header>
                  <button
                    className="content-offer-button"
                    onClick={() => setOfferOpen(true)}
                    type="button"
                  >
                    Content / Offer
                  </button>
                  <textarea
                    aria-label="Write a message"
                    onChange={(event) => {
                      setRelationshipDraft(
                        selected.personKey,
                        event.target.value,
                      );
                      sendKeys.current.delete(selected.personKey);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        send();
                      }
                    }}
                    placeholder="Type a message as Ava..."
                    rows={2}
                    value={draft}
                  />
                  <button disabled={sending || !draft.trim()} type="submit">
                    {sending ? "Sending…" : "Send"}
                  </button>
                  {sendError && (
                    <span className="manual-send-error" role="alert">
                      {sendError}
                    </span>
                  )}
                </form>
              )}
            </>
          )}
        </section>
      </div>
      {uncertainTarget && <DeliveryUncertainDismissModal busy={uncertainBusy} error={uncertainError} onCancel={() => setUncertainTarget(null)} onConfirm={dismissUncertainty} />}
    </main>
  );
}
