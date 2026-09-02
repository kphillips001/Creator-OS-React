"""Canonical Photoshoot member extraction into standalone Asset Library Images."""
from __future__ import annotations

import hashlib

from app.models.content_intelligence_profile import is_content_intelligence_complete
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


class PhotoshootMemberCurationService:
    MINIMUM_MEMBER_COUNT = 2

    def __init__(self, *, repository=None, deliverables=None):
        self.repository = repository or PhotoshootCommerceRepository()
        self.deliverables = deliverables or PhotoshootCommerceDeliverableService(
            repository=self.repository)

    def inspect(self, deliverable_id: str, *, creator_profile_id: int) -> dict:
        deliverable = self._deliverable(deliverable_id, creator_profile_id)
        members = tuple(self.repository.members(str(deliverable["photoshoot_session_id"])))
        blockers = dict(self.repository.member_curation_blockers(
            deliverable_id, creator_profile_id) or {})
        protected = any(int(blockers.get(key) or 0) for key in (
            "offering_count", "publication_count", "purchase_count", "teaser_count",
            "lifecycle_count"))
        in_asset_library = str(deliverable.get("registration_state") or "") == "IN_ASSET_LIBRARY"
        eligible = in_asset_library and not protected and len(members) > self.MINIMUM_MEMBER_COUNT
        reason = None
        if not in_asset_library:
            reason = "Add this Photoshoot to Asset Library before curating its members."
        elif protected:
            reason = "This Photoshoot has commercial activity and its members cannot be changed."
        elif len(members) <= self.MINIMUM_MEMBER_COUNT:
            reason = "A Photoshoot must retain at least 2 images."
        return {"eligible": eligible, "reason": reason,
                "memberCount": len(members),
                "maximumExtractable": max(0, len(members) - self.MINIMUM_MEMBER_COUNT)}

    def move_to_images(self, deliverable_id: str, *, creator_profile_id: int,
                       asset_ids) -> dict:
        requested = tuple(int(value) for value in asset_ids)
        if not requested:
            raise ValueError("Select at least one Photoshoot image.")
        if len(set(requested)) != len(requested):
            raise ValueError("Selected Asset IDs must be unique.")
        deliverable = self._deliverable(deliverable_id, creator_profile_id)
        if str(deliverable.get("registration_state") or "") != "IN_ASSET_LIBRARY":
            raise ValueError("Add this Photoshoot to Asset Library before curating its members.")
        session_id = str(deliverable["photoshoot_session_id"])
        members = tuple(self.repository.intelligence_members(session_id))
        member_ids = tuple(int(row["asset_id"]) for row in members)
        selected_members = tuple(value for value in requested if value in member_ids)
        if not selected_members:
            if self.repository.extracted_assets_are_standalone(requested, creator_profile_id):
                return self._result(deliverable, requested, member_ids, already_moved=True)
            raise ValueError("Selected Assets are not members of this Photoshoot.")
        if len(selected_members) != len(requested):
            raise ValueError("Selected Assets must all belong to this Photoshoot.")
        if len(member_ids) - len(requested) < self.MINIMUM_MEMBER_COUNT:
            raise ValueError("A Photoshoot must retain at least 2 images.")
        curation = self.inspect(deliverable_id, creator_profile_id=creator_profile_id)
        if not curation["eligible"]:
            raise ValueError(str(curation["reason"]))
        remaining = tuple(row for row in members if int(row["asset_id"]) not in set(requested))
        incomplete = [int(row["asset_id"]) for row in remaining
                      if not is_content_intelligence_complete(row.get("content_intelligence_status"))]
        if incomplete:
            raise ValueError("Remaining Photoshoot members require complete Content Intelligence.")
        hero_asset_id = int(deliverable["hero_asset_id"]) if deliverable.get("hero_asset_id") else None
        remaining_ids = tuple(int(row["asset_id"]) for row in remaining)
        if hero_asset_id not in remaining_ids:
            hero_asset_id = remaining_ids[0]
        version = self._version(remaining_ids)
        chapters = tuple({
            "asset_id": int(row["asset_id"]), "shot_order": position,
            "is_seed": int(row["asset_id"]) == hero_asset_id,
            "image_reference": row.get("file_path"),
            "approved_prompt": dict(row.get("media_metadata") or {}).get("prompt"),
            "approved_metadata": dict(row.get("media_metadata") or {}),
            "canonical_content_intelligence": dict(row.get("content_profile") or {}),
            "canonical_normalized_context": dict(row.get("normalized_context") or {}),
        } for position, row in enumerate(remaining, 1))
        profile = self.deliverables.build_source_neutral_intelligence(
            chapters=chapters,
            display_name=str(deliverable["display_name"]), hero_asset_id=hero_asset_id,
            source_kind=str(deliverable.get("source_kind") or "PHOTOSHOOT_STUDIO"),
            intelligence_version=version)
        applied = self.repository.apply_member_extraction(
            deliverable_id=deliverable_id, creator_profile_id=creator_profile_id,
            asset_ids=requested, intelligence_version=version,
            intelligence_profile=profile)
        return self._result(applied["deliverable"], requested,
                            applied["remaining_asset_ids"], already_moved=False)

    def _deliverable(self, deliverable_id: str, creator_profile_id: int):
        deliverable = self.repository.get(deliverable_id)
        if (deliverable is None or int(deliverable["creator_profile_id"]) != int(creator_profile_id)
                or bool(deliverable.get("is_archived"))):
            raise KeyError("Photoshoot not found.")
        return deliverable

    @staticmethod
    def _version(asset_ids) -> str:
        digest = hashlib.sha256(",".join(str(value) for value in asset_ids).encode()).hexdigest()[:12]
        return f"completed_photoshoot_v2:curated:{digest}"

    @staticmethod
    def _result(deliverable, moved, remaining, *, already_moved: bool):
        return {"deliverableId": str(deliverable["deliverable_id"]),
                "movedAssetIds": list(moved), "movedCount": len(moved),
                "remainingAssetIds": list(remaining), "shotCount": len(remaining),
                "heroAssetId": int(deliverable["hero_asset_id"]),
                "sourceKind": str(deliverable.get("source_kind") or "PHOTOSHOOT_STUDIO"),
                "alreadyMoved": already_moved}
