"""One durable Photoshoot auto-run state-machine step per leased claim."""

from __future__ import annotations

from app.models.generation_engine import GenerationStatus
from app.repositories.photoshoot_auto_run_repository import PhotoshootAutoRunRepository
from app.services.photoshoot_auto_run_service import PhotoshootAutoRunService


class PhotoshootAutoRunWorkerService:
    def __init__(self, *, worker_instance_id: str, repository=None, runtime=None):
        self.worker_id = worker_instance_id
        self.repository = repository or PhotoshootAutoRunRepository()
        self.runtime = runtime or PhotoshootAutoRunService(repository=self.repository)

    def process_one(self):
        run = self.repository.claim_next(self.worker_id)
        if run is None:
            return {"processed": False, "status": "IDLE"}
        try:
            return self._step(run)
        except Exception as error:
            return self._fail(run, error)

    def _step(self, run):
        session = self.runtime.queue.get_session(run.session_id)
        continuity = dict(session.creative_continuity or {})
        plan = [dict(item) for item in tuple(continuity.get("session_plan") or ())]
        session_index = max(0, int(continuity.get("session_plan_index") or 0))
        index = max(session_index, run.current_plan_index)
        if session.status == "completed":
            return self._transition(run, "PHOTOSHOOT_COMPLETE", current_plan_index=len(plan))
        if index >= len(plan):
            return self._transition(run, "PLAN_COMPLETE", current_plan_index=len(plan))
        active = self.runtime._active_request(run.session_id)
        if active:
            if active.status == "awaiting_review":
                if run.state == "APPROVING":
                    self.runtime.manual.approve(creator_profile_id=session.creator_profile_id,
                                                session_id=run.session_id, request_id=active.request_id)
                    return self._transition(run, "ADVANCING", current_request_id=active.request_id)
                if run.state != "WAITING_FOR_REVIEW":
                    return self._transition(run, "WAITING_FOR_REVIEW", current_request_id=active.request_id,
                                            current_plan_index=index)
                if not run.auto_approve_enabled:
                    return self._transition(run, "WAITING_FOR_REVIEW", current_request_id=active.request_id)
                return self._transition(run, "APPROVING", current_request_id=active.request_id)
            if active.status in {"queued", "generating"}:
                failure = str(dict(active.metadata or {}).get("last_generation_failure") or "")
                if failure:
                    if run.state == "READY":
                        return self._transition(run, "PREPARING", current_request_id=active.request_id)
                    if run.state != "PREPARING":
                        raise RuntimeError(failure)
                    locks = dict(continuity.get("continuity_locks") or {})
                    request, job = self.runtime.manual.create_manual_request(
                        creator_profile_id=session.creator_profile_id, session_id=run.session_id,
                        provider_id=session.provider_id, creative_mode=session.creative_mode,
                        prompt=active.prompt_text, continuity_locks=locks,
                        session_direction=str(continuity.get("creator_guidance") or ""),
                        creative_hint=str(continuity.get("creative_hint") or ""))
                    self.repository.transition(run.session_id, "GENERATING", worker_id=self.worker_id,
                                               release_lease=False, current_request_id=request.request_id)
                    self.runtime.manual.execute(session_id=run.session_id, job=job)
                    return self._transition(run, "GENERATING", current_request_id=request.request_id)
                job = self.runtime.manual.engine.get_job(active.generation_job_id) if active.generation_job_id else None
                if job and job.status in {GenerationStatus.QUEUED.value, GenerationStatus.RETRY.value}:
                    self.runtime.manual.execute(session_id=run.session_id, job=job)
                elif job and job.status == GenerationStatus.SUCCEEDED.value:
                    records = self.runtime.manual.library.sync_job(job)
                    marked = self.runtime.manual.library.mark_photoshoot_session_records(
                        (record.image_id for record in records), session_id=run.session_id, session_title=session.title)
                    if not marked.success:
                        raise RuntimeError("; ".join(marked.errors) or marked.message)
                    self.runtime.queue.mark_generation_complete(
                        generation_job_id=job.job_id, generated_image_ids=tuple(record.image_id for record in records))
                elif job and job.status in {GenerationStatus.FAILED.value, GenerationStatus.CANCELLED.value}:
                    reason = job.failure.reason if job.failure else "Generation failed."
                    self.runtime.queue.mark_generation_failed(job.job_id, reason=reason)
                    raise RuntimeError(reason)
                return self._transition(run, "GENERATING", current_request_id=active.request_id)
        checkpoint_request = self.runtime.queue.get_request(run.current_request_id) if run.current_request_id else None
        if run.state != "ADVANCING" and checkpoint_request and checkpoint_request.status == "approved":
            return self._transition(run, "ADVANCING", current_request_id=checkpoint_request.request_id)
        if run.state == "APPROVING":
            if checkpoint_request and checkpoint_request.status == "awaiting_review":
                self.runtime.manual.approve(creator_profile_id=session.creator_profile_id,
                                            session_id=run.session_id, request_id=checkpoint_request.request_id)
            return self._transition(run, "ADVANCING", current_request_id=run.current_request_id)
        if run.state == "ADVANCING":
            latest_index = int(dict(self.runtime.queue.get_session(run.session_id).creative_continuity or {}).get("session_plan_index") or 0)
            if latest_index <= run.current_plan_index:
                advanced = self.runtime.director.advance_session_plan(
                    creator_profile_id=session.creator_profile_id, session_id=run.session_id)
                latest_index = int(advanced["session_plan_index"])
            next_state = "PLAN_COMPLETE" if latest_index >= len(plan) else "PREPARING"
            return self._transition(run, next_state, current_plan_index=latest_index, current_request_id=None)
        if run.state == "READY":
            return self._transition(run, "PREPARING", current_plan_index=index, current_request_id=None)
        planned = self.runtime.director.develop_planned_shot(
            creator_profile_id=session.creator_profile_id, session_id=run.session_id)
        approved = self.runtime.director.approve(
            creator_profile_id=session.creator_profile_id, session_id=run.session_id)
        continuity = dict(self.runtime.queue.get_session(run.session_id).creative_continuity or {})
        locks = dict(continuity.get("continuity_locks") or {})
        request, job = self.runtime.manual.create_manual_request(
            creator_profile_id=session.creator_profile_id, session_id=run.session_id,
            provider_id=session.provider_id, creative_mode=session.creative_mode, prompt=approved["prompt"],
            continuity_locks=locks, session_direction=str(continuity.get("creator_guidance") or ""),
            creative_hint=str(planned.get("creative_direction") or ""))
        self.repository.transition(run.session_id, "GENERATING", worker_id=self.worker_id,
                                   release_lease=False, current_plan_index=index,
                                   current_request_id=request.request_id)
        self.runtime.manual.execute(session_id=run.session_id, job=job)
        self.repository.transition(run.session_id, "GENERATING", worker_id=self.worker_id,
                                   current_plan_index=index, current_request_id=request.request_id)
        return {"processed": True, "session_id": run.session_id, "status": "GENERATING"}

    def _transition(self, run, state, **fields):
        self.repository.transition(run.session_id, state, worker_id=self.worker_id, **fields)
        return {"processed": True, "session_id": run.session_id, "status": state}

    def _fail(self, run, error):
        try:
            session = self.runtime.queue.get_session(run.session_id)
            plan = list(dict(session.creative_continuity or {}).get("session_plan") or ())
            frame = plan[run.current_plan_index] if run.current_plan_index < len(plan) else {}
            request = self.runtime._active_request(run.session_id)
            self.repository.transition(
                run.session_id, "FAILED", worker_id=self.worker_id,
                last_error_code=type(error).__name__, last_error_message=str(error), failure_stage=run.state,
                failed_frame_index=run.current_plan_index, failed_frame_title=str(frame.get("title") or ""),
                failed_provider=session.provider_id, failed_request_id=request.request_id if request else run.current_request_id,
                failed_generation_job_id=request.generation_job_id if request else None)
        finally:
            return {"processed": True, "session_id": run.session_id, "status": "FAILED", "error": str(error)}
