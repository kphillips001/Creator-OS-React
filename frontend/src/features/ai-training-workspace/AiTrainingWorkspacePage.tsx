import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { aiTrainingControlsApi, type CustomerTrainingPlan, type CustomerTreatment, type TrainingInstruction, type TrainingWorkItem } from "../../infrastructure/api/aiTrainingControlsApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import { AiTrainingControlsPage } from "../ai-training-controls/AiTrainingControlsPage";
import { relationshipsApi, type Relationship, type RelationshipIntelligence } from "../relationships/api";
import "./ai-training-workspace.css";
import "./implementation-handoff.css";
import "./customer-training-controls.css";

type Tab = "global" | "customers" | "queue" | "history";
const tabs: Tab[] = ["global", "customers", "queue", "history"];

export function AiTrainingWorkspacePage() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab") as Tab | null;
  const tab = requested && tabs.includes(requested) ? requested : "global";
  const selectTab = (next: Tab) => {
    const updated = new URLSearchParams(params);
    updated.set("tab", next);
    if (next !== "customers") updated.delete("customer");
    setParams(updated);
  };
  return <main className="ai-training-workspace">
    <PageHeader title="AI Training" description="Refine how Ava responds globally and with individual customers." />
    <nav aria-label="AI Training sections" className="ai-training-tabs">
      {tabs.map((item) => <button aria-current={tab === item ? "page" : undefined} key={item} onClick={() => selectTab(item)} type="button">{item.toUpperCase()}</button>)}
    </nav>
    {tab === "global" && <GlobalTraining />}
    {tab === "customers" && <CustomerTraining customerKey={params.get("customer")} onSelect={(key) => { const updated = new URLSearchParams(params); updated.set("tab", "customers"); updated.set("customer", key); setParams(updated); }} />}
    {tab === "queue" && <TrainingQueue initialScope={params.get("scope") === "customer" ? "CUSTOMER" : "GLOBAL"} initialCustomer={params.get("customer") || ""} />}
    {tab === "history" && <TrainingHistory />}
  </main>;
}

function TrainingQueue({initialScope,initialCustomer}:{initialScope:"GLOBAL"|"CUSTOMER";initialCustomer:string}){
  const [items,setItems]=useState<TrainingWorkItem[]>([]);const [text,setText]=useState("");const [editing,setEditing]=useState<string|null>(null);const [expanded,setExpanded]=useState<string|null>(null);const [filter,setFilter]=useState("OPEN");const [scope,setScope]=useState<"GLOBAL"|"CUSTOMER">(initialScope);const [customer,setCustomer]=useState(initialCustomer);const [people,setPeople]=useState<Relationship[]>([]);const [error,setError]=useState("");
  const load=()=>aiTrainingControlsApi.queueList().then((value)=>setItems(value.items)).catch((reason)=>setError(reason instanceof Error?reason.message:"Unable to load Queue."));
  useEffect(()=>{load();relationshipsApi.list("","LATEST_ACTIVITY","ALL").then((value)=>setPeople(value.items)).catch(()=>undefined)},[]);
  const add=async()=>{try{if(editing)await aiTrainingControlsApi.queueEdit(editing,text);else await aiTrainingControlsApi.queueAdd(text,scope,scope==="CUSTOMER"?customer:undefined);setText("");setEditing(null);await load()}catch(reason){setError(reason instanceof Error?reason.message:"Unable to add Queue item.")}};
  const action=async(item:TrainingWorkItem,value:"analyze"|"apply"|"close")=>{try{await aiTrainingControlsApi.queueAction(item.workItemId,value);await load()}catch(reason){setError(reason instanceof Error?reason.message:"Unable to update Queue item.")}};
  const implementation=async(item:TrainingWorkItem,value:"prepare"|"start"|"detail"|"verify")=>{try{const method={prepare:aiTrainingControlsApi.implementationPrepare,start:aiTrainingControlsApi.implementationStart,detail:aiTrainingControlsApi.implementationDetail,verify:aiTrainingControlsApi.implementationVerify}[value];const next=await method(item.workItemId);setItems((current)=>current.map((entry)=>entry.workItemId===item.workItemId?next:entry));setExpanded(item.workItemId)}catch(reason){setError(reason instanceof Error?reason.message:"Unable to update implementation.")}};
  const visible=items.filter((item)=>filter==="ALL"||(filter==="OPEN"&&["TODO","READY_TO_APPLY","REQUIRES_IMPLEMENTATION","READY_FOR_IMPLEMENTATION","IMPLEMENTING","NEEDS_VERIFICATION","IMPLEMENTATION_FAILED"].includes(item.status))||(filter==="READY"&&item.status==="READY_TO_APPLY")||(filter==="REQUIRES"&&item.status.includes("IMPLEMENTATION"))||(filter==="IMPLEMENTED"&&item.status==="IMPLEMENTED")||(filter==="CLOSED"&&["CLOSED","SUPERSEDED","REJECTED"].includes(item.status)));
  return <section className="ai-training-panel"><div className="ai-training-panel-title"><div><span>QUEUE</span><h2>AI Improvement Queue</h2><p>Capture what Ava should learn or change, then analyze and launch it into training.</p></div></div>
    <div className="customer-training-editor"><label>What should Ava learn or do differently?<textarea value={text} onChange={(event)=>setText(event.target.value)}/></label><label>Scope<select disabled={Boolean(editing)} value={scope} onChange={(event)=>setScope(event.target.value as "GLOBAL"|"CUSTOMER")}><option>GLOBAL</option><option>CUSTOMER</option></select></label>{scope==="CUSTOMER"&&<label>Customer<select aria-label="Queue customer" disabled={Boolean(editing)} value={customer} onChange={(event)=>setCustomer(event.target.value)}><option value="">Select customer</option>{people.map((person)=><option key={person.personKey} value={person.personKey}>{person.displayName}</option>)}</select></label>}<button className="training-primary-action" disabled={!text.trim()||(!editing&&scope==="CUSTOMER"&&!customer)} onClick={add} type="button">{editing?"Save Queue Item":"+ New Training"}</button></div>
    {error&&<p role="alert">{error}</p>}<nav aria-label="Queue filters" className="ai-training-tabs">{([['OPEN','Open'],['ALL','All'],['READY','Ready'],['REQUIRES','Requires Implementation'],['IMPLEMENTED','Implemented'],['CLOSED','Closed']] as const).map(([value,label])=><button aria-current={filter===value?"page":undefined} key={value} onClick={()=>setFilter(value)} type="button">{label}</button>)}</nav>
    <div className="training-history-list">{visible.map((item)=><article key={item.workItemId}><div><span>{item.scope}</span><span>{queueLabel(item.status)}</span>{item.classification&&<span>{item.classification.replaceAll("_"," ")}</span>}</div><strong>{item.originalRequestText}</strong>{item.scope==="CUSTOMER"&&<small>Customer: {people.find((person)=>person.personKey===item.analysis.customerProjectionKey)?.displayName||String(item.analysis.customerProjectionKey||"Canonical customer")}</small>}{item.classificationRationale&&<p>{item.classificationRationale}</p>}<small>Updated {new Date(item.updatedAt).toLocaleString()}</small>{item.linkedInstructionId&&<><small>Destination: {item.scope==="GLOBAL"?"Global Training":"Customer Training"}</small><Link to={item.scope==="GLOBAL"?`?tab=global#training-${item.linkedInstructionId}`:`?tab=customers&customer=${encodeURIComponent(String(item.analysis.customerProjectionKey||""))}`}>View Training</Link></>}{expanded===item.workItemId&&<ImplementationDetail item={item}/>}<div>{item.status==="TODO"&&<><button onClick={()=>{setEditing(item.workItemId);setText(item.originalRequestText);setScope(item.scope)}} type="button">Edit</button><button onClick={()=>action(item,"analyze")} type="button">Analyze</button></>}{item.status==="READY_TO_APPLY"&&<button onClick={()=>action(item,"apply")} type="button">Launch Training</button>}{item.status==="REQUIRES_IMPLEMENTATION"&&<button onClick={()=>implementation(item,"prepare")} type="button">Prepare Implementation</button>}{item.status==="READY_FOR_IMPLEMENTATION"&&<><button onClick={()=>implementation(item,"detail")} type="button">Review Plan</button><button onClick={()=>implementation(item,"start")} type="button">Approve &amp; Start Implementation</button></>}{item.status==="IMPLEMENTING"&&<button onClick={()=>implementation(item,"detail")} type="button">View Job</button>}{item.status==="NEEDS_VERIFICATION"&&<><button onClick={()=>implementation(item,"detail")} type="button">Review Result</button><button onClick={()=>implementation(item,"verify")} type="button">Verify Implementation</button></>}{item.status==="IMPLEMENTATION_FAILED"&&<><button onClick={()=>implementation(item,"detail")} type="button">Review Failure</button><button onClick={()=>implementation(item,"prepare")} type="button">Prepare Retry</button></>}{item.status==="IMPLEMENTED"&&<button onClick={()=>implementation(item,"detail")} type="button">View Implementation</button>}{!["CLOSED","SUPERSEDED","IMPLEMENTING"].includes(item.status)&&<button onClick={()=>action(item,"close")} type="button">Close</button>}</div></article>)}</div>
  </section>;
}
const queueLabel=(status:string)=>({TODO:"TODO",READY_TO_APPLY:"READY TO APPLY",REQUIRES_IMPLEMENTATION:"REQUIRES IMPLEMENTATION",READY_FOR_IMPLEMENTATION:"READY FOR IMPLEMENTATION",IMPLEMENTING:"IMPLEMENTING",NEEDS_VERIFICATION:"NEEDS VERIFICATION",IMPLEMENTATION_FAILED:"IMPLEMENTATION FAILED",IMPLEMENTED:"IMPLEMENTED",REJECTED:"REJECTED",CLOSED:"CLOSED",SUPERSEDED:"SUPERSEDED"}[status]||status);

function ImplementationDetail({item}:{item:TrainingWorkItem}) {
  const brief=(item.implementation?.brief||item.analysis.implementationBrief) as import("../../infrastructure/api/aiTrainingControlsApi").ImplementationBrief|undefined;
  const execution=item.implementation?.execution;
  if(!brief)return <aside className="implementation-detail">Implementation details are not loaded.</aside>;
  return <aside className="implementation-detail">
    <h3>Implementation Review</h3>
    {item.status==="NEEDS_VERIFICATION"&&<p className="implementation-verification-notice">Implementation completed. Verification required.</p>}
    <h4>Request</h4><p>{brief.request}</p>
    <h4>Why Implementation Is Required</h4><p>{brief.whyImplementationIsRequired}</p>
    <h4>Implementation Plan</h4><p>{brief.desiredBehavior}</p>
    <h4>Acceptance Criteria</h4><ul>{brief.acceptanceCriteria.map((value)=><li key={value}>{value}</li>)}</ul>
    <h4>Protected Boundaries</h4><ul>{brief.protectedAuthorities.map((value)=><li key={value}>{value}</li>)}</ul>
    <h4>Proposed Verification</h4><ul>{brief.proposedVerification.map((value)=><li key={value}>{value}</li>)}</ul>
    {item.status==="IMPLEMENTATION_FAILED"&&<section className="implementation-failure" aria-label="Implementation failure"><h4>Failure</h4><p>{execution?.failure_reason||"Failure details unavailable."}</p></section>}
    {execution?.final_report&&<ResultEvidence report={execution.final_report}/>}
    <h4>Execution</h4><p>{execution?`${execution.status} · ${execution.execution_id}`:`Awaiting explicit approval · ${brief.repository} · ${brief.branch}`}</p>
    {execution?.completed_at&&<p>Completed {new Date(execution.completed_at).toLocaleString()}</p>}
    {execution&&<Link state={{developerExecutionId:execution.execution_id}} to="/agents/developer">View Job</Link>}
    {!!item.implementation?.attempts?.length&&<ImplementationAttempts attempts={item.implementation.attempts}/>}
  </aside>;
}

function ImplementationAttempts({attempts}:{attempts:import("../../infrastructure/api/aiTrainingControlsApi").ImplementationAttempt[]}) {
  return <details className="implementation-attempts"><summary>Implementation Attempts ({attempts.length})</summary>
    <div>{attempts.map((attempt)=><article className={attempt.isCurrent?"current":""} key={attempt.attemptId}>
      <strong>Attempt {attempt.attemptNumber} · {attempt.status.replaceAll("_"," ")}</strong>
      {attempt.isCurrent&&<span>Current</span>}<small>Brief v{attempt.briefVersion}</small>
      <small>Task: {attempt.taskId}</small><small>Execution: {attempt.executionId||"Not started"}</small>
      {attempt.completedAt&&<small>Completed: {new Date(attempt.completedAt).toLocaleString()}</small>}
      {attempt.verifiedAt&&<small>Verified: {new Date(attempt.verifiedAt).toLocaleString()}</small>}
      {attempt.execution?.failure_reason&&<p><strong>Failure:</strong> {attempt.execution.failure_reason}</p>}
      {attempt.execution?.final_report&&<details><summary>View Result</summary><ResultEvidence report={attempt.execution.final_report}/></details>}
      {attempt.executionId&&<Link state={{developerExecutionId:attempt.executionId}} to="/agents/developer">View Job</Link>}
    </article>)}</div>
  </details>;
}

function ResultEvidence({report}:{report:Record<string,unknown>}) {
  const asList=(value:unknown):unknown[]=>Array.isArray(value)?value:[];
  const files=asList(report.filesModified||report.files_changed).map(String);
  const tests=asList(report.tests);
  const warnings=asList(report.remainingWarnings||report.warnings).map(String);
  const validation=(report.validation&&typeof report.validation==="object"?report.validation:{}) as Record<string,unknown>;
  const migrationRequired=report.migration_required??report.migrationRequired;
  const migrationApplied=report.migration_applied??report.databaseMigrationsApplied;
  const schema=report.schema_certification??validation.schemaCertification;
  return <section className="implementation-result" aria-label="Implementation result">
    <h4>Implementation Summary</h4><p>{String(report.summary||"Implementation summary unavailable.")}</p>
    <h4>Files Changed</h4>{files.length?<ul>{files.map((value,index)=><li key={`${value}-${index}`}>{value}</li>)}</ul>:<p>Files changed information unavailable.</p>}
    <h4>Tests &amp; Checks</h4>{tests.length?<ul>{tests.map((value,index)=><li key={index}>{resultLabel(value)}</li>)}</ul>:<p>Test results unavailable.</p>}
    <CheckRow label="TypeScript typecheck" value={report.typecheck??validation.typecheck}/>
    <CheckRow label="Production build" value={report.build??validation.build}/>
    <CheckRow label="Python compilation" value={report.python_compilation??validation.pythonCompilation}/>
    <CheckRow label="git diff --check" value={validation.gitDiffCheck}/>
    {warnings.length>0&&<><h4>Warnings</h4><ul className="implementation-warnings">{warnings.map((value,index)=><li key={`${value}-${index}`}>{value}</li>)}</ul></>}
    {(migrationRequired!==undefined||migrationApplied!==undefined||schema!==undefined)&&<><h4>Migration</h4><CheckRow label="Migration required" value={migrationRequired}/><CheckRow label="Migration applied" value={migrationApplied}/><CheckRow label="Schema certification" value={schema}/></>}
  </section>;
}

function CheckRow({label,value}:{label:string;value:unknown}){return <p className={`implementation-check ${checkState(value).toLowerCase()}`}><strong>{label}:</strong> {checkState(value)}</p>}
function checkState(value:unknown){if(value===undefined||value===null||value==="")return "UNKNOWN";if(typeof value==="boolean")return value?"PASS":"FAIL";if(typeof value==="object"){const record=value as Record<string,unknown>;if(typeof record.exitCode==="number")return record.exitCode===0?"PASS":"FAIL";return String(record.status||record.result||"UNKNOWN").toUpperCase()}return String(value).toUpperCase()}
function resultLabel(value:unknown){if(typeof value!=="object"||value===null)return String(value);const record=value as Record<string,unknown>;return [record.name||record.command||"Check",record.status||record.result,record.count||record.detail].filter(Boolean).join(" — ")}

function GlobalTraining() {
  return <section className="ai-training-panel">
    <div className="ai-training-panel-title"><div><span>GLOBAL</span><h2>Global Training</h2><p>Train account-wide conversation behavior through the existing Ava Rules authority.</p></div><Link to="/agents/ai-training">Advanced Rule Details</Link></div>
    <aside className="training-truth-warning">Changing inventory, availability, price, ownership, and settlement remain canonical business truth. A conversation rule does not create or replace those authorities.</aside>
    <AiTrainingControlsPage workspace />
  </section>;
}

function CustomerTraining({ customerKey, onSelect }: { customerKey: string | null; onSelect: (key: string) => void }) {
  const [search, setSearch] = useState("");
  const [people, setPeople] = useState<Relationship[]>([]);
  const [selected, setSelected] = useState<Relationship | null>(null);
  const [intelligence, setIntelligence] = useState<RelationshipIntelligence | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { const controller = new AbortController(); relationshipsApi.list(search, "LATEST_ACTIVITY", "ALL", null, controller.signal).then((result) => setPeople(result.items)).catch((reason) => { if (reason?.name !== "AbortError") setError(reason instanceof Error ? reason.message : "Unable to load customers."); }); return () => controller.abort(); }, [search]);
  useEffect(() => { if (!customerKey) return; const controller = new AbortController(); relationshipsApi.intelligence(customerKey, controller.signal).then((result) => { setSelected(result.person); setIntelligence(result); }).catch((reason) => { if (reason?.name !== "AbortError") setError(reason instanceof Error ? reason.message : "Unable to resolve customer identity."); }); return () => controller.abort(); }, [customerKey]);
  useEffect(() => { if (!selected) { setIntelligence(null); return; } if (intelligence?.person.personKey === selected.personKey) return; const controller = new AbortController(); relationshipsApi.intelligence(selected.personKey, controller.signal).then(setIntelligence).catch((reason) => { if (reason?.name !== "AbortError") setError(reason instanceof Error ? reason.message : "Unable to load customer facts."); }); return () => controller.abort(); }, [selected, intelligence]);
  const facts = intelligence?.relationshipIntelligence;
  return <section className="customer-training-layout" aria-label="Customer Training"><p className="customer-training-purpose">View and manage how Ava is trained to respond to individual customers. New customer training starts through Queue.</p>
    <aside className="customer-training-list"><label>Find a customer<input aria-label="Search customers" onChange={(event) => setSearch(event.target.value)} placeholder="Name, Telegram username, or identity" value={search} /></label>{people.map((person) => <button aria-pressed={selected?.personKey === person.personKey} key={person.personKey} onClick={() => { setSelected(person); onSelect(person.personKey); }} type="button"><strong>{person.displayName}</strong>{person.username && <span>@{person.username}</span>}<small>{person.identityStatus.replaceAll("_", " ")} · {person.isBuyer ? "Buyer" : "Prospect"}</small></button>)}</aside>
    <div className="customer-training-detail">{error && <p role="alert">{error}</p>}{!selected ? <div className="customer-training-empty">Select a customer to review training context.</div> : <><header><div><span>CUSTOMER</span><h2>{selected.displayName}</h2>{selected.username && <p>@{selected.username}</p>}</div><div><strong>{selected.identityStatus.replaceAll("_", " ")}</strong><small>Canonical identity: {selected.personKey}</small></div></header>
      <section><h3>Known Facts</h3><p>Read-only customer memory and relationship intelligence. These facts are not training instructions.</p><dl><Fact label="Location" value={facts?.location} /><Fact label="Timezone" value={facts?.timezone} /><Fact label="Interests" value={facts?.interests?.join(", ")} /><Fact label="Pets" value={facts?.pets?.join(", ")} /><Fact label="Music" value={facts?.music?.join(", ")} /><Fact label="Preferences" value={facts?.preferences?.join(", ")} /></dl></section>
      <CustomerBehavior customer={selected} />
    </>}</div>
  </section>;
}

function CustomerBehavior({ customer }: { customer: Relationship }) {
  const [items, setItems] = useState<TrainingInstruction[]>([]);
  const [eligible, setEligible] = useState(false);
  const [reason, setReason] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [priority, setPriority] = useState(100);
  const [preview, setPreview] = useState<CustomerTrainingPlan | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState("");
  const reload = () => aiTrainingControlsApi.customerList(customer.personKey).then((result) => {
    setItems(result.items); setEligible(result.eligible); setReason(result.eligibilityReason);
  }).catch((failure) => setError(failure instanceof Error ? failure.message : "Unable to load customer training."));
  useEffect(() => { setDraft(""); setPreview(null); setEditing(null); setError(""); reload(); }, [customer.personKey]);
  const review = async () => { setError(""); try { setPreview(await aiTrainingControlsApi.customerAnalyze(customer.personKey,draft)); } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to analyze training."); } };
  const activate = async () => { if(!preview)return; setError(""); try {
    if(editing){await aiTrainingControlsApi.customerEdit(customer.personKey,editing,preview.conversationGuidance[0]||draft,priority);await aiTrainingControlsApi.treatmentApply(customer.personKey,preview.treatment);}
    else await aiTrainingControlsApi.customerApplyPlan(customer.personKey,preview);
    setDraft(""); setPreview(null); setEditing(null); await reload();
  } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to save customer training."); } };
  const transition = async (item: TrainingInstruction, action: "enable" | "disable" | "archive") => { setError(""); try { await aiTrainingControlsApi.customerTransition(customer.personKey, item.instructionId, action); await reload(); } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to update customer training."); } };
  const guidanceItems=items.filter((item)=>item.instructionType!=="CUSTOMER_TREATMENT_POLICY"&&item.status!=="ARCHIVED");
  return <section><div className="customer-behavior-heading"><h3>How Ava Should Behave</h3><span>CUSTOMER</span></div>
    <p>Use natural language first. Ava separates conversational guidance from bounded treatment preferences for review.</p>
    {!eligible && <aside className="training-truth-warning">{reason || "A verified customer identity is required before training can be activated."}</aside>}
    {error && <p role="alert">{error}</p>}
    {eligible && editing && <div className="customer-training-editor"><label>Edit existing customer training<textarea value={draft} onChange={(event) => { setDraft(event.target.value); setPreview(null); }} /></label><button disabled={!draft.trim()} onClick={review} type="button">Analyze Changes</button></div>}
    {preview && <div className="customer-training-preview"><span>TRAINING FOR</span><h4>{customer.displayName}</h4>{preview.supported?<><Fact label="Conversation" value={preview.conversationGuidance.join(" ")||"Use existing conversational style"}/><Fact label="Sales Approach" value={preview.treatment.sales_pressure==="REDUCED"?"Reduced pressure":preview.treatment.sales_pressure==="INCREASED"?"Increased pressure":"Normal"}/><Fact label="Free Engagement" value={preview.treatment.free_engagement.replaceAll("_"," ")}/><Fact label="Response Style" value={preview.treatment.response_length==="SHORTER"?"Shorter":preview.treatment.response_length==="LONGER"?"Longer":"Normal"}/><p><strong>Protected authorities:</strong> Safety, pricing, ownership, inventory, settlement and fulfillment remain unchanged.</p><CustomerTreatmentControls customer={customer} pending={preview.treatment} onPending={(treatment)=>setPreview({...preview,treatment})}/><button onClick={activate} type="button">Apply Training</button></>:<><p role="alert">{preview.explanation}</p><p>No override is available for this protected authority.</p></>}</div>}
    <div className="customer-training-rules">{guidanceItems.map((item) => <article key={item.instructionId}><div><span>CUSTOMER</span><span>{item.status}</span><span>v{item.version}</span><span>Priority {item.priority}</span></div>{item.implementationStatus&&<b>{item.implementationStatus.implemented?"✓ ":""}{item.implementationStatus.label}</b>}<strong>{item.normalizedInstruction}</strong><time>{new Date(item.updatedAt).toLocaleString()}</time><div><button onClick={() => { setEditing(item.instructionId); setDraft(item.originalOperatorText); setPriority(item.priority); setPreview(null); }} type="button">Edit</button>{item.status === "ENABLED" ? <button onClick={() => transition(item, "disable")} type="button">Disable</button> : <button onClick={() => transition(item, "enable")} type="button">Enable</button>}<button onClick={() => transition(item, "archive")} type="button">Archive</button></div></article>)}</div>
    {eligible && guidanceItems.length === 0 && <div className="customer-training-coming"><strong>No active customer training</strong><p>Use the Queue to create new customer training.</p></div>}
    {!preview&&<CustomerTreatmentControls customer={customer} />}
  </section>;
}

const treatmentDefaults: CustomerTreatment = { sales_pressure:"NORMAL", free_engagement:"NORMAL", response_length:"NORMAL" };
function CustomerTreatmentControls({ customer,pending,onPending }: { customer: Relationship;pending?:CustomerTreatment;onPending?:(value:CustomerTreatment)=>void }) {
  const [saved, setSaved] = useState<CustomerTreatment>(treatmentDefaults);
  const [draft, setDraft] = useState<CustomerTreatment>(treatmentDefaults);
  const [eligible, setEligible] = useState(false);
  const [usingDefaults, setUsingDefaults] = useState(true);
  const [item, setItem] = useState<TrainingInstruction|null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setReviewed(false); setError(""); aiTrainingControlsApi.treatmentGet(customer.personKey).then((result) => { const configuration=result.configuration||treatmentDefaults; setSaved(configuration); setDraft(pending||configuration); setEligible(Boolean(result.eligible)); setUsingDefaults(result.usingAvaDefaults!==false); setItem(result.item||null); }).catch((failure) => setError(failure instanceof Error ? failure.message : "Unable to load customer treatment.")); }, [customer.personKey]);
  useEffect(()=>{if(pending)setDraft(pending)},[pending]);
  const choose = (key:keyof CustomerTreatment,value:string) => { const next=({...draft,[key]:value}) as CustomerTreatment;setDraft(next);onPending?.(next);setReviewed(false); };
  const review = async () => { try { await aiTrainingControlsApi.treatmentPreview(draft); setReviewed(true); setError(""); } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to review treatment."); } };
  const apply = async () => { try { const result=await aiTrainingControlsApi.treatmentApply(customer.personKey,draft); setSaved(result.configuration); setDraft(result.configuration); setUsingDefaults(result.usingAvaDefaults); setItem(result.item); setReviewed(false); setError(""); } catch (failure) { setError(failure instanceof Error ? failure.message : "Unable to apply treatment."); } };
  const changed=JSON.stringify(saved)!==JSON.stringify(draft);
  return <details className="customer-treatment"><summary>Advanced Treatment Controls</summary><div className="customer-behavior-heading"><h4>Customer Treatment</h4><span>{usingDefaults?"Using Ava defaults":item?.implementationStatus?.label||item?.status||"CUSTOMER"}</span></div>
    <p>Fine tune, inspect, or correct the pending interpretation. Changes do not persist until reviewed and applied.</p>
    {error&&<p role="alert">{error}</p>}
    <TreatmentChoice label="Sales Pressure" help="How assertively Ava should pursue discretionary sales opportunities." value={draft.sales_pressure} options={["REDUCED","NORMAL","INCREASED"]} onChange={(value)=>choose("sales_pressure",value)} disabled={!eligible}/>
    <TreatmentChoice label="Free Engagement" help="How much discretionary free conversation Ava should invest." value={draft.free_engagement} options={["MORE_LIMITED","NORMAL","MORE_FLEXIBLE"]} onChange={(value)=>choose("free_engagement",value)} disabled={!eligible}/>
    <TreatmentChoice label="Response Length" help="How concise or detailed Ava should generally be." value={draft.response_length} options={["SHORTER","NORMAL","LONGER"]} onChange={(value)=>choose("response_length",value)} disabled={!eligible}/>
    {!eligible&&<p>A verified customer identity is required before treatment can be applied.</p>}
    {eligible&&!pending&&<button disabled={!changed} onClick={review} type="button">Review Changes</button>}
    {reviewed&&<div className="customer-treatment-review"><span>CUSTOMER</span><strong>{customer.displayName}</strong><Fact label="Sales Pressure" value={draft.sales_pressure.replaceAll("_"," ")} /><Fact label="Free Engagement" value={draft.free_engagement.replaceAll("_"," ")} /><Fact label="Response Length" value={draft.response_length} /><p><strong>Protected authorities:</strong> Safety, pricing, ownership, inventory, settlement, fulfillment, and Sales Brain authorization remain unchanged.</p><button onClick={apply} type="button">Apply Treatment</button></div>}
  </details>;
}

const treatmentHelp:Record<string,string>={REDUCED:"Ava gives this customer more conversational room before pursuing marginal sales opportunities. Direct buying requests are still handled normally.",INCREASED:"Ava may lean more commercial when a legitimate opportunity already exists. This never forces an offer or bypasses sales protections.",MORE_LIMITED:"Ava spends less time on optional free conversation.",MORE_FLEXIBLE:"Ava may invest somewhat more in relationship-building where global limits allow.",SHORTER:"Prefer concise, natural replies.",LONGER:"Allow somewhat more detail when appropriate."};
function TreatmentChoice({label,help,value,options,onChange,disabled}:{label:string;help:string;value:string;options:string[];onChange:(value:string)=>void;disabled:boolean}) { const explanation=value==="NORMAL"?(label==="Sales Pressure"?"Use Ava's standard Sales Brain behavior.":label==="Free Engagement"?"Use Ava's standard free-engagement limits.":"Use Ava's standard concise response style."):treatmentHelp[value];return <fieldset className="treatment-choice" disabled={disabled}><legend>{label}</legend><p>{help}</p><div>{options.map((option)=><button aria-pressed={value===option} key={option} onClick={()=>onChange(option)} type="button">{option.replaceAll("_"," ")}</button>)}</div><small>{explanation}</small></fieldset>; }

function Fact({ label, value }: { label: string; value?: string | null }) { return <div><dt>{label}</dt><dd>{value || "—"}</dd></div>; }

function TrainingHistory() {
  const [rules, setRules] = useState<TrainingInstruction[]>([]);
  const [filter, setFilter] = useState<"ALL" | "GLOBAL" | "CUSTOMER">("ALL");
  const [error, setError] = useState("");
  useEffect(() => { aiTrainingControlsApi.historyView().then((result)=>setRules(result.items)).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load training history.")); }, []);
  const rows = useMemo(() => rules.filter((rule) => filter === "ALL" || (rule.scope || "GLOBAL") === filter).map((rule)=>({rule,revision:{action:"CURRENT STATE",enforcement_mode:rule.enforcementMode,priority:rule.priority,normalized_instruction:rule.normalizedInstruction,status:rule.implementationStatus?.label||rule.status,version:rule.version,created_at:rule.updatedAt}})), [rules, filter]);
  return <section className="ai-training-panel"><div className="ai-training-panel-title"><div><span>HISTORY</span><h2>Training History</h2><p>Versioned lifecycle evidence from the canonical Ava Rules authority.</p></div></div><nav aria-label="Training history scope" className="ai-training-tabs">{(["ALL", "GLOBAL", "CUSTOMER"] as const).map((value) => <button aria-current={filter === value ? "page" : undefined} key={value} onClick={() => setFilter(value)} type="button">{value}</button>)}</nav>{error && <p role="alert">{error}</p>}<div className="training-history-list">{rows.map(({ rule, revision }) => <article key={`${rule.instructionId}-${revision.version}`}><div><span>{rule.scope || "GLOBAL"}</span>{rule.instructionType === "CUSTOMER_TREATMENT_POLICY" && <span>Customer Treatment</span>}<span>{revision.action}</span><span>{revision.enforcement_mode || rule.enforcementMode}</span><span>Priority {revision.priority}</span></div>{rule.scope === "CUSTOMER" && <small>Customer #{rule.customerFanvueUserId}</small>}<strong>{revision.normalized_instruction}</strong><p>{revision.status} · v{revision.version}</p><time>{new Date(revision.created_at).toLocaleString()}</time></article>)}</div>{rules.length > 0 && rows.length === 0 && <p>No training history in this scope.</p>}</section>;
}
