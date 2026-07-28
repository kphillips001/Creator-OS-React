import { useCallback, useEffect, useState } from "react";
import { Brain, Check, Pencil, RefreshCw, Sparkles, X } from "lucide-react";

import { avaCoachApi } from "./api";
import type { AvaCoachDashboard, CoachEvidenceItem, CoachRecommendation } from "./types";
import "./ava-coach.css";

const confidenceLabel = (value: number) =>
  value >= 0.75 ? "High" : value >= 0.5 ? "Medium" : "Low";
const formatDate = (value?: string | null) =>
  value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "Not analyzed";

// Exported for deterministic browser-local greeting tests.
// eslint-disable-next-line react-refresh/only-export-components
export function coachGreeting(now = new Date()) {
  const hour = now.getHours();
  if (hour < 12) return "Good morning, Kevin.";
  if (hour < 18) return "Good afternoon, Kevin.";
  return "Good evening, Kevin.";
}

export function AvaCoachPage() {
  const [data, setData] = useState<AvaCoachDashboard | null>(null);
  const [busy, setBusy] = useState(false);
  const [analysisMessage, setAnalysisMessage] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<CoachRecommendation | null>(null);
  const [approving, setApproving] = useState<CoachRecommendation | null>(null);

  const load = useCallback(async () => {
    const dashboard = await avaCoachApi.dashboard();
    return dashboard.snapshot ? dashboard : avaCoachApi.analyze();
  }, []);
  useEffect(() => {
    void load().then(setData).catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : "Unable to load Ava Coach."));
  }, [load]);

  const analyze = async () => {
    if (busy) return;
    setBusy(true); setError(""); setAnalysisMessage("Analyzing conversation evidence…");
    try {
      const result = await avaCoachApi.analyze();
      setData(result);
      setAnalysisMessage(`Analysis complete: ${result.overview.totalConversationsReviewed} conversations and ${result.overview.totalMessagesReviewed} messages reviewed.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis failed.");
      setAnalysisMessage("");
    } finally { setBusy(false); }
  };
  const transition = async (recommendation: CoachRecommendation, action: "approve" | "reject" | "dismiss") => {
    setBusy(true); setError("");
    try {
      await avaCoachApi.transition(recommendation.recommendation_id, action);
      setData(await avaCoachApi.dashboard());
      setApproving(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Recommendation update failed.");
    } finally { setBusy(false); }
  };
  const saveEdit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!editing) return;
    const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      await avaCoachApi.edit(editing.recommendation_id, String(form.get("title")), String(form.get("description")));
      setData(await avaCoachApi.dashboard()); setEditing(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Recommendation edit failed.");
    } finally { setBusy(false); }
  };

  if (error && !data) return <main className="ava-coach"><div className="coach-state" role="alert">{error}</div></main>;
  if (!data) return <main className="ava-coach"><div className="coach-state">Reviewing conversation evidence…</div></main>;
  const positive = data.insights.filter((item) => item.insight_type === "POSITIVE_STRENGTH");
  const behaviors = data.insights.filter((item) => !["POSITIVE_STRENGTH", "TOPICS"].includes(item.insight_type ?? ""));
  const pending = data.recommendations.filter((item) => item.status === "PENDING");
  const history = data.recommendations.filter((item) => item.status !== "PENDING");
  const current = data.versions.find((item) => item.status === "BASELINE" || item.status === "ACTIVE");
  const proposed = data.versions.find((item) => item.status === "DRAFT");
  const approved = data.recommendations.filter((item) => item.status === "APPROVED_FOR_VERSION").length;
  const rejected = data.recommendations.filter((item) => ["REJECTED", "DISMISSED"].includes(item.status)).length;

  return <main className="ava-coach">
    <header className="coach-hero">
      <div><p>Ava Coach</p><h1>{coachGreeting()}</h1>
        <span>Here’s what I noticed about Ava.</span></div>
      <button disabled={busy} onClick={() => void analyze()} type="button">
        <RefreshCw size={15} className={busy ? "is-spinning" : ""} />Run Conversation Analysis
      </button>
      <div className="coach-hero__metrics">
        <Stat label="Last analysis" value={formatDate(data.snapshot?.created_at)} />
        <Stat label="Period" value={data.snapshot?.period_start ? `${formatDate(data.snapshot.period_start)} – ${formatDate(data.snapshot.period_end)}` : "No evidence yet"} />
        <Stat label="Conversations" value={data.overview.totalConversationsReviewed} />
        <Stat label="Messages" value={data.overview.totalMessagesReviewed} />
        <Stat label="Current version" value={current?.version_label ?? "Not tracked yet"} />
        <Stat label="Target version" value={proposed?.version_label ?? "Not tracked yet"} />
      </div>
    </header>
    <div className="coach-observational"><Brain size={17} />
      <span>Coach recommendations are observational. Approval adds them to the proposed personality version; it does not change Ava’s live behavior.</span>
    </div>
    {analysisMessage && <p className="coach-progress" role="status">{analysisMessage}</p>}
    {error && <p className="coach-error" role="alert">{error}</p>}

    <section><Heading title="Conversation Health" />
      <div className="coach-stat-grid">
        <Stat label="Conversations reviewed" value={data.overview.totalConversationsReviewed} />
        <Stat label="Messages reviewed" value={data.overview.totalMessagesReviewed} />
        <Stat label="Average length" value={data.overview.averageConversationLength} />
        <Stat label="Continuation rate" value={`${data.overview.conversationContinuationRate}%`} />
        <Stat label="Returning visitors" value={data.overview.returningVisitors} />
        <Stat label="Questions asked" value={data.overview.questionsAsked} />
        <Stat label="Ended with Ava" value={data.overview.conversationEndings.ava} />
        <Stat label="Ended with visitor" value={data.overview.conversationEndings.visitor} />
      </div>
    </section>
    <EvidenceSection title="What Ava Did Well" items={positive} empty="No positive pattern has enough evidence yet. Run analysis after more conversations." />
    <EvidenceSection title="Behavior Insights" items={behaviors} empty="No behavior patterns need attention in the reviewed evidence." />
    <section><Heading title="Emerging Topics" />
      {!data.overview.topicsDiscussed.length ? <Empty>No recurring topics have emerged yet.</Empty> :
        <div className="coach-topic-list">{data.overview.topicsDiscussed.map((topic) =>
          <article key={topic.topic}><strong>{topic.topic}</strong>
            <span>{topic.conversationCount} conversation{topic.conversationCount === 1 ? "" : "s"} · {topic.messageCount} message{topic.messageCount === 1 ? "" : "s"}</span>
            <small>Trend unavailable until a comparable analysis period exists.</small>
          </article>)}</div>}
    </section>
    <section><Heading icon={<Sparkles size={17} />} title="Recommendations" />
      <p className="coach-section-note">Review or edit each proposal before adding it to {proposed?.version_label ?? "the draft version"}.</p>
      {!pending.length ? <Empty>No recommendations are awaiting review.</Empty> :
        <div className="coach-card-grid">{pending.map((item) =>
          <RecommendationCard key={item.recommendation_id} item={item} busy={busy}
            onApprove={() => setApproving(item)} onEdit={() => setEditing(item)}
            onReject={() => void transition(item, "reject")}
            onDismiss={() => void transition(item, "dismiss")} />)}</div>}
    </section>
    <section><Heading title="Personality Evolution" />
      <div className="coach-version-list">
        <article><span>Current</span><strong>{current?.version_label ?? "No baseline"}</strong><p>{current?.notes}</p></article>
        <article><span>Proposed · DRAFT</span><strong>{proposed?.version_label ?? "No draft"}</strong><p>{proposed?.notes}</p></article>
      </div>
      <div className="coach-stat-grid coach-evolution-counts">
        <Stat label="Pending" value={pending.length} /><Stat label="Approved for version" value={approved} /><Stat label="Rejected" value={rejected} />
      </div>
      <div className="coach-observational">Approved recommendations have no effect until a future personality-version activation workflow is explicitly performed.</div>
    </section>
    <section><Heading title="Recommendation History" />
      {!history.length ? <Empty>No recommendation decisions have been recorded yet.</Empty> :
        <div className="coach-card-grid">{history.map((item) => <EvidenceCard key={item.recommendation_id} item={item} status={item.status} />)}</div>}
    </section>

    {editing && <div className="coach-dialog-backdrop"><form className="coach-dialog" onSubmit={saveEdit}>
      <h2>Edit recommendation</h2><label>Title<input name="title" defaultValue={editing.title} required /></label>
      <label>Recommendation<textarea name="description" defaultValue={editing.description} required /></label>
      <div className="coach-actions"><button disabled={busy} type="submit">Save changes</button><button disabled={busy} onClick={() => setEditing(null)} type="button">Cancel</button></div>
    </form></div>}
    {approving && <div className="coach-dialog-backdrop"><div className="coach-dialog" role="dialog" aria-modal="true">
      <h2>Approve this coaching recommendation?</h2>
      <p>This will add the recommendation to {approving.version_label}’s proposed improvement set. Ava’s live personality and runtime behavior will not change.</p>
      <div className="coach-actions"><button disabled={busy} onClick={() => void transition(approving, "approve")} type="button"><Check size={14} />Approve Recommendation</button><button disabled={busy} onClick={() => setApproving(null)} type="button">Cancel</button></div>
    </div></div>}
  </main>;
}

function Heading({ title, icon }: { title: string; icon?: React.ReactNode }) {
  return <div className="coach-heading">{icon}<h2>{title}</h2></div>;
}
function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return <article><span>{label}</span><strong>{value}</strong></article>;
}
function Empty({ children }: { children: React.ReactNode }) { return <div className="coach-empty">{children}</div>; }
function sampleSize(item: CoachEvidenceItem) {
  const value = item.evidence.sampleSize;
  return typeof value === "number" ? value : null;
}
function EvidenceSection({ title, items, empty }: { title: string; items: CoachEvidenceItem[]; empty: string }) {
  return <section><Heading title={title} />{!items.length ? <Empty>{empty}</Empty> :
    <div className="coach-card-grid">{items.map((item) => <EvidenceCard key={`${item.insight_type}-${item.title}`} item={item} />)}</div>}</section>;
}
function EvidenceCard({ item, status }: { item: CoachEvidenceItem; status?: string }) {
  const sample = sampleSize(item);
  return <article className="coach-card"><div className="coach-card__top"><strong>{item.title}</strong>
    <span className={`coach-confidence coach-confidence--${confidenceLabel(item.confidence).toLowerCase()}`}>{confidenceLabel(item.confidence)} confidence</span></div>
    <p>{item.description}</p>{sample !== null && <p className="coach-evidence-summary">Evidence sample: {sample}</p>}
    {status && <span className={`coach-status coach-status--${status.toLowerCase()}`}>{status.replaceAll("_", " ")}</span>}
    <details><summary>View evidence IDs and details</summary><pre>{JSON.stringify(item.evidence, null, 2)}</pre></details>
  </article>;
}
function RecommendationCard({ item, busy, onApprove, onEdit, onReject, onDismiss }: {
  item: CoachRecommendation; busy: boolean; onApprove: () => void; onEdit: () => void;
  onReject: () => void; onDismiss: () => void;
}) {
  return <article className="coach-card"><div className="coach-card__top"><strong>{item.title}</strong>
    <span className={`coach-confidence coach-confidence--${confidenceLabel(item.confidence).toLowerCase()}`}>{confidenceLabel(item.confidence)} confidence</span></div>
    <p>{item.description}</p><p className="coach-evidence-summary">Expected impact: {item.expected_impact} · Sample: {sampleSize(item) ?? "not reported"}</p>
    <details><summary>View evidence IDs and details</summary><pre>{JSON.stringify(item.evidence, null, 2)}</pre></details>
    <div className="coach-actions"><button disabled={busy} onClick={onApprove} type="button"><Check size={14} />Approve</button>
      <button disabled={busy} onClick={onEdit} type="button"><Pencil size={14} />Edit</button>
      <button disabled={busy} onClick={onReject} type="button"><X size={14} />Reject</button>
      <button disabled={busy} onClick={onDismiss} type="button">Dismiss</button></div>
  </article>;
}
