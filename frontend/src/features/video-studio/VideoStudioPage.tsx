import { Check, ChevronRight, Clapperboard, Clock3, Film, ImagePlus, Library, Play, RotateCcw, Sparkles, Upload, Video } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { PageHeader } from "../../shared/ui/PageHeader";
import { useBackgroundOperations } from "../background-operations/BackgroundOperationsContext";
import { uploadEditStudioReference } from "../../infrastructure/api/editStudioApi";
import { videoStudioApi } from "../../infrastructure/api/videoStudioApi";
import type { VideoConcept, VideoProvider, VideoSession, VideoSettings, VideoSource } from "./types";
import "./video-studio.css";

const defaultSettings: VideoSettings = { desired_runtime: 15, aspect_ratio: "9:16", resolution: "720p", generate_audio: true, video_provider: "wavespeed_seedance_2_0" };
const title = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const sessionConcepts = (session: VideoSession | null) => session?.concept_batches.at(-1)?.concepts ?? [];

function sourceFromQuery(params: URLSearchParams): VideoSource | null {
  const type = params.get("sourceType") as VideoSource["type"] | null;
  const id = params.get("sourceId");
  return type && id ? { type, id, previewUrl: params.get("preview") || undefined, label: params.get("label") || undefined, context: params.get("context") || undefined } : null;
}

export function VideoStudioPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const operations = useBackgroundOperations();
  const [source, setSource] = useState<VideoSource | null>(() => sourceFromQuery(params));
  const [settings, setSettings] = useState(defaultSettings);
  const [providers, setProviders] = useState<VideoProvider[]>([]);
  const [session, setSession] = useState<VideoSession | null>(null);
  const [history, setHistory] = useState<VideoSession[]>([]);
  const [ideaOpen, setIdeaOpen] = useState(false);
  const [idea, setIdea] = useState("");
  const [busyStage, setBusyStage] = useState("");
  const [error, setError] = useState("");
  const [operationId, setOperationId] = useState<string | null>(null);
  const [extensionOpen, setExtensionOpen] = useState(false);
  const [extensionRuntime, setExtensionRuntime] = useState(15);

  const reloadHistory = useCallback(async () => {
    const value = await videoStudioApi.sessions(); setHistory(value.sessions);
  }, []);
  useEffect(() => { void videoStudioApi.providers().then((value) => setProviders(value.providers)).catch(() => setProviders([])); void reloadHistory(); }, [reloadHistory]);
  useEffect(() => {
    const id = params.get("session");
    if (!id) return;
    void videoStudioApi.session(id).then((value) => { setSession(value); setSettings({ ...defaultSettings, ...value.settings, aspect_ratio: value.settings.aspect_ratio || "9:16" }); setSource({ type: value.source_type as VideoSource["type"], id: value.source_id, previewUrl: value.source_asset_id ? `/api/v1/assets/${value.source_asset_id}/media` : undefined, label: "Reopened session" }); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to reopen session."));
  }, [params]);
  useEffect(() => {
    const parentId = params.get("alternateFrom");
    if (!parentId || session) return;
    void videoStudioApi.alternate(parentId).then((created) => {
      setSession(created); setSettings(created.settings);
      setSource({ type: created.source_type as VideoSource["type"], id: created.source_id, label: "Alternate from completed video" });
      setParams({ session: created.session_id });
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Unable to start alternate."));
  }, [params, session, setParams]);

  const operation = useMemo(() => {
    const all = [...operations.active, ...operations.recent];
    return all.find((item) => item.operationId === operationId) || (session ? all.find((item) => item.subjectType === "video_generation_session" && item.subjectId === session.session_id) : undefined);
  }, [operationId, operations.active, operations.recent, session]);
  const operationStatus = operation?.status;
  const activeSessionId = session?.session_id;

  useEffect(() => {
    if (!activeSessionId || !operationStatus || !["SUCCEEDED", "FAILED", "PARTIAL"].includes(operationStatus)) return;
    void videoStudioApi.session(activeSessionId).then((value) => { setSession(value); void reloadHistory(); });
  }, [activeSessionId, operationStatus, reloadHistory]);

  const changeSettings = async (changes: Partial<VideoSettings>) => {
    const next = { ...settings, ...changes }; setSettings(next); setError("");
    if (session && !session.final_generated_media_id) {
      try { setSession(await videoStudioApi.settings(session.session_id, changes)); }
      catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to update settings."); }
    }
  };

  const ensureSession = async () => {
    if (!source) throw new Error("Choose a source image first.");
    if (session && session.source_id === source.id && !session.final_generated_media_id) return session;
    const parentSession = params.get("parentSession");
    const created = await videoStudioApi.create(source.type, source.id, settings, parentSession ? { sessionId: parentSession, videoId: source.id } : undefined); setSession(created); setParams({ session: created.session_id }); return created;
  };

  const develop = async (operatorIdea?: string) => {
    setError("");
    try {
      setBusyStage("Understanding the scene..."); const current = await ensureSession();
      await videoStudioApi.analyze(current.session_id);
      setBusyStage(`Planning a ${settings.desired_runtime}-second experience...`);
      const result = await videoStudioApi.concepts(current.session_id, operatorIdea);
      setBusyStage("Developing complete cinematic concepts...");
      const refreshed = await videoStudioApi.session(current.session_id);
      setSession({ ...refreshed, concept_batches: [...refreshed.concept_batches.slice(0, -1), { ...(refreshed.concept_batches.at(-1) || { batch_id: "current" }), concepts: result.concepts }] }); setIdeaOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Creator_OS could not develop concepts."); }
    finally { setBusyStage(""); }
  };

  const choose = async (concept: VideoConcept) => {
    if (!session) return; setError("");
    try { setSession(await videoStudioApi.select(session.session_id, concept.concept_id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to choose concept."); }
  };

  const generate = async () => {
    if (!session) return; setError(""); setBusyStage("Preparing your video...");
    try { await videoStudioApi.plan(session.session_id); const result = await videoStudioApi.generate(session.session_id); setOperationId(result.operation.operationId); setSession(await videoStudioApi.session(session.session_id)); await operations.refresh(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to begin video generation."); }
    finally { setBusyStage(""); }
  };

  const startNew = () => { setSession(null); setSource(null); setOperationId(null); setIdea(""); setError(""); setParams({}); };
  const alternate = async () => { if (!session) return; try { const created = await videoStudioApi.alternate(session.session_id); setSession(created); setSettings(created.settings); setSource({ type: created.source_type as VideoSource["type"], id: created.source_id, label: "Alternate from completed video" }); setParams({ session: created.session_id }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start alternate."); } };
  const extend = async () => {
    if (!session) return;
    try { const created = await videoStudioApi.extend(session.session_id, { desired_runtime: extensionRuntime }); setSession(created); setSettings(created.settings); setSource({ type: "generated_video", id: String(session.final_generated_media_id), label: "Generated video continuation" }); setExtensionOpen(false); setParams({ session: created.session_id }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to start extension."); }
  };

  const concepts = sessionConcepts(session);
  const completed = Boolean(session?.final_generated_media_id);
  const generating = Boolean(operation && ["QUEUED", "RUNNING", "WAITING_EXTERNAL"].includes(operation.status));
  const selected = session?.selected_concept;
  const sourcePreview = source?.previewUrl || (session?.source_asset_id ? `/api/v1/assets/${session.source_asset_id}/media` : "");

  return <section className="video-studio">
    <PageHeader title="Video Studio" description="Create a complete cinematic experience with your AI Film Director." />
    {error && <div className="video-studio__alert" role="alert"><strong>Something interrupted the creative process.</strong><span>{error}</span><button onClick={() => setError("")} type="button">Dismiss</button></div>}

    {!source && !session ? <section className="video-empty">
      <Film size={42} /><h2>Choose your starting image</h2><p>Bring an existing Creator_OS image into one shared filmmaking workspace.</p>
      <div><Link to="/library/generations"><Sparkles />Generation Library</Link><Link to="/library/assets?assetType=images"><Library />Asset Library</Link><label><Upload />Upload Image<input accept="image/jpeg,image/png,image/webp" type="file" onChange={async (event) => { const file = event.target.files?.[0]; if (!file) return; try { setBusyStage("Preparing your image..."); const uploaded = await uploadEditStudioReference(file); setSource({ type: "upload", id: String(uploaded.assetId), previewUrl: uploaded.previewUrl, label: uploaded.label }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to upload image."); } finally { setBusyStage(""); } }} /></label></div>
    </section> : <>
      {!completed && !generating && concepts.length === 0 && <div className="video-setup">
        <section className="video-source-card"><span>Reference image</span><div>{sourcePreview ? <img alt="Video source" src={sourcePreview} /> : <ImagePlus size={52} />}</div><h2>{source?.label || "Selected Creator_OS image"}</h2>{source?.context && <p>{source.context}</p>}<small>{source?.type === "photoshoot_shot" ? "Source · Production Photoshoot" : `Source · ${title(source?.type || "asset")}`}</small></section>
        <section className="video-settings"><header><span>Creative setup</span><h2>Generation Settings</h2><p>Set the experience. Creator_OS handles the filmmaking.</p></header>
          <label><span>Desired runtime</span><select value={settings.desired_runtime} onChange={(event) => void changeSettings({ desired_runtime: Number(event.target.value) })}>{[5,10,15,30,45,60].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></label>
          <label><span>Aspect ratio</span><select value={settings.aspect_ratio} onChange={(event) => void changeSettings({ aspect_ratio: event.target.value })}>{["9:16","16:9","1:1","4:3","3:4","21:9","adaptive"].map((value) => <option key={value}>{value}</option>)}</select></label>
          <label><span>Resolution</span><select value={settings.resolution} onChange={(event) => void changeSettings({ resolution: event.target.value })}>{["720p","1080p","4k","480p"].map((value) => <option key={value}>{value}</option>)}</select></label>
          <label className="video-settings__switch"><span><strong>Generate Audio</strong><small>Include native sound and atmosphere</small></span><input checked={settings.generate_audio} onChange={(event) => void changeSettings({ generate_audio: event.target.checked })} type="checkbox" /></label>
          <label><span>Video model</span><select value={settings.video_provider} onChange={(event) => void changeSettings({ video_provider: event.target.value })}>{providers.length ? providers.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>) : <option value="wavespeed_seedance_2_0">Seedance 2.0</option>}</select></label>
          <div className="video-settings__actions"><button className="video-primary" disabled={Boolean(busyStage)} onClick={() => void develop()} type="button"><Sparkles />Inspire Me</button><button className="video-secondary" onClick={() => setIdeaOpen((value) => !value)} type="button">Develop My Idea</button></div>
          {ideaOpen && <div className="video-idea"><label><span>Your idea</span><textarea placeholder="Describe the video you'd like..." rows={4} value={idea} onChange={(event) => setIdea(event.target.value)} /></label><p>Try “Have her slowly wash her hair” or “I want something more playful.”</p><button className="video-primary" disabled={!idea.trim() || Boolean(busyStage)} onClick={() => void develop(idea.trim())} type="button">Develop My Idea</button></div>}
        </section>
      </div>}

      {busyStage && <section className="video-directing" role="status"><span className="video-directing__orb"><Sparkles /></span><div><small>Creator_OS Film Director</small><h2>{busyStage}</h2><p>Building one coherent experience around your image and settings.</p></div></section>}

      {!generating && !completed && concepts.length > 0 && !selected && <section className="video-concepts"><header><span>Creative direction</span><h2>Choose your video experience</h2><p>Each concept is a complete {settings.desired_runtime}-second story designed for this scene.</p></header><div>{concepts.map((concept) => <article key={concept.concept_id}><small>{concept.tone} · {concept.pacing}</small><h3>{concept.title}</h3><p>{concept.experience_summary}</p><footer><span><Clock3 size={15} />{concept.requested_runtime} seconds</span><button onClick={() => void choose(concept)} type="button">Choose This Concept <ChevronRight /></button></footer></article>)}</div></section>}

      {!generating && !completed && selected && <section className="video-concept-detail"><header><span>Selected experience</span><h2>{selected.title}</h2><p>{selected.experience_summary}</p></header><div className="video-timeline">{selected.timeline.map((beat, index) => <article key={`${beat.start_second}-${beat.end_second}`}><span>{index === 0 ? "Opening" : index === selected.timeline.length - 1 ? "Ending" : "Development"}</span><strong>{beat.start_second}–{beat.end_second}s</strong><p>{beat.creative_beat}</p></article>)}</div><dl><div><dt>Runtime</dt><dd>{settings.desired_runtime}s</dd></div><div><dt>Aspect</dt><dd>{settings.aspect_ratio}</dd></div><div><dt>Resolution</dt><dd>{settings.resolution}</dd></div><div><dt>Audio</dt><dd>{settings.generate_audio ? "On" : "Off"}</dd></div><div><dt>Model</dt><dd>{providers.find((item) => item.provider_id === settings.video_provider)?.display_name || "Seedance 2.0"}</dd></div></dl><footer><button className="video-secondary" onClick={() => setSession({ ...session!, selected_concept: null })} type="button">Choose Another</button><button className="video-primary" onClick={() => void generate()} type="button"><Play />Generate Video</button></footer></section>}

      {generating && operation && <section className="video-progress" aria-live="polite"><span className="video-progress__icon"><Clapperboard /></span><small>AI Film Director</small><h2>Creating your video...</h2><div className="video-progress__bar"><span style={{ width: `${operation.progressPercent}%` }} /></div><strong>{operation.progressCurrent} / {operation.progressTotal} seconds completed</strong><p>{operation.currentStage?.includes("EXTENSION") ? "Extending" : operation.currentStage?.includes("REGISTER") ? "Registering" : operation.currentStage?.includes("DOWNLOAD") ? "Finalizing" : "Generating"}</p><em>You can leave this page. Creator_OS will keep working.</em></section>}

      {completed && session && <section className="video-complete"><header><span className="video-complete__check"><Check /></span><div><small>Video complete</small><h2>{selected?.title || "Your cinematic experience"}</h2><p>Saved to Creator_OS and ready for what comes next.</p></div></header><div className="video-complete__player"><video controls playsInline poster={`${videoStudioApi.mediaUrl(session.final_generated_media_id!)}/poster`} src={videoStudioApi.mediaUrl(session.final_generated_media_id!)} /></div><dl><div><dt>Duration</dt><dd>{settings.desired_runtime}s</dd></div><div><dt>Resolution</dt><dd>{settings.resolution}</dd></div><div><dt>Aspect</dt><dd>{settings.aspect_ratio}</dd></div><div><dt>Audio</dt><dd>{settings.generate_audio ? "On" : "Off"}</dd></div><div><dt>Model</dt><dd>{providers.find((item) => item.provider_id === settings.video_provider)?.display_name || "Seedance 2.0"}</dd></div></dl><div className="video-complete__actions"><Link className="video-primary" to="/gallery/videos" state={{ generatedMediaId: session.final_generated_media_id }}>View in Video Gallery</Link><button className="video-primary" onClick={() => setExtensionOpen((value) => !value)} type="button"><Video />Extend Video</button><button className="video-secondary" onClick={() => void alternate()} type="button"><RotateCcw />Generate Alternate</button><button className="video-secondary" onClick={startNew} type="button">Start New Video</button><Link to="/library/assets?assetType=videos">In Asset Library</Link></div>{extensionOpen && <div className="video-extension"><h3>Continue this experience</h3><p>Choose how much additional story Creator_OS should direct.</p><label><span>Additional runtime</span><select value={extensionRuntime} onChange={(event) => setExtensionRuntime(Number(event.target.value))}>{[5,10,15,30,45,60].map((value) => <option key={value} value={value}>{value} seconds</option>)}</select></label><button className="video-primary" onClick={() => void extend()} type="button">Continue to Creative Direction</button></div>}</section>}
    </>}

    {history.length > 0 && <section className="video-history"><header><span>Video Studio</span><h2>Recent Sessions</h2></header><div>{history.slice(0, 8).map((item) => <button key={item.session_id} onClick={() => navigate(`/studio/video?session=${item.session_id}`)} type="button"><span className={`video-history__status video-history__status--${item.status.toLowerCase()}`} /><span><strong>{item.selected_concept?.title || "Video session"}</strong><small>{title(item.status)} · {item.settings.desired_runtime}s · {new Date(item.updated_at).toLocaleDateString()}</small></span><ChevronRight /></button>)}</div></section>}
  </section>;
}
