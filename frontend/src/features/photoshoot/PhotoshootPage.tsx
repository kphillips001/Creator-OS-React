import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  approvePhotoshootCandidate,
  approvePhotoshootRecommendation,
  chooseAnotherPhotoshootIdea,
  editPhotoshootCandidatePrompt,
  generatePhotoshootShot,
  finishPhotoshoot,
  getCreativeDirectorContext,
  getPhotoshootStatus,
  persistPhotoshootGuidance,
  regeneratePhotoshootCandidate,
  rejectPhotoshootCandidate,
  requestPhotoshootInspiration,
  requestPhotoshootRecommendation,
  returnPhotoshootToLibrary,
  selectPhotoshootInspiration,
  stopPhotoshootAndReturnSeed,
  type PhotoshootStatus,
} from "../../infrastructure/api/photoshootApi";
import type { PhotoshootContext } from "./types";
import type { CreativeDirectorRecommendation } from "./types";
import { CandidatePanel } from "./components/CandidatePanel";
import { CreativeDirectionPanel } from "./components/CreativeDirectionPanel";
import { GenerationPanel } from "./components/GenerationPanel";
import { PhotoshootHeader } from "./components/PhotoshootHeader";
import { PhotoshootSettings } from "./components/PhotoshootSettings";
import { PhotoshootStateGate } from "./components/PhotoshootStateGate";
import { PhotoshootTimeline } from "./components/PhotoshootTimeline";
import { PromptPanel } from "./components/PromptPanel";
import { SeedImageCard } from "./components/SeedImageCard";
import { ActivePhotoshootActions, PhotoshootCompletedPanel, StopPhotoshootDialog } from "./components/ShotApprovedPanel";
import { usePhotoshootContext } from "./usePhotoshootContext";
import "./photoshoot.css";

type Ready = Extract<PhotoshootContext, { status: "ready" }>;

function ManualWorkspace({
  ready,
  refresh,
  onReturn,
  onOpenLibrary,
}: {
  ready: Ready;
  refresh: () => Promise<unknown>;
  onReturn: () => void;
  onOpenLibrary: (message?: string) => void;
}) {
  const provider = ready.session.providerId;
  const [mode, setMode] = useState(ready.session.creativeMode);
  const locks = ready.session.continuityLocks;
  const [guidance, setGuidance] = useState("");
  const [directorRestored, setDirectorRestored] = useState(false);
  const [ideas, setIdeas] = useState<string[]>([]);
  const [selectedIdea, setSelectedIdea] = useState("");
  const [recommendation, setRecommendation] = useState<CreativeDirectorRecommendation | null>(null);
  const [directionApproved, setDirectionApproved] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<PhotoshootStatus>({
    request: null,
    candidate: null,
  });
  const [pollRevision, setPollRevision] = useState(0);
  const [completedShots, setCompletedShots] = useState<number | null>(null);
  const [approvalNotice, setApprovalNotice] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = status.request;
  const working =
    busy ||
    (!request?.failure &&
      (request?.status === "queued" || request?.status === "generating"));

  useEffect(() => {
    const controller = new AbortController();
    let timer = 0;
    const poll = async () => {
      try {
        const next = await getPhotoshootStatus(
          ready.session.sessionId,
          controller.signal,
        );
        setStatus(next);
        if (next.request?.failure) setError(next.request.failure);
        if (
          next.request &&
          !next.request.failure &&
          ["queued", "generating"].includes(next.request.status)
        )
          timer = window.setTimeout(poll, 750);
      } catch (reason) {
        if ((reason as { name?: string }).name !== "AbortError")
          setError(
            reason instanceof Error
              ? reason.message
              : "Unable to refresh generation status.",
          );
      }
    };
    void poll();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [ready.session.sessionId, pollRevision]);

  useEffect(() => {
    const controller = new AbortController();
    void getCreativeDirectorContext(ready.session.sessionId, controller.signal).then((state) => {
      setGuidance(state.creatorGuidance);
      setIdeas(state.ideas);
      setSelectedIdea(state.selectedInspiration);
      setRecommendation(state.recommendation);
      setDirectionApproved(state.directionApproved);
      if (state.currentPrompt) setPrompt(state.currentPrompt);
      setDirectorRestored(true);
    }).catch((reason: unknown) => {
      if ((reason as { name?: string }).name !== "AbortError") setError(reason instanceof Error ? reason.message : "Unable to restore Creative Director state.");
    });
    return () => controller.abort();
  }, [ready.session.sessionId]);

  useEffect(() => {
    if (!directorRestored) return;
    const timer = window.setTimeout(() => {
      void persistPhotoshootGuidance({ session_id: ready.session.sessionId, creator_guidance: guidance }).catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Unable to save Creative Director guidance.");
      });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [directorRestored, guidance, ready.session.sessionId]);

  const continuityBody = () => ({
    location: locks.location, wardrobe: locks.wardrobe, lighting: locks.lighting,
    hairstyle: locks.hairstyle, makeup: locks.makeup, camera_style: locks.cameraStyle,
  });

  const askAi = async () => {
    setBusy(true); setError("");
    try {
      const result = await requestPhotoshootInspiration({ session_id: ready.session.sessionId, creative_mode: mode, creator_guidance: guidance, provider_context: ready.providers.find((item) => item.value === provider)?.label || provider, continuity_locks: continuityBody() });
      setIdeas(result.ideas); setSelectedIdea(""); setRecommendation(null); setDirectionApproved(false); setPrompt("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to generate inspiration ideas."); }
    finally { setBusy(false); }
  };

  const chooseIdea = async (idea: string) => {
    setSelectedIdea(idea); setRecommendation(null); setDirectionApproved(false); setPrompt(""); setError("");
    try { await selectPhotoshootInspiration({ session_id: ready.session.sessionId, idea }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to save inspiration selection."); }
  };

  const generateRecommendation = async () => {
    setBusy(true); setError("");
    try { setRecommendation(await requestPhotoshootRecommendation({ session_id: ready.session.sessionId, creative_mode: mode, creator_guidance: guidance, continuity_locks: continuityBody() })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to generate a recommendation."); }
    finally { setBusy(false); }
  };

  const approveRecommendation = async () => {
    setBusy(true); setError("");
    try { const result = await approvePhotoshootRecommendation({ session_id: ready.session.sessionId }); setPrompt(result.prompt); setDirectionApproved(true); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to approve the recommendation."); }
    finally { setBusy(false); }
  };

  const chooseAnother = async () => {
    setBusy(true); setError("");
    try { await chooseAnotherPhotoshootIdea({ session_id: ready.session.sessionId }); setSelectedIdea(""); setRecommendation(null); setDirectionApproved(false); setPrompt(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to choose another idea."); }
    finally { setBusy(false); }
  };

  const submit = async () => {
    if (!prompt.trim()) {
      setError("Prompt is required.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await generatePhotoshootShot({
        session_id: ready.session.sessionId,
        provider_id: provider,
        creative_mode: mode,
        prompt,
        continuity_settings: {
          location: locks.location,
          wardrobe: locks.wardrobe,
          lighting: locks.lighting,
          hairstyle: locks.hairstyle,
          makeup: locks.makeup,
          camera_style: locks.cameraStyle,
        },
        session_direction: guidance,
        creative_hint: selectedIdea,
      });
      setStatus({
        request: {
          request_id: result.request_id,
          status: "generating",
          prompt,
          provider_id: provider,
          generation_job_id: null,
          failure: null,
        },
        candidate: null,
      });
      setPollRevision((current) => current + 1);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Generation failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  const action = async (kind: "approve" | "regenerate" | "edit" | "reject") => {
    if (!request) return;
    setBusy(true);
    setError("");
    const body = {
      session_id: ready.session.sessionId,
      request_id: request.request_id,
    };
    try {
      if (kind === "approve") {
        await approvePhotoshootCandidate(body);
        setPrompt("");
        setIdeas([]);
        setSelectedIdea("");
        setRecommendation(null);
        setDirectionApproved(false);
        setStatus({ request: null, candidate: null });
        await refresh();
        setApprovalNotice(true);
        window.setTimeout(() => setApprovalNotice(false), 3200);
        await askAi();
      }
      if (kind === "regenerate") {
        await regeneratePhotoshootCandidate(body);
        setStatus({
          request: { ...request, status: "generating" },
          candidate: null,
        });
        setPollRevision((current) => current + 1);
      }
      if (kind === "edit") {
        const result = await editPhotoshootCandidatePrompt(body);
        setPrompt(result.prompt);
        setStatus({ request: null, candidate: null });
      }
      if (kind === "reject") {
        await rejectPhotoshootCandidate(body);
        setPrompt("");
        setStatus({ request: null, candidate: null });
      }
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Candidate action failed.",
      );
    } finally {
      setBusy(false);
    }
  };

  const finishSession = async () => {
    setBusy(true); setError("");
    try {
      const result = await finishPhotoshoot({ session_id: ready.session.sessionId });
      setCompletedShots(result.approved_shot_count);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to finish this Photoshoot."); }
    finally { setBusy(false); }
  };

  const stopSession = async () => {
    setBusy(true); setError("");
    try {
      const result = await stopPhotoshootAndReturnSeed();
      setConfirmStop(false);
      onOpenLibrary(result.message);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to stop this Photoshoot."); }
    finally { setBusy(false); }
  };

  const latest = ready.timeline.at(-1)?.image || ready.seedImage;
  if (completedShots !== null) return <div className="photoshoot-workflow"><PhotoshootTimeline items={ready.timeline} /><PhotoshootCompletedPanel approvedShotCount={completedShots} onOpenLibrary={onOpenLibrary} /></div>;
  return (
    <div className="photoshoot-workflow">
      <SeedImageCard seed={ready.seedImage} onReturn={onReturn} />
      <PhotoshootTimeline items={ready.timeline} />
      <ActivePhotoshootActions busy={busy} onFinish={() => { void finishSession(); }} onStop={() => setConfirmStop(true)} />
      {confirmStop && <StopPhotoshootDialog busy={busy} onCancel={() => setConfirmStop(false)} onConfirm={() => { void stopSession(); }} />}
      {approvalNotice && <div className="photoshoot-approval-notice" role="status"><strong>✅ Shot Approved</strong><span>Updating Photoshoot...</span></div>}
      <PhotoshootSettings
        disabled={working || Boolean(status.candidate)}
        creativeMode={mode}
        onMode={setMode}
        providers={ready.providers}
        session={ready.session}
      />
      <CreativeDirectionPanel
        disabled={working || Boolean(status.candidate)}
        busy={busy}
        guidance={guidance}
        ideas={ideas}
        selectedIdea={selectedIdea}
        recommendation={recommendation}
        directionApproved={directionApproved}
        onApprove={() => { void approveRecommendation(); }}
        onAsk={() => { void askAi(); }}
        onDifferentIdeas={() => { void askAi(); }}
        onGuidance={setGuidance}
        onDevelop={() => { void generateRecommendation(); }}
        onChooseAnother={() => { void chooseAnother(); }}
        onSelectIdea={(idea) => { void chooseIdea(idea); }}
      />
      <PromptPanel
        disabled={working || Boolean(status.candidate)}
        onPrompt={setPrompt}
        prompt={prompt}
      />
      {error && (
        <div className="photoshoot-state photoshoot-state--error" role="alert">
          {error}
        </div>
      )}
      <GenerationPanel
        disabled={working || Boolean(status.candidate) || !prompt.trim()}
        onGenerate={() => {
          void submit();
        }}
        provider={provider}
        status={request?.status || ""}
      />
      {status.candidate && <CandidatePanel
        busy={busy}
        candidate={status.candidate}
        current={latest}
        onApprove={() => {
          void action("approve");
        }}
        onEdit={() => {
          void action("edit");
        }}
        onRegenerate={() => {
          void action("regenerate");
        }}
        onReject={() => {
          void action("reject");
        }}
      />}
    </div>
  );
}

export function PhotoshootPage() {
  const navigate = useNavigate();
  const state = usePhotoshootContext();
  const [returnError, setReturnError] = useState("");
  const ready = state.context?.status === "ready" ? state.context : null;
  const returnToLibrary = async () => {
    setReturnError("");
    try {
      navigate(await returnPhotoshootToLibrary());
    } catch (reason) {
      setReturnError(
        reason instanceof Error
          ? reason.message
          : "Unable to return this image to Generation Library.",
      );
    }
  };
  return (
    <section className="photoshoot-page">
      <PhotoshootHeader />
      {returnError && (
        <div className="photoshoot-state photoshoot-state--error" role="alert">
          {returnError}
        </div>
      )}
      <PhotoshootStateGate {...state}>
        {ready && <ManualWorkspace key={`${ready.session.sessionId}:${ready.seedImage.image_id}`} onOpenLibrary={(message) => navigate("/library/generations", { state: message ? { notification: message } : undefined })} onReturn={() => { void returnToLibrary(); }} ready={ready} refresh={state.refresh} />}
      </PhotoshootStateGate>
    </section>
  );
}
