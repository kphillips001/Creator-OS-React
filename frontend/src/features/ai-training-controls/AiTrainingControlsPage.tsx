import { Archive, Check, Edit3, Power, PowerOff, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { aiTrainingControlsApi, type TrainingInstruction, type TrainingPreview } from "../../infrastructure/api/aiTrainingControlsApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import "./ai-training-controls.css";

const groups = [
  ["ENABLED", "Active"], ["DRAFT", "Draft"], ["DISABLED", "Disabled"],
  ["REQUIRES_IMPLEMENTATION", "Requires Implementation"], ["ARCHIVED", "Archived"],
] as const;

export function AiTrainingControlsPage() {
  const [items, setItems] = useState<TrainingInstruction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [priority, setPriority] = useState(100);
  const [policyConfig, setPolicyConfig] = useState<Record<string, number | boolean | string>>({});
  const [preview, setPreview] = useState<TrainingPreview | null>(null);
  const [editing, setEditing] = useState<TrainingInstruction | null>(null);
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { setItems((await aiTrainingControlsApi.list()).items); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load AI Training."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  const byStatus = useMemo(() => Object.fromEntries(groups.map(([status]) => [status, items.filter((item) => item.status === status)])), [items]);
  const reset = () => { setOpen(false); setEditing(null); setText(""); setPriority(100); setPolicyConfig({}); setPreview(null); };
  const beginCreate = () => { reset(); setOpen(true); };
  const beginEdit = (item: TrainingInstruction) => { setEditing(item); setText(item.originalOperatorText); setPriority(item.priority); setPolicyConfig(item.policyConfiguration || {}); setPreview(null); setOpen(true); };
  const inspect = async () => {
    setBusy(true); setError("");
    try { const value = await aiTrainingControlsApi.preview(text); setPreview(value); setPolicyConfig(value.policyConfiguration || {}); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to preview instruction."); }
    finally { setBusy(false); }
  };
  const save = async () => {
    if (!preview) return;
    setBusy(true); setError("");
    try {
      const saved = editing
        ? await aiTrainingControlsApi.edit(editing.instructionId, text, priority, policyConfig)
        : await aiTrainingControlsApi.create(text, priority, preview.runtimeEligible, policyConfig);
      if (saved.instructionType === "SAFETY_HARD_STOP" && saved.runtimeRecognized !== true) {
        throw new Error("Safety policy was not recognized by runtime enforcement.");
      }
      setSuccess(saved.instructionType === "SAFETY_HARD_STOP"
        ? "Training Activated ✓ Underage Customer Hard Stop is now ACTIVE. Backend enforced · Global policy · UNDERAGE_BLOCKED customers only · Other customers unaffected."
        : `Training ${editing ? "updated" : "activated"} ✓`);
      reset(); await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save instruction."); }
    finally { setBusy(false); }
  };
  const transition = async (item: TrainingInstruction, action: "enable" | "disable" | "archive") => {
    setError("");
    try { await aiTrainingControlsApi.transition(item.instructionId, action); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to update instruction."); }
  };

  return <main className="training-controls-page">
    <PageHeader title="AI Training" description="Create and control global conversation guidance used by Creator-OS AI." />
    <section className="training-controls-heading">
      <div><span>GLOBAL TRAINING</span><p>Conversation preferences apply account-wide. Safety, sales, commerce, ownership, and delivery remain backend-authoritative.</p></div>
      <button onClick={beginCreate} type="button">+ New Global Training</button>
    </section>
    {error && <div className="training-controls-alert" role="alert">{error}</div>}
    {success && <div className="training-controls-alert" role="status">{success}</div>}
    {loading && <div className="training-controls-state">Loading global training…</div>}
    {!loading && groups.map(([status, label]) => <section className="training-controls-group" key={status}>
      <header><h2>{label}</h2><span>{byStatus[status]?.length ?? 0}</span></header>
      {!byStatus[status]?.length && <p className="training-controls-empty">No {label.toLowerCase()} instructions.</p>}
      <div className="training-controls-grid">{byStatus[status]?.map((item) => <article className="training-control-card" key={item.instructionId}>
        <div className="training-control-meta"><span>{item.instructionType === "SAFETY_HARD_STOP" ? "SAFETY / HARD STOP" : item.instructionType.replaceAll("_", " ")}</span>{item.enforcementMode === "BACKEND" && <><span>BACKEND ENFORCED</span><span>GLOBAL POLICY</span></>}<span>{item.status}</span><span>Priority {item.priority}</span><span>v{item.version}</span></div>
        <p>{item.normalizedInstruction}</p>
        {item.policyKey === "UNDERAGE_CUSTOMER" && <aside><strong>Underage Customer Hard Stop</strong>Only customers deliberately marked UNDERAGE_BLOCKED are prevented from autonomous interaction. Other customers are unaffected. Disabling this policy does not restore marked customers.</aside>}
        {item.status === "REQUIRES_IMPLEMENTATION" && <aside><strong>Requires Backend Enforcement</strong>{item.classificationReason}</aside>}
        <footer><small>Updated {new Date(item.updatedAt).toLocaleString()}</small><div>
          {item.status !== "ARCHIVED" && <button aria-label="Edit instruction" onClick={() => beginEdit(item)} title="Edit"><Edit3 size={15} /></button>}
          {(item.status === "DISABLED" || item.status === "DRAFT") && ["CONVERSATION_RULE", "ENGAGEMENT_RULE", "SALES_RULE"].includes(item.instructionType) && <button aria-label="Enable instruction" onClick={() => void transition(item, "enable")} title="Enable"><Power size={15} /></button>}
          {item.status === "ENABLED" && <button aria-label="Disable instruction" onClick={() => void transition(item, "disable")} title="Disable"><PowerOff size={15} /></button>}
          {item.status !== "ARCHIVED" && <button aria-label="Archive instruction" onClick={() => void transition(item, "archive")} title="Archive"><Archive size={15} /></button>}
        </div></footer>
      </article>)}</div>
    </section>)}
    {open && <div className="training-control-dialog" role="dialog" aria-modal="true" aria-labelledby="training-dialog-title"><form onSubmit={(event) => { event.preventDefault(); preview ? void save() : void inspect(); }}>
      <header><div><span>GLOBAL CONVERSATION RULE</span><h2 id="training-dialog-title">{editing ? "Edit training instruction" : "New training instruction"}</h2></div><button aria-label="Close" onClick={reset} type="button"><X size={18} /></button></header>
      <label>Instruction<textarea autoFocus maxLength={2000} onChange={(event) => { setText(event.target.value); setPreview(null); }} rows={6} value={text} /></label>
      <label>Priority<input min={0} max={1000} onChange={(event) => setPriority(Number(event.target.value))} type="number" value={priority} /></label>
      {preview?.instructionType === "ENGAGEMENT_RULE" && <fieldset className="engagement-policy-fields"><legend>Engagement frequency</legend>{([
        ["dormant_inactivity_days", "Dormant inactivity threshold (days)"], ["reengagement_cooldown_days", "Re-engagement cooldown (days)"],
        ["warm_up_minimum_inbound_messages", "Warm-up minimum conversation depth"], ["relationship_cooldown_days", "Relationship teaser cooldown (days)"],
        ["maximum_per_rolling_period", "Maximum teasers per rolling period"],
      ] as const).map(([key, label]) => <label key={key}>{label}<input min={1} type="number" value={Number(policyConfig[key] ?? 1)} onChange={(event) => setPolicyConfig((current) => ({ ...current, [key]: Number(event.target.value) }))} /></label>)}</fieldset>}
      {preview?.policyKey === "ADAPTIVE_SALES_READINESS" && <fieldset className="engagement-policy-fields"><legend>Advisory new-prospect benchmark</legend>{([
        ["normal_prospect_target_min", "Normal benchmark start (inbound messages)"], ["normal_prospect_target_max", "Normal benchmark end (inbound messages)"],
        ["meaningful_inactivity_days", "New episode after inactivity (days)"],
      ] as const).map(([key, label]) => <label key={key}>{label}<input min={1} type="number" value={Number(policyConfig[key] ?? 1)} onChange={(event) => setPolicyConfig((current) => ({ ...current, [key]: Number(event.target.value) }))} /></label>)}</fieldset>}
      {preview?.policyKey === "ADAPTIVE_SALES_READINESS" && <section className="training-control-preview"><span>GLOBAL · SALES RULE</span><h3>Adaptive Sales Readiness</h3><p>Goal: Sell when the customer is ready without being pushy or spammy.</p><p>Normal benchmark: approximately {String(policyConfig.normal_prospect_target_min)}–{String(policyConfig.normal_prospect_target_max)} inbound customer messages.</p><p>Hard minimum: None · Automatic offer at maximum: NO</p><p>Direct purchase intent may bypass warm-up. Sending a Free Teaser adds no readiness; customer response is supporting evidence only.</p><p>Sessions, active offers, payment state, BACK_OFF, cooldowns, safety, ownership, and availability take precedence.</p><small>{preview.classificationReason}</small></section>}
      {preview && <section className="training-control-preview"><span>GLOBAL · {preview.instructionType === "SAFETY_HARD_STOP" ? "SAFETY / HARD STOP" : preview.instructionType.replaceAll("_", " ")}</span>{preview.instructionType === "ENGAGEMENT_RULE" ? <><h3>Intelligent Free Engagement Teasers</h3><p>Purposes: Warm up new/newer customers · Re-engage dormant customers · Occasionally reward good subscribers</p><p>Captions: Generated by Ava using customer context + Asset Intelligence</p><p>Duplicate policy: Same Teaser → Same Customer = NEVER</p><p>Paid sales: Does not advance paid sales · Active offers and Sessions suppressed</p><p>Safety: Backend enforced · Frequency controlled and occasional</p></> : <dl><div><dt>Original</dt><dd>{preview.originalOperatorText}</dd></div><div><dt>Creator-OS understood</dt><dd>{preview.normalizedInstruction}</dd></div><div><dt>Enforcement</dt><dd>{preview.enforcementMode === "BACKEND" ? "Backend enforced" : preview.runtimeEligible ? "GPT conversation context" : "Requires implementation"}</dd></div><div><dt>Applies to</dt><dd>{preview.policyKey === "UNDERAGE_CUSTOMER" ? "All customers as a global policy" : "All customers"}</dd></div>{preview.policyKey === "UNDERAGE_CUSTOMER" && <><div><dt>Effect</dt><dd>Only customers marked UNDERAGE_BLOCKED are prevented from autonomous interaction.</dd></div><div><dt>Other customers</dt><dd>Unaffected.</dd></div><div><dt>Age determination</dt><dd>This rule does not automatically determine or mark customers underage.</dd></div></>}</dl>}<small>{preview.classificationReason}</small></section>}
      <footer><button className="secondary" onClick={reset} type="button">Cancel</button><button disabled={busy || !text.trim()} type="submit">{preview ? <><Check size={15} />{editing ? "Save Changes" : preview.runtimeEligible ? "Activate" : "Save for Review"}</> : "Preview Instruction"}</button></footer>
    </form></div>}
  </main>;
}
