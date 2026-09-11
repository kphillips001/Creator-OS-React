import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { PageHeader } from "../../shared/ui/PageHeader";
import type { CustomerListResponse, CustomerWorkspaceItem } from "./types";
import "./business-customers.css";

const emptyData:CustomerListResponse={items:[],summary:{total:0,buyers:0,activeSubscribers:0,formerSubscribers:0,highValue:0,activeSessions:0},total:0,page:1,pageSize:24,totalPages:1};
const labels:Record<string,string>={all:"All",buyers:"Buyers",subscribers:"Subscribers","active-sessions":"Active Sessions"};
const money=(minor:number)=>new Intl.NumberFormat("en-US",{style:"currency",currency:"USD"}).format(minor/100);
const title=(value:unknown)=>String(value||"Not available").replaceAll("_"," ").replace(/\b\w/g,letter=>letter.toUpperCase());
const subscriptionLabel=(value:string)=>({ACTIVE:"Active",CANCELED_ACCESS_REMAINING:"Canceled — Access Remaining",FORMER_EXPIRED:"Former / Expired",NONE:"None"}[value]||title(value));
const date=(value:string|null)=>value?new Intl.DateTimeFormat("en-US",{dateStyle:"medium"}).format(new Date(value)):"Not recorded";

async function read<T>(response:Response,fallback:string):Promise<T>{
  const type=response.headers.get("content-type")||"";
  const body=type.includes("application/json")?await response.json() as T&{detail?:string}:null;
  if(!response.ok)throw new Error((body as {detail?:string}|null)?.detail||fallback);
  if(!body)throw new Error(fallback);
  return body;
}

export function BusinessCustomersPage(){
  const [params,setParams]=useSearchParams();
  const initial=params.get("filter")||"all";
  const [filter,setFilter]=useState(labels[initial]?initial:"all");
  const [search,setSearch]=useState(""); const [page,setPage]=useState(1);
  const [data,setData]=useState(emptyData); const [loading,setLoading]=useState(true); const [error,setError]=useState("");
  const [selected,setSelected]=useState<CustomerWorkspaceItem|null>(null); const [detailLoading,setDetailLoading]=useState(false);
  const requestedCustomer=params.get("customer");
  const [safetyReason,setSafetyReason]=useState(""); const [safetySaving,setSafetySaving]=useState(false);
  const [abuseSaving,setAbuseSaving]=useState(false);

  useEffect(()=>{const controller=new AbortController();const query=new URLSearchParams({page:String(page),page_size:"24",filter});if(search.trim())query.set("search",search.trim());
    setLoading(true);setError("");fetch(`/api/v1/customers?${query}`,{cache:"no-store",signal:controller.signal}).then(r=>read<CustomerListResponse>(r,"Unable to load verified Customers.")).then(setData).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"Unable to load verified Customers.")}).finally(()=>{if(!controller.signal.aborted)setLoading(false)});return()=>controller.abort();},[filter,page,search]);
  const metrics=useMemo(()=>[["Total Customers",data.summary.total],["Buyers",data.summary.buyers],["Active Subscribers",data.summary.activeSubscribers],["Active Sessions",data.summary.activeSessions]] as const,[data.summary]);
  const chooseFilter=(value:string)=>{setFilter(value);setPage(1);setParams(value==="all"?{}:{filter:value},{replace:true});};
  const openDetails=async(customer:CustomerWorkspaceItem)=>{setDetailLoading(true);setError("");try{setSelected(await fetch(`/api/v1/customers/${encodeURIComponent(customer.customerId)}`,{cache:"no-store"}).then(r=>read<CustomerWorkspaceItem>(r,"Unable to load Customer details.")))}catch(reason){setError(reason instanceof Error?reason.message:"Unable to load Customer details.")}finally{setDetailLoading(false)}};
  useEffect(()=>{if(!requestedCustomer||selected||loading)return;const customer=data.items.find(item=>item.customerId===requestedCustomer);if(customer)void openDetails(customer);},[requestedCustomer,data.items,loading,selected]);
  const changeSafety=async(status:"NORMAL"|"UNDERAGE_BLOCKED")=>{if(!selected||safetyReason.trim().length<5){setError("Enter a reason for this audited safety change.");return}if(!window.confirm(status==="UNDERAGE_BLOCKED"?"Block all autonomous interaction for this customer?":"Restore autonomous interaction for this customer?"))return;setSafetySaving(true);setError("");try{setSelected(await fetch(`/api/v1/customers/${encodeURIComponent(selected.customerId)}/safety`,{method:"PUT",headers:{"content-type":"application/json"},body:JSON.stringify({safetyStatus:status,reason:safetyReason.trim()})}).then(r=>read<CustomerWorkspaceItem>(r,"Unable to update customer safety.")));setSafetyReason("")}catch(reason){setError(reason instanceof Error?reason.message:"Unable to update customer safety.")}finally{setSafetySaving(false)}};
  const resolveAbuse=async(action:"release"|"manual-block")=>{const incident=String(selected?.abuseReview?.incident_id||"");if(!incident||safetyReason.trim().length<5){setError("Enter a reason for this audited abuse-review decision.");return}setAbuseSaving(true);setError("");try{await fetch(`/api/v1/customers/abuse-reviews/${encodeURIComponent(incident)}/${action}`,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({reason:safetyReason.trim()})}).then(r=>read<Record<string,unknown>>(r,"Unable to resolve abuse review."));if(selected)await openDetails(selected);setSafetyReason("")}catch(reason){setError(reason instanceof Error?reason.message:"Unable to resolve abuse review.")}finally{setAbuseSaving(false)}};

  return <section className="business-customers-page"><PageHeader title="Customers" description="People with verified commercial history with Ava."/>
    <div className="customer-metrics">{metrics.map(([name,value])=><article key={name}><span>{name}</span><strong>{value}</strong></article>)}</div>
    <div className="customer-toolbar customer-toolbar--verified"><label className="customer-search"><Search size={16}/><span className="sr-only">Search Customers</span><input aria-label="Search Customers" placeholder="Search name, username, or mapped identity" value={search} onChange={event=>{setSearch(event.target.value);setPage(1)}}/></label><div className="customer-filters" role="group" aria-label="Customer filter">{Object.entries(labels).map(([value,label])=><button aria-pressed={filter===value} key={value} onClick={()=>chooseFilter(value)} type="button">{label}</button>)}</div></div>
    {error&&<div className="customer-state customer-state--error" role="alert"><AlertTriangle size={18}/>{error}</div>}{loading&&<div className="customer-state">Loading verified Customers…</div>}
    {!loading&&!error&&!data.items.length&&<div className="customer-state"><strong>No verified Customers found.</strong><span>Customers appear after a successful provider-backed payment.</span></div>}
    {!loading&&data.items.length>0&&<div className="customer-inventory">{data.items.map(customer=><article className="customer-row customer-row--verified" key={customer.customerId}><div className="customer-avatar">{customer.displayName.slice(0,1).toUpperCase()}</div><div className="customer-row__identity"><h2>{customer.displayName}</h2>{customer.username&&<span>@{customer.username}</span>}<div className="customer-badges">{customer.commercialStatuses.map(status=><span className="customer-badge" key={status}>{title(status)}</span>)}</div></div><div><small>Lifetime Spend</small><strong>{money(customer.totalSpendMinor)}</strong><span>{customer.transactionCount} verified transaction{customer.transactionCount===1?"":"s"}</span></div><div><small>Subscription</small><strong>{title(customer.subscriptionStatus)}</strong><span>{customer.subscriptionPeriodEnd?`Through ${date(customer.subscriptionPeriodEnd)}`:"No active subscription"}</span></div><div><small>Last Activity</small><strong>{date(customer.lastActivityAt)}</strong><span>{customer.activeSalesSession?"Active Sales Session":title(customer.retentionStatus)}</span></div><button className="customer-detail-button" disabled={detailLoading} onClick={()=>void openDetails(customer)} type="button">View details</button></article>)}</div>}
    {data.totalPages>1&&<nav className="customer-pagination"><button disabled={page<=1} onClick={()=>setPage(v=>v-1)}><ChevronLeft size={16}/>Previous</button><span>Page {data.page} of {data.totalPages}</span><button disabled={page>=data.totalPages} onClick={()=>setPage(v=>v+1)}>Next<ChevronRight size={16}/></button></nav>}
    {selected&&<aside className="customer-detail" aria-label="Customer details"><header><div><small>Verified Customer</small><h2>{selected.displayName}</h2></div><button aria-label="Close Customer details" onClick={()=>setSelected(null)}><X/></button></header><div className="customer-detail__body">
      {selected.hasTelegramRelationship&&selected.relationshipKey&&<Link className="view-conversation" to={`/business/relationships?relationship=${encodeURIComponent(selected.relationshipKey)}`}>View Conversation</Link>}
      <section className="customer-detail__section"><h3>Customer Value</h3><dl><Row label="Status" value={selected.isBuyer?"Buyer":"Customer"}/><Row label="Value tier" value={title(selected.valueTier)}/><Row label="Attention" value={selected.attentionTier?title(selected.attentionTier):"Not available"}/><Row label="Lifetime spend" value={money(selected.totalSpendMinor)}/><Row label="Verified transactions" value={selected.transactionCount}/><Row label="Retention" value={title(selected.retentionStatus)}/></dl></section>
      <section className="customer-detail__section"><h3>Subscription</h3><dl><Row label="Status" value={subscriptionLabel(selected.subscriptionStatus)}/><Row label="Period end" value={selected.subscriptionPeriodEnd?date(selected.subscriptionPeriodEnd):"Not applicable"}/></dl></section>
      <section className="customer-detail__section"><h3>Transaction History</h3>{selected.transactions?.length?<div className="transaction-history">{selected.transactions.map(item=><article key={item.transactionId}><strong>{title(item.type)}</strong><span>{money(item.grossMinor)}</span><time>{date(item.occurredAt)}</time></article>)}</div>:<p>No verified transactions found.</p>}</section>
      <section className="customer-detail__section"><h3>Commercial State</h3><dl><Row label="Active PurchaseIntent" value={selected.activePurchaseIntent?"Yes":"No"}/><Row label="Active Sales Session" value={selected.activeSalesSession?"Yes":"No"}/><Row label="Last interaction" value={date(selected.lastActivityAt)}/></dl></section>
      <section className="customer-detail__section"><h3>Ownership</h3><p>{selected.ownership?.length?`${selected.ownership.length} owned item${selected.ownership.length===1?"":"s"}.`:"No concise ownership records are available in this projection."}</p></section>
      {selected.interactionSafety&&<section className={`customer-detail__section customer-safety${selected.interactionSafety.safetyStatus==="UNDERAGE_BLOCKED"?" customer-safety--blocked":""}`}><h3>Interaction Safety</h3><strong>{selected.interactionSafety.safetyStatus==="UNDERAGE_BLOCKED"?"UNDERAGE — CHAT BLOCKED":"NORMAL"}</strong><p>{selected.interactionSafety.safetyStatus==="UNDERAGE_BLOCKED"?"All autonomous interaction is blocked. Historical records remain intact.":"No customer-specific interaction block is active."}</p><label>Required reason<input aria-label="Safety change reason" value={safetyReason} onChange={event=>setSafetyReason(event.target.value)}/></label><button disabled={safetySaving} onClick={()=>void changeSafety(selected.interactionSafety?.safetyStatus==="UNDERAGE_BLOCKED"?"NORMAL":"UNDERAGE_BLOCKED")} type="button">{selected.interactionSafety.safetyStatus==="UNDERAGE_BLOCKED"?"Restore NORMAL":"Mark UNDERAGE — BLOCKED"}</button></section>}
      {selected.abuseReview&&<section className="customer-detail__section customer-safety"><h3>Abuse Review</h3><p>An active abuse review requires operator resolution.</p><label>Required reason<input aria-label="Safety change reason" value={safetyReason} onChange={event=>setSafetyReason(event.target.value)}/></label><div className="abuse-review-actions"><button disabled={abuseSaving} onClick={()=>void resolveAbuse("release")} type="button">Release</button><button disabled={abuseSaving} onClick={()=>void resolveAbuse("manual-block")} type="button">Manual Block</button></div></section>}
    </div></aside>}
  </section>;
}
function Row({label,value}:{label:string;value:unknown}){return <div><dt>{label}</dt><dd>{String(value)}</dd></div>}
