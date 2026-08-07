"""Review and curation boundary between Photoshoot creation and Asset Library."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from uuid import NAMESPACE_URL, uuid5

from app.models.generation_engine import utc_now
from app.services.generation_library_service import GenerationLibraryService
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService
from app.services.photoshoot_auto_run_service import PhotoshootAutoRunService
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.creative_intelligence_learning_service import CreativeIntelligenceLearningService


class PhotoshootCurationService:
    DECISIONS = {"APPROVED", "DECLINED"}
    LEGACY_DECISIONS = {
        "PHOTOSHOOT": "APPROVED", "BOTH": "APPROVED",
        "IMAGES": "DECLINED", "ARCHIVE_ONLY": "DECLINED",
    }
    _lock_guard = Lock()
    _session_locks = {}

    def __init__(self, *, queue=None, library=None, deliverables=None, auto_run=None,
                 generation_engine=None, ingestion=None, content_destinations=None,
                 creative_intelligence=None):
        self.queue = queue or PhotoshootQueueService()
        self.library = library or GenerationLibraryService()
        self.deliverables = deliverables or PhotoshootCommerceDeliverableService(queue=self.queue, library=self.library)
        self.auto_run = auto_run or PhotoshootAutoRunService(queue=self.queue)
        self.generation_engine = generation_engine or GenerationEngineService()
        self.ingestion = ingestion or GenerationResultIngestionService()
        self.creative_intelligence = creative_intelligence or CreativeIntelligenceLearningService()

    def review(self, *, creator_profile_id: int, session_id: str):
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        plan = [dict(item) for item in tuple(continuity.get("session_plan") or ())]
        shots = []
        seed_image = None
        frame_index = 0
        for request in self.queue.requests_for_session(session_id):
            if request.status != "approved":
                continue
            is_seed = bool(dict(request.metadata or {}).get("is_seed_image"))
            direction = dict(dict(request.metadata or {}).get("creative_direction") or {})
            planned = plan[frame_index] if frame_index < len(plan) else {}
            for image_id in tuple(dict(request.metadata or {}).get("generated_image_ids") or ()):
                try: record = self.library.get(str(image_id))
                except KeyError: continue
                record_metadata = dict(getattr(record, "generation_metadata", {}) or {})
                item = {
                    "image_id": record.image_id,
                    "asset_id": record.imported_asset_id,
                    "shot_number": 0 if is_seed else len(shots) + 1,
                    "title": direction.get("title") or record_metadata.get("user_title") or record_metadata.get("ai_title") or ("Seed Image" if is_seed else planned.get("title") or f"Shot {len(shots) + 1}"),
                    "description": direction.get("creative_direction") or planned.get("creative_direction") or record.prompt_text,
                    "image_url": f"/api/v1/generation-library/{record.image_id}/media",
                    "keep": not is_seed, "is_seed": is_seed,
                }
                if is_seed: seed_image = item
                else: shots.append(item)
            if not is_seed: frame_index += 1
        raw_curation = dict(continuity.get("curation") or {})
        curation = self._normalized_curation(raw_curation) if raw_curation else {
            "photoshoot_decision": "PENDING", "photoshoot_decided_at": None,
        }
        if curation != raw_curation:
            session = self.queue.reconcile_curation(session_id, curation=curation)
        return {"session_id": session_id, "session_title": session.title,
                "seed_image": seed_image, "shots": shots,
                "photoshoot_decision": curation.get("photoshoot_decision", "PENDING"),
                "confirmed": curation.get("photoshoot_decision") in self.DECISIONS,
                "curation": curation}

    def confirm(self, *, creator_profile_id: int, session_id: str, selected_image_ids, photoshoot_decision: str):
        with self._lock_guard:
            lock = self._session_locks.setdefault(session_id, Lock())
        with lock:
            return self._confirm_locked(creator_profile_id=creator_profile_id, session_id=session_id,
                                        selected_image_ids=selected_image_ids,
                                        photoshoot_decision=photoshoot_decision)

    def complete(self, *, creator_profile_id: int, session_id: str):
        """Complete a Photoshoot with every approved shot in timeline order."""
        review = self.review(creator_profile_id=creator_profile_id, session_id=session_id)
        return self.confirm(
            creator_profile_id=creator_profile_id,
            session_id=session_id,
            selected_image_ids=[shot["image_id"] for shot in review["shots"]],
            photoshoot_decision="APPROVED",
        )

    def _confirm_locked(self, *, creator_profile_id: int, session_id: str, selected_image_ids, photoshoot_decision: str):
        decision = str(photoshoot_decision or "").upper()
        if decision not in self.DECISIONS: raise ValueError("Approve or decline this Photoshoot.")
        session = self._session(creator_profile_id, session_id)
        raw_existing = dict(dict(session.creative_continuity or {}).get("curation") or {})
        existing = self._normalized_curation(raw_existing)
        if existing.get("photoshoot_decision") in self.DECISIONS:
            if existing != raw_existing:
                session = self.queue.reconcile_curation(session_id, curation=existing)
            return self._result(session, existing, already_confirmed=True)
        review = self.review(creator_profile_id=creator_profile_id, session_id=session_id)
        available = {shot["image_id"]: shot for shot in review["shots"]}
        requested = tuple(dict.fromkeys(str(value) for value in selected_image_ids))
        invalid = tuple(value for value in requested if value not in available)
        if invalid:
            raise ValueError(
                "Selected Photoshoot image is not an approved candidate: "
                + ", ".join(invalid)
            )
        selected = tuple(value for value in requested if value in available)
        seed = review.get("seed_image")
        if decision == "APPROVED" and seed is None:
            raise ValueError("The canonical Seed Image is required to create a Photoshoot.")
        if decision == "APPROVED" and seed.get("asset_id") is None:
            approval = self.library.approve_creator_content(
                (seed["image_id"],), source_workflow="photoshoot_seed",
                source_session_id=session_id, generation_engine=self.generation_engine,
                ingestion_service=self.ingestion,
                source_metadata={"approval_entrypoint": "photoshoot_curation_seed",
                                 "photoshoot_session_id": session_id, "is_seed_image": True},
            )
            if not approval.success or not approval.imported_asset_ids:
                raise RuntimeError("; ".join(approval.errors) or "The Photoshoot Seed Image could not be created as an Asset.")
            seed = {**seed, "asset_id": int(approval.imported_asset_ids[0])}
        finalized_ids = tuple(([seed["image_id"]] if seed and decision == "APPROVED" else []) + list(selected))
        finalized = self.library.finish_photoshoot_session(
            session_id=session_id, approved_image_ids=finalized_ids, session_title=session.title)
        if not finalized.success: raise RuntimeError("; ".join(finalized.errors) or finalized.message)
        for image_id in finalized_ids:
            try:
                record = self.library.get(image_id)
            except KeyError:
                continue
            self.creative_intelligence.record_positive_safely(
                creator_profile_id=int(getattr(record, "creator_profile_id", creator_profile_id)),
                image_reference=record.output_reference,
                event_type="photoshoot_added",
                source_workflow="photoshoot",
                source_image_id=record.image_id,
                source_asset_id=getattr(record, "imported_asset_id", None),
                operational_metadata={"photoshoot_session_id": session_id},
            )
        image_assets = []
        if decision == "DECLINED":
            for image_id in selected:
                record, _ = self.library.stage_photoshoot_image_in_asset_library(image_id)
                image_assets.append(record.image_id)
        deliverable = None
        if decision == "APPROVED":
            member_ids = (seed["image_id"],) + selected
            member_map = {seed["image_id"]: seed, **available}
            deliverable = self._create_photoshoot(session, member_ids, member_map)
        curation = {
            "photoshoot_decision": decision, "photoshoot_decided_at": utc_now(),
            "selected_image_ids": list(selected), "photoshoot_created": bool(deliverable),
            "photoshoot_deliverable_id": str(deliverable["deliverable_id"]) if deliverable else None,
            "image_asset_generation_ids": image_assets,
        }
        session = self.queue.archive_curated_session(session_id, curation=curation)
        self.auto_run.mark_photoshoot_complete(session_id)
        return self._result(session, curation, already_confirmed=False)

    def _create_photoshoot(self, session, selected, available):
        records = {r.image_id: r for r in self.library.list_records()}
        members = tuple((int(available[image_id]["asset_id"]), order)
                        for order, image_id in enumerate(selected, 1)
                        if image_id in available and available[image_id].get("asset_id") is not None)
        if len(members) != len(selected): raise RuntimeError("A selected shot is missing its canonical Asset.")
        hero = members[0][0]
        self.deliverables.repository.replace_members(session.session_id, members, hero)
        first = records[selected[0]]
        gallery_path = str(Path(first.output_reference).parent)
        row = self.deliverables.repository.upsert_deliverable(
            deliverable_id=str(uuid5(NAMESPACE_URL, f"creator-os:photoshoot-deliverable:{session.session_id}")),
            session_id=session.session_id, creator_profile_id=session.creator_profile_id,
            display_name=session.title, member_ids=tuple(asset_id for asset_id, _ in members),
            hero_asset_id=hero, gallery_path=gallery_path,
            completed_at=self.deliverables._completed_at(session), intelligence_status="PENDING", commerce_status="CURATED")
        try:
            self.deliverables.run_canonical_intelligence(session)
        except Exception as error:
            self.deliverables.repository.set_analysis_failure(
                str(row["deliverable_id"]), str(error))
        else:
            self.deliverables.repository.set_completion_intelligence_status(
                str(row["deliverable_id"]), "READY")
        return self.deliverables.repository.get(str(row["deliverable_id"]))

    @classmethod
    def _normalized_curation(cls, curation):
        if not curation: return {}
        normalized = dict(curation)
        if not normalized.get("photoshoot_decision"):
            normalized["photoshoot_decision"] = cls.LEGACY_DECISIONS.get(
                str(normalized.get("mode") or "").upper(), "PENDING")
        if normalized.get("photoshoot_decision") == "PENDING":
            normalized["photoshoot_decided_at"] = None
        else:
            normalized.setdefault("photoshoot_decided_at", normalized.get("confirmed_at") or utc_now())
        normalized.pop("mode", None)
        return normalized

    def _session(self, creator_profile_id, session_id):
        session = self.queue.get_session(session_id)
        if int(session.creator_profile_id) != int(creator_profile_id): raise KeyError("Photoshoot Session not found.")
        active = next((r for r in self.queue.requests_for_session(session_id)
                       if r.status in {"queued", "generating", "awaiting_review"}), None)
        if active: raise ValueError("Complete or review the current frame before curating this Photoshoot.")
        return session

    @staticmethod
    def _result(session, curation, already_confirmed):
        return {"session_id": session.session_id, "status": session.status, "already_confirmed": already_confirmed,
                "photoshoot_decision": curation.get("photoshoot_decision", "PENDING"),
                "photoshoot_decided_at": curation.get("photoshoot_decided_at"),
                "selected_image_ids": list(curation.get("selected_image_ids") or ()),
                "photoshoot_created": bool(curation.get("photoshoot_created")),
                "photoshoot_deliverable_id": curation.get("photoshoot_deliverable_id"),
                "image_asset_generation_ids": list(curation.get("image_asset_generation_ids") or ())}
