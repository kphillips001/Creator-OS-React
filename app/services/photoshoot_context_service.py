"""Read-only Photoshoot Studio context aggregation for presentation clients."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from app.models.generation_engine import GenerationType
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService
from app.services.photoshoot_queue_service import PhotoshootQueueService


class PhotoshootContextService:
    """Combines existing Photoshoot state without owning workflow mutations."""

    def __init__(
        self,
        *,
        generation_library: GenerationLibraryService | None = None,
        generation_engine: GenerationEngineService | None = None,
        photoshoot_queue: PhotoshootQueueService | None = None,
    ) -> None:
        self.generation_library = generation_library or GenerationLibraryService()
        self.generation_engine = generation_engine or GenerationEngineService()
        self.photoshoot_queue = photoshoot_queue or PhotoshootQueueService()

    def read(self, *, creator_profile: Mapping[str, Any] | None) -> dict[str, Any]:
        creator_profile_id = int((creator_profile or {}).get("id") or 0)
        session = (
            self.photoshoot_queue.current_session(creator_profile_id=creator_profile_id)
            if creator_profile_id
            else None
        )
        continuity = dict(session.creative_continuity or {}) if session else {}
        pending = self._pending_photoshoot(
            creator_profile_id,
            seed_image_id=str(continuity.get("seed_image_id") or ""),
        ) if creator_profile_id and session else None
        return {
            "creator_profile_exists": bool(creator_profile_id),
            "pending_photoshoot": self._generation_payload(pending),
            "active_session": self._session_payload(session),
            "provider_list": self._provider_list(),
            "creative_mode": str(session.creative_mode or "safe") if session else None,
            "continuity_settings": self._continuity_settings(continuity) if session else None,
            "timeline_summary": self._timeline_summary(session),
        }

    def _pending_photoshoot(self, creator_profile_id: int, *, seed_image_id: str):
        records = tuple(
            record
            for record in self.generation_library.list_records()
            if record.creator_profile_id == int(creator_profile_id)
            and record.status == "pending_photoshoot"
            and record.image_id == seed_image_id
        )
        if not records:
            return None
        return sorted(
            records,
            key=lambda record: (record.updated_at or record.created_at or "", record.image_id),
            reverse=True,
        )[0]

    def _timeline_summary(self, session) -> list[dict[str, Any]]:
        if session is None:
            return []
        items = []
        positions = self.display_timeline_positions(
            self.photoshoot_queue.requests_for_session(session.session_id)
        )
        for shot_number, request in positions:
            if request.status in {"replacement_pending", "continuity_invalidated", "queued", "generating"}:
                items.append({
                    "request_id": request.request_id, "sequence_index": request.sequence_index,
                    "shot_number": shot_number, "label": f"Shot {shot_number}", "is_seed": False,
                    "status": request.status, "image": None,
                })
                continue
            if request.status != "approved":
                continue
            for image_id in tuple((request.metadata or {}).get("generated_image_ids") or ()):
                try:
                    record = self.generation_library.get(str(image_id))
                except KeyError:
                    continue
                is_seed = bool((request.metadata or {}).get("is_seed_image"))
                items.append({
                    "request_id": request.request_id,
                    "sequence_index": request.sequence_index,
                    "shot_number": shot_number,
                    "label": f"Shot {shot_number}" + (" (Seed)" if is_seed else ""),
                    "is_seed": is_seed,
                    "status": "approved",
                    "image": self._generation_payload(record),
                })
        return items

    @staticmethod
    def display_timeline_positions(requests) -> tuple[tuple[int, Any], ...]:
        """Return presentation-only shot ordinals without counting failed attempts."""
        requests_by_position = {}
        for fallback_position, request in enumerate(requests, start=1):
            metadata = dict(getattr(request, "metadata", None) or {})
            is_replacement_work = bool(metadata.get("replaces_request_id"))
            if request.status in {"approved", "replacement_pending", "continuity_invalidated"} or (is_replacement_work and request.status in {"queued", "generating"}):
                requests_by_position[int(getattr(request, "sequence_index", fallback_position))] = request
        visible_requests = tuple(requests_by_position[index] for index in sorted(requests_by_position))
        return tuple(enumerate(visible_requests, start=1))

    @classmethod
    def approved_display_count(cls, requests) -> int:
        return sum(
            1 for _shot_number, request in cls.display_timeline_positions(requests)
            if request.status == "approved"
        )

    def _provider_list(self) -> list[dict[str, str]]:
        return [
            {"value": metadata.provider_id, "label": metadata.display_name}
            for metadata in self.generation_engine.provider_registry.metadata()
            if metadata.enabled
            and metadata.capabilities.supports_images
            and GenerationType.IMAGE_TO_IMAGE.value
            in metadata.capabilities.supported_generation_types
        ]

    @staticmethod
    def _continuity_settings(continuity: Mapping[str, Any]) -> dict[str, bool]:
        locks = dict(continuity.get("continuity_locks") or {})
        return {
            "location": bool(locks.get("location", True)),
            "wardrobe": bool(locks.get("wardrobe", True)),
            "lighting": bool(locks.get("lighting", True)),
            "hairstyle": bool(locks.get("hairstyle", True)),
            "makeup": bool(locks.get("makeup", True)),
            "camera_style": bool(locks.get("camera_style", True)),
        }

    @classmethod
    def _session_payload(cls, session) -> dict[str, Any] | None:
        if session is None:
            return None
        payload = asdict(session)
        payload["continuity_locks"] = cls._continuity_settings(
            dict(session.creative_continuity or {})
        )
        return payload

    @staticmethod
    def _generation_payload(record) -> dict[str, Any] | None:
        if record is None:
            return None
        payload = asdict(record)
        output_reference = str(record.output_reference or "")
        version = str(record.updated_at or record.generation_date or record.image_id)
        payload["image_url"] = (
            output_reference
            if output_reference.startswith(("http://", "https://", "data:"))
            else f"/api/v1/generation-library/{record.image_id}/media?v={version}"
        )
        return payload
