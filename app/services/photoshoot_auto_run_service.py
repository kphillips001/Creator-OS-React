"""Durable backend-owned Photoshoot full-plan runtime."""

from __future__ import annotations

from app.models.photoshoot_auto_run import PhotoshootAutoRunState
from app.repositories.photoshoot_auto_run_repository import PhotoshootAutoRunRepository
from app.services.photoshoot_creative_director_service import PhotoshootCreativeDirectorWorkflowService
from app.services.photoshoot_manual_service import PhotoshootManualService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_context_service import PhotoshootContextService


class PhotoshootAutoRunService:
    ACTIVE = {"READY", "PREPARING", "GENERATING", "WAITING_FOR_REVIEW", "APPROVING", "ADVANCING"}
    SPINNER = {"PREPARING", "GENERATING", "APPROVING", "ADVANCING"}

    def __init__(self, *, repository=None, queue=None, manual=None, director=None, background_operations=None):
        self.repository = repository or PhotoshootAutoRunRepository()
        self.queue = queue or PhotoshootQueueService()
        self.manual = manual or PhotoshootManualService(queue=self.queue)
        self.director = director or PhotoshootCreativeDirectorWorkflowService(queue=self.queue)
        self.background_operations = background_operations

    def start(self, *, creator_profile_id: int, session_id: str, auto_approve_enabled: bool = True):
        session, plan, index = self._plan(creator_profile_id, session_id)
        self._ensure_operator_generation_inactive(creator_profile_id, session_id)
        current = self._active_request(session_id)
        if current is not None and self.repository.get(session_id) is None:
            raise ValueError("Operator-driven Photoshoot generation currently owns this session.")
        self.repository.start(session_id, current_plan_index=index, total_frames=len(plan),
                              current_request_id=current.request_id if current else None,
                              auto_approve_enabled=auto_approve_enabled)
        return self.runtime(creator_profile_id=creator_profile_id, session_id=session_id)

    def pause(self, *, creator_profile_id: int, session_id: str):
        self._plan(creator_profile_id, session_id)
        if not self.repository.get(session_id):
            raise KeyError("Photoshoot Auto Generation has not been started.")
        self.repository.command(session_id, "pause")
        return self.runtime(creator_profile_id=creator_profile_id, session_id=session_id)

    def resume(self, *, creator_profile_id: int, session_id: str):
        session, plan, index = self._plan(creator_profile_id, session_id)
        self._ensure_operator_generation_inactive(creator_profile_id, session_id)
        run = self.repository.get(session_id)
        current = self._active_request(session_id)
        if run is None:
            self.repository.start(session_id, current_plan_index=index, total_frames=len(plan),
                                  current_request_id=current.request_id if current else None)
        else:
            self.repository.command(session_id, "resume")
        return self.runtime(creator_profile_id=creator_profile_id, session_id=session_id)

    def stop(self, *, creator_profile_id: int, session_id: str):
        self._plan(creator_profile_id, session_id)
        self.repository.command(session_id, "stop")
        return self.runtime(creator_profile_id=creator_profile_id, session_id=session_id)

    def retry(self, *, creator_profile_id: int, session_id: str):
        self._plan(creator_profile_id, session_id)
        self._ensure_operator_generation_inactive(creator_profile_id, session_id)
        self.repository.command(session_id, "retry")
        return self.runtime(creator_profile_id=creator_profile_id, session_id=session_id)

    def mark_photoshoot_complete(self, session_id: str):
        if self.repository.get(session_id):
            self.repository.transition(session_id, PhotoshootAutoRunState.PHOTOSHOOT_COMPLETE.value)

    def runtime(self, *, creator_profile_id: int, session_id: str):
        session, plan, session_index = self._plan(creator_profile_id, session_id, require_approved=False)
        run = self.repository.get(session_id)
        current = self._active_request(session_id)
        index = max(session_index, int(run.current_plan_index if run else session_index))
        total = len(plan)
        state = run.state if run else ("PLAN_COMPLETE" if total and index >= total else "READY")
        if session.status == "completed":
            state = "PHOTOSHOOT_COMPLETE"
        frame = plan[index] if index < total else None
        candidate = None
        if current and current.status == "awaiting_review":
            candidate = self.manual._candidate_record(current)
        failure = None
        if run and run.last_error_message:
            failure = {
                "stage": run.failure_stage, "frame_index": run.failed_frame_index,
                "frame_title": run.failed_frame_title, "provider": run.failed_provider,
                "error_code": run.last_error_code, "error_message": run.last_error_message,
                "request_id": run.failed_request_id, "generation_job_id": run.failed_generation_job_id,
            }
        completed = min(index, total)
        return {
            "session_id": session_id, "auto_run_state": state, "is_running": state in self.ACTIVE,
            "is_paused": state == "PAUSED", "is_failed": state == "FAILED",
            "plan_complete": state in {"PLAN_COMPLETE", "PHOTOSHOOT_COMPLETE"},
            "photoshoot_complete": state == "PHOTOSHOOT_COMPLETE",
            "completed_frames": completed, "total_frames": total,
            "progress_percent": round((completed / total) * 100, 2) if total else 0,
            "current_frame_index": index if frame else None,
            "current_frame_number": index + 1 if frame else None,
            "current_frame_title": str(frame.get("title") or f"Frame {index + 1}") if frame else None,
            "current_frame_status": str(frame.get("status") or "pending") if frame else "completed",
            "current_request_id": current.request_id if current else (run.current_request_id if run else None),
            "generation_job_id": current.generation_job_id if current else None,
            "candidate": None if candidate is None else PhotoshootContextService._generation_payload(candidate),
            "spinner_active": state in self.SPINNER, "waiting_for_review": state == "WAITING_FOR_REVIEW",
            "failure": failure, "last_updated_at": str(run.updated_at) if run and run.updated_at else session.updated_at,
            "auto_approve_enabled": bool(run.auto_approve_enabled) if run else True,
            "review_mode": run.review_mode if run else "AUTO_APPROVE",
            "available_actions": self._actions(state, bool(run and run.auto_approve_enabled)),
        }

    def _plan(self, creator_profile_id, session_id, require_approved=True):
        session = self.manual.session_for_creator(session_id, creator_profile_id)
        continuity = dict(session.creative_continuity or {})
        plan = [dict(item) for item in tuple(continuity.get("session_plan") or ())]
        if require_approved and (not plan or not continuity.get("session_plan_approved")):
            raise ValueError("An approved full session plan is required.")
        return session, plan, max(0, int(continuity.get("session_plan_index") or 0))

    def _active_request(self, session_id):
        return next((item for item in reversed(self.queue.requests_for_session(session_id))
                     if item.status in {"queued", "generating", "awaiting_review"}), None)

    def _ensure_operator_generation_inactive(self, creator_profile_id: int, session_id: str) -> None:
        if self.background_operations is None:
            from app.services.background_operation_service import BackgroundOperationService
            self.background_operations = BackgroundOperationService()
        active = self.background_operations.list(
            creator_profile_id=creator_profile_id, status="active",
            workspace="photoshoot_studio", subject_type="photoshoot_session", subject_id=session_id,
        )
        if any(item.operation_type == "photoshoot_generation" for item in active):
            raise ValueError("Operator-driven Photoshoot generation currently owns this session.")

    @staticmethod
    def _actions(state, auto_approve):
        if state == "READY": return ["start"]
        if state in {"PREPARING", "GENERATING", "APPROVING", "ADVANCING"}: return ["pause", "stop"]
        if state == "WAITING_FOR_REVIEW": return ["pause", "stop"] if auto_approve else ["approve", "reject", "pause", "stop"]
        if state == "PAUSED": return ["resume"]
        if state == "FAILED": return ["retry", "stop"]
        if state == "PLAN_COMPLETE": return ["finish"]
        return []
