"""HTTP-safe orchestration for the manual Photoshoot Studio loop."""

from __future__ import annotations

import logging

from app.models.generation_engine import GenerationStatus
from app.services.content_studio_generation_service import ContentStudioGenerationService
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_summary_service import PhotoshootSummaryService


class PhotoshootManualService:
    def __init__(self, *, queue=None, engine=None, library=None, ingestion=None, summary_service=None,
                 commerce_deliverables=None, continuity_assessor=None):
        self.queue = queue or PhotoshootQueueService()
        self.engine = engine or GenerationEngineService()
        self.library = library or GenerationLibraryService()
        self.ingestion = ingestion or GenerationResultIngestionService()
        self.summary = summary_service or PhotoshootSummaryService(queue=self.queue)
        self._commerce_deliverables = commerce_deliverables
        self._continuity_assessor = continuity_assessor

    def session_for_creator(self, session_id: str, creator_profile_id: int):
        session = self.queue.get_session(session_id)
        if session.creator_profile_id != int(creator_profile_id):
            raise KeyError("Photoshoot Session not found.")
        return session

    def create_manual_request(self, *, creator_profile_id: int, session_id: str, provider_id: str,
                              creative_mode: str, prompt: str, continuity_locks: dict,
                              session_direction: str, creative_hint: str):
        session = self.session_for_creator(session_id, creator_profile_id)
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ValueError("Prompt is required before generating a Photoshoot shot.")
        active = self._active_request(session_id)
        retryable = active is not None and active.status == "queued" and bool(
            dict(active.metadata or {}).get("last_generation_failure")
        )
        if active is not None and not retryable:
            raise ValueError("A Photoshoot request is already active.")
        session = self.queue.update_session_settings(
            session_id, provider_id=provider_id, creative_mode=creative_mode,
            continuity_locks=continuity_locks, session_direction=session_direction,
            creative_hint=creative_hint, workflow_stage="ready_to_generate",
        )
        reference = self._latest_approved_record(session)
        continuity_reference = self._provider_output_reference(reference) if reference else None
        if retryable:
            request = self.queue.update_request_continuity_reference(
                active.request_id,
                image_id=reference.image_id if reference else None,
                output_reference=continuity_reference,
            )
        else:
            request = self.queue.add_studio_shot_request(
                session_id=session_id, prompt_text=prompt,
                shot_direction="\n".join(value for value in (session_direction.strip(), creative_hint.strip()) if value),
                provider_id=provider_id,
                active_reference_image_id=reference.image_id if reference else None,
                active_reference_output_reference=continuity_reference,
                creative_direction=dict(session.creative_continuity or {}).get("current_direction") or {},
            )
        job = self.queue.queue_next_prompt(session_id=session_id, generation_engine=self.engine)
        if job is None:
            raise ValueError("A Photoshoot request is already active.")
        return request, job

    def execute(self, *, session_id: str, job) -> None:
        generation = ContentStudioGenerationService(
            creative_director=None, generation_engine=self.engine,
            generation_library=self.library, reference_service=None,
        )
        try:
            executed, records = generation.execute(job)
            if executed.status == GenerationStatus.SUCCEEDED.value and records:
                session = self.queue.get_session(session_id)
                marked = self.library.mark_photoshoot_session_records(
                    (record.image_id for record in records), session_id=session_id, session_title=session.title,
                )
                if not marked.success:
                    raise RuntimeError("; ".join(marked.errors) or marked.message)
                completed = self.queue.mark_generation_complete(
                    generation_job_id=executed.job_id,
                    generated_image_ids=tuple(record.image_id for record in records),
                )
                if completed is not None:
                    self.queue.record_continuity_assessment(completed.request_id, {"status": "pending", "warning": False})
                    try:
                        from app.services.photoshoot_creative_director_service import PhotoshootCreativeDirectorWorkflowService
                        assessor = self._continuity_assessor or PhotoshootCreativeDirectorWorkflowService(
                            queue=self.queue, library=self.library,
                        )
                        assessment = assessor.assess_continuity(
                            session_id=session_id, request_id=completed.request_id,
                            candidate_image_id=records[-1].image_id,
                        )
                        if assessment:
                            self.queue.record_continuity_assessment(completed.request_id, {**assessment, "status": "completed"})
                    except Exception:
                        logging.getLogger("creator_os.photoshoot.continuity").exception(
                            "Continuity assessment unavailable session_id=%s request_id=%s",
                            session_id, completed.request_id,
                        )
                        self.queue.record_continuity_assessment(completed.request_id, {"status": "unavailable", "warning": False})
                return
            reason = executed.failure.reason if executed.failure else "Generation failed. Please try again."
            self.queue.mark_generation_failed(executed.job_id, reason=reason)
        except Exception as error:
            self.queue.mark_generation_failed(job.job_id, reason=str(error))

    def status(self, *, creator_profile_id: int, session_id: str) -> dict:
        session = self.session_for_creator(session_id, creator_profile_id)
        requests = self.queue.requests_for_session(session_id)
        current = next((item for item in reversed(requests) if item.status in {"queued", "generating", "awaiting_review"}), None)
        candidate = self._candidate_record(current) if current and current.status == "awaiting_review" else None
        failure = str(dict(current.metadata or {}).get("last_generation_failure") or "") if current else ""
        return {"session": session, "request": current, "candidate": candidate, "failure": failure}

    def approve(self, *, creator_profile_id: int, session_id: str, request_id: str):
        session = self.session_for_creator(session_id, creator_profile_id)
        request = self._review_request(session_id, request_id)
        image_ids = tuple(dict(request.metadata or {}).get("generated_image_ids") or ())
        approval = self.library.approve_creator_content(
            image_ids, source_workflow="photoshoot", source_session_id=session_id,
            generation_engine=self.engine, ingestion_service=self.ingestion,
            source_metadata={"approval_entrypoint": "react_photoshoot_approve_shot", "photoshoot_session_id": session_id,
                             "photoshoot_request_id": request_id, "photoshoot_sequence_index": request.sequence_index,
                             "prompt_plan_id": request.prompt_plan_id},
        )
        if not approval.success:
            raise RuntimeError("; ".join(approval.errors) or approval.message)
        promoted = self.library.approve_photoshoot_records(image_ids, session_id=session_id, session_title=session.title)
        if not promoted.success:
            raise RuntimeError("; ".join(promoted.errors) or promoted.message)
        approved = self.queue.approve_request(request_id, imported_asset_ids=approval.imported_asset_ids)
        self.summary.refresh(session_id)
        return approved

    def finish_session(self, *, creator_profile_id: int, session_id: str):
        from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService
        service = self._commerce_deliverables or PhotoshootCommerceDeliverableService(
            queue=self.queue, library=self.library,
        )
        session, _deliverable = service.complete(session_id, creator_profile_id)
        return session

    def stop_and_return_seed(self, *, creator_profile_id: int):
        session = self.queue.current_session(creator_profile_id=creator_profile_id)
        if session is None:
            session = next((
                item for item in reversed(self.queue.list_sessions(creator_profile_id=creator_profile_id))
                if item.status == "cancelled"
                and bool(dict(item.creative_continuity or {}).get("seed_returned_to_library"))
            ), None)
            if session is None:
                raise KeyError("No active Photoshoot was found.")
        continuity = dict(session.creative_continuity or {})
        seed_id = str(continuity.get("seed_image_id") or "")
        if not seed_id:
            raise KeyError("The original Photoshoot seed was not found.")
        result = self.library.return_photoshoot_seed_to_library(seed_id)
        if not result.success:
            raise RuntimeError("; ".join(result.errors) or result.message)
        if session.status != "cancelled" or not continuity.get("seed_returned_to_library"):
            seed_request = next((
                item for item in self.queue.requests_for_session(session.session_id)
                if bool(dict(item.metadata or {}).get("is_seed_image"))
            ), None)
            if seed_request is not None and seed_request.status != "returned_to_library":
                self.queue.return_seed_request_to_library(seed_request.request_id, notes="Photoshoot stopped and seed returned.")
            session = self.queue.cancel_session_for_seed_return(session.session_id, seed_image_id=seed_id)
        return session, seed_id

    def regenerate(self, *, creator_profile_id: int, session_id: str, request_id: str):
        session = self.session_for_creator(session_id, creator_profile_id)
        request = self._review_request(session_id, request_id)
        self._junk_candidate(session, request, "photoshoot_regenerate")
        request = self.queue.regenerate_request(request_id)
        job = self.queue.queue_next_prompt(session_id=session_id, generation_engine=self.engine)
        if job is None:
            raise RuntimeError("Photoshoot regeneration could not be queued.")
        return request, job

    def edit_prompt(self, *, creator_profile_id: int, session_id: str, request_id: str) -> str:
        session = self.session_for_creator(session_id, creator_profile_id)
        request = self._review_request(session_id, request_id)
        self._junk_candidate(session, request, "photoshoot_edit_prompt")
        self.queue.reject_request(request_id, notes="Returned to prompt editing.")
        self.queue.update_session_settings(session_id, workflow_stage="ready_for_next_shot")
        return request.prompt_text

    def reject(self, *, creator_profile_id: int, session_id: str, request_id: str) -> None:
        session = self.session_for_creator(session_id, creator_profile_id)
        request = self._review_request(session_id, request_id)
        self._junk_candidate(session, request, "photoshoot_rejected")
        self.queue.reject_request(request_id)

    def replace_shot(self, *, creator_profile_id: int, session_id: str, request_id: str):
        self.session_for_creator(session_id, creator_profile_id)
        replaced, invalidated, _session = self.queue.replace_approved_shot(request_id)
        self.summary.refresh(session_id)
        return replaced, invalidated, self.queue.get_session(session_id)

    def _active_request(self, session_id: str):
        return next((item for item in reversed(self.queue.requests_for_session(session_id))
                     if item.status in {"queued", "generating", "awaiting_review"}), None)

    def _review_request(self, session_id: str, request_id: str):
        request = self.queue.get_request(request_id)
        if request.session_id != session_id or request.status != "awaiting_review":
            raise ValueError("Photoshoot candidate is no longer awaiting review.")
        return request

    def _candidate_record(self, request):
        ids = tuple(dict(request.metadata or {}).get("generated_image_ids") or ())
        if not ids:
            return None
        try:
            return self.library.get(str(ids[-1]))
        except KeyError:
            return None

    def _latest_approved_record(self, session):
        continuity = dict(session.creative_continuity or {})
        image_id = continuity.get("current_shot_image_id") or continuity.get("seed_image_id")
        try:
            return self.library.get(str(image_id)) if image_id else None
        except KeyError:
            return None

    def _provider_output_reference(self, record) -> str:
        """Prefer the provider-hosted result while it is available for Photoshoot continuity."""
        try:
            job = self.engine.get_job(str(record.generation_job_id))
            references = tuple(job.result.output_references or ()) if job.result else ()
            remote = next(
                (str(value) for value in references if str(value).startswith(("http://", "https://"))),
                "",
            )
            if remote:
                return remote
        except Exception:
            pass
        return str(record.output_reference)

    def _junk_candidate(self, session, request, reason: str) -> None:
        result = self.library.move_photoshoot_records_to_junk(
            tuple(dict(request.metadata or {}).get("generated_image_ids") or ()),
            session_id=session.session_id, session_title=session.title, reason=reason,
        )
        if not result.success:
            raise RuntimeError("; ".join(result.errors) or result.message)
