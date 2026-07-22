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
from app.services.photoshoot_summary_service import PhotoshootSummaryService


class PhotoshootCreativeDirectorWorkflowService:
    """Adapts persisted Photoshoot state to the legacy AI services."""

    def __init__(self, *, queue=None, library=None, creative_director=None, summary_service=None):
        self.queue = queue or PhotoshootQueueService()
        self.library = library or GenerationLibraryService()
        self.creative_director = creative_director or CreativeDirectorService()
        self.summary = summary_service or PhotoshootSummaryService(queue=self.queue)

    def context(self, *, creator_profile_id: int, session_id: str | None = None) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        photoshoot_summary = dict(continuity.get("photoshoot_summary") or {})
        planning_mode = str(continuity.get("planning_mode") or "frame_by_frame").strip().lower()
        if planning_mode not in {"frame_by_frame", "full_plan"}:
            planning_mode = "frame_by_frame"
        session_plan = [dict(item) for item in tuple(continuity.get("session_plan") or ()) if isinstance(item, Mapping)]
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
            "photoshoot_summary": photoshoot_summary,
            "planning_mode": planning_mode,
            "plan_frame_count": max(4, min(12, int(continuity.get("plan_frame_count") or 8))),
            "session_plan": session_plan,
            "session_plan_index": max(0, int(continuity.get("session_plan_index") or 0)),
            "session_plan_approved": bool(continuity.get("session_plan_approved")),
            "recommendation_state": {
                "inspiration_ideas": list(continuity.get("inspiration_ideas") or ()),
                "selected_inspiration": str(continuity.get("selected_inspiration") or ""),
                "recommendation": dict(continuity.get("current_direction") or {}),
                "direction_approved": bool(continuity.get("direction_approved")),
            },
        }

    def set_planning_mode(
        self,
        *,
        creator_profile_id: int,
        session_id: str,
        planning_mode: str,
        plan_frame_count: int = 8,
    ) -> dict[str, Any]:
        self._session(creator_profile_id, session_id)
        mode = str(planning_mode or "frame_by_frame").strip().lower()
        if mode not in {"frame_by_frame", "full_plan"}:
            mode = "frame_by_frame"
        count = max(4, min(12, int(plan_frame_count or 8)))
        if mode == "frame_by_frame":
            self.queue.update_session_settings(
                session_id,
                planning_mode=mode,
                plan_frame_count=count,
                session_plan=(),
                session_plan_index=0,
                session_plan_approved=False,
                workflow_stage="ready_for_direction",
            )
        else:
            self.queue.update_session_settings(
                session_id,
                planning_mode=mode,
                plan_frame_count=count,
                session_plan_approved=False,
            )
        continuity = dict((self.queue.get_session(session_id).creative_continuity or {}))
        plan = [dict(item) for item in tuple(continuity.get("session_plan") or ()) if isinstance(item, Mapping)]
        return {
            "planning_mode": mode,
            "plan_frame_count": count,
            "session_plan": [] if mode == "frame_by_frame" else plan,
            "session_plan_approved": False if mode == "frame_by_frame" else bool(continuity.get("session_plan_approved")),
        }

    def generate_session_plan(
        self,
        *,
        creator_profile_id: int,
        session_id: str,
        creative_mode: str,
        creator_guidance: str,
        continuity_locks: Mapping[str, bool],
        plan_frame_count: int = 8,
    ) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        session = self.queue.update_session_settings(
            session_id,
            creative_mode=creative_mode,
            planning_mode="full_plan",
            plan_frame_count=plan_frame_count,
            creator_guidance=creator_guidance,
            grok_guidance=creator_guidance,
            continuity_locks=continuity_locks,
        )
        continuity = dict(session.creative_continuity or {})
        summary = self.summary.refresh(session.session_id)
        current, _timeline = self._vision_context(session)
        image_bytes, mime_type = self._image_bytes(current.output_reference)
        original_direction = self._original_direction(session)
        ai_context = self._ai_context(
            original_direction,
            summary,
            creator_guidance,
            progression_stage=int(continuity.get("progression_stage") or 0),
            timeline_image_count=1,
        )
        plan = self.creative_director.plan_full_photoshoot_session(
            image_bytes=image_bytes,
            image_mime_type=mime_type,
            session_context=ai_context,
            creative_mode=session.creative_mode,
            session_direction=original_direction,
            creator_guidance=creator_guidance,
            continuity_locks=continuity_locks,
            frame_count=int(continuity.get("plan_frame_count") or plan_frame_count or 8),
        )
        plan_list = [dict(item) for item in plan]
        self.queue.clear_workspace_state(session_id, workflow_stage="session_plan_ready")
        self.queue.update_session_settings(
            session_id,
            planning_mode="full_plan",
            plan_frame_count=len(plan_list),
            session_plan=plan_list,
            session_plan_index=0,
            session_plan_approved=False,
            creator_guidance=creator_guidance,
            grok_guidance=creator_guidance,
            continuity_locks=continuity_locks,
            creative_hint="",
            selected_inspiration="",
            inspiration_ideas=(),
            workflow_stage="session_plan_ready",
        )
        return {
            "planning_mode": "full_plan",
            "plan_frame_count": len(plan_list),
            "session_plan": plan_list,
            "session_plan_index": 0,
            "session_plan_approved": False,
        }

    def approve_session_plan(self, *, creator_profile_id: int, session_id: str) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        plan = [dict(item) for item in tuple(continuity.get("session_plan") or ()) if isinstance(item, Mapping)]
        if not plan:
            raise ValueError("Generate a full session plan before approving it.")
        for index, item in enumerate(plan):
            item["status"] = "current" if index == 0 else "pending"
        self.queue.update_session_settings(
            session_id,
            session_plan=plan,
            session_plan_index=0,
            session_plan_approved=True,
            planning_mode="full_plan",
            workflow_stage="session_plan_approved",
        )
        return {
            "session_plan": plan,
            "session_plan_index": 0,
            "session_plan_approved": True,
            "workflow_stage": "session_plan_approved",
        }

    def develop_planned_shot(self, *, creator_profile_id: int, session_id: str) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        if str(continuity.get("planning_mode") or "") != "full_plan":
            raise ValueError("Full session plan mode is required to develop a planned shot.")
        if not continuity.get("session_plan_approved"):
            raise ValueError("Approve the session plan before developing planned shots.")
        plan = [dict(item) for item in tuple(continuity.get("session_plan") or ()) if isinstance(item, Mapping)]
        index = max(0, int(continuity.get("session_plan_index") or 0))
        if index >= len(plan):
            raise ValueError("All planned shots have already been developed.")
        item = plan[index]
        direction = str(item.get("creative_direction") or "").strip()
        if not direction:
            raise ValueError("The current planned shot is missing a creative direction.")
        recommendation = {
            "title": str(item.get("title") or f"Shot {index + 1}").strip(),
            "creative_direction": direction,
            "reasoning": str(item.get("reasoning") or "Taken from the approved full session plan.").strip(),
            "continuity_notes": str(item.get("continuity_notes") or "Preserve locked continuity.").strip(),
            "camera_framing": str(item.get("camera_framing") or "").strip(),
            "lighting": str(item.get("lighting") or "").strip(),
            "emotion": str(item.get("emotion") or "").strip(),
            "pose_composition": str(item.get("pose_composition") or "").strip(),
            "creative_mode": session.creative_mode,
            "session_direction": self._original_direction(session),
            "continuity_locks": dict(continuity.get("continuity_locks") or {}),
        }
        for position, planned in enumerate(plan):
            if position < index:
                planned["status"] = "completed"
            elif position == index:
                planned["status"] = "current"
            else:
                planned["status"] = "pending"
        self.queue.update_session_settings(
            session_id,
            session_plan=plan,
            session_plan_index=index,
            creative_hint=direction,
            selected_inspiration=direction,
            workflow_stage="plan_shot_ready",
        )
        self.queue.record_pending_recommendation(session_id=session_id, recommendation=recommendation)
        return recommendation

    def advance_session_plan(self, *, creator_profile_id: int, session_id: str) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        plan = [dict(item) for item in tuple(continuity.get("session_plan") or ()) if isinstance(item, Mapping)]
        index = max(0, int(continuity.get("session_plan_index") or 0))
        if plan and index < len(plan):
            plan[index]["status"] = "completed"
            index += 1
        if index < len(plan):
            plan[index]["status"] = "current"
            stage = "session_plan_approved"
            complete = False
        else:
            stage = "session_plan_complete"
            complete = True
        self.queue.clear_workspace_state(session_id, workflow_stage=stage)
        self.queue.update_session_settings(
            session_id,
            session_plan=plan,
            session_plan_index=index,
            session_plan_approved=True,
            planning_mode="full_plan",
            creative_hint="",
            selected_inspiration="",
            inspiration_ideas=(),
            workflow_stage=stage,
        )
        next_item = plan[index] if index < len(plan) else None
        return {
            "session_plan": plan,
            "session_plan_index": index,
            "session_plan_complete": complete,
            "next_planned_shot": next_item,
            "workflow_stage": stage,
        }

    def inspiration(self, *, creator_profile_id: int, session_id: str, creative_mode: str,
                    creator_guidance: str, provider_context: str,
                    continuity_locks: Mapping[str, bool]) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        session = self.queue.update_session_settings(session_id, creative_mode=creative_mode)
        continuity = dict(session.creative_continuity or {})
        summary = self.summary.refresh(session.session_id)
        current, timeline = self._vision_context(session)
        image_bytes, mime_type = self._image_bytes(current.output_reference)
        if not timeline:
            timeline = [{"bytes": image_bytes, "mime_type": mime_type, "label": "Current shot"}]
        original_direction = self._original_direction(session)
        approved_history = self._approved_history(continuity)
        ai_context = self._ai_context(
            original_direction,
            summary,
            creator_guidance,
            progression_stage=int(continuity.get("progression_stage") or 0),
            timeline_image_count=len(timeline),
        )
        ideas = self.creative_director.suggest_photoshoot_inspiration(
            image_bytes=image_bytes, image_mime_type=mime_type,
            session_context=ai_context,
            approved_history=approved_history,
            creative_mode=session.creative_mode, session_direction=original_direction,
            creative_hint="", grok_guidance=creator_guidance,
            continuity_locks=continuity_locks, provider_context=provider_context,
            idea_count=10, timeline_images=tuple(timeline),
        )
        idea_list = [str(item).strip() for item in ideas if str(item or "").strip()]
        # Explicit mode: idea #1 is Grok's recommended natural next progression — pre-select it.
        is_explicit = str(session.creative_mode or "").strip().lower() == "explicit"
        selected = idea_list[0] if is_explicit and idea_list else ""
        stage = "inspiration_selected" if selected else "inspiration_ready"
        self.queue.clear_workspace_state(session_id, workflow_stage=stage)
        self.queue.update_session_settings(
            session_id, creator_guidance=creator_guidance,
            creative_hint=selected, grok_guidance=creator_guidance, inspiration_ideas=idea_list,
            selected_inspiration=selected, continuity_locks=continuity_locks,
            workflow_stage=stage,
        )
        return {"ideas": idea_list, "selected_inspiration": selected}

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
            session_id, creator_guidance=guidance, grok_guidance=guidance,
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
        current, timeline = self._vision_context(session)
        image_bytes, mime_type = self._image_bytes(current.output_reference)
        summary = self.summary.refresh(session.session_id)
        original_direction = self._original_direction(session)
        approved_history = self._approved_history(continuity)
        ai_context = self._ai_context(
            original_direction,
            summary,
            creator_guidance,
            progression_stage=int(continuity.get("progression_stage") or 0),
            timeline_image_count=len(timeline) or 1,
        )
        recommendation = self.creative_director.recommend_photoshoot_direction(
            image_bytes=image_bytes, image_mime_type=mime_type,
            session_context=ai_context,
            approved_history=approved_history,
            creative_mode=session.creative_mode, session_direction=original_direction,
            creative_hint=selected, continuity_locks=continuity_locks,
        )
        payload = asdict(recommendation)
        self.queue.update_session_settings(
            session_id, creator_guidance=creator_guidance,
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

    def _current_record(self, session):
        continuity = dict(session.creative_continuity or {})
        current_id = continuity.get("current_shot_image_id") or continuity.get("seed_image_id")
        if not current_id:
            raise ValueError("Current Photoshoot image is unavailable.")
        return self.library.get(str(current_id))

    @staticmethod
    def _original_direction(session) -> str:
        continuity = dict(session.creative_continuity or {})
        return str(
            continuity.get("original_photoshoot_direction")
            or continuity.get("seed_prompt_text")
            or session.creator_notes
            or "Continue the selected seed as one cohesive photoshoot."
        ).strip()

    @staticmethod
    def _approved_history(continuity: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
        history = []
        for item in tuple(continuity.get("approved_directions") or ()):
            if isinstance(item, Mapping):
                history.append(dict(item))
        return tuple(history)

    @staticmethod
    def _ai_context(
        original_direction: str,
        summary: Mapping[str, Any],
        creator_guidance: str,
        *,
        progression_stage: int = 0,
        timeline_image_count: int = 0,
    ) -> dict[str, Any]:
        return {
            "original_photoshoot_direction": str(original_direction or "").strip(),
            "current_photoshoot_summary": dict(summary or {}),
            "optional_user_guidance": str(creator_guidance or "").strip(),
            "progression_stage": max(0, int(progression_stage or 0)),
            "timeline_image_count": max(0, int(timeline_image_count or 0)),
        }

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
