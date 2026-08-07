import { ArrowLeft, Clapperboard, Clock3, Film, Library, Play, RotateCcw, Search, Video } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { videoGalleryApi, type VideoGalleryItem } from "../../infrastructure/api/videoGalleryApi";
import "./video-gallery.css";

const duration = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;

export function VideoGalleryPage() {
  const navigate = useNavigate(); const location = useLocation();
  const highlighted = (location.state as { generatedMediaId?: string } | null)?.generatedMediaId;
  const [items,setItems]=useState<VideoGalleryItem[]>([]); const [selected,setSelected]=useState<VideoGalleryItem|null>(null);
  const [search,setSearch]=useState(""); const [sort,setSort]=useState("newest"); const [error,setError]=useState("");
  const load=useCallback(async()=>{ const query=new URLSearchParams({sort}); if(search.trim()) query.set("search",search.trim()); const value=await videoGalleryApi.list(query); setItems(value.items); },[search,sort]);
  useEffect(()=>{ void load().catch((reason:Error)=>setError(reason.message)); },[load]);

  if(selected) return <section className="video-gallery-viewer">
    <button className="video-gallery-back" onClick={()=>setSelected(null)} type="button"><ArrowLeft/>Back to Video Gallery</button>
    <div className="video-gallery-viewer__layout"><div className="video-gallery-viewer__player"><video controls playsInline poster={selected.posterUrl} src={selected.mediaUrl}/></div>
      <aside><small>Completed video</small><h1>{selected.title}</h1>{selected.conceptSummary&&<p>{selected.conceptSummary}</p>}
        <dl><div><dt>Duration</dt><dd>{duration(selected.duration)}</dd></div><div><dt>Resolution</dt><dd>{selected.resolution}</dd></div><div><dt>Aspect ratio</dt><dd>{selected.aspectRatio}</dd></div><div><dt>Audio</dt><dd>{selected.hasAudio?"On":"Off"}</dd></div><div><dt>Model</dt><dd>{selected.providerModel}</dd></div><div><dt>Source</dt><dd>{selected.sourceLabel}</dd></div></dl>
        <div className="video-gallery-actions">{selected.extensionAvailable&&<button onClick={()=>navigate(`/studio/video?sourceType=generated_video&sourceId=${encodeURIComponent(selected.generatedMediaId)}&parentSession=${encodeURIComponent(selected.sessionId)}`)} type="button"><Video/>Extend Video</button>}
          {selected.alternateGenerationAvailable&&<button onClick={()=>navigate(`/studio/video?alternateFrom=${encodeURIComponent(selected.sessionId)}`)} type="button"><RotateCcw/>Generate Alternate</button>}
          {selected.assetState==="IN_ASSET_LIBRARY"?<Link to={`/library/assets?assetType=videos&assetId=${selected.finalAssetId}`}><Library/>In Asset Library</Link>:<span>Not in Asset Library</span>}</div>
      </aside></div>
  </section>;

  return <section className="video-gallery"><header><small>Library</small><h1>Video Gallery</h1><p>Browse and continue your completed generated videos.</p></header>
    <div className="video-gallery-toolbar"><label><Search/><input aria-label="Search videos" placeholder="Search concepts, sources, or models" value={search} onChange={(e)=>setSearch(e.target.value)}/></label><select aria-label="Sort videos" value={sort} onChange={(e)=>setSort(e.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select></div>
    {error&&<div role="alert">{error}</div>}
    {!error&&items.length===0&&<div className="video-gallery-empty"><Film/><h2>Your completed videos will appear here.</h2><p>Create your first video in Video Studio.</p><Link to="/studio/video"><Clapperboard/>Open Video Studio</Link></div>}
    <div className="video-gallery-grid">{items.map(item=><button className={item.generatedMediaId===highlighted?"video-gallery-card video-gallery-card--new":"video-gallery-card"} key={item.generatedMediaId} onClick={()=>setSelected(item)} type="button">
      <div className="video-gallery-card__poster">{item.posterUrl?<img alt="" src={item.posterUrl}/>:<Film/>}<span className="video-gallery-card__play"><Play/></span><span className="video-gallery-card__duration"><Clock3/>{duration(item.duration)}</span></div>
      <div><strong>{item.title}</strong><small>{item.providerModel}</small></div></button>)}</div>
  </section>;
}
