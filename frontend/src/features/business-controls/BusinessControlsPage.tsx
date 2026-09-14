import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, ChevronRight, Search, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import {
  controlsApi,
  type CustomerControlRow,
  type CustomerControls,
  type CustomerInventoryFilter,
  type CustomerSnapshot,
  type CustomerSnapshotItem,
  type IntelligencePreview,
  type GlobalControls,
} from "./api";
import type { RelationshipSort } from "../relationships/api";
import "./business-controls.css";

type Tab = "global" | "customers";
type CustomerControlName = "ava-chat" | "content-selling" | "session-selling";
type DetailSection = "controls" | "identity" | "commerce" | "intelligence" | "context";

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

const money=(value:number|null)=>value==null?"—":`$${(value/100).toFixed(2)}`;
const date=(value:string|null)=>value?new Date(/^\d{4}-\d{2}-\d{2}$/.test(value)?`${value}T12:00:00`:value).toLocaleDateString(undefined,{year:"numeric",month:"short",day:"numeric"}):"—";

function IdentityWorkflow({person,onEnriched}:{person:CustomerControlRow["person"];onEnriched:(customer:any)=>void}){
  const customerId=person.localFanvueUserId; const [preview,setPreview]=useState<any>(null); const [status,setStatus]=useState<any>(null);
  const [error,setError]=useState(""); const [saving,setSaving]=useState(false); const [telegram,setTelegram]=useState<any>(null); const [x,setX]=useState<any>(null);
  const savingRef=useRef(false);
  const [selectedTelegram,setSelectedTelegram]=useState(""); const [selectedX,setSelectedX]=useState(""); const [note,setNote]=useState("");
  const [subscriberSearch,setSubscriberSearch]=useState("");const [subscriberResults,setSubscriberResults]=useState<any[]>([]);const [selectedSubscriber,setSelectedSubscriber]=useState<any>(null);
  const [workflowObservation,setWorkflowObservation]=useState<any>(null);
  const fail=(reason:unknown)=>setError(reason instanceof Error?reason.message:"Identity operation failed.");
  const loadCandidates=()=>{setError("");void Promise.all([controlsApi.telegramReadiness(),controlsApi.xObservations()]).then(([t,xs])=>{setTelegram(t);setX(xs)}).catch(fail)};
  const apply=()=>{if(!customerId||savingRef.current)return;savingRef.current=true;setSaving(true);setError("");void controlsApi.applyMetadata(customerId).then(result=>{setStatus(result);setPreview(null);if(result.customer)onEnriched(result.customer)}).catch(fail).finally(()=>{savingRef.current=false;setSaving(false)})};
  const verifyTelegram=()=>{if(!customerId||!selectedTelegram||saving)return;setSaving(true);void controlsApi.verifyTelegram(selectedTelegram,customerId,note).then(setStatus).catch(fail).finally(()=>setSaving(false))};
  const persistObservation=()=>{
    if(!selectedSubscriber||savingRef.current)return;
    savingRef.current=true;setSaving(true);setError("");
    void controlsApi.persistTelegramObservation({telegramUserId:selectedSubscriber.telegramUserId,channelId:selectedSubscriber.channelId,username:selectedSubscriber.username,displayName:selectedSubscriber.displayName,participantStatus:selectedSubscriber.participantStatus})
      .then(async persisted=>{
        const readiness=await controlsApi.telegramReadiness();
        const telegramUserId=String(persisted.telegram_user_id??selectedSubscriber.telegramUserId);
        const authoritative=(readiness.items||[]).find((item:any)=>String(item.telegramUserId)===telegramUserId);
        if(!authoritative)throw new Error("Observation committed but authoritative refresh did not return it.");
        setTelegram(readiness);setWorkflowObservation(authoritative);setSelectedTelegram(telegramUserId);
        setStatus({status:"BROADCAST_OBSERVATION_PERSISTED"});setSelectedSubscriber(null);setSubscriberResults([]);
        onEnriched(null);
      }).catch(fail).finally(()=>{savingRef.current=false;setSaving(false)});
  };
  const selectedObservation=(telegram?.items||[]).find((item:any)=>String(item.telegramUserId)===selectedTelegram);
  const displayedObservation=person.platforms.telegram!=="NOT_OBSERVED"?person.telegramObservation:workflowObservation;
  const telegramStatus=person.platforms.telegram!=="NOT_OBSERVED"?person.platforms.telegram:workflowObservation?"OBSERVED — BROADCAST":"NOT OBSERVED";
  const xCandidate=(x||[]).find((item:any)=>String(item.external_numeric_id)===selectedX);
  const xBody={localFanvueUserId:customerId,externalNumericId:selectedX,observedUsername:xCandidate?.observed_username??null,observedDisplayName:xCandidate?.observed_display_name??null,verificationNote:note};
  return <div className="identity-workflow"><h3>Platform identities</h3>
    <article><header><strong>FANVUE</strong><b>CANONICAL</b></header><p>{person.metadataComplete?(person.username?`@${person.username}`:"Observed"):"Metadata incomplete"}</p>{person.providerEvidenceAvailable&&customerId&&<button onClick={()=>controlsApi.metadataPreview(customerId).then(setPreview).catch(fail)} type="button">Preview Enrichment</button>}
      {preview&&<div className="operator-preview"><h4>CURRENT</h4><p>username: {preview.customer?.username??"—"}<br/>display name: {preview.customer?.displayName??"—"}<br/>source: {preview.customer?.source??"—"}</p><h4>PROPOSED</h4><p>username: {preview.changes?.username??preview.customer?.username??"—"}<br/>display name: {preview.changes?.display_name??preview.customer?.displayName??"—"}<br/>source: {preview.changes?.source??preview.customer?.source??"—"}</p>{Object.keys(preview.conflicts||{}).length>0&&<p role="alert">ATTENTION / CONFLICT: canonical metadata differs from provider evidence.</p>}<p>Evidence: {preview.evidence?.type??"—"}</p><button disabled={!preview.canApply||saving} onClick={apply} type="button">Apply Enrichment</button></div>}</article>
    <article><header><strong>TELEGRAM</strong><b>{telegramStatus.replaceAll("_"," ")}</b></header><p>{telegramStatus==="NOT OBSERVED"?"NOT OBSERVED":displayedObservation?.privateChatEstablished?"Private chat: Established":"Private chat: Not established"}</p>{(displayedObservation?.sources||displayedObservation?.observationSources||[]).includes("BROADCAST_MEMBER")&&<><p>Source: Broadcast Member{displayedObservation.participantStatus?` · ${displayedObservation.participantStatus}`:""}</p><p>Mapping: {person.platforms.telegram==="VERIFIED"?"Verified":"Unverified"}</p></>}<label>Find Telegram Subscriber<input aria-label="Telegram subscriber search" value={subscriberSearch} onChange={e=>setSubscriberSearch(e.target.value)}/></label><button disabled={subscriberSearch.trim().length<2||saving} onClick={()=>{setError("");controlsApi.findTelegramSubscribers(subscriberSearch).then(result=>setSubscriberResults(result.items||[])).catch(fail)}} type="button">Find Telegram Subscriber</button>{subscriberResults.map(candidate=><button key={candidate.telegramUserId} onClick={()=>setSelectedSubscriber(candidate)} type="button">Select {candidate.displayName} {candidate.username?`@${candidate.username}`:""} · {String(candidate.telegramUserId).slice(0,4)}… · Broadcast Member</button>)}{selectedSubscriber&&<button disabled={saving} onClick={persistObservation} type="button">Persist Observation</button>}</article>
    <article><header><strong>X</strong><b>{person.platforms.x.replaceAll("_"," ")}</b></header><p>{person.platforms.x==="NOT_OBSERVED"?"NOT OBSERVED — a stable numeric observation is required.":"Verified stable identity."}</p>{person.xLinkId&&<><label>Deactivation / correction reason<input value={note} onChange={e=>setNote(e.target.value)}/></label><button disabled={saving||note.trim().length<5} onClick={()=>{setSaving(true);controlsApi.deactivateX(person.xLinkId!,note).then(setStatus).catch(fail).finally(()=>setSaving(false))}} type="button">Deactivate X Link</button></>}</article>
    {customerId&&<button onClick={loadCandidates} type="button">Manage Observed Identities</button>}
    {telegram&&<section><h4>OBSERVED TELEGRAM IDENTITIES</h4><select aria-label="Observed Telegram identity" value={selectedTelegram} onChange={e=>{const value=e.target.value;setSelectedTelegram(value);if(person.platforms.telegram==="NOT_OBSERVED")setWorkflowObservation((telegram.items||[]).find((item:any)=>String(item.telegramUserId)===value)||null)}}><option value="">Select observed Telegram identity</option>{telegram.items.map((item:any)=><option key={item.telegramUserId} value={item.telegramUserId}>{item.displayName}{item.username?` · @${item.username}`:""} · {item.telegramUserIdMasked} · {item.source==="BROADCAST_SUBSCRIBER"?"Broadcast Member":"Private Chat"}</option>)}</select>{selectedObservation&&<p>Observation: {selectedObservation.source==="BROADCAST_SUBSCRIBER"?"Broadcast Member":"Private Chat"}<br/>Private chat: {selectedObservation.privateChatEstablished?"Established":"Not established"}<br/>Mapping: {selectedObservation.status==="MAPPED"?"Verified":"Unverified"}</p>}</section>}
    {x&&<section><h4>OBSERVED X IDENTITIES</h4><select aria-label="Observed X identity" value={selectedX} onChange={e=>setSelectedX(e.target.value)}><option value="">Select stable numeric observation</option>{x.map((item:any)=><option key={item.external_numeric_id} value={item.external_numeric_id}>@{item.observed_username||"unknown"} · {String(item.external_numeric_id).slice(0,4)}…</option>)}</select></section>}
    {(selectedTelegram||selectedX)&&<><label>Verification evidence<textarea value={note} onChange={e=>setNote(e.target.value)}/></label>{selectedTelegram&&<><button onClick={()=>customerId&&controlsApi.previewTelegram(selectedTelegram,customerId).then(setStatus).catch(fail)} type="button">Preview Mapping</button><button disabled={saving||note.trim().length<10} onClick={verifyTelegram} type="button">Verify Telegram Mapping</button></>}{selectedX&&<><button onClick={()=>controlsApi.previewX(xBody).then(setStatus).catch(fail)} type="button">Preview X Link</button><button disabled={saving||note.trim().length<10} onClick={()=>{setSaving(true);controlsApi.verifyX(xBody).then(setStatus).catch(fail).finally(()=>setSaving(false))}} type="button">Verify X Link</button></>}</>}
    {status&&<div className="operator-preview" role="status"><strong>Authoritative result: {status.status||status.link?.verification_method||"Verified"}{status.idempotentReplay&&" · idempotent replay"}</strong>{status.mutationPerformed===false&&<p>Preview only — no mapping changed.</p>}{status.telegramUserIdMasked&&<><h4>CANONICAL CUSTOMER</h4><p>{person.displayName}{person.username?` · @${person.username}`:""}</p><h4>TELEGRAM IDENTITY</h4><p>{status.displayName}{status.username?` · @${status.username}`:""} · {status.telegramUserIdMasked}<br/>Observation: {status.source==="BROADCAST_SUBSCRIBER"?"Broadcast Member":"Private Chat"}<br/>Private Chat Evidence: {status.privateChatEstablished?"ESTABLISHED":"NOT ESTABLISHED"}<br/>Existing Mapping: {status.existingMapping??"NONE"}<br/>Conflict: {status.conflict??"NONE"}</p></>}</div>}{error&&<p role="alert">{error}</p>}
  </div>;
}

function FactCard({fact,onChanged}:{fact:any,onChanged:()=>void}){
  const [detail,setDetail]=useState<any>(null); const [reason,setReason]=useState(""); const [replacement,setReplacement]=useState(fact.object_value||fact.object?.value||""); const silent=fact.usage_policy==="SILENT_CONTEXT"||fact.usagePolicy==="SILENT_CONTEXT";
  const correction={subjectType:fact.subject_type,subjectId:fact.subject_id,category:fact.category,relation:fact.relation,objectType:fact.object_type,objectValue:replacement,objectData:fact.object_data||{},attributes:fact.attributes||{},sourcePlatform:fact.source_platform,sourceType:fact.source_type,sourceReference:{correctionOf:fact.fact_id},verificationMethod:fact.verification_method,confidence:Number(fact.confidence),usagePolicy:fact.usage_policy,observedAt:fact.observed_at,idempotencyKey:`correction-${fact.fact_id}-${replacement.trim().toLowerCase()}`};
  return <article className="fact-card"><header><strong>{fact.object_value||fact.object?.value}</strong>{silent&&<b>SILENT</b>}</header><p>{humanize(fact.relation)}</p>{Object.entries(fact.attributes||{}).map(([key,value])=><small key={key}>{humanize(key)}: {String(value)}</small>)}<footer><span>{humanize(fact.category)} · {humanize(fact.source_type||fact.provenance?.type)}</span><button onClick={()=>controlsApi.factHistory(fact.fact_id||fact.factId).then(setDetail)} type="button">Provenance</button><button onClick={()=>setDetail({correct:true})} type="button">Correct</button><button onClick={()=>setDetail({deactivate:true})} type="button">Deactivate</button></footer>{silent&&<p>Used for understanding and continuity. Ava should not proactively repeat this fact.</p>}{detail&&<div className="operator-preview">{detail.correct?<><p>Current fact: {fact.object_value}<br/>Replacement fact:</p><input aria-label="Replacement fact" value={replacement} onChange={e=>setReplacement(e.target.value)}/></>:detail.deactivate?<p>Deactivate removes this fact from active context without deleting history.</p>:<p>Verification: {detail.verification_method}<br/>Confidence: {detail.confidence}<br/>State: {detail.state}<br/>Verified: {date(detail.verified_at)}<br/>Audit events: {detail.audit?.length??0}</p>}<label>Reason<input value={reason} onChange={e=>setReason(e.target.value)}/></label>{detail.correct&&<button disabled={reason.length<5||!replacement.trim()} onClick={()=>controlsApi.correctFact(fact.fact_id||fact.factId,correction,reason).then(onChanged)} type="button">Confirm Correction</button>}{detail.deactivate&&<button disabled={reason.length<5} onClick={()=>controlsApi.deactivateFact(fact.fact_id||fact.factId,reason).then(onChanged)} type="button">Confirm Deactivation</button>}</div>}</article>;
}

function LegacyIntelligenceWorkflow({person}:{person:CustomerControlRow["person"]}){
 const customerId=person.localFanvueUserId; const [facts,setFacts]=useState<any[]|null>(null); const [preview,setPreview]=useState<any>(null); const [error,setError]=useState("");
 const [form,setForm]=useState({subjectType:"CUSTOMER",category:"RELATIONSHIP",relation:"owns_pet",objectValue:"",attributeType:"",attributeGender:"",sourceType:"OPERATOR_VERIFIED",sourcePlatform:"CREATOR_OS",verificationMethod:"OPERATOR_VERIFIED",usagePolicy:"NORMAL_CONTEXT",evidence:""});
 const load=()=>customerId&&controlsApi.relationshipFacts(customerId).then(setFacts).catch(e=>setError(String(e)));
 useEffect(()=>{load()},[customerId]);
 const payload={subjectType:form.subjectType,subjectId:form.subjectType==="CUSTOMER"?customerId:2,category:form.category,relation:form.relation,objectType:"ENTITY",objectValue:form.objectValue,objectData:{},attributes:Object.fromEntries(Object.entries({type:form.attributeType,gender:form.attributeGender}).filter(([,v])=>v)),sourcePlatform:form.sourcePlatform,sourceType:form.sourceType,sourceReference:{operatorNote:form.evidence},verificationMethod:form.verificationMethod,confidence:1,usagePolicy:form.usagePolicy,observedAt:null,idempotencyKey:`operator-${customerId}-${form.relation}-${form.objectValue.trim().toLowerCase()}`};
 const change=(key:string,value:string)=>setForm(current=>({...current,[key]:value}));
 if(!customerId)return <p>Canonical customer required to manage intelligence.</p>;
 const customerFacts=(facts||[]).filter(f=>f.subject_type==="CUSTOMER"),creatorFacts=(facts||[]).filter(f=>f.subject_type==="CREATOR");
 return <div className="intelligence-workflow"><h3>CUSTOMER INTELLIGENCE</h3>{facts===null?<p>Loading intelligence…</p>:customerFacts.length?customerFacts.map(f=><FactCard fact={f} key={f.fact_id} onChanged={load}/>):<p>No customer intelligence recorded.</p>}<h3>RELEVANT CREATOR FACTS</h3>{creatorFacts.length?creatorFacts.map(f=><FactCard fact={f} key={f.fact_id} onChanged={load}/>):<p>No relevant creator facts recorded.</p>}
 <details><summary>Add Intelligence</summary><div className="intelligence-form"><label>Subject<select value={form.subjectType} onChange={e=>change("subjectType",e.target.value)}><option value="CUSTOMER">{person.displayName}</option><option value="CREATOR">Ava / Creator</option></select></label><label>Category<select value={form.category} onChange={e=>change("category",e.target.value)}><option value="RELATIONSHIP">Relationship</option><option value="PREFERENCE">Preference</option><option value="RECURRING_BEHAVIOR">Recurring behavior</option><option value="IDENTITY_CONTEXT">Identity context</option><option value="CREATOR_SELF">Creator self</option><option value="SILENT_CONTEXT">Silent context</option></select></label><label>Relation<select value={form.relation} onChange={e=>change("relation",e.target.value)}><option value="owns_pet">Owns pet</option><option value="prefers">Prefers</option><option value="frequently_creates">Frequently creates</option><option value="understands">Understands</option><option value="knows">Knows</option><option value="relationship_dynamic">Relationship dynamic</option></select></label><label>Object<input value={form.objectValue} onChange={e=>change("objectValue",e.target.value)}/></label><label>Type<input value={form.attributeType} onChange={e=>change("attributeType",e.target.value)}/></label><label>Gender<input value={form.attributeGender} onChange={e=>change("attributeGender",e.target.value)}/></label><label>Source<select value={form.sourceType} onChange={e=>change("sourceType",e.target.value)}><option value="OPERATOR_VERIFIED">Operator verified</option><option value="FANVUE_CONVERSATION">Fanvue conversation</option><option value="TELEGRAM_CONVERSATION">Telegram conversation</option><option value="X_OBSERVATION">X observation</option><option value="CREATOR_CANONICAL">Creator canonical</option></select></label><label>Usage<select value={form.usagePolicy} onChange={e=>change("usagePolicy",e.target.value)}><option value="NORMAL_CONTEXT">Normal Context</option><option value="SILENT_CONTEXT">Silent</option></select></label><label>Evidence / note<textarea value={form.evidence} onChange={e=>change("evidence",e.target.value)}/></label><button disabled={!form.objectValue.trim()} onClick={()=>controlsApi.previewFact(payload).then(setPreview).catch(e=>setError(String(e)))} type="button">Preview Fact</button></div></details>
 {preview&&<div className="operator-preview"><h4>WHAT WILL BE STORED</h4><p>Subject: {form.subjectType==="CUSTOMER"?person.displayName:"Ava / Creator"}<br/>Relation: {humanize(form.relation)}<br/>Object: {form.objectValue}<br/>Attributes: {[form.attributeType,form.attributeGender].filter(Boolean).join(", ")||"—"}<br/>Source: {humanize(form.sourceType)}<br/>Verification: {humanize(form.verificationMethod)}<br/>Usage: {humanize(form.usagePolicy)}</p><button onClick={()=>controlsApi.createFact(payload).then(()=>{setPreview(null);load()}).catch(e=>setError(String(e)))} type="button">Add Fact</button></div>}{error&&<p role="alert">{error}</p>}</div>;
}

void LegacyIntelligenceWorkflow;
const SNAPSHOT_TITLES:Record<string,string>={PERSONAL:"Personal",INTERESTS:"Interests",PREFERENCES:"Preferences",RELATIONSHIP_WITH_AVA:"Relationship With Ava",THINGS_TO_REMEMBER:"Things To Remember",RECENT_LEARNINGS:"Recent Learnings",SILENT_CONTEXT:"Silent Context",RELEVANT_CREATOR_FACTS:"Relevant Creator Facts"};
const snapshotSource=(value:string)=>value==="TELEGRAM_CONVERSATIONAL_MEMORY"?"Learned from Telegram":value==="CREATOR_FACT"?"Ava / Creator Fact":"Verified Intelligence";

function SnapshotItemCard({item,onChanged}:{item:CustomerSnapshotItem;onChanged:()=>void}){
 const [detail,setDetail]=useState<any>(null);const factId=item.native_reference.factId;
 const open=()=>{if(factId)controlsApi.factHistory(factId).then(setDetail);else setDetail({telegram:true})};
 return <article className="snapshot-item"><header><div><strong>{item.label}</strong><p>{item.description}</p></div><div className="snapshot-badges"><span className="snapshot-source">{snapshotSource(item.source_authority)}</span>{item.inferred&&<span className="snapshot-source">INFERRED</span>}{item.usage_policy==="SILENT_CONTEXT"&&<span className="snapshot-source">SILENT</span>}</div></header>
  {Object.entries(item.attributes||{}).filter(([,value])=>value!=null&&value!=="").map(([key,value])=><small key={key}>{humanize(key)}: {String(value)}</small>)}
  <footer><span>{item.last_observed_at?`Updated ${date(item.last_observed_at)}`:"Current"}</span><button onClick={open} type="button">Details</button></footer>
  {item.usage_policy==="SILENT_CONTEXT"&&<p className="snapshot-helper">Used quietly for understanding and continuity; Ava should not proactively repeat it.</p>}
  {detail?.telegram&&<div className="operator-preview"><p>This was learned from Telegram conversation history. Correction support is coming later.</p></div>}
  {detail&&!detail.telegram&&<FactCard fact={detail} onChanged={onChanged}/>}</article>;
}

function NaturalIntelligenceEntry({person,onAdded,onCancel}:{person:CustomerControlRow["person"];onAdded:()=>void;onCancel:()=>void}){
 const [text,setText]=useState("");const [sourceType,setSourceType]=useState("OPERATOR_VERIFIED");const [preview,setPreview]=useState<IntelligencePreview|null>(null);const [selected,setSelected]=useState<string[]>([]);const [silent,setSilent]=useState<string[]>([]);const [loading,setLoading]=useState(false);const [error,setError]=useState("");const saving=useRef(false);const customerId=person.localFanvueUserId;
 const body={customerId:customerId!,customerName:person.displayName,text,sourceType};
 const runPreview=()=>{if(!customerId||loading)return;setLoading(true);setError("");controlsApi.previewNaturalIntelligence(body).then(result=>{setPreview(result);setSelected(result.proposals.filter(item=>item.validationState==="READY").map(item=>item.proposalId));setSilent([])}).catch(reason=>setError(reason instanceof Error?reason.message:String(reason))).finally(()=>setLoading(false))};
 const apply=()=>{if(!customerId||saving.current||!selected.length)return;saving.current=true;setLoading(true);setError("");controlsApi.applyNaturalIntelligence({...body,selectedProposalIds:selected,silentProposalIds:silent.filter(id=>selected.includes(id))}).then(()=>{onAdded();onCancel()}).catch(reason=>setError(reason instanceof Error?reason.message:String(reason))).finally(()=>{saving.current=false;setLoading(false)})};
 if(!customerId)return <div className="natural-intelligence-entry"><h4>ADD SOMETHING AVA SHOULD KNOW</h4><p>Canonical customer mapping is required before manual intelligence can be added.</p><button onClick={onCancel} type="button">Cancel</button></div>;
 return <section className="natural-intelligence-entry" aria-label="Add customer intelligence"><h4>ADD SOMETHING AVA SHOULD KNOW</h4>{!preview?<><textarea aria-label="Something Ava should know" autoFocus placeholder={`${person.displayName}'s dog is Bully. She's a girl and he sometimes includes her in the AI images he makes of himself and Ava.`} value={text} onChange={event=>setText(event.target.value)}/><details><summary>More Options</summary><label>Source context<select aria-label="Source context" value={sourceType} onChange={event=>setSourceType(event.target.value)}><option value="OPERATOR_VERIFIED">Operator provided</option><option value="FANVUE_CONVERSATION">Fanvue conversation</option><option value="TELEGRAM_CONVERSATION">Telegram conversation</option><option value="X_OBSERVATION">X observation</option></select></label></details><footer><button disabled={!text.trim()||loading} onClick={runPreview} type="button">{loading?"Previewing…":"Preview"}</button><button onClick={onCancel} type="button">Cancel</button></footer></>:<><h5>I FOUND {preview.proposals.length} {preview.proposals.length===1?"FACT":"FACTS"}</h5><div className="proposal-list">{preview.proposals.map(item=>{const ready=item.validationState==="READY";const checked=selected.includes(item.proposalId);return <article className={`proposal-card is-${item.validationState.toLowerCase()}`} key={item.proposalId}><header>{ready&&<input aria-label={`Select ${item.label}`} checked={checked} onChange={()=>setSelected(current=>checked?current.filter(id=>id!==item.proposalId):[...current,item.proposalId])} type="checkbox"/>}<div><strong>{item.label}</strong><p>{item.meaning}</p></div><span>{item.validationState.replaceAll("_"," ")}</span></header><small>{item.subjectLabel} · {item.sourceLabel}</small>{item.current&&<p>Current: {item.current.label} · {Object.entries(item.current.attributes).map(([key,value])=>`${humanize(key)} ${value}`).join(", ")}<br/>Proposed: {item.meaning}</p>}{item.warnings.map(warning=><p className="proposal-warning" key={warning}>{warning}</p>)}{ready&&<label className="silent-choice"><input aria-label={`Mark ${item.label} silent`} checked={silent.includes(item.proposalId)} onChange={()=>setSilent(current=>current.includes(item.proposalId)?current.filter(id=>id!==item.proposalId):[...current,item.proposalId])} type="checkbox"/> Silent</label>}</article>})}</div><footer><button disabled={!selected.length||loading} onClick={apply} type="button">{loading?"Adding…":`Add ${selected.length} ${selected.length===1?"Fact":"Facts"}`}</button><button disabled={loading} onClick={()=>setPreview(null)} type="button">Edit</button><button disabled={loading} onClick={onCancel} type="button">Cancel</button></footer></>}{error&&<p role="alert">{error}</p>}</section>;
}

function IntelligenceWorkflow({person}:{person:CustomerControlRow["person"]}){
 const [snapshot,setSnapshot]=useState<CustomerSnapshot|null>(null);const [error,setError]=useState("");const [adding,setAdding]=useState(false);
 const load=useCallback(()=>{setError("");const key=person.localFanvueUserId?{customerId:person.localFanvueUserId}:{telegramUserId:person.telegramUserId!};controlsApi.customerSnapshot(key).then(setSnapshot).catch(e=>setError(e instanceof Error?e.message:String(e)))},[person.localFanvueUserId,person.telegramUserId]);
 useEffect(()=>{load()},[load]);const prospect=snapshot?.mapping_state==="TELEGRAM_PROSPECT_NOT_MAPPED";
 return <div className="snapshot-workflow" aria-label="Customer snapshot"><header className="snapshot-heading"><div><small>CUSTOMER SNAPSHOT</small><h3>{person.displayName}</h3>{person.username&&<span>@{person.username}</span>}<p>What Ava knows about this customer from conversations and verified relationship intelligence.</p></div>{prospect&&<span className="snapshot-unmapped">TELEGRAM PROSPECT · NOT MAPPED</span>}</header>
  {!snapshot&&!error&&<p role="status">Loading customer snapshot…</p>}
  {snapshot&&Object.keys(snapshot.sections).length===0&&<div className="snapshot-empty"><strong>No customer intelligence yet.</strong><p>Verified facts and eligible conversation learnings will appear here.</p></div>}
  {snapshot&&Object.entries(snapshot.sections).map(([section,items])=><section className="snapshot-section" key={section} aria-labelledby={`snapshot-${section}`}><h4 id={`snapshot-${section}`}>{SNAPSHOT_TITLES[section]||humanize(section)}</h4>{section==="RELEVANT_CREATOR_FACTS"&&<p className="snapshot-helper">This is about Ava and may help personalize the relationship.</p>}<div className="snapshot-grid">{items.map(item=><SnapshotItemCard item={item} key={item.item_id} onChanged={load}/>)}</div></section>)}
  {!adding&&<button className="snapshot-add" onClick={()=>setAdding(true)} type="button">+ Add Something Ava Should Know</button>}{adding&&<NaturalIntelligenceEntry person={person} onAdded={load} onCancel={()=>setAdding(false)}/>}
  {error&&<p role="alert">{error}</p>}</div>;
}

function ContextWorkflow({person,controls}:{person:CustomerControlRow["person"],controls:CustomerControls|null}){
 const [sample,setSample]=useState(""); const [result,setResult]=useState<any>(null); const [error,setError]=useState(""); const context=result?.relationshipContext;
 return <div><h3>Preview Ava Context</h3>{!person.hasConversation&&<p><strong>NO VERIFIED TELEGRAM IDENTITY</strong> — this preview does not imply that live Telegram can currently resolve this customer.</p>}<label>Sample message<textarea value={sample} onChange={e=>setSample(e.target.value)}/></label><button disabled={!person.localFanvueUserId} onClick={()=>person.localFanvueUserId&&controlsApi.contextPreview(person.localFanvueUserId,sample).then(setResult).catch(e=>setError(String(e)))} type="button">Preview Ava Context</button>{result&&<div className="context-result"><h4>IDENTITY</h4><p>Canonical customer {person.displayName}. Telegram: {person.platforms.telegram.replaceAll("_"," ")}.</p><h4>COMMERCE</h4><p>{result.commerceSummary?`${result.commerceSummary.purchaseCount} transactions · ${money(result.commerceSummary.lifetimeGrossMinor)} gross · ${money(result.commerceSummary.lifetimeNetMinor)} net`:"No canonical commerce."}</p><h4>RELATIONSHIP CONTEXT</h4>{context.facts.some((f:any)=>f.subject.type==="CUSTOMER")?context.facts.filter((f:any)=>f.subject.type==="CUSTOMER").map((f:any)=><p key={f.factId}>{f.object.value} · {humanize(f.relation)}</p>):<p>None selected.</p>}<h4>SILENT CONTEXT</h4><p>Not for proactive recitation.</p>{context.silentFacts.length?context.silentFacts.map((f:any)=><p key={f.factId}>{f.object.value}</p>):<p>None selected.</p>}<h4>CREATOR CONTEXT</h4>{context.facts.some((f:any)=>f.subject.type==="CREATOR")?context.facts.filter((f:any)=>f.subject.type==="CREATOR").map((f:any)=><p key={f.factId}>{f.object.value} · {humanize(f.relation)}</p>):<p>None selected.</p>}<h4>EXCLUDED INTELLIGENCE</h4>{context.exclusions.length?context.exclusions.map((x:any)=><p key={x.factId}>{x.factId}: {humanize(x.reason)}</p>):<p>None.</p>}<h4>EFFECTIVE CONTROLS</h4><p>{controls?effectiveMode(controls):"Telegram controls unavailable"}</p></div>}{error&&<p role="alert">{error}</p>}</div>;
}

function CommerceSummary({person}:{person:CustomerControlRow["person"]}){
 const commerce=person.commerce;const attributed=commerce.ownedAssetCount??0;const attribution=attributed>0?"ATTRIBUTED":"UNATTRIBUTED / UNRESOLVED";
 return <div className="customer-commerce-summary" aria-label="Customer commerce summary">
  <div className="commerce-metrics" aria-label="Commerce metrics">
   <article className="commerce-metric commerce-metric-primary"><span>LIFETIME GROSS</span><strong>{money(commerce.lifetimeGrossMinor)}</strong></article>
   <article className="commerce-metric"><span>CREATOR NET</span><strong>{money(commerce.lifetimeNetMinor)}</strong></article>
   <article className="commerce-metric"><span>TRANSACTIONS</span><strong>{commerce.purchaseCount}</strong></article>
  </div>
  <section className="commerce-card" aria-labelledby="purchase-history-title"><h3 id="purchase-history-title">PURCHASE HISTORY</h3><dl className="commerce-rows">
   <div><dt>First Purchase</dt><dd>{date(commerce.firstPurchaseAt)}</dd></div><div><dt>Latest Purchase</dt><dd>{date(commerce.lastPurchaseAt)}</dd></div><div><dt>Last Sync</dt><dd>{date(commerce.lastSyncedAt)}<small className="commerce-stale-warning">Provider data may be stale</small></dd></div>
  </dl></section>
  <section className="commerce-card" aria-labelledby="content-attribution-title"><h3 id="content-attribution-title">CONTENT ATTRIBUTION</h3><dl className="commerce-rows"><div><dt>Attributed Assets</dt><dd>{attributed}</dd></div><div><dt>Status</dt><dd><span className={`commerce-attribution-badge${attributed>0?" is-attributed":""}`}>{attribution}</span></dd></div></dl></section>
  <aside className="commerce-info">Verified purchases are financial evidence. Content attribution is shown only when Creator_OS can prove which asset was purchased.</aside>
 </div>;
}

function CustomerIntelligencePanel({person,controls,section,onSection,onEnriched}:{person:CustomerControlRow["person"],controls:CustomerControls|null,section:DetailSection,onSection:(section:DetailSection)=>void,onEnriched:(customer:any)=>void}){
 return <section className="customer-intelligence-panel"><nav aria-label="Customer detail sections">{(["controls","identity","commerce","intelligence","context"] as DetailSection[]).map(value=><button aria-pressed={section===value} key={value} onClick={()=>onSection(value)} type="button">{value==="context"?"CONTEXT PREVIEW":value.toUpperCase()}</button>)}</nav>
 {section==="controls"&&<p>The operational controls above remain authoritative and independent.</p>}{section==="identity"&&<IdentityWorkflow onEnriched={onEnriched} person={person}/>} {section==="commerce"&&<CommerceSummary person={person}/>} {section==="intelligence"&&<IntelligenceWorkflow person={person}/>} {section==="context"&&<ContextWorkflow controls={controls} person={person}/>}</section>;
}

function CustomerDetail({ row, close, onUpdated, onEnriched, section, onSection }: { row: CustomerControlRow; close: () => void; onUpdated: (state: CustomerControls) => void; onEnriched:(customer:any)=>void; section: DetailSection; onSection:(section:DetailSection)=>void }) {
  const { person } = row;
  const [controls, setControls] = useState(row.controls);
  const [saving, setSaving] = useState<CustomerControlName | null>(null);
  const savingRef = useRef(false);
  const [error, setError] = useState(row.error || "");
  const [pending, setPending] = useState<{ control: CustomerControlName; value: boolean } | null>(null);
  useEffect(() => {
    setControls(row.controls); setError(row.error || "");
    if (row.person.controlAvailability === "AVAILABLE" && row.person.relationshipKey && !row.controls) {
      controlsApi.customer(row.person.relationshipKey).then(setControls).catch((reason) => setError(reason instanceof Error ? reason.message : "Controls unavailable."));
    }
  }, [row]);
  const apply = (control: CustomerControlName, value: boolean) => {
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(control); setError("");
    if (!person.relationshipKey) return;
    controlsApi.setCustomer(person.relationshipKey, control, value).then((result) => { setControls(result.state); onUpdated(result.state); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to update customer controls.")).finally(() => { savingRef.current = false; setSaving(null); setPending(null); });
  };
  const requestChange = (control: CustomerControlName, value: boolean) => {
    const sellingOff = !value && (control === "content-selling" || control === "session-selling");
    if (sellingOff && (person.activePurchaseIntent || (control === "session-selling" && person.activeSalesSession))) setPending({ control, value });
    else apply(control, value);
  };
  return <aside aria-label="Customer Controls" className="customer-controls-drawer">
    <header><div><small>Customer Controls</small><h2>{person.displayName}</h2>{person.username && <span>@{person.username}</span>}</div><button aria-label="Close Customer Controls" onClick={close} type="button"><X size={18}/></button></header>
    <div className="customer-controls-body">
      {section==="controls"&&<>
      <dl className="customer-identity"><div><dt>Status</dt><dd>{humanize(person.buyerStatus || (person.isBuyer ? "BUYER" : "PROSPECT"))}</dd></div><div><dt>Identity</dt><dd>{humanize(person.identityStatus)}</dd></div><div><dt>Telegram ID</dt><dd>{person.telegramUserId}</dd></div></dl>
      <p className="controls-explainer">Global controls set the maximum permissions for everyone. Customer controls can further restrict this customer.</p>
      {person.controlAvailability === "UNAVAILABLE" && <div className="controls-state"><strong>TELEGRAM CONTROLS<br/>Not available yet</strong><span>This customer has not established a private Telegram relationship.</span></div>}
      {person.controlAvailability === "AVAILABLE" && !controls && !error && <div className="controls-state" role="status">Loading customer controls…</div>}
      {error && <p className="controls-error" role="alert">{error}</p>}
      {controls && <>
        <section className="customer-control-item"><div><h3>AVA AUTO</h3><p>Ava may automatically chat with this customer.</p></div><Toggle label="AVA AUTO control" value={controls.configured.avaChatEnabled} disabled={saving !== null} onChange={(value) => requestChange("ava-chat", value)}/></section>
        <section className="customer-control-item"><div><h3>CONTENT SELLING</h3><p>Controls eligibility for normal content sales.</p>{controls.configured.contentSellingEnabled && !controls.effective.contentSellingAllowed && <small>Effective: OFF · {controls.effective.contentSellingReason === "GLOBAL_CONTENT_SELLING_DISABLED" ? "Global Content Selling is off." : "Ava Auto is not currently active."}</small>}</div><Toggle label="CONTENT SELLING customer control" value={controls.configured.contentSellingEnabled} disabled={saving !== null} onChange={(value) => requestChange("content-selling", value)}/></section>
        <section className="customer-control-item"><div><h3>SESSION SELLING</h3><p>Controls eligibility for new session selling.</p>{controls.configured.sessionSellingEnabled && !controls.effective.sessionSellingAllowed && <small>Effective: OFF · {controls.effective.sessionSellingReason === "GLOBAL_SESSION_SELLING_DISABLED" ? "Global Session Selling is off." : "Ava Auto is not currently active."}</small>}</div><Toggle label="SESSION SELLING customer control" value={controls.configured.sessionSellingEnabled} disabled={saving !== null} onChange={(value) => requestChange("session-selling", value)}/></section>
        <div className="effective-behavior"><span>Effective behavior</span><strong>{effectiveMode(controls)}</strong></div>
        {saving && <p role="status">Saving authoritative state…</p>}
      </>}
      </>}
      <CustomerIntelligencePanel controls={controls} onEnriched={onEnriched} onSection={onSection} person={person} section={section}/>
      {person.hasConversation && person.relationshipKey && <Link className="view-conversation" to={`/business/relationships?relationship=${encodeURIComponent(person.relationshipKey)}`}>View Conversation →</Link>}
    </div>
    {pending && <div className="controls-confirm" role="dialog" aria-modal="true" aria-labelledby="selling-warning-title"><div><h3 id="selling-warning-title">Preserve existing commitments?</h3>{person.activeSalesSession && pending.control === "session-selling" && <p>The current purchased or active session is preserved. No new unpurchased session progression will be offered while disabled.</p>}{person.activePurchaseIntent && <p>The existing presented offer may still settle, but no new offers will be authorized while this selling permission is off.</p>}<footer><button onClick={() => setPending(null)} type="button">Cancel</button><button onClick={() => apply(pending.control, pending.value)} type="button">Turn Off</button></footer></div></div>}
  </aside>;
}

function CustomerControlsTab({ requestedKey, section, onSelection, onSection }: { requestedKey: string | null; section:DetailSection; onSelection:(key:string|null)=>void; onSection:(section:DetailSection)=>void }) {
  const [rows, setRows] = useState<CustomerControlRow[]>([]);
  const [selectedKey, setSelectedKey] = useState<string | null>(requestedKey);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<RelationshipSort>("LATEST_ACTIVITY");
  const [filter, setFilter] = useState<CustomerInventoryFilter>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [inventoryVersion,setInventoryVersion]=useState(0);
  const requestVersion = useRef(0);
  useEffect(() => { if (requestedKey) setSelectedKey(requestedKey); }, [requestedKey]);
  useEffect(() => {
    const version = ++requestVersion.current;
    setLoading(true); setError("");
    controlsApi.inventory(query, sort, filter).then((result) => {
      if (requestVersion.current === version) setRows(result.items.map((person) => ({ person, controls: null })));
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "Unable to load customers.")).finally(() => { if (requestVersion.current === version) setLoading(false); });
  }, [query, sort, filter, inventoryVersion]);
  const selected = rows.find((row) => row.person.personKey === selectedKey) || null;
  const updateRow = (state: CustomerControls) => setRows((current) => current.map((row) => row.person.personKey === selectedKey ? { ...row, controls: state, error: undefined } : row));
  const enrichmentApplied=(customer:any)=>{if(customer)setRows(current=>current.map(row=>row.person.personKey===selectedKey?{...row,person:{...row.person,displayName:customer.display_name||customer.username||row.person.displayName,username:customer.username??row.person.username,metadataComplete:Boolean(customer.username&&customer.display_name&&customer.source)}}:row));setInventoryVersion(value=>value+1)};
  return <section aria-label="Customer Controls" className="controls-panel customer-controls-panel">
    <p className="controls-explainer">Global controls set the maximum permissions for everyone. Customer controls can further restrict an individual customer.</p>
    <div className="customer-toolbar"><form onSubmit={(event) => { event.preventDefault(); setQuery(search.trim()); }}><Search size={15}/><input aria-label="Search customers" onChange={(event) => setSearch(event.target.value)} placeholder="Search all platform names and IDs" value={search}/></form><select aria-label="Filter customers" onChange={(event) => setFilter(event.target.value as CustomerInventoryFilter)} value={filter}><option value="ALL">All customers</option><option value="BUYERS">Buyers</option><option value="PROSPECTS">Prospects</option><option value="TELEGRAM">Telegram</option><option value="FANVUE">Fanvue</option><option value="X">X</option></select><select aria-label="Sort customers" onChange={(event) => setSort(event.target.value as RelationshipSort)} value={sort}><option value="LATEST_ACTIVITY">Latest activity</option><option value="LIFETIME_SPEND">Lifetime spend</option></select></div>
    {loading && !rows.length && <div className="controls-state" role="status">Loading customer controls…</div>}
    {error && <div className="controls-state is-error" role="alert">{error}</div>}
    {!loading && !error && !rows.length && <div className="controls-state">No customers match this view.</div>}
    {!!rows.length && <div className="customer-controls-table" role="table" aria-label="Customer permission controls"><div className="customer-controls-heading" role="row"><span>CUSTOMER</span><span>AVA AUTO</span><span>CONTENT</span><span>SESSIONS</span><span>EFFECTIVE MODE</span><span/></div>{rows.map((row) => <button className="customer-controls-row" key={row.person.personKey} onClick={() => {setSelectedKey(row.person.personKey);onSelection(row.person.personKey)}} role="row" type="button"><span><strong>{row.person.displayName}</strong>{row.person.username && <small>@{row.person.username}</small>}</span>{row.person.controls ? <><span>{row.person.controls.avaChatEnabled ? "ON" : "OFF"}</span><span>{row.person.controls.contentSellingEnabled ? "ON" : "OFF"}</span><span>{row.person.controls.sessionSellingEnabled ? "ON" : "OFF"}</span><span className="mode-label">{row.controls ? effectiveMode(row.controls) : row.person.controls.avaChatEnabled ? "AVA AUTO" : "MANUAL"}</span></> : <><span>—</span><span>—</span><span>—</span><span>Unavailable</span></>}<ChevronRight size={15}/></button>)}</div>}
    {selected && <CustomerDetail close={() => {setSelectedKey(null);onSelection(null)}} onEnriched={enrichmentApplied} onSection={onSection} onUpdated={updateRow} row={selected} section={section}/>}
  </section>;
}

export function BusinessControlsPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "customers" ? "customers" : "global";
  const relationship = params.get("relationship");
  const rawSection=params.get("section");
  const section:DetailSection=(["controls","identity","commerce","intelligence","context"] as string[]).includes(rawSection||"")?rawSection as DetailSection:"controls";
  const updateDetail=(key:string|null,nextSection:DetailSection=section)=>{const updated=new URLSearchParams(params);if(key){updated.set("tab","customers");updated.set("relationship",key);updated.set("section",nextSection)}else{updated.delete("relationship");updated.delete("section")}setParams(updated)};
  const chooseTab = (next: Tab) => {
    const updated = new URLSearchParams(params);
    updated.set("tab", next);
    if (next === "global") updated.delete("relationship");
    setParams(updated);
  };
  return <main className="business-controls-page"><header><span>BUSINESS</span><h1>Controls</h1><p>Control when Ava chats and what she is allowed to sell.</p></header><nav aria-label="Controls sections"><button aria-pressed={tab === "global"} onClick={() => chooseTab("global")} type="button">GLOBAL CONTROLS</button><button aria-pressed={tab === "customers"} onClick={() => chooseTab("customers")} type="button">CUSTOMER CONTROLS</button></nav>{tab === "global" ? <GlobalControlsTab/> : <CustomerControlsTab onSection={next=>relationship&&updateDetail(relationship,next)} onSelection={key=>updateDetail(key,"controls")} requestedKey={relationship} section={section}/>}</main>;
}
