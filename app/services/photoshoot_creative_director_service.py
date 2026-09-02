"""HTTP orchestration for the existing Photoshoot Creative Director workflow."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
import urllib.request
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from app.models.creative_director import new_id
from app.models.render_policy import photoshoot_planning_mode
from app.models.photoshoot_queue import (
    CanonicalPhotoshootSeedSummary, PhotoshootPlanningContext, normalize_target_shot_count,
)
from app.services.creative_director_service import CreativeDirectorService
from app.services.generation_library_service import GenerationLibraryService
from app.services.photoshoot_expression_guidance import normalize_photoshoot_emotion
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_summary_service import PhotoshootSummaryService
from app.services.photoshoot_context_service import PhotoshootContextService

LOGGER = logging.getLogger("creator_os.photoshoot.approve")


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
        planning = self._planning_progress(session)
        ideas_are_current = int(continuity.get("inspiration_planning_shot") or 0) == planning["planning_shot"]
        freeflow_idea_set = self._freeflow_idea_set_payload(session, continuity)
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
            "target_shot_count": normalize_target_shot_count(session.target_shot_count),
            "current_shot": planning["current_shot"],
            "planning_shot": planning["planning_shot"],
            "remaining_shots": planning["remaining_shots"],
            "editorial_stage": planning["editorial_stage"],
            "planner_explanation": self._planner_explanation(planning),
            "session_plan": session_plan,
            "session_plan_index": max(0, int(continuity.get("session_plan_index") or 0)),
            "session_plan_approved": bool(continuity.get("session_plan_approved")),
            "freeflow_idea_set": freeflow_idea_set,
            "recommendation_state": {
                "inspiration_ideas": list(continuity.get("inspiration_ideas") or ()) if ideas_are_current else [],
                "selected_inspiration": str(continuity.get("selected_inspiration") or "") if ideas_are_current else "",
                "inspiration_edits": dict(continuity.get("inspiration_edits") or {}) if ideas_are_current else {},
                "recommendation": dict(continuity.get("current_direction") or {}) if ideas_are_current else {},
                "direction_approved": bool(continuity.get("direction_approved")) if ideas_are_current else False,
            },
        }

    def set_planning_mode(
        self,
        *,
        creator_profile_id: int,
        session_id: str,
        planning_mode: str,
        plan_frame_count: int = 8,
        target_shot_count: int = 5,
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
                target_shot_count=target_shot_count,
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
                target_shot_count=target_shot_count,
                session_plan_approved=False,
            )
        continuity = dict((self.queue.get_session(session_id).creative_continuity or {}))
        plan = [dict(item) for item in tuple(continuity.get("session_plan") or ()) if isinstance(item, Mapping)]
        return {
            "planning_mode": mode,
            "plan_frame_count": count,
            "target_shot_count": normalize_target_shot_count(target_shot_count),
            "session_plan": [] if mode == "frame_by_frame" else plan,
            "session_plan_approved": False if mode == "frame_by_frame" else bool(continuity.get("session_plan_approved")),
        }

    def set_target_shot_count(
        self,
        *,
        creator_profile_id: int,
        session_id: str,
        target_shot_count: int,
    ) -> dict[str, int]:
        self._session(creator_profile_id, session_id)
        session = self.queue.update_session_settings(
            session_id,
            target_shot_count=target_shot_count,
        )
        return {"target_shot_count": session.target_shot_count}

    def extend_photoshoot(self, *, creator_profile_id: int, session_id: str,
                          expected_target_shot_count: int) -> dict[str, Any]:
        self._session(creator_profile_id, session_id)
        session, extended = self.queue.extend_target_one_shot(
            session_id, expected_target_shot_count=expected_target_shot_count,
        )
        progress = self._planning_progress(session)
        return {
            "target_shot_count": session.target_shot_count,
            "extended": extended,
            "current_shot": progress["current_shot"],
            "planning_shot": progress["planning_shot"],
            "remaining_shots": progress["remaining_shots"],
            "editorial_stage": progress["editorial_stage"],
            "workflow_stage": "ready_for_next_shot",
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
        target_shot_count: int = 5,
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
            target_shot_count=target_shot_count,
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
            latest_approved_shot=self._latest_approved_shot_summary(session, summary),
            progression_stage=int(continuity.get("progression_stage") or 0),
            current_shot=1,
            planning_shot=2,
            editorial_stage="Beginning",
            timeline_image_count=1,
            target_shot_count=session.target_shot_count,
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
            "emotion": normalize_photoshoot_emotion(
                item.get("emotion"),
                creative_mode=session.creative_mode,
            ),
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
                    continuity_locks: Mapping[str, bool], target_shot_count: int = 5) -> dict[str, Any]:
        session = self._session(creator_profile_id, session_id)
        session = self.queue.update_session_settings(
            session_id, creative_mode=creative_mode, target_shot_count=target_shot_count,
        )
        continuity = dict(session.creative_continuity or {})
        summary = self.summary.refresh(session.session_id)
        current, timeline = self._vision_context(session)
        image_bytes, mime_type = self._image_bytes(current.output_reference)
        if not timeline:
            timeline = [{"bytes": image_bytes, "mime_type": mime_type, "label": "Current shot"}]
        original_direction = self._original_direction(session)
        approved_history = self._approved_history(continuity)
        planning = self._planning_progress(session)
        if planning["target_shot_count"] > 0 and planning["current_shot"] >= planning["target_shot_count"]:
            raise ValueError("The target Photoshoot length has been reached.")
        ai_context = self._ai_context(
            original_direction,
            summary,
            creator_guidance,
            latest_approved_shot=self._latest_approved_shot_summary(session, summary),
            progression_stage=int(continuity.get("progression_stage") or 0),
            current_shot=planning["current_shot"],
            planning_shot=planning["planning_shot"],
            editorial_stage=planning["editorial_stage"],
            timeline_image_count=len(timeline),
            target_shot_count=session.target_shot_count,
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
            inspiration_planning_shot=planning["planning_shot"],
            selected_inspiration=selected, continuity_locks=continuity_locks,
            inspiration_edits={},
            workflow_stage=stage,
        )
        idea_set = None
        planning_mode = str(continuity.get("planning_mode") or "frame_by_frame").strip().lower()
        if session.target_shot_count == 0 and planning_mode == "frame_by_frame" and idea_list:
            idea_set_id = new_id("freeflow_ideas")
            self.queue.record_freeflow_idea_set(
                session_id, idea_set_id=idea_set_id, ideas=idea_list,
                recommended_idea=idea_list[0], planning_shot=planning["planning_shot"],
            )
            persisted = self.queue.get_session(session_id)
            idea_set = self._freeflow_idea_set_payload(persisted, dict(persisted.creative_continuity or {}))
        return {"ideas": idea_list, "selected_inspiration": selected, "freeflow_idea_set": idea_set}

    def existing_inspiration(self, *, creator_profile_id: int, session_id: str) -> dict[str, Any]:
        """Reactivate the newest persisted Freeflow idea set without invoking AI."""
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        planning_mode = str(continuity.get("planning_mode") or "frame_by_frame").strip().lower()
        if session.target_shot_count != 0 or planning_mode != "frame_by_frame":
            raise ValueError("Existing AI ideas are available only in Creative Freeflow.")
        sets = [dict(item) for item in tuple(continuity.get("freeflow_idea_sets") or ()) if isinstance(item, Mapping)]
        if not sets:
            raise ValueError("No persisted Creative Freeflow ideas are available.")
        latest = sets[-1]
        idea_set_id = str(latest.get("idea_set_id") or "")
        planning = self._planning_progress(session)
        self.queue.activate_freeflow_idea_set(
            session_id, idea_set_id=idea_set_id, planning_shot=planning["planning_shot"],
        )
        restored = self.queue.get_session(session_id)
        restored_continuity = dict(restored.creative_continuity or {})
        return {
            "ideas": list(restored_continuity.get("inspiration_ideas") or ()),
            "selected_inspiration": "",
            "freeflow_idea_set": self._freeflow_idea_set_payload(restored, restored_continuity),
        }

    def _freeflow_idea_set_payload(self, session, continuity: Mapping[str, Any]) -> dict[str, Any] | None:
        sets = [dict(item) for item in tuple(continuity.get("freeflow_idea_sets") or ()) if isinstance(item, Mapping)]
        planning_mode = str(continuity.get("planning_mode") or "frame_by_frame").strip().lower()
        if session.target_shot_count != 0 or planning_mode != "frame_by_frame" or not sets:
            return None
        latest = sets[-1]
        idea_set_id = str(latest.get("idea_set_id") or "")
        usage: dict[str, list[str]] = {}
        positions = {request.request_id: shot for shot, request in PhotoshootContextService.display_timeline_positions(self.queue.requests_for_session(session.session_id))}
        for request in self.queue.requests_for_session(session.session_id):
            metadata = dict(request.metadata or {})
            if str(metadata.get("inspiration_idea_set_id") or "") != idea_set_id:
                continue
            idea = str(metadata.get("selected_inspiration") or "").strip()
            if not idea:
                continue
            label = f"Shot {positions[request.request_id]}" if request.request_id in positions and request.status == "approved" else "Generated"
            if label not in usage.setdefault(idea, []):
                usage[idea].append(label)
        return {
            "idea_set_id": idea_set_id,
            "ideas": list(latest.get("ideas") or ()),
            "recommended_idea": str(latest.get("recommended_idea") or ""),
            "planning_shot": int(latest.get("planning_shot") or 0),
            "approved_shot_count": int(latest.get("approved_shot_count") or 0),
            "created_at": str(latest.get("created_at") or ""),
            "usage": usage,
        }

    def select_inspiration(self, *, creator_profile_id: int, session_id: str, idea: str,
                           edited_direction: str = "") -> dict[str, str]:
        session = self._session(creator_profile_id, session_id)
        continuity = dict(session.creative_continuity or {})
        planning = self._planning_progress(session)
        if int(continuity.get("inspiration_planning_shot") or 0) != planning["planning_shot"]:
            raise ValueError("These AI ideas belong to a different Photoshoot position. Ask AI again.")
        selected = str(idea or "").strip()
        if selected not in tuple(continuity.get("inspiration_ideas") or ()):
            raise ValueError("Select an inspiration idea returned for this Photoshoot session.")
        edits_by_idea = dict(continuity.get("inspiration_edits") or {})
        edited = str(edited_direction or "").strip()
        if edited and edited != selected:
            edits_by_idea[selected] = edited
        else:
            edits_by_idea.pop(selected, None)
        effective = edits_by_idea.get(selected) or selected
        self.queue.update_session_settings(
            session_id, creative_hint=effective, selected_inspiration=selected,
            inspiration_edits=edits_by_idea,
            workflow_stage="inspiration_selected",
        )
        return {"selected_inspiration": selected, "creative_hint": effective, "edited_direction": edits_by_idea.get(selected, "")}

    def save_guidance(self, *, creator_profile_id: int, session_id: str, creator_guidance: str) -> dict[str, str]:
        self._session(creator_profile_id, session_id)
        guidance = str(creator_guidance or "")
        self.queue.update_session_settings(
            session_id, creator_guidance=guidance, grok_guidance=guidance,
        )
        return {"creator_guidance": guidance}

    def recommendation(self, *, creator_profile_id: int, session_id: str, creative_mode: str,
                       creator_guidance: str, continuity_locks: Mapping[str, bool],
                       target_shot_count: int = 5):
        session = self._session(creator_profile_id, session_id)
        session = self.queue.update_session_settings(
            session_id, creative_mode=creative_mode, target_shot_count=target_shot_count,
        )
        continuity = dict(session.creative_continuity or {})
        planning = self._planning_progress(session)
        if int(continuity.get("inspiration_planning_shot") or 0) != planning["planning_shot"]:
            raise ValueError("These AI ideas belong to a different Photoshoot position. Ask AI again.")
        selected = str(continuity.get("selected_inspiration") or "").strip()
        if not selected or selected not in tuple(continuity.get("inspiration_ideas") or ()):
            raise ValueError("Select an AI idea before developing the next shot.")
        effective = str(dict(continuity.get("inspiration_edits") or {}).get(selected) or selected).strip()
        current, timeline = self._vision_context(session)
        image_bytes, mime_type = self._image_bytes(current.output_reference)
        summary = self.summary.refresh(session.session_id)
        original_direction = self._original_direction(session)
        approved_history = self._approved_history(continuity)
        ai_context = self._ai_context(
            original_direction,
            summary,
            creator_guidance,
            latest_approved_shot=self._latest_approved_shot_summary(session, summary),
            progression_stage=int(continuity.get("progression_stage") or 0),
            current_shot=planning["current_shot"],
            planning_shot=planning["planning_shot"],
            editorial_stage=planning["editorial_stage"],
            timeline_image_count=len(timeline),
            target_shot_count=session.target_shot_count,
        )
        recommendation = self.creative_director.recommend_photoshoot_direction(
            image_bytes=image_bytes, image_mime_type=mime_type,
            session_context=ai_context,
            approved_history=approved_history,
            creative_mode=session.creative_mode, session_direction=original_direction,
            creative_hint=effective, continuity_locks=continuity_locks,
        )
        payload = asdict(recommendation)
        self.queue.update_session_settings(
            session_id, creator_guidance=creator_guidance,
            creative_hint=effective, selected_inspiration=selected, continuity_locks=continuity_locks,
        )
        self.queue.record_pending_recommendation(session_id=session_id, recommendation=payload)
        return payload

    def direct_recommendation(
        self,
        *,
        creator_profile_id: int,
        session_id: str,
        creative_mode: str,
        operator_direction: str,
        continuity_locks: Mapping[str, bool],
        target_shot_count: int = 5,
    ) -> dict[str, Any]:
        direction = str(operator_direction or "").strip()
        if not direction:
            raise ValueError("Describe what should happen in the next shot.")
        session = self._session(creator_profile_id, session_id)
        session = self.queue.update_session_settings(
            session_id, creative_mode=creative_mode, target_shot_count=target_shot_count,
        )
        continuity = dict(session.creative_continuity or {})
        current, timeline = self._vision_context(session)
        image_bytes, mime_type = self._image_bytes(current.output_reference)
        summary = self.summary.refresh(session.session_id)
        original_direction = self._original_direction(session)
        approved_history = self._approved_history(continuity)
        planning = self._planning_progress(session)
        ai_context = {
            **self._ai_context(
                original_direction,
                summary,
                direction,
                latest_approved_shot=self._latest_approved_shot_summary(session, summary),
                progression_stage=int(continuity.get("progression_stage") or 0),
                current_shot=planning["current_shot"],
                planning_shot=planning["planning_shot"],
                editorial_stage=planning["editorial_stage"],
                timeline_image_count=len(timeline),
                target_shot_count=session.target_shot_count,
            ),
            "canonical_seed_summary": self._seed_context(
                continuity,
                fallback=current.prompt_text,
            ),
        }
        recommendation = self.creative_director.recommend_photoshoot_direction(
            image_bytes=image_bytes,
            image_mime_type=mime_type,
            session_context=ai_context,
            approved_history=approved_history,
            creative_mode=session.creative_mode,
            session_direction=original_direction,
            creative_hint=direction,
            continuity_locks=continuity_locks,
        )
        payload = asdict(recommendation)
        self.queue.update_session_settings(
            session_id,
            creator_guidance=direction,
            creative_hint=direction,
            selected_inspiration="",
            continuity_locks=continuity_locks,
        )
        self.queue.record_pending_recommendation(
            session_id=session_id,
            recommendation=payload,
        )
        return payload

    def choose_another(self, *, creator_profile_id: int, session_id: str) -> dict[str, str]:
        self._session(creator_profile_id, session_id)
        self.queue.clear_workspace_state(session_id, workflow_stage="inspiration_ready")
        self.queue.update_session_settings(session_id, creative_hint="", selected_inspiration="")
        return {"workflow_stage": "inspiration_ready", "selected_inspiration": ""}

    def assess_continuity(self, *, session_id: str, request_id: str, candidate_image_id: str) -> dict[str, Any]:
        request = self.queue.get_request(request_id)
        if request.session_id != session_id:
            raise ValueError("Photoshoot request does not belong to this session.")
        session = self.queue.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        reference_id = str(dict(request.metadata or {}).get("active_reference_image_id") or "").strip()
        if not reference_id:
            return {}
        reference = self.library.get(reference_id)
        candidate = self.library.get(candidate_image_id)
        reference_bytes, reference_mime = self._image_bytes(reference.output_reference)
        candidate_bytes, candidate_mime = self._image_bytes(candidate.output_reference)
        frozen_identity = dict(continuity.get("canonical_identity_reference") or {})
        frozen_identity_path = str(frozen_identity.get("path") or "").strip()
        identity_frozen = bool(continuity.get("canonical_identity_reference_frozen"))
        if identity_frozen and not frozen_identity_path:
            raise ValueError("The frozen canonical identity reference is unavailable for this Photoshoot.")
        if frozen_identity_path:
            identity_bytes, identity_mime = self._image_bytes(frozen_identity_path)
            question = (
                "Compare Image 3 (new candidate) against two authorities. Assess identity only against "
                "Image 1 (the frozen canonical identity reference). Assess wardrobe, location, lighting, "
                "composition, and overall_continuity against Image 2 (the latest approved Photoshoot shot). "
                "Expression may intentionally change and must not count as identity drift. Return only JSON "
                "with identity, wardrobe, location, lighting, composition, overall_continuity, and a short reason."
            )
            images = (
                {"bytes": identity_bytes, "mime_type": identity_mime, "label": "Frozen canonical identity"},
                {"bytes": reference_bytes, "mime_type": reference_mime, "label": "Approved continuity reference"},
                {"bytes": candidate_bytes, "mime_type": candidate_mime, "label": "Candidate"},
            )
        else:
            question = (
                "Compare Image 1 (approved Photoshoot continuity reference) with Image 2 (new candidate). "
                "Assess identity, wardrobe, location, lighting, composition, and overall_continuity as "
                "strong, acceptable, or weak. Composition may intentionally evolve and should be weak only "
                "when it breaks the established shoot. Return only JSON with those six keys and a short reason."
            )
            images = (
                {"bytes": reference_bytes, "mime_type": reference_mime, "label": "Approved reference"},
                {"bytes": candidate_bytes, "mime_type": candidate_mime, "label": "Candidate"},
            )
        response = self.creative_director.ask_anything(
            question=question,
            image_bytes=candidate_bytes,
            image_mime_type=candidate_mime,
            images=images,
        )
        cleaned = str(response or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        categories = ("identity", "wardrobe", "location", "lighting", "composition", "overall_continuity")
        normalized = {key: str(parsed.get(key) or "unknown").strip().lower() for key in categories}
        weak = tuple(key for key, value in normalized.items() if value == "weak")
        warning = normalized["overall_continuity"] == "weak" or normalized["identity"] == "weak" or len(weak) >= 2
        return {
            **normalized,
            "reason": str(parsed.get("reason") or "").strip(),
            "warning": warning,
            "warning_message": "This generation may have drifted from the current photoshoot." if warning else "",
        }

    def approve(self, *, creator_profile_id: int, session_id: str) -> dict[str, Any]:
        started = time.perf_counter()
        LOGGER.info("[Approve] START approve() session_id=%s timestamp=%.6f", session_id, time.time())
        LOGGER.info("[Approve] Loading Photoshoot session elapsed_ms=%.2f", (time.perf_counter() - started) * 1000)
        session = self._session(creator_profile_id, session_id)
        LOGGER.info("[Approve] Session loaded creative_mode=%s elapsed_ms=%.2f", session.creative_mode, (time.perf_counter() - started) * 1000)
        continuity = dict(session.creative_continuity or {})
        LOGGER.info("[Approve] Continuity loaded elapsed_ms=%.2f", (time.perf_counter() - started) * 1000)
        recommendation = dict(continuity.get("current_direction") or {})
        LOGGER.info("[Approve] Selected direction loaded present=%s elapsed_ms=%.2f", bool(recommendation), (time.perf_counter() - started) * 1000)
        if not recommendation:
            raise ValueError("Generate a Creative Director recommendation before approving it.")
        current, _ = self._vision_context(session)
        direction = self._direction_text(recommendation)
        seed_context = self._seed_context(continuity, fallback=current.prompt_text)
        planning_context = self._planning_context(session)
        # A Photoshoot approval is one selected shot concept. The explicit planner
        # treats newline-delimited input as multiple independent concepts and
        # derives editorial guidance for every line, so preserve the full content
        # while presenting it as one canonical concept.
        creative_tags = " ".join(" ".join(part.split()) for part in (
            "Photoshoot Studio continuation.", f"Creative direction: {direction}",
            f"Photoshoot Seed Summary: {seed_context}",
            f"Session continuity: {planning_context.to_prompt_text()}",
            "Preserve continuity defaults unless the Session Direction explicitly overrides them.",
        ) if str(part or "").strip())
        planning_mode = photoshoot_planning_mode(session.creative_mode)
        LOGGER.info("[Approve] Canonical planning request built mode=%s elapsed_ms=%.2f", planning_mode, (time.perf_counter() - started) * 1000)
        LOGGER.info("[Approve] Entering Canonical Prompt Planner elapsed_ms=%.2f", (time.perf_counter() - started) * 1000)
        operator_expression = normalize_photoshoot_emotion(
            recommendation.get("emotion"),
            creative_mode=session.creative_mode,
        )
        freeflow_expression = not planning_context.progression_enabled
        result = self.creative_director.plan_prompts(
            mode=planning_mode,
            creative_tags=creative_tags, prompt_count=1, optional_direction=direction,
            metadata={
                "source": "photoshoot_studio",
                # Shot-level face direction from Creative Director becomes the
                # canonical expression override. Weak/bland continuity phrases are
                # normalized to alluring defaults so identity locks cannot freeze
                # a vacant model face across the shoot.
                "operator_expression": operator_expression,
                "freeflow_expression": freeflow_expression,
                "concept_tier": (
                    "hardcore"
                    if str(session.creative_mode or "").strip().lower() == "explicit"
                    else "softcore"
                ),
            },
        )
        LOGGER.info("[Approve] Prompt planner complete prompt_count=%s elapsed_ms=%.2f", len(result.prompts), (time.perf_counter() - started) * 1000)
        if not result.prompts:
            raise ValueError("Canonical Prompt Planner did not return a Photoshoot prompt.")
        prompt = result.prompts[0]
        LOGGER.info("[Approve] Persisting prompt chars=%s elapsed_ms=%.2f", len(prompt), (time.perf_counter() - started) * 1000)
        self.queue.record_creative_direction(
            session_id=session_id, recommendation=recommendation, final_prompt=prompt,
        )
        LOGGER.info("[Approve] Prompt persisted elapsed_ms=%.2f", (time.perf_counter() - started) * 1000)
        response = {
            "prompt": prompt,
            "recommendation": recommendation,
            "approval_state": "approved",
            "workflow_stage": "direction_approved",
        }
        LOGGER.info("[Approve] Returning approve response elapsed_ms=%.2f", (time.perf_counter() - started) * 1000)
        LOGGER.info("[Approve] END approve() elapsed_ms=%.2f", (time.perf_counter() - started) * 1000)
        return response

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
        seed_summary = continuity.get("canonical_seed_summary")
        if isinstance(seed_summary, Mapping) and str(seed_summary.get("scene") or "").strip():
            return CanonicalPhotoshootSeedSummary.from_dict(seed_summary).to_prompt_text()
        if isinstance(seed_summary, str) and seed_summary.strip():
            return seed_summary.strip()
        return str(
            continuity.get("original_photoshoot_direction")
            or session.creator_notes
            or "Continue the selected seed as one cohesive photoshoot."
        ).strip()

    @staticmethod
    def _seed_prompt(continuity: Mapping[str, Any], *, fallback: str = "") -> str:
        return str(
            continuity.get("seed_prompt_text")
            or continuity.get("original_photoshoot_direction")
            or fallback
            or "Use the selected image as the canonical visual reference."
        ).strip()

    @classmethod
    def _seed_context(cls, continuity: Mapping[str, Any], *, fallback: str = "") -> str:
        summary = continuity.get("canonical_seed_summary")
        if isinstance(summary, Mapping) and str(summary.get("scene") or "").strip():
            return CanonicalPhotoshootSeedSummary.from_dict(summary).to_prompt_text()
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
        return cls._seed_prompt(continuity, fallback=fallback)

    def _planning_context(self, session) -> PhotoshootPlanningContext:
        continuity = dict(session.creative_continuity or {})
        summary = dict(continuity.get("photoshoot_summary") or {})
        defaults = dict(continuity.get("session_defaults") or {})
        approved = self._approved_history(continuity)
        latest_direction = self._direction_text(approved[-1]) if approved else ""
        progress = self._planning_progress(session)
        current_shot = progress["current_shot"]
        target_shot_count = normalize_target_shot_count(continuity.get("target_shot_count"))
        return PhotoshootPlanningContext(
            photoshoot_summary=str(summary.get("summary_text") or summary.get("overall_theme") or "").strip(),
            latest_approved_direction=latest_direction,
            current_wardrobe=str(
                summary.get("current_wardrobe")
                or defaults.get("wardrobe")
                or "Preserve the established wardrobe."
            ).strip(),
            current_location=str(
                summary.get("current_location")
                or defaults.get("location")
                or "Preserve the established location."
            ).strip(),
            current_lighting=str(
                summary.get("lighting")
                or defaults.get("lighting")
                or "Preserve the established lighting."
            ).strip(),
            camera_style=str(
                summary.get("visual_style")
                or defaults.get("camera_style")
                or "Preserve the established camera style."
            ).strip(),
            hairstyle=str(
                defaults.get("hairstyle")
                or "Preserve the established hairstyle unless overridden."
            ).strip(),
            makeup=str(
                defaults.get("makeup")
                or "Preserve the established makeup unless overridden."
            ).strip(),
            continuity_locks={
                str(key): bool(value)
                for key, value in dict(continuity.get("continuity_locks") or {}).items()
            },
            progression_stage=(
                max(0, int(continuity.get("progression_stage") or 0))
                if target_shot_count > 0 else None
            ),
            current_shot=current_shot,
            planning_shot=progress["planning_shot"],
            target_shot_count=target_shot_count,
            remaining_shots=max(0, target_shot_count - current_shot) if target_shot_count > 0 else None,
            editorial_stage=progress["editorial_stage"] if target_shot_count > 0 else None,
            progression_enabled=target_shot_count > 0,
            operator_guidance=str(
                continuity.get("creator_guidance")
                or continuity.get("grok_guidance")
                or ""
            ).strip(),
            required_identity_instructions=str(
                defaults.get("identity_continuity")
                or "Preserve the same creator identity, face, body, skin tone, and proportions."
            ).strip(),
            latest_approved_shot_reference=(
                "Use the latest approved Photoshoot image supplied downstream as the visual continuity reference."
            ),
            latest_approved_shot=self._latest_approved_shot_summary(session, summary),
            repetition_avoidance=str(
                summary.get("avoid_repetition")
                or "Avoid an exact duplicate through one subtle change; preserve the latest composition and camera setup."
            ).strip(),
        )

    def _planning_progress(self, session) -> dict[str, Any]:
        try:
            requests = tuple(self.queue.requests_for_session(session.session_id))
        except TypeError:
            requests = ()
        current_shot = max(1, PhotoshootContextService.approved_display_count(requests))
        target = normalize_target_shot_count(getattr(session, "target_shot_count", None))
        planning_shot = current_shot + 1
        ratio = planning_shot / target if target > 0 else 0
        if target == 0:
            stage = "Open-ended"
        elif planning_shot >= target:
            stage = "Finale"
        elif ratio >= 0.75:
            stage = "Late"
        elif ratio >= 0.5:
            stage = "Middle"
        else:
            stage = "Beginning"
        return {
            "current_shot": current_shot,
            "planning_shot": planning_shot,
            "target_shot_count": target,
            "remaining_shots": max(0, target - current_shot) if target > 0 else 0,
            "editorial_stage": stage,
        }

    def _latest_approved_shot_summary(self, session, summary: Mapping[str, Any]) -> dict[str, Any]:
        """Return the latest approved frame as an explicit scene-continuity contract."""
        continuity = dict(session.creative_continuity or {})
        defaults = dict(continuity.get("session_defaults") or {})
        approved = tuple(
            request for request in self.queue.requests_for_session(session.session_id)
            if request.status == "approved"
        )
        latest = max(
            enumerate(approved, start=1),
            key=lambda pair: int(getattr(pair[1], "sequence_index", pair[0])),
            default=(0, None),
        )[1]
        direction = dict((latest.metadata or {}).get("creative_direction") or {}) if latest else {}
        pose = str(direction.get("pose_composition") or "").strip()
        framing = str(direction.get("camera_framing") or "").strip()
        wardrobe = str(
            summary.get("current_wardrobe") or defaults.get("wardrobe")
            or "Preserve exactly as shown in the latest approved image."
        ).strip()
        return {
            "environment": str(
                summary.get("overall_theme") or defaults.get("environment")
                or "Preserve exactly as shown in the latest approved image."
            ).strip(),
            "location": str(
                summary.get("current_location") or defaults.get("location")
                or "Preserve exactly as shown in the latest approved image."
            ).strip(),
            "wardrobe": wardrobe,
            "clothing_state": wardrobe,
            "pose": pose or "Preserve the latest approved pose with only one small natural evolution.",
            "body_orientation": pose or "Preserve the latest approved body orientation.",
            "hand_placement": pose or "Preserve the latest approved hand placement.",
            "facial_expression": normalize_photoshoot_emotion(
                direction.get("emotion"),
                creative_mode=getattr(session, "creative_mode", None),
            ),

            "camera_angle": framing or "Preserve the latest approved camera angle.",
            "framing": framing or str(
                summary.get("visual_style") or defaults.get("camera_style")
                or "Preserve the latest approved framing."
            ).strip(),
            "lighting": str(
                direction.get("lighting") or summary.get("lighting") or defaults.get("lighting")
                or "Preserve exactly as shown in the latest approved image."
            ).strip(),
            "progression_stage": max(0, int(continuity.get("progression_stage") or 0)),
        }

    @staticmethod
    def _planner_explanation(progress: Mapping[str, Any]) -> str:
        if int(progress["target_shot_count"]) == 0:
            return (
                f"Planning the natural next shot after Shot {progress['current_shot']}. "
                "The session is open-ended, so continuity, approved history, and operator guidance determine pacing."
            )
        return (
            f"Planning Shot {progress['planning_shot']} of {progress['target_shot_count']} in the "
            f"{str(progress['editorial_stage']).lower()} stage. Continuing naturally from the latest "
            f"approved shot while preserving continuity and pacing {progress['remaining_shots']} remaining shot(s)."
        )

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
        current_shot: int = 1,
        planning_shot: int | None = None,
        editorial_stage: str = "Beginning",
        timeline_image_count: int = 0,
        target_shot_count: int = 5,
        latest_approved_shot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_shot = max(1, int(current_shot or 1))
        planning_shot = max(current_shot + 1, int(planning_shot or current_shot + 1))
        normalized_target = normalize_target_shot_count(target_shot_count)
        progression_enabled = normalized_target > 0
        return {
            "original_photoshoot_direction": str(original_direction or "").strip(),
            "current_photoshoot_summary": dict(summary or {}),
            "optional_user_guidance": str(creator_guidance or "").strip(),
            "progression_stage": max(0, int(progression_stage or 0)) if progression_enabled else None,
            "timeline_image_count": max(0, int(timeline_image_count or 0)),
            "current_shot": current_shot,
            "planning_shot": planning_shot,
            "target_shot_count": normalized_target,
            "remaining_shots": max(0, normalized_target - current_shot) if progression_enabled else None,
            "editorial_stage": str(editorial_stage or "Beginning") if progression_enabled else None,
            "progress_percent": (
                round((current_shot / normalized_target) * 100, 2)
                if progression_enabled else None
            ),
            "open_ended": normalized_target == 0,
            "progression_enabled": progression_enabled,
            "creative_structure": "PROGRESSION_AWARE" if progression_enabled else "OPEN_ENDED_NON_PROGRESSIVE",
            "latest_approved_shot": dict(latest_approved_shot or {}),
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
