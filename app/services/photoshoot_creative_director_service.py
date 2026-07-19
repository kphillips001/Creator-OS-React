"""HTTP orchestration for the existing Photoshoot Creative Director workflow."""

from __future__ import annotations

import base64
import json
import mimetypes
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from app.services.creative_director_service import CreativeDirectorService
from app.services.generation_library_service import GenerationLibraryService
from app.services.photoshoot_queue_service import PhotoshootQueueService


class PhotoshootCreativeDirectorWorkflowService:
    """Adapts persisted Photoshoot state to the legacy AI services."""

    def __init__(self, *, queue=None, library=None, creative_director=None):
        self.queue = queue or PhotoshootQueueService()
        self.library = library or GenerationLibraryService()
        self.creative_director = creative_director or CreativeDirectorService()

    def context(self, *, creator_profile_id: int, session_id: str | None = None) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        return {
            "current_session": asdict(session),
            "session_id": session.session_id,
            "creative_mode": session.creative_mode,
            "creator_guidance": str(continuity.get("creator_guidance") or continuity.get("grok_guidance") or ""),
            "current_direction": dict(continuity.get("current_direction") or {}),
            "current_prompt": str(continuity.get("current_prompt") or ""),
            "creative_hint": str(continuity.get("creative_hint") or ""),
            "grok_guidance": str(continuity.get("grok_guidance") or ""),
            "workflow_stage": str(continuity.get("workflow_stage") or "ready_for_direction"),
            "continuity_locks": dict(continuity.get("continuity_locks") or {}),
            "recommendation_state": {
                "inspiration_ideas": list(continuity.get("inspiration_ideas") or ()),
                "selected_inspiration": str(continuity.get("selected_inspiration") or ""),
                "recommendation": dict(continuity.get("current_direction") or {}),
                "direction_approved": bool(continuity.get("direction_approved")),
            },
        }

    def inspiration(self, *, creator_profile_id: int, session_id: str, creative_mode: str,
                    creator_guidance: str, provider_context: str,
                    continuity_locks: Mapping[str, bool]) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        session = self.queue.update_session_settings(session_id, creative_mode=creative_mode)
        continuity = dict(session.creative_continuity or {})
        current, timeline = self._vision_context(session)
        image_bytes, mime_type = self._image_bytes(current.output_reference)
        ideas = self.creative_director.suggest_photoshoot_inspiration(
            image_bytes=image_bytes, image_mime_type=mime_type,
            session_context=continuity,
            approved_history=tuple(continuity.get("approved_directions") or ()),
            creative_mode=session.creative_mode, session_direction=creator_guidance,
            creative_hint="", grok_guidance=creator_guidance,
            continuity_locks=continuity_locks, provider_context=provider_context,
            idea_count=10, timeline_images=timeline,
        )
        self.queue.clear_workspace_state(session_id, workflow_stage="inspiration_ready")
        self.queue.update_session_settings(
            session_id, session_direction=creator_guidance, creator_guidance=creator_guidance,
            creative_hint="", grok_guidance=creator_guidance, inspiration_ideas=ideas,
            selected_inspiration="", continuity_locks=continuity_locks,
            workflow_stage="inspiration_ready",
        )
        return {"ideas": list(ideas), "selected_inspiration": ""}

    def select_inspiration(self, *, creator_profile_id: int, session_id: str, idea: str) -> dict[str, str]:
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        selected = str(idea or "").strip()
        if selected not in tuple(continuity.get("inspiration_ideas") or ()):
            raise ValueError("Select an inspiration idea returned for this Photoshoot session.")
        self.queue.update_session_settings(
            session_id, creative_hint=selected, selected_inspiration=selected,
            workflow_stage="inspiration_selected",
        )
        return {"selected_inspiration": selected, "creative_hint": selected}

    def save_guidance(self, *, creator_profile_id: int, session_id: str, creator_guidance: str) -> dict[str, str]:
        self._session(creator_profile_id, session_id)
        guidance = str(creator_guidance or "")
        self.queue.update_session_settings(
            session_id, creator_guidance=guidance, session_direction=guidance, grok_guidance=guidance,
        )
        return {"creator_guidance": guidance}

    def recommendation(self, *, creator_profile_id: int, session_id: str, creative_mode: str,
                       creator_guidance: str, continuity_locks: Mapping[str, bool]):
        session = self._session(creator_profile_id, session_id)
        session = self.queue.update_session_settings(session_id, creative_mode=creative_mode)
        continuity = dict(session.creative_continuity or {})
        selected = str(continuity.get("selected_inspiration") or "").strip()
        if not selected or selected not in tuple(continuity.get("inspiration_ideas") or ()):
            raise ValueError("Select an AI idea before developing the next shot.")
        current, _ = self._vision_context(session)
        image_bytes, mime_type = self._image_bytes(current.output_reference)
        recommendation = self.creative_director.recommend_photoshoot_direction(
            image_bytes=image_bytes, image_mime_type=mime_type,
            session_context=continuity,
            approved_history=tuple(continuity.get("approved_directions") or ()),
            creative_mode=session.creative_mode, session_direction=creator_guidance,
            creative_hint=selected, continuity_locks=continuity_locks,
        )
        payload = asdict(recommendation)
        self.queue.update_session_settings(
            session_id, session_direction=creator_guidance, creator_guidance=creator_guidance,
            creative_hint=selected, selected_inspiration=selected, continuity_locks=continuity_locks,
        )
        self.queue.record_pending_recommendation(session_id=session_id, recommendation=payload)
        return payload

    def choose_another(self, *, creator_profile_id: int, session_id: str) -> dict[str, str]:
        self._session(creator_profile_id, session_id)
        self.queue.clear_workspace_state(session_id, workflow_stage="inspiration_ready")
        self.queue.update_session_settings(session_id, creative_hint="", selected_inspiration="")
        return {"workflow_stage": "inspiration_ready", "selected_inspiration": ""}

    def approve(self, *, creator_profile_id: int, session_id: str) -> dict[str, str]:
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        recommendation = dict(continuity.get("current_direction") or {})
        if not recommendation:
            raise ValueError("Generate a Creative Director recommendation before approving it.")
        current, _ = self._vision_context(session)
        direction = self._direction_text(recommendation)
        creative_tags = "\n".join((
            "Photoshoot Studio continuation.", f"Creative direction: {direction}",
            f"Seed image context: {str(current.prompt_text or '').strip() or 'Use the selected image as the canonical visual reference.'}",
            f"Session continuity: {json.dumps(continuity, ensure_ascii=True, default=str)}",
            "Preserve continuity defaults unless the Session Direction explicitly overrides them.",
        ))
        result = self.creative_director.plan_prompts(
            mode="explicit" if session.creative_mode.lower() == "explicit" else "photoshoot",
            creative_tags=creative_tags, prompt_count=1, optional_direction=direction,
            metadata={"source": "photoshoot_studio"},
        )
        if not result.prompts:
            raise ValueError("Canonical Prompt Planner did not return a Photoshoot prompt.")
        prompt = result.prompts[0]
        self.queue.record_creative_direction(
            session_id=session_id, recommendation=recommendation, final_prompt=prompt,
        )
        return {"prompt": prompt, "workflow_stage": "direction_approved"}

    def _session(self, creator_profile_id: int, session_id: str | None):
        session = self.queue.get_session(session_id) if session_id else self.queue.current_session(creator_profile_id=creator_profile_id)
        if session is None or session.creator_profile_id != int(creator_profile_id):
            raise KeyError("Photoshoot Session not found.")
        return session

    def _vision_context(self, session):
        continuity = dict(session.creative_continuity or {})
        current_id = continuity.get("current_shot_image_id") or continuity.get("seed_image_id")
        if not current_id:
            raise ValueError("Current Photoshoot image is unavailable.")
        current = self.library.get(str(current_id))
        timeline = []
        approved = [item for item in self.queue.requests_for_session(session.session_id) if item.status == "approved"]
        for shot_number, request in enumerate(approved, start=1):
            for image_id in tuple(dict(request.metadata or {}).get("generated_image_ids") or ()):
                try:
                    record = self.library.get(str(image_id))
                    raw, mime = self._image_bytes(record.output_reference)
                except (KeyError, OSError, ValueError):
                    continue
                label = f"Shot {shot_number}" + (" (Seed)" if dict(request.metadata or {}).get("is_seed_image") else "")
                if str(image_id) == str(current_id):
                    label += " — current"
                timeline.append({"bytes": raw, "mime_type": mime, "label": label})
        return current, timeline

    @staticmethod
    def _direction_text(recommendation: Mapping[str, Any]) -> str:
        values = (
            recommendation.get("creative_direction"),
            f"Camera framing: {recommendation.get('camera_framing')}" if recommendation.get("camera_framing") else "",
            f"Lighting: {recommendation.get('lighting')}" if recommendation.get("lighting") else "",
            f"Emotion: {recommendation.get('emotion')}" if recommendation.get("emotion") else "",
            f"Pose/composition: {recommendation.get('pose_composition')}" if recommendation.get("pose_composition") else "",
            f"Continuity notes: {recommendation.get('continuity_notes')}" if recommendation.get("continuity_notes") else "",
        )
        return "\n".join(str(value).strip() for value in values if str(value or "").strip())

    @staticmethod
    def _image_bytes(reference: str) -> tuple[bytes, str]:
        source = str(reference or "").strip()
        if source.startswith("data:"):
            header, _, encoded = source.partition(",")
            return base64.b64decode(encoded), header.removeprefix("data:").split(";")[0] or "image/png"
        if source.startswith(("http://", "https://")):
            with urllib.request.urlopen(source, timeout=20) as response:
                return response.read(), response.headers.get_content_type() or "image/png"
        path = Path(source).expanduser()
        if not path.is_file():
            raise ValueError(f"Current image file was not found: {source}")
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "image/png"
