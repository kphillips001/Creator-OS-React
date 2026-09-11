import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ChevronRight, Search, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import {
  controlsApi,
  type CustomerControlRow,
  type CustomerControls,
  type GlobalControls,
} from "./api";
import type { RelationshipFilter, RelationshipSort } from "../relationships/api";
import "./business-controls.css";

type Tab = "global" | "customers";
type CustomerControlName = "ava-chat" | "content-selling" | "session-selling";

const humanize = (value: string | null | undefined) =>
  value ? value.replaceAll("_", " ").toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()) : "—";

export function effectiveMode(controls: CustomerControls | null): string {
  if (!controls?.configured.avaChatEnabled) return "MANUAL";
  if (!controls.effective.chatAllowed) return "CHAT INACTIVE";
  const content = controls.effective.contentSellingAllowed;
  const sessions = controls.effective.sessionSellingAllowed;
  if (content && sessions) return "ALL SALES";
  if (content) return "CONTENT SALES";
  if (sessions) return "SESSION SALES";
  return "CHAT ONLY";
}

function Toggle({ label, value, disabled, onChange }: {
  label: string;
  value: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return <div aria-label={label} className="control-toggle">
    <button aria-pressed={!value} disabled={disabled} onClick={() => onChange(false)} type="button">OFF</button>
    <button aria-pressed={value} disabled={disabled} onClick={() => onChange(true)} type="button">ON</button>
  </div>;
}

function GlobalControlCard({ title, value, inactive, saving, children, onChange }: {
  title: string;
  value: boolean;
  inactive?: boolean;
  saving: boolean;
  children: React.ReactNode;
  onChange: (value: boolean) => void;
}) {
  return <article className={`primary-control-card${inactive ? " is-inactive" : ""}`}>
    <header><div><h2>{title}</h2><p>{children}</p></div><Toggle label={`${title} control`} value={value} disabled={saving} onChange={onChange}/></header>
    {inactive && <small>Will apply when Ava Bot is turned on.</small>}
    {saving && <small role="status">Saving…</small>}
  </article>;
}

function GlobalControlsTab() {
  const [state, setState] = useState<GlobalControls | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const savingRef = useRef(false);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setLoading(true); setError("");
    return controlsApi.global().then(setState).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load controls.")).finally(() => setLoading(false));
  }, []);
  useEffect(() => { void load(); }, [load]);
  const mutate = (key: string, request: () => Promise<{ state: GlobalControls }>) => {
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(key); setError("");
    request().then((result) => setState(result.state)).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to update controls.")).finally(() => { savingRef.current = false; setSaving(null); });
  };
  if (loading && !state) return <div className="controls-state" role="status">Loading global controls…</div>;
  if (!state) return <div className="controls-state is-error" role="alert">{error}<button onClick={() => void load()} type="button">Retry</button></div>;
  const botOn = state.avaBot.desired === "ON";
  return <section aria-label="Global Controls" className="controls-panel">
    <p className="controls-explainer">Global controls set the maximum permissions for everyone.</p>
    {error && <p className="controls-error" role="alert">{error}</p>}
    <article className="primary-control-card ava-bot-card">
      <header><div><h2>AVA BOT</h2><p>Ava may automatically respond according to global selling permissions, each customer&apos;s permissions, and all existing safety authorities.</p></div><Toggle label="AVA BOT control" value={botOn} disabled={saving !== null} onChange={(value) => mutate("ava", () => controlsApi.setAvaBot(value))}/></header>
      <div className={`effective-status is-${state.avaBot.effective.toLowerCase()}`}>{state.avaBot.effective}</div>
      {state.avaBot.effective === "ATTENTION" && <p className="attention-message"><AlertTriangle size={15}/> Ava is not fully operational. <Link to="/business/operations">View technical details →</Link></p>}
      {saving === "ava" && <small role="status">Saving…</small>}
    </article>
    <GlobalControlCard title="CONTENT SELLING" value={state.contentSellingEnabled} inactive={!botOn} saving={saving !== null} onChange={(value) => mutate("content", () => controlsApi.setGlobalContent(value))}>Ava may sell normal content when customer permissions and existing safeguards allow it.</GlobalControlCard>
    <GlobalControlCard title="SESSION SELLING" value={state.sessionSellingEnabled} inactive={!botOn} saving={saving !== null} onChange={(value) => mutate("session", () => controlsApi.setGlobalSession(value))}>Ava may offer and progress new sessions when customer permissions and existing safeguards allow it.</GlobalControlCard>
  </section>;
}

function PermissionSummary({ label, configured, effective, reason }: { label: string; configured: boolean; effective: boolean; reason: string | null }) {
  const globallyBlocked = configured && !effective && reason?.startsWith("GLOBAL_");
  return <span className={!effective ? "permission-summary is-off" : "permission-summary"}><strong>{configured ? "ON" : "OFF"}</strong>{globallyBlocked && <small>Blocked globally</small>}<span className="sr-only">{label}</span></span>;
}

function CustomerDetail({ row, close, onUpdated }: { row: CustomerControlRow; close: () => void; onUpdated: (state: CustomerControls) => void }) {
  const { person } = row;
  const [controls, setControls] = useState(row.controls);
  const [saving, setSaving] = useState<CustomerControlName | null>(null);
  const savingRef = useRef(false);
  const [error, setError] = useState(row.error || "");
  const [pending, setPending] = useState<{ control: CustomerControlName; value: boolean } | null>(null);
  useEffect(() => { setControls(row.controls); setError(row.error || ""); }, [row]);
  const apply = (control: CustomerControlName, value: boolean) => {
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(control); setError("");
    controlsApi.setCustomer(person.personKey, control, value).then((result) => { setControls(result.state); onUpdated(result.state); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to update customer controls.")).finally(() => { savingRef.current = false; setSaving(null); setPending(null); });
  };
  const requestChange = (control: CustomerControlName, value: boolean) => {
    const sellingOff = !value && (control === "content-selling" || control === "session-selling");
    if (sellingOff && (person.activePurchaseIntent || (control === "session-selling" && person.activeSalesSession))) setPending({ control, value });
    else apply(control, value);
  };
  return <aside aria-label="Customer Controls" className="customer-controls-drawer">
    <header><div><small>Customer Controls</small><h2>{person.displayName}</h2>{person.username && <span>@{person.username}</span>}</div><button aria-label="Close Customer Controls" onClick={close} type="button"><X size={18}/></button></header>
    <div className="customer-controls-body">
      <dl className="customer-identity"><div><dt>Status</dt><dd>{humanize(person.buyerStatus || (person.isBuyer ? "BUYER" : "PROSPECT"))}</dd></div><div><dt>Identity</dt><dd>{humanize(person.identityStatus)}</dd></div><div><dt>Telegram ID</dt><dd>{person.telegramUserId}</dd></div></dl>
      <p className="controls-explainer">Global controls set the maximum permissions for everyone. Customer controls can further restrict this customer.</p>
      {!controls && !error && <div className="controls-state" role="status">Loading customer controls…</div>}
      {error && <p className="controls-error" role="alert">{error}</p>}
      {controls && <>
        <section className="customer-control-item"><div><h3>AVA AUTO</h3><p>Ava may automatically chat with this customer.</p></div><Toggle label="AVA AUTO control" value={controls.configured.avaChatEnabled} disabled={saving !== null} onChange={(value) => requestChange("ava-chat", value)}/></section>
        <section className="customer-control-item"><div><h3>CONTENT SELLING</h3><p>Controls eligibility for normal content sales.</p>{controls.configured.contentSellingEnabled && !controls.effective.contentSellingAllowed && <small>Effective: OFF · {controls.effective.contentSellingReason === "GLOBAL_CONTENT_SELLING_DISABLED" ? "Global Content Selling is off." : "Ava Auto is not currently active."}</small>}</div><Toggle label="CONTENT SELLING customer control" value={controls.configured.contentSellingEnabled} disabled={saving !== null} onChange={(value) => requestChange("content-selling", value)}/></section>
        <section className="customer-control-item"><div><h3>SESSION SELLING</h3><p>Controls eligibility for new session selling.</p>{controls.configured.sessionSellingEnabled && !controls.effective.sessionSellingAllowed && <small>Effective: OFF · {controls.effective.sessionSellingReason === "GLOBAL_SESSION_SELLING_DISABLED" ? "Global Session Selling is off." : "Ava Auto is not currently active."}</small>}</div><Toggle label="SESSION SELLING customer control" value={controls.configured.sessionSellingEnabled} disabled={saving !== null} onChange={(value) => requestChange("session-selling", value)}/></section>
        <div className="effective-behavior"><span>Effective behavior</span><strong>{effectiveMode(controls)}</strong></div>
        {saving && <p role="status">Saving authoritative state…</p>}
      </>}
      <Link className="view-conversation" to={`/business/relationships?relationship=${encodeURIComponent(person.personKey)}`}>View Conversation →</Link>
    </div>
    {pending && <div className="controls-confirm" role="dialog" aria-modal="true" aria-labelledby="selling-warning-title"><div><h3 id="selling-warning-title">Preserve existing commitments?</h3>{person.activeSalesSession && pending.control === "session-selling" && <p>The current purchased or active session is preserved. No new unpurchased session progression will be offered while disabled.</p>}{person.activePurchaseIntent && <p>The existing presented offer may still settle, but no new offers will be authorized while this selling permission is off.</p>}<footer><button onClick={() => setPending(null)} type="button">Cancel</button><button onClick={() => apply(pending.control, pending.value)} type="button">Turn Off</button></footer></div></div>}
  </aside>;
}

function CustomerControlsTab({ requestedKey }: { requestedKey: string | null }) {
  const [rows, setRows] = useState<CustomerControlRow[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(requestedKey);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<RelationshipSort>("LATEST_ACTIVITY");
  const [filter, setFilter] = useState<RelationshipFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestVersion = useRef(0);
  useEffect(() => { if (requestedKey) setSelectedKey(requestedKey); }, [requestedKey]);
  useEffect(() => {
    const version = ++requestVersion.current;
    setLoading(true); setError("");
    controlsApi.relationships(query, sort, filter).then(async (result) => {
      const loaded = await Promise.all(result.items.map(async (person): Promise<CustomerControlRow> => {
        try { return { person, controls: await controlsApi.customer(person.personKey) }; }
        catch (reason) { return { person, controls: null, error: reason instanceof Error ? reason.message : "Controls unavailable." }; }
      }));
      if (requestVersion.current === version) setRows(loaded);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load customers.")).finally(() => { if (requestVersion.current === version) setLoading(false); });
  }, [query, sort, filter]);
  const selected = rows.find((row) => row.person.personKey === selectedKey) || null;
  const updateRow = (state: CustomerControls) => setRows((current) => current.map((row) => row.person.personKey === selectedKey ? { ...row, controls: state, error: undefined } : row));
  return <section aria-label="Customer Controls" className="controls-panel customer-controls-panel">
    <p className="controls-explainer">Global controls set the maximum permissions for everyone. Customer controls can further restrict an individual customer.</p>
    <div className="customer-toolbar"><form onSubmit={(event) => { event.preventDefault(); setQuery(search.trim()); }}><Search size={15}/><input aria-label="Search customers" onChange={(event) => setSearch(event.target.value)} placeholder="Search name, username, or Telegram ID" value={search}/></form><select aria-label="Filter customers" onChange={(event) => setFilter(event.target.value as RelationshipFilter)} value={filter}><option value="ALL">All customers</option><option value="BUYERS">Buyers</option><option value="PROSPECTS">Prospects</option><option value="MANUAL">Manual</option></select><select aria-label="Sort customers" onChange={(event) => setSort(event.target.value as RelationshipSort)} value={sort}><option value="LATEST_ACTIVITY">Latest activity</option><option value="LIFETIME_SPEND">Lifetime spend</option></select></div>
    {loading && !rows.length && <div className="controls-state" role="status">Loading customer controls…</div>}
    {error && <div className="controls-state is-error" role="alert">{error}</div>}
    {!loading && !error && !rows.length && <div className="controls-state">No customers match this view.</div>}
    {!!rows.length && <div className="customer-controls-table" role="table" aria-label="Customer permission controls"><div className="customer-controls-heading" role="row"><span>CUSTOMER</span><span>AVA AUTO</span><span>CONTENT</span><span>SESSIONS</span><span>EFFECTIVE MODE</span><span/></div>{rows.map((row) => <button className="customer-controls-row" key={row.person.personKey} onClick={() => setSelectedKey(row.person.personKey)} role="row" type="button"><span><strong>{row.person.displayName}</strong>{row.person.username && <small>@{row.person.username}</small>}</span>{row.controls ? <><PermissionSummary label="Ava Auto" configured={row.controls.configured.avaChatEnabled} effective={row.controls.effective.chatAllowed} reason={row.controls.effective.chatReason}/><PermissionSummary label="Content" configured={row.controls.configured.contentSellingEnabled} effective={row.controls.effective.contentSellingAllowed} reason={row.controls.effective.contentSellingReason}/><PermissionSummary label="Sessions" configured={row.controls.configured.sessionSellingEnabled} effective={row.controls.effective.sessionSellingAllowed} reason={row.controls.effective.sessionSellingReason}/><span className="mode-label">{effectiveMode(row.controls)}</span></> : <><span>—</span><span>—</span><span>—</span><span className="is-error">Unavailable</span></>}<ChevronRight size={15}/></button>)}</div>}
    {selected && <CustomerDetail close={() => setSelectedKey(null)} onUpdated={updateRow} row={selected}/>}
  </section>;
}

export function BusinessControlsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "customers" ? "customers" : "global";
  const relationship = params.get("relationship");
  const chooseTab = (next: Tab) => {
    const updated = new URLSearchParams(params);
    updated.set("tab", next);
    if (next === "global") updated.delete("relationship");
    setParams(updated);
  };
  return <main className="business-controls-page"><header><span>BUSINESS</span><h1>Controls</h1><p>Control when Ava chats and what she is allowed to sell.</p></header><nav aria-label="Controls sections"><button aria-pressed={tab === "global"} onClick={() => chooseTab("global")} type="button">GLOBAL CONTROLS</button><button aria-pressed={tab === "customers"} onClick={() => chooseTab("customers")} type="button">CUSTOMER CONTROLS</button></nav>{tab === "global" ? <GlobalControlsTab/> : <CustomerControlsTab requestedKey={relationship}/>}</main>;
}
