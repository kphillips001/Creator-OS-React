"""Idempotent completion and commerce grouping for Photoshoot sets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.repositories.content_intelligence_repository import ContentIntelligenceProfileRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.generation_library_service import GenerationLibraryService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_naming_service import PhotoshootNamingService


class PhotoshootCommerceDeliverableService:
    RISK = {"SAFE": 0, "TEASE": 1, "NUDITY": 2, "EXPLICIT": 3}

    def __init__(self, *, queue=None, library=None, repository=None, intelligence=None, naming=None, workflows=None):
        self.queue = queue or PhotoshootQueueService()
        self.library = library or GenerationLibraryService()
        self.repository = repository or PhotoshootCommerceRepository()
        self.intelligence = intelligence or ContentIntelligenceProfileRepository()
        self.naming = naming or PhotoshootNamingService()
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

        existing = self.repository.get_by_session(session_id)
        registered = bool(existing and existing.get("registration_state") == "REGISTERED")
        status = str(existing.get("intelligence_status")) if registered else "PENDING"
        profile = dict(existing.get("intelligence_profile") or {}) if registered else {}
        if not registered:
            self.repository.upsert_intelligence(session_id, status, profile)
        completed_at = self._completed_at(session)
        deliverable = self.repository.upsert_deliverable(
            deliverable_id=str(uuid5(NAMESPACE_URL, f"creator-os:photoshoot-deliverable:{session_id}")),
            session_id=session_id, creator_profile_id=creator_profile_id,
            display_name=session.title, member_ids=tuple(a for a, _ in members), hero_asset_id=hero,
            gallery_path=gallery_path, completed_at=completed_at,
            intelligence_status=status, commerce_status="ANALYZING")
        if session.status != "completed" or not dict(session.creative_continuity or {}).get("gallery_ready"):
            session = self.queue.finish_session(session_id)
        return session, deliverable

    def _ensure_naming(self, deliverable, profile, intelligence_status):
        if intelligence_status != "READY":
            return deliverable
        if not self.naming.needs_refinement(deliverable.get("ai_title"), deliverable.get("ai_description")):
            return deliverable
        try:
            title, description = self.naming.generate(profile, int(deliverable["shot_count"]))
            self.repository.set_ai_naming(str(deliverable["deliverable_id"]), title, description)
        except Exception as error:
            self.repository.record_naming_failure(str(deliverable["deliverable_id"]), str(error))
        return self.repository.get_by_session(str(deliverable["photoshoot_session_id"]))

    def reconcile_completed(self, *, creator_profile_id: int | None = None):
        output = []
        for session in self.queue.list_sessions(creator_profile_id=creator_profile_id):
            if session.status == "completed":
                output.append(self.complete(session.session_id, session.creator_profile_id)[1])
        return tuple(output)

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

    def ensure_naming_or_raise(self, deliverable, profile):
        if not self.naming.needs_refinement(deliverable.get("ai_title"), deliverable.get("ai_description")):
            return deliverable
        title, description = self.naming.generate(profile, int(deliverable["shot_count"]))
        return self.repository.set_ai_naming(str(deliverable["deliverable_id"]), title, description)

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
