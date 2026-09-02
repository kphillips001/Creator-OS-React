import { Archive, ArrowUpDown, Moon, Pencil, Plus, Search, Smartphone, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { androidDeviceApi, type AndroidDeviceStatus } from "../../infrastructure/api/androidDeviceApi";
import { PageHeader } from "../../shared/ui/PageHeader";
import "../x-competitor-intelligence/x-competitor-intelligence.css";
import "./ig-competitor-intelligence.css";

type IgCompetitor = { id: string; username: string; followers: number; profileImageUrl?: string | null; archivedAt?: string | null };
type Sort = "name-asc" | "name-desc" | "followers-desc" | "followers-asc";
const number = (value: number) => new Intl.NumberFormat("en-US").format(value);

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/api/v1/ig-intelligence${path}`, init);
  const body = await response.json().catch(() => null) as (IgCompetitor & { detail?: string }) | { items: IgCompetitor[]; detail?: string } | null;
  if (!response.ok || !body) throw new Error(body?.detail || "Unable to update IG Competitor Intelligence.");
  return body;
}

export function IgCompetitorIntelligencePage() {
  const [items, setItems] = useState<IgCompetitor[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [search, setSearch] = useState(""), [sort, setSort] = useState<Sort>("followers-desc");
  const [adding, setAdding] = useState(false), [selected, setSelected] = useState<IgCompetitor | null>(null), [archivedOpen, setArchivedOpen] = useState(false);
  const [archived, setArchived] = useState<IgCompetitor[]>([]), [archivedLoading, setArchivedLoading] = useState(false);
  const [phoneStatus, setPhoneStatus] = useState<AndroidDeviceStatus | null>(null), [phoneAction, setPhoneAction] = useState<"opening"|"sleeping"|null>(null);
  const load = () => { setLoading(true); setError(""); request("/competitors").then((body) => setItems((body as { items: IgCompetitor[] }).items)).catch((reason) => setError(reason.message)).finally(() => setLoading(false)); };
  useEffect(load, []);
  useEffect(() => { let active=true; const refresh=()=>androidDeviceApi.status().then(status=>{if(active)setPhoneStatus(status);}).catch(()=>{if(active)setPhoneStatus(null);}); void refresh(); const timer=window.setInterval(()=>void refresh(),5000); return()=>{active=false;window.clearInterval(timer);}; }, []);
  const visible = useMemo(() => items.filter((item) => item.username.includes(search.trim().toLowerCase())).sort((a, b) => {
    if (sort === "followers-desc") return b.followers - a.followers;
    if (sort === "followers-asc") return a.followers - b.followers;
    const compared = a.username.localeCompare(b.username);
    return sort === "name-asc" ? compared : -compared;
  }), [items, search, sort]);
  const toggle = (field: "name" | "followers") => setSort((current) => field === "name" ? current === "name-asc" ? "name-desc" : "name-asc" : current === "followers-desc" ? "followers-asc" : "followers-desc");
  const openArchived = async () => { setArchivedOpen(true); setArchivedLoading(true); setError(""); try { setArchived(((await request("/competitors?archived=true")) as { items: IgCompetitor[] }).items); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load archived competitors."); } finally { setArchivedLoading(false); } };
  const togglePhone = async () => { if (!phoneStatus||phoneAction) return; const sleeping=phoneStatus.mirror_running; if((sleeping&&phoneStatus.state!=="CONNECTED")||(!sleeping&&!phoneStatus.mirror_available))return; setPhoneAction(sleeping?"sleeping":"opening");setError("");try{if(sleeping)await androidDeviceApi.sleep();else await androidDeviceApi.mirror();setPhoneStatus(await androidDeviceApi.status());}catch(reason){setError(reason instanceof Error?reason.message:`Unable to ${sleeping?"sleep":"open"} the Android phone.`);}finally{setPhoneAction(null);} };
  const phoneHint = !phoneStatus ? "Checking Android phone status" : phoneStatus.mirror_running ? "Turn off the phone display and close the Creator-OS mirror" : phoneStatus.mirror_available ? `Open ${[phoneStatus.manufacturer,phoneStatus.model].filter(Boolean).join(" ")||"Android phone"}` : phoneStatus.message||"Phone mirroring unavailable";
  const phoneDisabled = Boolean(phoneAction)||!phoneStatus||(phoneStatus.mirror_running?phoneStatus.state!=="CONNECTED":!phoneStatus.mirror_available);
  const phoneLabel = phoneAction==="opening"?"Opening...":phoneAction==="sleeping"?"Sleeping...":phoneStatus?.mirror_running?"Sleep":"Open Phone";
  return <section className="x-intelligence-page ig-intelligence-page">
    <PageHeader title="IG Competitor Intelligence" description="Track Instagram competitors and build durable market intelligence over time." />
    <section className="x-intelligence-card" aria-labelledby="ig-competitors-title">
      <header><div><h2 id="ig-competitors-title">Competitors</h2><p>Manual follower tracking foundation for Instagram intelligence.</p></div><button className="ig-open-phone" disabled={phoneDisabled} onClick={()=>void togglePhone()} title={phoneHint}>{phoneStatus?.mirror_running?<Moon size={15}/>:<Smartphone size={15}/>} {phoneLabel}</button></header>
      <div className="x-intelligence-toolbar"><label className="x-intelligence-toolbar__search"><Search size={16}/><input aria-label="Search competitors" placeholder="Search competitors..." value={search} onChange={(event)=>setSearch(event.target.value)}/></label><div className="x-intelligence-card__actions"><button className="x-intelligence-card__archived" onClick={()=>void openArchived()}><Archive size={15}/> Archived</button><button className="x-intelligence-card__add" onClick={()=>setAdding(true)}><Plus size={15}/> Add Competitor</button></div></div>
      {error&&<p className="x-intelligence-state x-intelligence-state--error" role="alert">{error}</p>}
      <div className="x-intelligence-table" role="table" aria-label="Tracked IG competitors">
        <div className="x-intelligence-table__header" role="row"><span role="columnheader"><button className={sort.startsWith("name")?"is-active":""} onClick={()=>toggle("name")}>Competitor <ArrowUpDown/></button></span><span role="columnheader"><button className={sort.startsWith("followers")?"is-active":""} onClick={()=>toggle("followers")}>Followers <ArrowUpDown/></button></span>{["7D Growth","30D Growth","Last Active","Posts 7D","Engagement","TG","Last Scraped","Scrape"].map(label=><span role="columnheader" key={label}>{label}</span>)}</div>
        {loading?<div className="x-intelligence-table__empty" role="row"><span role="cell">Loading competitors…</span></div>:visible.length?visible.map(item=><div className="x-intelligence-table__row" role="row" key={item.id}>
          <span className="x-intelligence-competitor" role="cell">{item.profileImageUrl?<img alt="" src={item.profileImageUrl}/>:<span className="x-intelligence-competitor__avatar">{item.username.slice(0,1).toUpperCase()}</span>}<span><button className="x-intelligence-competitor__button" onClick={()=>setSelected(item)}>@{item.username}</button></span></span>
          <span role="cell"><button className="ig-followers-edit" aria-label={`Edit followers for @${item.username}`} onClick={()=>setSelected(item)}>{number(item.followers)} <Pencil size={12}/></button></span>
          {Array.from({length:7},(_,index)=><span className="ig-placeholder" role="cell" key={index}>{index===6?"Never":"—"}</span>)}
          <span role="cell"><button className="x-intelligence-scrape" disabled title="Instagram scraping is not available yet">Scrape</button></span>
        </div>):<div className="x-intelligence-table__empty" role="row"><span role="cell"><strong>{search?"No matching competitors.":"No competitors tracked yet."}</strong></span></div>}
      </div>
    </section>
    {adding&&<CompetitorForm onClose={()=>setAdding(false)} onSaved={(item)=>{setItems(current=>[item,...current]);setAdding(false);}}/>}
    {selected&&<CompetitorDetails item={selected} onClose={()=>setSelected(null)} onUpdated={(item)=>{setItems(current=>current.map(value=>value.id===item.id?item:value));setSelected(item);}} onArchived={(id)=>{setItems(current=>current.filter(item=>item.id!==id));setSelected(null);}}/>}
    {archivedOpen&&<ArchivedDialog items={archived} loading={archivedLoading} onClose={()=>setArchivedOpen(false)} onRestore={async(id)=>{const item=await request(`/competitors/${id}/restore`,{method:"POST"}) as IgCompetitor;setArchived(current=>current.filter(value=>value.id!==id));setItems(current=>[item,...current]);}}/>}
  </section>;
}

function CompetitorForm({onClose,onSaved}:{onClose:()=>void;onSaved:(item:IgCompetitor)=>void}) { const [username,setUsername]=useState(""),[followers,setFollowers]=useState(""),[error,setError]=useState(""),[saving,setSaving]=useState(false); const save=async()=>{setSaving(true);setError("");try{onSaved(await request("/competitors",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username,followers:Number(followers)})}) as IgCompetitor);}catch(reason){setError(reason instanceof Error?reason.message:"Unable to add competitor.");}finally{setSaving(false);}}; return <div className="x-competitor-dialog-backdrop"><section className="x-competitor-dialog ig-competitor-form" role="dialog" aria-modal="true" aria-labelledby="add-ig-title"><header><div><h2 id="add-ig-title">Add IG Competitor</h2><p>Followers is the only manually maintained metric in V1.</p></div><button aria-label="Close Add IG Competitor" onClick={onClose}><X/></button></header><label>IG Username<input aria-label="IG Username" value={username} onChange={e=>setUsername(e.target.value)}/></label><label>Followers<input aria-label="Followers" min="0" type="number" value={followers} onChange={e=>setFollowers(e.target.value)}/></label>{error&&<p role="alert">{error}</p>}<footer><button onClick={onClose}>Cancel</button><button disabled={saving||!username.trim()||followers===""} onClick={()=>void save()}>{saving?"Adding…":"Add Competitor"}</button></footer></section></div>; }

function CompetitorDetails({item,onClose,onUpdated,onArchived}:{item:IgCompetitor;onClose:()=>void;onUpdated:(item:IgCompetitor)=>void;onArchived:(id:string)=>void}) { const [followers,setFollowers]=useState(String(item.followers)),[error,setError]=useState(""); const save=async()=>{try{onUpdated(await request(`/competitors/${item.id}/followers`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({followers:Number(followers)})}) as IgCompetitor);}catch(reason){setError(reason instanceof Error?reason.message:"Unable to update followers.");}}; const archive=async()=>{if(!window.confirm(`Archive @${item.username}?`))return;try{await request(`/competitors/${item.id}/archive`,{method:"POST"});onArchived(item.id);}catch(reason){setError(reason instanceof Error?reason.message:"Unable to archive competitor.");}}; return <div className="x-competitor-dialog-backdrop"><section className="x-competitor-dialog ig-competitor-form" role="dialog" aria-modal="true" aria-label={`IG competitor @${item.username}`}><header><div><h2>@{item.username}</h2></div><button aria-label="Close IG competitor" onClick={onClose}><X/></button></header><label>Followers<input aria-label="Followers" min="0" type="number" value={followers} onChange={e=>setFollowers(e.target.value)}/></label>{error&&<p role="alert">{error}</p>}<footer><button className="ig-archive-action" onClick={()=>void archive()}>Archive</button><button onClick={onClose}>Close</button><button onClick={()=>void save()}>Save Followers</button></footer></section></div>; }

function ArchivedDialog({items,loading,onClose,onRestore}:{items:IgCompetitor[];loading:boolean;onClose:()=>void;onRestore:(id:string)=>Promise<void>}) { return <div className="x-competitor-dialog-backdrop"><section className="x-competitor-dialog x-archived-competitors" role="dialog" aria-modal="true" aria-labelledby="archived-ig-title"><header><div><h2 id="archived-ig-title">Archived IG Competitors</h2><p>Archived Instagram competitors remain persisted.</p></div><button aria-label="Close Archived IG Competitors" onClick={onClose}><X/></button></header>{loading?<p>Loading archived competitors…</p>:items.length?<div className="x-archived-competitors__list">{items.map(item=><article key={item.id}><div><strong>@{item.username}</strong></div><span>{number(item.followers)} followers</span><button onClick={()=>void onRestore(item.id)}>Restore</button></article>)}</div>:<p>No archived competitors.</p>}<footer><button onClick={onClose}>Close</button></footer></section></div>; }
