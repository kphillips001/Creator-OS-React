import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  approvePhotoshootCandidate,
  approvePhotoshootRecommendation,
  approvePhotoshootSessionPlan,
  chooseAnotherPhotoshootIdea,
  editPhotoshootCandidatePrompt,
  generatePhotoshootSessionPlan,
  generatePhotoshootShot,
  finishPhotoshoot,
  getCreativeDirectorContext,
  getPhotoshootStatus,
  getPhotoshootAutoRunRuntime,
  pausePhotoshootAutoRun,
  persistPhotoshootGuidance,
  regeneratePhotoshootCandidate,
  rejectPhotoshootCandidate,
  requestPhotoshootInspiration,
  requestDirectPhotoshootRecommendation,
  requestPhotoshootRecommendation,
  replacePhotoshootShot,
  resumePhotoshootAutoRun,
  retryPhotoshootAutoRun,
  returnPhotoshootToLibrary,
  selectPhotoshootInspiration,
  setPhotoshootPlanningMode,
  setPhotoshootTargetShotCount,
  stopPhotoshootAndReturnSeed,
  stopPhotoshootAutoRun,
  startPhotoshootAutoRun,
  type PhotoshootStatus,
} from "../../infrastructure/api/photoshootApi";
import type { PhotoshootAutoRunRuntime, PhotoshootContext, PlannedShot, PlanningMode } from "./types";
import type { CreativeDirectorRecommendation } from "./types";
import { CandidatePanel } from "./components/CandidatePanel";
import { CreativeDirectionPanel } from "./components/CreativeDirectionPanel";
import { GenerationPanel } from "./components/GenerationPanel";
import { PhotoshootHeader } from "./components/PhotoshootHeader";
import { PhotoshootSettings } from "./components/PhotoshootSettings";
import { PhotoshootStateGate } from "./components/PhotoshootStateGate";
import { PhotoshootTimeline } from "./components/PhotoshootTimeline";
import { SeedImageCard } from "./components/SeedImageCard";
import { SessionPlanPanel } from "./components/SessionPlanPanel";
import { ActivePhotoshootActions, StopPhotoshootDialog } from "./components/ShotApprovedPanel";
import { PhotoshootAutoGenerationProgress } from "./components/PhotoshootAutoGenerationProgress";
import { SelectedShotProgress, type SelectedShotStage } from "./components/SelectedShotProgress";
import { usePhotoshootContext } from "./usePhotoshootContext";
import "./photoshoot.css";

type Ready = Extract<PhotoshootContext, { status: "ready" }>;

function ManualWorkspace({
  ready,
  refresh,
  onReturn,
  onOpenLibrary,
  onOpenGallery,
}: {
  ready: Ready;
  refresh: () => Promise<unknown>;
  onReturn: () => void;
  onOpenLibrary: (message?: string) => void;
  onOpenGallery: (deliverableId: string | null) => void;
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
  const [planningMode, setPlanningMode] = useState<PlanningMode>("frame_by_frame");
  const [planFrameCount, setPlanFrameCount] = useState(8);
  const [targetShotCount, setTargetShotCount] = useState(10);
  const [planningStatus, setPlanningStatus] = useState({ currentShot: 1, planningShot: 2, targetShotCount: 10, remainingShots: 9, editorialStage: "Beginning", explanation: "Continuing from the latest approved shot." });
  const [sessionPlan, setSessionPlan] = useState<PlannedShot[]>([]);
  const [sessionPlanIndex, setSessionPlanIndex] = useState(0);
  const [sessionPlanApproved, setSessionPlanApproved] = useState(false);
  const [autoRuntime, setAutoRuntime] = useState<PhotoshootAutoRunRuntime | null>(null);
  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<PhotoshootStatus>({
    request: null,
    candidate: null,
  });
  const [pollRevision, setPollRevision] = useState(0);
  const [approvalNotice, setApprovalNotice] = useState(false);
  const [confirmStop, setConfirmStop] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedShotStage, setSelectedShotStage] = useState<SelectedShotStage | null>(null);
  const [selectedShotError, setSelectedShotError] = useState("");
  const [selectedShotSource, setSelectedShotSource] = useState<"idea" | "direct">("idea");
  const selectionSaveRef = useRef<Promise<void>>(Promise.resolve());
  const promptEditorRef = useRef<HTMLTextAreaElement>(null);
  const request = status.request;
  const working =
    busy ||
    Boolean(autoRuntime?.spinner_active) ||
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
        if (next.request?.failure) {
          setError(next.request.failure);
          setSelectedShotError(next.request.failure);
        }
        if (next.candidate) {
          setSelectedShotStage((current) => current === null ? null : 4);
        }
        if (
          next.request &&
          !next.request.failure &&
          (["queued", "generating"].includes(next.request.status) || next.continuity_assessment?.status === "pending")
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
      const recreateScene = sessionStorage.getItem("creator-os:photoshoot-scene");
      setGuidance(recreateScene || state.creatorGuidance);
      if (recreateScene) sessionStorage.removeItem("creator-os:photoshoot-scene");
      setIdeas(state.ideas);
      setSelectedIdea(state.selectedInspiration);
      setRecommendation(state.recommendation);
      setDirectionApproved(state.directionApproved);
      setPlanningMode(state.planningMode);
      setPlanFrameCount(state.planFrameCount);
      setTargetShotCount(state.targetShotCount);
      setPlanningStatus({ currentShot: state.currentShot, planningShot: state.planningShot, targetShotCount: state.targetShotCount, remainingShots: state.remainingShots, editorialStage: state.editorialStage, explanation: state.plannerExplanation });
      setSessionPlan(state.sessionPlan);
      setSessionPlanIndex(state.sessionPlanIndex);
      setSessionPlanApproved(state.sessionPlanApproved);
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

  useEffect(() => {
    if (planningMode !== "full_plan" || !sessionPlanApproved) return;
    const controller = new AbortController();
    let timer = 0;
    const poll = async () => {
      try {
        const runtime = await getPhotoshootAutoRunRuntime(ready.session.sessionId, controller.signal);
        setAutoRuntime(runtime);
        const runtimeIndex = runtime.current_frame_index ?? runtime.completed_frames;
        setSessionPlanIndex(runtimeIndex);
        setSessionPlan((current) => current.map((shot, index) => ({
          ...shot, status: index < runtime.completed_frames ? "completed" : index === runtimeIndex && !runtime.plan_complete ? "current" : "pending",
        })));
        if (!runtime.photoshoot_complete) timer = window.setTimeout(poll, 1000);
      } catch (reason) {
        if ((reason as { name?: string }).name !== "AbortError") setError(reason instanceof Error ? reason.message : "Unable to refresh Auto Generation status.");
      }
    };
    void poll();
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [planningMode, ready.session.sessionId, sessionPlanApproved]);

  const continuityBody = () => ({
    location: locks.location, wardrobe: locks.wardrobe, lighting: locks.lighting,
    hairstyle: locks.hairstyle, makeup: locks.makeup, camera_style: locks.cameraStyle,
  });

  const askAi = async () => {
    setBusy(true); setError("");
    try {
      const result = await requestPhotoshootInspiration({ session_id: ready.session.sessionId, creative_mode: mode, creator_guidance: guidance, provider_context: ready.providers.find((item) => item.value === provider)?.label || provider, continuity_locks: continuityBody(), target_shot_count: targetShotCount });
      setIdeas(result.ideas);
      setSelectedIdea(result.selected_inspiration || "");
      setRecommendation(null); setDirectionApproved(false); setPrompt("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to generate inspiration ideas."); }
    finally { setBusy(false); }
  };

  const changePlanningMode = async (next: PlanningMode) => {
    setBusy(true); setError("");
    try {
      const result = await setPhotoshootPlanningMode({
        session_id: ready.session.sessionId,
        planning_mode: next,
        plan_frame_count: planFrameCount,
        target_shot_count: targetShotCount,
      });
      setPlanningMode(result.planning_mode);
      setPlanFrameCount(result.plan_frame_count);
      setSessionPlan(result.session_plan || []);
      setSessionPlanApproved(Boolean(result.session_plan_approved));
      setSessionPlanIndex(0);
      if (next === "frame_by_frame") {
        setIdeas([]);
        setSelectedIdea("");
        setRecommendation(null);
        setDirectionApproved(false);
        setPrompt("");
        setGuidance("");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to change planning mode.");
    } finally {
      setBusy(false);
    }
  };

  const changeFrameCount = async (count: number) => {
    setPlanFrameCount(count);
    if (planningMode !== "full_plan") return;
    try {
      await setPhotoshootPlanningMode({
        session_id: ready.session.sessionId,
        planning_mode: "full_plan",
        plan_frame_count: count,
        target_shot_count: targetShotCount,
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update frame count.");
    }
  };

  const changeTargetShotCount = async (count: number) => {
    setTargetShotCount(count);
    try {
      const result = await setPhotoshootTargetShotCount({
        session_id: ready.session.sessionId,
        target_shot_count: count,
      });
      setTargetShotCount(result.target_shot_count);
      const restored = await getCreativeDirectorContext(ready.session.sessionId);
      setPlanningStatus({ currentShot: restored.currentShot, planningShot: restored.planningShot, targetShotCount: restored.targetShotCount, remainingShots: restored.remainingShots, editorialStage: restored.editorialStage, explanation: restored.plannerExplanation });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update target photoshoot length.");
    }
  };

  const generateFullPlan = async () => {
    setBusy(true); setError("");
    try {
      const result = await generatePhotoshootSessionPlan({
        session_id: ready.session.sessionId,
        creative_mode: mode,
        creator_guidance: guidance,
        continuity_locks: continuityBody(),
        plan_frame_count: planFrameCount,
        target_shot_count: targetShotCount,
      });
      setPlanningMode("full_plan");
      setPlanFrameCount(result.plan_frame_count);
      setSessionPlan(result.session_plan || []);
      setSessionPlanIndex(result.session_plan_index || 0);
      setSessionPlanApproved(false);
      setIdeas([]);
      setSelectedIdea("");
      setRecommendation(null);
      setDirectionApproved(false);
      setPrompt("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to plan the full session.");
    } finally {
      setBusy(false);
    }
  };

  const approveFullPlan = async () => {
    setBusy(true); setError("");
    try {
      const result = await approvePhotoshootSessionPlan({ session_id: ready.session.sessionId });
      const plan = result.session_plan || [];
      setSessionPlan(plan);
      setSessionPlanIndex(result.session_plan_index || 0);
      setSessionPlanApproved(true);
      const runtime = await startPhotoshootAutoRun({ session_id: ready.session.sessionId, auto_approve_enabled: true });
      setAutoRuntime(runtime);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to approve the session plan.");
      setBusy(false);
    }
  };

  const resumePlanRun = async () => {
    setBusy(true); setError("");
    try { setAutoRuntime(await (autoRuntime?.auto_run_state === "READY" ? startPhotoshootAutoRun({ session_id: ready.session.sessionId, auto_approve_enabled: true }) : resumePhotoshootAutoRun({ session_id: ready.session.sessionId }))); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to resume Auto Generation."); }
    finally { setBusy(false); }
  };

  const stopPlanRun = async () => {
    setBusy(true); setError("");
    try {
      setAutoRuntime(await (autoRuntime?.auto_run_state === "FAILED"
        ? stopPhotoshootAutoRun({ session_id: ready.session.sessionId })
        : pausePhotoshootAutoRun({ session_id: ready.session.sessionId })));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to pause Auto Generation."); }
    finally { setBusy(false); }
  };

  const retryPlanRun = async () => {
    setBusy(true); setError("");
    try { setAutoRuntime(await retryPhotoshootAutoRun({ session_id: ready.session.sessionId })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to retry this frame."); }
    finally { setBusy(false); }
  };

  const chooseIdea = async (idea: string) => {
    setSelectedIdea(idea); setRecommendation(null); setDirectionApproved(false); setPrompt(""); setError("");
    const save = selectPhotoshootInspiration({ session_id: ready.session.sessionId, idea }).then(() => undefined);
    selectionSaveRef.current = save;
    try { await save; }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save inspiration selection.");
    }
  };

  const chooseAnother = async () => {
    setBusy(true); setError("");
    try { await chooseAnotherPhotoshootIdea({ session_id: ready.session.sessionId }); setSelectedIdea(""); setRecommendation(null); setDirectionApproved(false); setPrompt(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to choose another idea."); }
    finally { setBusy(false); }
  };

  const submit = async (plannedPrompt = prompt, creativeHint = selectedIdea) => {
    if (!plannedPrompt.trim()) {
      setError("Prompt is required.");
      return false;
    }
    setBusy(true);
    setError("");
    try {
      const result = await generatePhotoshootShot({
        session_id: ready.session.sessionId,
        provider_id: provider,
        creative_mode: mode,
        prompt: plannedPrompt,
        continuity_settings: {
          location: locks.location,
          wardrobe: locks.wardrobe,
          lighting: locks.lighting,
          hairstyle: locks.hairstyle,
          makeup: locks.makeup,
          camera_style: locks.cameraStyle,
        },
        session_direction: guidance,
        creative_hint: creativeHint,
      });
      setStatus({
        request: {
          request_id: result.request_id,
          status: "generating",
          prompt: plannedPrompt,
          provider_id: provider,
          generation_job_id: null,
          failure: null,
        },
        candidate: null,
      });
      setPollRevision((current) => current + 1);
      return true;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Generation failed. Please try again.";
      setError(message);
      setSelectedShotError(message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const runAutomaticShot = async (
    developDirection: () => Promise<CreativeDirectorRecommendation>,
    creativeHint: string,
  ) => {
    setBusy(true);
    setError("");
    setSelectedShotError("");
    setSelectedShotStage(0);
    try {
      const developed = await developDirection();
      setRecommendation(developed);
      setSelectedShotStage(1);
      setSelectedShotStage(2);
      const approvalRequest = approvePhotoshootRecommendation({
        session_id: ready.session.sessionId,
      }).then((result) => {
        if (!String(result.prompt || "").trim()) throw new Error("Canonical Prompt Planner completed without returning a prompt.");
        return result.prompt;
      });
      let recoveryCancelled = false;
      let recoveryTimer = 0;
      const recoverPersistedPrompt = new Promise<string>((resolve, reject) => {
        const startedAt = Date.now();
        const poll = async () => {
          if (recoveryCancelled) return;
          try {
            const restored = await getCreativeDirectorContext(ready.session.sessionId);
            if (restored.directionApproved && restored.currentPrompt.trim()) {
              resolve(restored.currentPrompt);
              return;
            }
          } catch {
            // The approval request remains authoritative; transient context polling errors are ignored.
          }
          if (Date.now() - startedAt >= 120_000) {
            reject(new Error("Canonical prompt planning did not complete within two minutes. Retry the selected shot."));
            return;
          }
          recoveryTimer = window.setTimeout(() => { void poll(); }, 500);
        };
        recoveryTimer = window.setTimeout(() => { void poll(); }, 500);
      });
      const approvedPrompt = await Promise.race([approvalRequest, recoverPersistedPrompt]).finally(() => {
        recoveryCancelled = true;
        window.clearTimeout(recoveryTimer);
      });
      setPrompt(approvedPrompt);
      setDirectionApproved(true);
      setSelectedShotStage(3);
      await submit(approvedPrompt, creativeHint);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Unable to generate the selected shot.";
      setError(message);
      setSelectedShotError(message);
    } finally {
      setBusy(false);
    }
  };

  const generateSelectedShot = async () => {
    if (!selectedIdea) return;
    setSelectedShotSource("idea");
    await runAutomaticShot(async () => {
      await selectionSaveRef.current;
      return requestPhotoshootRecommendation({
        session_id: ready.session.sessionId,
        creative_mode: mode,
        creator_guidance: guidance,
        continuity_locks: continuityBody(),
        target_shot_count: targetShotCount,
      });
    }, selectedIdea);
  };

  const directShot = async () => {
    const operatorDirection = guidance.trim();
    if (!operatorDirection) return;
    setSelectedShotSource("direct");
    setSelectedIdea("");
    await runAutomaticShot(
      () => requestDirectPhotoshootRecommendation({
        session_id: ready.session.sessionId,
        creative_mode: mode,
        operator_direction: operatorDirection,
        continuity_locks: continuityBody(),
        target_shot_count: targetShotCount,
      }),
      operatorDirection,
    );
  };

  const openPromptEditor = () => {
    const editor = promptEditorRef.current;
    if (!editor) return;
    editor.scrollIntoView({ behavior: "smooth", block: "center" });
    editor.focus({ preventScroll: true });
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
        setGuidance("");
        setIdeas([]);
        setSelectedIdea("");
        setRecommendation(null);
        setDirectionApproved(false);
        setStatus({ request: null, candidate: null });
        await refresh();
        const restored = await getCreativeDirectorContext(ready.session.sessionId);
        setPlanningStatus({ currentShot: restored.currentShot, planningShot: restored.planningShot, targetShotCount: restored.targetShotCount, remainingShots: restored.remainingShots, editorialStage: restored.editorialStage, explanation: restored.plannerExplanation });
        setApprovalNotice(true);
        window.setTimeout(() => setApprovalNotice(false), 3200);
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
        setStatus({ request: null, candidate: null });
        setSelectedShotStage(null);
        setSelectedShotError("");
        setDirectionApproved(false);
        setPollRevision((current) => current + 1);
        await refresh();
        const restored = await getCreativeDirectorContext(ready.session.sessionId);
        setIdeas(restored.ideas);
        setSelectedIdea(restored.selectedInspiration);
        setRecommendation(restored.recommendation);
        setDirectionApproved(restored.directionApproved);
        setPrompt(restored.currentPrompt || prompt);
        setPlanningStatus({ currentShot: restored.currentShot, planningShot: restored.planningShot, targetShotCount: restored.targetShotCount, remainingShots: restored.remainingShots, editorialStage: restored.editorialStage, explanation: restored.plannerExplanation });
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
      await refresh();
      onOpenGallery(result.photoshoot_deliverable_id);
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

  const replaceShot = async (requestId: string) => {
    setBusy(true); setError("");
    try {
      await replacePhotoshootShot({ session_id: ready.session.sessionId, request_id: requestId });
      await refresh();
      const state = await getCreativeDirectorContext(ready.session.sessionId);
      setIdeas(state.ideas); setSelectedIdea(state.selectedInspiration); setRecommendation(state.recommendation);
      setDirectionApproved(state.directionApproved); setPrompt(state.currentPrompt); setGuidance(state.creatorGuidance);
      setSelectedShotStage(null); setSelectedShotError("");
      setPlanningStatus({ currentShot: state.currentShot, planningShot: state.planningShot, targetShotCount: state.targetShotCount, remainingShots: state.remainingShots, editorialStage: state.editorialStage, explanation: state.plannerExplanation });
      document.getElementById("photoshoot-direction-title")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to replace this shot."); }
    finally { setBusy(false); }
  };

  const latest = [...ready.timeline].reverse().find((item) => item.image)?.image || ready.seedImage;
  const targetReached = planningStatus.targetShotCount > 0 && planningStatus.currentShot >= planningStatus.targetShotCount;
  return (
    <div className="photoshoot-workflow">
      <SeedImageCard seed={ready.seedImage} onReturn={onReturn} />
      <PhotoshootTimeline busy={busy} items={ready.timeline} onReplace={(requestId) => { void replaceShot(requestId); }} />
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
      {autoRuntime && sessionPlanApproved && (
        <PhotoshootAutoGenerationProgress
          busy={busy}
          onFinish={() => { void finishSession(); }}
          onPause={() => { void stopPlanRun(); }}
          onResume={() => { void resumePlanRun(); }}
          onRetry={() => { void retryPlanRun(); }}
          runtime={autoRuntime}
        />
      )}
      <SessionPlanPanel
        autoRunning={Boolean(autoRuntime?.is_running)}
        runtime={autoRuntime}
        busy={busy}
        directionApproved={directionApproved}
        disabled={working || Boolean(status.candidate)}
        hasRecommendation={Boolean(recommendation)}
        onApprovePlan={() => { void approveFullPlan(); }}
        onFrameCount={(count) => { void changeFrameCount(count); }}
        onGeneratePlan={() => { void generateFullPlan(); }}
        onPlanningMode={(next) => { void changePlanningMode(next); }}
        onTargetShotCount={(count) => { void changeTargetShotCount(count); }}
        onResumePlan={() => { void resumePlanRun(); }}
        planFrameCount={planFrameCount}
        targetShotCount={targetShotCount}
        planningMode={planningMode}
        sessionPlan={sessionPlan}
        sessionPlanApproved={sessionPlanApproved}
        sessionPlanIndex={sessionPlanIndex}
      />
      {planningMode === "frame_by_frame" && targetReached ? (
        <section className="photoshoot-card photoshoot-target-complete" role="status">
          <h2>Target Photoshoot Length Reached</h2>
          <p>{planningStatus.currentShot} of {planningStatus.targetShotCount} shots are approved. Finish the Photoshoot when you are ready.</p>
        </section>
      ) : planningMode === "frame_by_frame" ? (
        <>
          <CreativeDirectionPanel
            disabled={working || Boolean(status.candidate)}
            busy={busy}
            creativeMode={mode}
            guidance={guidance}
            ideas={ideas}
            selectedIdea={selectedIdea}
            recommendation={recommendation}
            directionApproved={directionApproved}
            planningStatus={planningStatus}
            onAsk={() => { void askAi(); }}
            onDirect={() => { void directShot(); }}
            onDifferentIdeas={() => { void askAi(); }}
            onGuidance={setGuidance}
            onGenerateSelected={() => { void generateSelectedShot(); }}
            onDirectSelected={openPromptEditor}
            onChooseAnother={() => { void chooseAnother(); }}
            onSelectIdea={(idea) => { void chooseIdea(idea); }}
          />
          {selectedShotStage !== null && <SelectedShotProgress
            activeStage={selectedShotStage}
            error={selectedShotError}
            onRetry={() => { void (selectedShotSource === "direct" ? directShot() : generateSelectedShot()); }}
            providerLabel={ready.providers.find((item) => item.value === provider)?.label || provider}
          />}
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
            continuityWarning={status.continuity_assessment?.warning ? status.continuity_assessment.warning_message || "This generation may have drifted from the current photoshoot." : ""}
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
        </>
      ) : (
        <section className="photoshoot-card photoshoot-creative-director" aria-labelledby="photoshoot-plan-guidance-title">
          <header>
            <h2 id="photoshoot-plan-guidance-title">Session Guidance</h2>
            <span>Optional steering before you approve the plan</span>
          </header>
          <label>
            <span>Guide the plan (Optional)</span>
            <textarea
              disabled={working || Boolean(status.candidate) || sessionPlanApproved}
              onChange={(event) => setGuidance(event.target.value)}
              placeholder="e.g. start clothed, end topless, keep pink lingerie until later shots..."
              value={guidance}
            />
          </label>
          {Boolean(autoRuntime?.is_running) && recommendation && (
            <article className="photoshoot-recommendation">
              <h3>{recommendation.title || "Generating planned shot"}</h3>
              <p>{recommendation.creative_direction}</p>
              {prompt ? <small className="photoshoot-session-plan__hint">Prompt ready · waiting for image</small> : null}
            </article>
          )}
          {error && (
            <div className="photoshoot-state photoshoot-state--error" role="alert">
              {error}
            </div>
          )}
        </section>
      )}
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
        {ready && <ManualWorkspace key={`${ready.session.sessionId}:${ready.seedImage.image_id}`} onOpenGallery={(deliverableId) => navigate("/library/photoshoots", { state: { newlyCompletedDeliverableId: deliverableId } })} onOpenLibrary={(message) => navigate("/library/generations", { state: message ? { notification: message } : undefined })} onReturn={() => { void returnToLibrary(); }} ready={ready} refresh={state.refresh} />}
      </PhotoshootStateGate>
    </section>
  );
}
