"""Idempotent completion and commerce grouping for Photoshoot sets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.repositories.content_intelligence_repository import ContentIntelligenceProfileRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.generation_library_service import GenerationLibraryService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_commercial_intelligence_service import (
    PHOTOSHOOT_INTELLIGENCE_VERSION, PhotoshootCommercialIntelligenceService,
)


class PhotoshootCommerceDeliverableService:
    RISK = {"SAFE": 0, "TEASE": 1, "NUDITY": 2, "EXPLICIT": 3}

    def __init__(self, *, queue=None, library=None, repository=None, intelligence=None,
                 commercial_intelligence=None, session_sales_strategy=None, workflows=None):
        self.queue = queue or PhotoshootQueueService()
        self.library = library or GenerationLibraryService()
        self.repository = repository or PhotoshootCommerceRepository()
        self.intelligence = intelligence or ContentIntelligenceProfileRepository()
        self.commercial_intelligence = commercial_intelligence or PhotoshootCommercialIntelligenceService()
        if session_sales_strategy is None:
            from app.services.photoshoot_session_sales_strategy_service import PhotoshootSessionSalesStrategyService
            session_sales_strategy = PhotoshootSessionSalesStrategyService(photoshoots=self.repository)
        self.session_sales_strategy = session_sales_strategy
        if workflows is None:
            from app.repositories.photoshoot_analysis_workflow_repository import PhotoshootAnalysisWorkflowRepository
            workflows = PhotoshootAnalysisWorkflowRepository()
        self.workflows = workflows

    def complete(self, session_id: str, creator_profile_id: int):
        session = self.queue.get_session(session_id)
        if int(session.creator_profile_id) != int(creator_profile_id):
            raise KeyError("Photoshoot Session not found.")
        active = next((r for r in self.queue.requests_for_session(session_id)
                       if r.status in {"queued", "generating", "awaiting_review"}), None)
        if active is not None:
            raise ValueError("Review the current candidate before finishing this Photoshoot.")
        members, image_ids = self._ordered_members(session_id)
        if not members:
            raise ValueError("Approve at least one generated Photoshoot shot before finishing.")

        finalization = self.library.finish_photoshoot_session(
            session_id=session_id, approved_image_ids=image_ids, session_title=session.title)
        if not finalization.success:
            raise RuntimeError("; ".join(finalization.errors) or finalization.message)
        records = {r.image_id: r for r in self.library.list_records()}
        completed_records = [records[i] for i in image_ids if i in records]
        if len(completed_records) != len(image_ids) or any(r.status != "photoshoot_completed" for r in completed_records):
            raise RuntimeError("Photoshoot Gallery finalization did not reconcile every approved shot.")
        gallery_path = str(Path(completed_records[0].output_reference).parent)
        hero = members[0][0]
        self.repository.replace_members(session_id, members, hero)

        completed_at = self._completed_at(session)
        deliverable = self.repository.upsert_deliverable(
            deliverable_id=str(uuid5(NAMESPACE_URL, f"creator-os:photoshoot-deliverable:{session_id}")),
            session_id=session_id, creator_profile_id=creator_profile_id,
            display_name=session.title, member_ids=tuple(a for a, _ in members), hero_asset_id=hero,
            gallery_path=gallery_path, completed_at=completed_at,
            intelligence_status="PENDING", commerce_status="ANALYZING")
        self.run_canonical_intelligence(session)
        self.session_sales_strategy.generate(
            str(deliverable["deliverable_id"]), creator_profile_id=creator_profile_id
        )
        self.repository.set_completion_intelligence_status(str(deliverable["deliverable_id"]), "READY")
        deliverable = self.repository.get(str(deliverable["deliverable_id"]))
        if session.status != "completed" or not dict(session.creative_continuity or {}).get("gallery_ready"):
            session = self.queue.finish_session(session_id)
        return session, deliverable

    def reconcile_completed(self, *, creator_profile_id: int | None = None):
        output = []
        for session in self.queue.list_sessions(creator_profile_id=creator_profile_id):
            if session.status == "completed":
                output.append(self.complete(session.session_id, session.creator_profile_id)[1])
        return tuple(output)

    def regenerate_commercial_intelligence(self, deliverable_id: str, creator_profile_id: int):
        """Safely replace only the canonical intelligence row from preserved approved evidence."""
        deliverable = self.repository.get(deliverable_id)
        if deliverable is None or int(deliverable["creator_profile_id"]) != int(creator_profile_id):
            raise KeyError("Completed Photoshoot not found.")
        session_id = str(deliverable["photoshoot_session_id"])
        session = self.queue.get_session(session_id)
        profile = self.run_canonical_intelligence(session, force=True)
        self.repository.set_completion_intelligence_status(deliverable_id, "READY")
        return self.repository.get(deliverable_id)

    def generate_session_sales_strategy(
        self, deliverable_id: str, creator_profile_id: int, *, strategy_version: str,
    ):
        """Generate an intentional new version, or return the existing same version."""
        return self.session_sales_strategy.generate(
            deliverable_id,
            creator_profile_id=creator_profile_id,
            strategy_version=strategy_version,
        )

    def run_canonical_intelligence(self, session, *, intelligence_version: str = PHOTOSHOOT_INTELLIGENCE_VERSION,
                                   force: bool = False, preserve_commercial_intelligence: bool = False):
        session_id = str(session.session_id)
        chapters = self._approved_chapters(session_id)
        if not chapters:
            raise ValueError("Canonical Photoshoot Intelligence requires approved persisted members.")
        existing = self.repository.get_intelligence(session_id)
        if (not force and existing and existing.get("status") == "READY"
                and existing.get("pipeline_stage") == "COMPLETE"
                and existing.get("intelligence_version") == intelligence_version
                and len(self.repository.shot_intelligence(session_id, intelligence_version)) == len(chapters)):
            return dict(existing.get("profile_data") or {})
        self.repository.mark_intelligence_running(session_id, intelligence_version)
        try:
            profile = self.commercial_intelligence.generate(
                chapters=chapters, approved_metadata=self._production_context(session),
                intelligence_version=intelligence_version,
                progress=lambda stage, state: self.repository.update_intelligence_stage(session_id, stage, dict(state)))
            if preserve_commercial_intelligence and existing:
                profile = self._preserve_legacy_commercial_intelligence(profile, existing)
            self.repository.persist_canonical_intelligence(session_id, intelligence_version, profile)
            return profile
        except Exception as error:
            stage = str(getattr(error, "stage", "PERSISTENCE_FAILED"))
            self.repository.mark_intelligence_failure(session_id, intelligence_version, stage, error)
            raise

    @staticmethod
    def _preserve_legacy_commercial_intelligence(profile: dict, existing: dict) -> dict:
        """Add canonical analysis while retaining the legacy commercial aggregate verbatim."""
        merged = dict(profile)
        legacy_profile = dict(existing.get("profile_data") or {})
        commercial_fields = (
            "commercial_title", "subtitle", "commercial_summary", "story", "theme",
            "experience", "emotional_journey", "buyer_profile", "sales_strategy",
            "sales_brain_brief", "input_snapshot", "model", "generated_at",
        )
        for field in commercial_fields:
            if field in legacy_profile:
                merged[field] = legacy_profile[field]
            elif existing.get(field) is not None:
                merged[field] = existing[field]
        return merged

    def register(self, deliverable_id: str, creator_profile_id: int):
        """Promote one completed Gallery record into commerce; safe to repeat."""
        existing = self.repository.get(deliverable_id)
        if existing is None or int(existing["creator_profile_id"]) != int(creator_profile_id):
            raise KeyError("Completed Photoshoot not found.")
        if existing["registration_state"] == "ARCHIVED" or existing["is_archived"]:
            raise ValueError("Archived Photoshoots cannot be registered.")
        if existing["registration_state"] == "REGISTERED":
            self.workflows.enqueue(deliverable_id)
            return existing
        if existing["registration_state"] != "IN_ASSET_LIBRARY":
            raise ValueError("Add the Photoshoot to Asset Library before registering it.")
        registered = self.repository.register(deliverable_id, int(creator_profile_id))
        if registered is None:
            raise RuntimeError("Photoshoot could not be registered.")
        self.workflows.enqueue(deliverable_id)
        return self.repository.get(deliverable_id)

    def add_to_asset_library(self, deliverable_id: str, creator_profile_id: int):
        """Promote a completed Photoshoot into the common curation gateway."""
        existing = self.repository.get(deliverable_id)
        if existing is None or int(existing["creator_profile_id"]) != int(creator_profile_id):
            raise KeyError("Completed Photoshoot not found.")
        state = existing["registration_state"]
        if state in {"IN_ASSET_LIBRARY", "REGISTERED"}:
            return existing
        if state == "ARCHIVED" or existing["is_archived"]:
            raise ValueError("Archived Photoshoots cannot be added to Asset Library.")
        added = self.repository.add_to_asset_library(deliverable_id, int(creator_profile_id))
        if added is None:
            raise RuntimeError("Photoshoot could not be added to Asset Library.")
        return self.repository.get(deliverable_id)

    def _ordered_members(self, session_id: str):
        members, images = [], []
        approved = sorted((r for r in self.queue.requests_for_session(session_id) if r.status == "approved"),
                          key=lambda r: r.sequence_index)
        for request in approved:
            request_images = tuple(dict(request.metadata or {}).get("generated_image_ids") or ())
            assets = tuple(int(a) for a in request.imported_asset_ids)
            for index, asset_id in enumerate(assets):
                members.append((asset_id, len(members) + 1))
                if index < len(request_images): images.append(str(request_images[index]))
        return tuple(members), tuple(images)

    def _aggregate(self, asset_ids: tuple[int, ...]):
        try:
            profiles = [self.intelligence.get_by_asset_id(asset_id) for asset_id in asset_ids]
            if any(p is None or not p.ready for p in profiles):
                raise RuntimeError("One or more Photoshoot member intelligence profiles are not ready.")
            contexts = [dict(p.normalized_context or {}) for p in profiles]
            contents = [dict(p.content_profile or {}) for p in profiles]
            values = lambda key: self._dedupe(c.get(key) for c in contexts)
            safety = max((str(c.get("safety_classification") or "SAFE").upper() for c in contexts),
                         key=lambda v: self.RISK.get(v, -1))
            profile = {k: v for k, v in {
                "overall_summary": " ".join(str(c.get("summary") or "").strip() for c in contexts if c.get("summary")),
                "mood": values("mood"), "theme": values("themes"), "setting": values("setting"),
                "wardrobe_continuity": values("outfit"), "lighting_continuity": values("lighting"),
                "visual_progression": tuple(str(c.get("summary") or "").strip() for c in contexts if c.get("summary")),
                "suggested_collections": self._dedupe(
                    dict(c.get("ai_metadata") or {}).get("semantic", {}).get("suggested_collections") for c in contents),
                "search_phrases": self._dedupe(c.get("search_phrases") for c in contexts),
                "decision_engine_summary": " ".join(str(c.get("summary") or "").strip() for c in contexts if c.get("summary")),
                "highest_safety_risk": safety, "hero_asset_id": asset_ids[0],
            }.items() if v not in (None, "", (), [])}
            return "READY", profile, None
        except Exception as error:
            return "FAILED", {}, error

    def aggregate_members(self, asset_ids: tuple[int, ...]):
        return self._aggregate(asset_ids)

    def generate_commercial_intelligence(self, session_id: str, approved_metadata: dict):
        return self.commercial_intelligence.generate(
            chapters=self._approved_chapters(session_id), approved_metadata=approved_metadata)

    def _approved_chapters(self, session_id: str):
        by_asset = {}
        for request in sorted((r for r in self.queue.requests_for_session(session_id) if r.status == "approved"),
                              key=lambda r: r.sequence_index):
            for asset_id in request.imported_asset_ids:
                by_asset[int(asset_id)] = {
                    "asset_id": int(asset_id),
                    "approved_prompt": request.prompt_text,
                    "review_notes": request.review_notes,
                    "approved_metadata": dict(request.metadata or {}),
                }
        members = self.repository.intelligence_members(session_id)
        if members:
            return tuple({
                "shot_order": int(member["shot_order"]),
                **by_asset.get(int(member["asset_id"]), {
                    "asset_id": int(member["asset_id"]),
                    "approved_metadata": {"sequence_role": "reference_seed" if member.get("is_hero") else "approved_member"},
                }),
                "is_seed": bool(member.get("is_hero")),
                "image_reference": str(member.get("file_path") or ""),
                "canonical_content_intelligence": dict(member.get("content_profile") or {}),
                "canonical_normalized_context": dict(member.get("normalized_context") or {}),
            } for member in members)
        return tuple({"shot_order": index + 1, **chapter}
                     for index, chapter in enumerate(by_asset.values()))

    @staticmethod
    def _production_context(session):
        continuity = dict(session.creative_continuity or {})
        return {
            "photoshoot_summary": dict(continuity.get("photoshoot_summary") or {}),
            "session_plan": tuple(continuity.get("session_plan") or ()),
            "approved_directions": tuple(continuity.get("approved_directions") or ()),
            "canonical_seed_summary": continuity.get("canonical_seed_summary") or continuity.get("seed_summary"),
            "creator_notes": session.creator_notes,
            "creative_mode": session.creative_mode,
        }

    @staticmethod
    def _dedupe(values):
        out, seen = [], set()
        for value in values:
            items = value if isinstance(value, (list, tuple)) else (value,)
            for item in items:
                text = str(item or "").strip()
                if text and text.casefold() not in seen: seen.add(text.casefold()); out.append(text)
        return tuple(out)

    @staticmethod
    def _completed_at(session):
        value = dict(session.creative_continuity or {}).get("completed_at")
        return value or datetime.now(timezone.utc)
