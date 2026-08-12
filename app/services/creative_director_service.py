"""Provider-neutral Creative Director workflow service with Wavespeed brain."""

from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping

from app.config import GROK_VISION_MODEL
from app.models.creative_director import (
    CREATIVE_MODE_OPTIONS,
    CreativeDirectorSettings,
    CreativeHistoryEntry,
    CreativeRecommendation,
    CreativeSession,
    PhotoshootCreativeDirection,
    PromptAssistantBatch,
    PromptPlan,
    new_id,
)
from app.models.reference_library import ReferenceAsset
from app.models.inspiration_scene import InspirationSceneAnalysis
from app.models.photoshoot_queue import normalize_target_shot_count
from app.services.llm_json_parser import parse_llm_json
from app.prompts.generation_modes import GENERATION_MODES
from app.prompts.prompt_builder import build_chatgpt_prompt, normalize_social_prompt_continuity
from app.services.canonical_prompt_planner import (
    CanonicalPromptPlanner,
    CanonicalPromptPlanningRequest,
    CanonicalPromptPlanningResult,
)
from app.services.explicit_prompt_service import enhance_explicit_tags
from app.services.premium_lucky_service import (
    generate_lucky_explicit_tags,
    generate_lucky_premium_tags,
)
from app.services.premium_tag_enhancer_service import (
    enhance_premium_tags as wavespeed_enhance_premium_tags,
    surprise_premium_tags as wavespeed_surprise_premium_tags,
)
from app.services.reference_library_service import ReferenceLibraryService
from app.services.social_lucky_service import generate_lucky_social_tags
from app.services.wavespeed_grok_service import generate_prompts_with_grok


class CreativeDirectorService:
    """Owns Creative Director persistence and delegates generation brain to Wavespeed."""

    DEFAULT_STORAGE_DIR = Path("data") / "creative_director"

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        reference_library_service: ReferenceLibraryService | None = None,
        ask_anything_provider: Callable[..., str] | None = None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self.reference_library = reference_library_service or ReferenceLibraryService()
        self.ask_anything_provider = ask_anything_provider
        self.prompt_planner = CanonicalPromptPlanner()

    @property
    def sessions_path(self) -> Path:
        return self.storage_dir / "creative_sessions.json"

    @property
    def settings_path(self) -> Path:
        return self.storage_dir / "creative_settings.json"

    @property
    def prompt_assistant_path(self) -> Path:
        return self.storage_dir / "premium_prompt_assistant_archive.json"

    def normalize_tags(self, creative_tags: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(creative_tags, str):
            return self._normalize_tag_text(creative_tags)
        tags = []
        for item in creative_tags or ():
            tags.extend(self._normalize_tag_text(str(item)))
        return tuple(dict.fromkeys(tags))

    @classmethod
    def has_multiple_tag_lines(cls, raw_tags: str | list[str] | tuple[str, ...]) -> bool:
        if not isinstance(raw_tags, str):
            return len(tuple(raw_tags or ())) > 1
        return len([line for line in raw_tags.splitlines() if line.strip()]) > 1

    @classmethod
    def tag_concept_lines(cls, raw_tags: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
        if isinstance(raw_tags, str):
            lines = [line.strip() for line in raw_tags.splitlines() if line.strip()]
            return tuple(lines) if lines else (raw_tags.strip(),)
        return tuple(str(item).strip() for item in raw_tags or () if str(item).strip())

    @staticmethod
    def _normalize_tag_text(raw_tags: str) -> tuple[str, ...]:
        pieces = []
        for line in str(raw_tags or "").splitlines():
            line = line.replace(";", ",")
            for part in line.split(","):
                value = part.strip(" \t\r\n,.-")
                if value:
                    pieces.append(value)
        return tuple(dict.fromkeys(pieces))

    @classmethod
    def is_broad_lingerie_request(cls, raw_tags: str) -> bool:
        from app.services.premium_tag_enhancer_service import is_broad_lingerie_request

        return is_broad_lingerie_request(raw_tags)

    @classmethod
    def ensure_lingerie_variety(cls, *, source_tags: str, enhanced_tags: str) -> str:
        from app.services.premium_tag_enhancer_service import ensure_lingerie_variety_tags

        return ensure_lingerie_variety_tags(source_tags, enhanced_tags)

    @classmethod
    def has_specific_wardrobe(cls, source_tags: str) -> bool:
        wardrobe_terms = (
            "tank", "top", "crop", "shirt", "tee", "blouse", "sweater", "hoodie", "jacket",
            "dress", "skirt", "shorts", "jeans", "pants", "cargo", "leggings", "bodysuit",
            "bra", "bralette", "lingerie", "bikini", "swimsuit", "robe", "heels", "boots",
            "socks", "stockings", "thong", "panties",
        )
        normalized = " ".join(self_tag.lower() for self_tag in cls._normalize_tag_text(source_tags))
        return any(term in normalized for term in wardrobe_terms)

    def i_feel_lucky(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        creative_mode: str,
        prompt_count: int = 5,
    ) -> tuple[str, ...]:
        mode = self.normalize_mode(creative_mode)
        if mode in {"premium_teaser", "story_sequence"}:
            return tuple(
                line.strip()
                for line in generate_lucky_premium_tags(prompt_count=max(1, int(prompt_count or 1))).splitlines()
                if line.strip()
            )
        if mode == "spicy":
            return tuple(
                line.strip()
                for line in generate_lucky_social_tags(prompt_count=max(1, int(prompt_count or 1))).splitlines()
                if line.strip()
            )
        return tuple(
            line.strip()
            for line in generate_lucky_social_tags(prompt_count=max(1, int(prompt_count or 1))).splitlines()
            if line.strip()
        )

    def premium_lucky_tags(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        prompt_count: int = 5,
        explicit: bool = False,
    ) -> str:
        if explicit:
            return generate_lucky_explicit_tags(prompt_count=max(1, int(prompt_count or 1)))
        return generate_lucky_premium_tags(prompt_count=max(1, int(prompt_count or 1)))

    def enhance_premium_tags(
        self,
        *,
        simple_tags: str,
        creator_profile: Mapping[str, Any] | None = None,
        explicit: bool = False,
    ) -> str:
        if explicit:
            return enhance_explicit_tags(simple_tags)
        return wavespeed_enhance_premium_tags(simple_tags)

    def enhance_social_tags(
        self,
        *,
        simple_tags: str,
        creator_profile: Mapping[str, Any] | None = None,
    ) -> str:
        tags = ", ".join(self.normalize_tags(simple_tags))
        if not tags:
            return ""
        return normalize_social_prompt_continuity(tags)

    def surprise_social_tags(
        self,
        *,
        simple_tags: str,
        creator_profile: Mapping[str, Any] | None = None,
    ) -> str:
        tags = ", ".join(self.normalize_tags(simple_tags))
        if not tags:
            tags = "social-safe lifestyle creator concept"
        prompt = build_chatgpt_prompt(
            prompt_count=1,
            user_request=f"{tags}, unexpected social-safe variation",
            generation_mode=GENERATION_MODES["1"],
            platform_mode="Social Content Studio",
            spice_level="Social Safe",
        )
        prompts = generate_prompts_with_grok(prompt, self._grok_api_key())
        return normalize_social_prompt_continuity(prompts[0]) if prompts else tags

    def surprise_premium_tags(
        self,
        *,
        simple_tags: str,
        creator_profile: Mapping[str, Any] | None = None,
    ) -> str:
        return wavespeed_surprise_premium_tags(simple_tags)

    def ask_prompt_assistant(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        request_text: str,
        lane: str = "premium",
        prompt_count: int = 5,
    ) -> PromptAssistantBatch:
        creator_profile_id = int((creator_profile or {}).get("id") or 0)
        if not creator_profile_id:
            raise ValueError("Creator Profile required before using the prompt assistant.")
        request = str(request_text or "").strip()
        if not request:
            raise ValueError("Prompt assistant request is required.")
        planning_result = self.plan_prompts(
            mode=str(lane or "premium").strip().lower(),
            creative_tags=request,
            prompt_count=prompt_count,
            metadata={"source": "prompt_workshop"},
        )
        batch = PromptAssistantBatch(
            batch_id=new_id("prompt_assistant"),
            creator_profile_id=creator_profile_id,
            request_text=request,
            lane=planning_result.mode,
            prompts=planning_result.prompts,
        )
        self.save_prompt_assistant_batch(batch)
        return batch

    def plan_prompts(
        self,
        *,
        mode: str,
        creative_tags: str,
        prompt_count: int,
        optional_direction: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CanonicalPromptPlanningResult:
        return self.prompt_planner.plan(
            CanonicalPromptPlanningRequest(
                mode=mode,
                creative_tags=creative_tags,
                prompt_count=prompt_count,
                optional_direction=optional_direction,
                metadata=metadata or {},
            )
        )

    def save_prompt_assistant_batch(self, batch: PromptAssistantBatch) -> None:
        entries = self._read_json(self.prompt_assistant_path, [])
        entries.insert(0, asdict(batch))
        self._write_json(self.prompt_assistant_path, entries)

    def prompt_assistant_history(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 20,
    ) -> tuple[PromptAssistantBatch, ...]:
        entries = self._read_json(self.prompt_assistant_path, [])
        batches = []
        for entry in entries:
            batch = self._prompt_assistant_batch_from_dict(entry)
            if batch is None:
                continue
            if creator_profile_id is not None and batch.creator_profile_id != int(creator_profile_id):
                continue
            batches.append(batch)
        return tuple(batches[:limit])

    def mark_prompt_assistant_used(self, batch_id: str, prompt_number: int) -> None:
        entries = self._read_json(self.prompt_assistant_path, [])
        changed = False
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("batch_id") != batch_id:
                continue
            used = list(entry.get("used_prompt_numbers") or [])
            number = int(prompt_number)
            if number not in used:
                used.append(number)
                entry["used_prompt_numbers"] = used
                changed = True
        if changed:
            self._write_json(self.prompt_assistant_path, entries)

    def ask_anything(
        self,
        *,
        question: str,
        image_bytes: bytes | None = None,
        image_mime_type: str | None = None,
        image_name: str | None = None,
        images: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] | None = None,
    ) -> str:
        prompt = str(question or "").strip()
        if not prompt:
            raise ValueError("Enter a question before asking.")
        image_payloads = self._normalize_vision_images(
            image_bytes=image_bytes,
            image_mime_type=image_mime_type,
            image_name=image_name,
            images=images,
        )
        if self.ask_anything_provider:
            # Prefer the latest/current frame as the primary image for backward-compatible providers.
            primary = image_payloads[-1] if image_payloads else {}
            return str(
                self.ask_anything_provider(
                    question=prompt,
                    image_bytes=primary.get("bytes"),
                    image_mime_type=primary.get("mime_type"),
                    image_name=primary.get("label") or image_name,
                    images=image_payloads,
                )
            ).strip()
        module = __import__("openai")
        client_class = getattr(module, "Open" + "AI")
        client = client_class(
            api_key=self._grok_api_key(),
            base_url=os.getenv("GROK_BASE_URL") or "https://api.x.ai/v1",
        )
        has_image = bool(image_payloads)
        model = (
            GROK_VISION_MODEL
            if has_image
            else os.getenv("GROK_MODEL") or "grok-3-mini"
        )
        if has_image:
            content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            for item in image_payloads:
                label = str(item.get("label") or "").strip()
                if label:
                    content.append({"type": "text", "text": f"[Image: {label}]"})
                mime_type = str(item.get("mime_type") or "image/png")
                encoded = base64.b64encode(item.get("bytes") or b"").decode("utf-8")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    }
                )
        else:
            content = prompt
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            temperature=0.8,
        )
        return str(response.choices[0].message.content or "").strip()

    def analyze_inspiration_scene(
        self, *, image_bytes: bytes, image_mime_type: str | None = None,
        image_name: str | None = None,
    ) -> InspirationSceneAnalysis:
        """Extract transferable creative direction without subject identity."""
        if not image_bytes:
            raise ValueError("An inspiration image is required.")
        prompt = """Analyze this image as creative inspiration for a new image whose subject will be Ava.
The uploaded person is never the identity source. Do not preserve or describe their face, hair, skin tone,
body, age, ethnicity, or recognizable identity. Return ONLY one JSON object with exactly these keys:
scene, pose, camera_angle, camera_framing, lighting, composition, wardrobe_concept, expression,
mood, environment, color_palette, styling, elements_to_preserve, elements_to_ignore,
identity_transfer_prohibited, confidence. All descriptive fields are strings; preserve/ignore are string
arrays; identity_transfer_prohibited must be true; confidence is 0..1. Describe transferable creative
attributes precisely and put all uploaded-subject identity attributes in elements_to_ignore."""
        response = self.ask_anything(
            question=prompt, image_bytes=image_bytes,
            image_mime_type=image_mime_type or "image/png", image_name=image_name,
        )
        parsed = parse_llm_json(
            response, model_name="creative-director-vision",
            caller="CreativeDirectorService.analyze_inspiration_scene",
        )
        if not isinstance(parsed, Mapping):
            raise ValueError("Creative Director returned malformed inspiration analysis.")
        return InspirationSceneAnalysis.from_mapping(parsed)

    @staticmethod
    def _normalize_vision_images(
        *,
        image_bytes: bytes | None = None,
        image_mime_type: str | None = None,
        image_name: str | None = None,
        images: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] | None = None,
    ) -> tuple[dict[str, Any], ...]:
        payloads: list[dict[str, Any]] = []
        for item in images or ():
            if not isinstance(item, Mapping):
                continue
            raw = item.get("bytes")
            if raw is None:
                raw = item.get("image_bytes")
            if not raw:
                continue
            payloads.append(
                {
                    "bytes": bytes(raw),
                    "mime_type": str(item.get("mime_type") or item.get("image_mime_type") or "image/png"),
                    "label": str(item.get("label") or item.get("image_name") or item.get("name") or "").strip(),
                }
            )
        if not payloads and image_bytes:
            payloads.append(
                {
                    "bytes": bytes(image_bytes),
                    "mime_type": str(image_mime_type or "image/png"),
                    "label": str(image_name or "").strip(),
                }
            )
        return tuple(payloads)

    def recommend_photoshoot_direction(
        self,
        *,
        image_bytes: bytes,
        image_mime_type: str | None = None,
        session_context: Mapping[str, Any] | None = None,
        approved_history: tuple[Mapping[str, Any], ...] = (),
        creative_mode: str = "premium",
        session_direction: str = "",
        creative_hint: str = "",
        continuity_locks: Mapping[str, bool] | None = None,
    ) -> PhotoshootCreativeDirection:
        if not image_bytes:
            raise ValueError("Current image is required before asking the Creative Director.")
        locks = {
            "location": True,
            "wardrobe": True,
            "lighting": True,
            "hairstyle": True,
            "makeup": True,
            "camera_style": True,
            **dict(continuity_locks or {}),
        }
        context = dict(session_context or {})
        history = tuple(dict(item or {}) for item in approved_history)
        direction = str(session_direction or "").strip()
        hint = str(creative_hint or "").strip()
        mode = str(creative_mode or "premium").strip().lower()
        prompt = self._build_photoshoot_creative_director_prompt(
            session_context=context,
            approved_history=history,
            creative_mode=mode,
            session_direction=direction,
            creative_hint=hint,
            continuity_locks=locks,
        )
        response = self.ask_anything(
            question=prompt,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type or "image/png",
        )
        return self._photoshoot_direction_from_response(
            response=response,
            creative_mode=mode,
            session_direction=direction,
            continuity_locks=locks,
        )

    def plan_full_photoshoot_session(
        self,
        *,
        image_bytes: bytes,
        image_mime_type: str | None = None,
        session_context: Mapping[str, Any] | None = None,
        creative_mode: str = "premium",
        session_direction: str = "",
        creator_guidance: str = "",
        continuity_locks: Mapping[str, bool] | None = None,
        frame_count: int = 8,
    ) -> tuple[dict[str, Any], ...]:
        """Plan an ordered multi-shot photoshoot arc from the seed/current image."""
        if not image_bytes:
            raise ValueError("Seed image is required before planning a full Photoshoot.")
        count = max(4, min(12, int(frame_count or 8)))
        locks = {
            "location": True,
            "wardrobe": True,
            "lighting": True,
            "hairstyle": True,
            "makeup": True,
            "camera_style": True,
            **dict(continuity_locks or {}),
        }
        prompt = self._build_full_photoshoot_plan_prompt(
            session_context=dict(session_context or {}),
            creative_mode=str(creative_mode or "premium").strip().lower(),
            session_direction=str(session_direction or "").strip(),
            creator_guidance=str(creator_guidance or "").strip(),
            continuity_locks=locks,
            frame_count=count,
        )
        response = self.ask_anything(
            question=prompt,
            image_bytes=image_bytes,
            image_mime_type=image_mime_type or "image/png",
        )
        return self._parse_full_photoshoot_plan(response, frame_count=count)

    def suggest_photoshoot_inspiration(
        self,
        *,
        image_bytes: bytes,
        image_mime_type: str | None = None,
        session_context: Mapping[str, Any] | None = None,
        approved_history: tuple[Mapping[str, Any], ...] = (),
        creative_mode: str = "premium",
        session_direction: str = "",
        creative_hint: str = "",
        grok_guidance: str = "",
        continuity_locks: Mapping[str, bool] | None = None,
        provider_context: str = "",
        idea_count: int = 8,
        timeline_images: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] | None = None,
    ) -> tuple[str, ...]:
        if not image_bytes and not timeline_images:
            raise ValueError("Current image is required before asking Grok.")
        locks = {
            "location": True,
            "wardrobe": True,
            "lighting": True,
            "hairstyle": True,
            "makeup": True,
            "camera_style": True,
            **dict(continuity_locks or {}),
        }
        count = max(5, min(10, int(idea_count or 8)))
        vision_images = self._select_timeline_vision_images(
            timeline_images=timeline_images,
            fallback_bytes=image_bytes,
            fallback_mime_type=image_mime_type or "image/png",
        )
        if not vision_images:
            raise ValueError("Current image is required before asking Grok.")
        # Prefer dedicated Ask Grok guidance; fall back to creative_hint only if guidance is blank.
        guidance = str(grok_guidance or "").strip() or str(creative_hint or "").strip()
        prompt = self._build_photoshoot_grok_inspiration_prompt(
            session_context=dict(session_context or {}),
            approved_history=tuple(dict(item or {}) for item in approved_history),
            creative_mode=str(creative_mode or "premium").strip().lower(),
            session_direction=str(session_direction or "").strip(),
            creative_hint=str(creative_hint or "").strip(),
            grok_guidance=guidance,
            continuity_locks=locks,
            provider_context=str(provider_context or "").strip(),
            idea_count=count,
            timeline_labels=tuple(
                str(item.get("label") or f"Shot {index}")
                for index, item in enumerate(vision_images, start=1)
            ),
        )
        response = self.ask_anything(
            question=prompt,
            image_bytes=vision_images[-1]["bytes"],
            image_mime_type=str(vision_images[-1].get("mime_type") or "image/png"),
            images=vision_images,
        )
        return self._parse_inspiration_ideas(response, idea_count=count)

    @classmethod
    def _select_timeline_vision_images(
        cls,
        *,
        timeline_images: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] | None,
        fallback_bytes: bytes | None,
        fallback_mime_type: str = "image/png",
        max_images: int = 12,
    ) -> tuple[dict[str, Any], ...]:
        """Keep ordered timeline frames for vision; cap long shoots while preserving arc."""
        normalized = list(
            cls._normalize_vision_images(
                image_bytes=None,
                images=timeline_images,
            )
        )
        if not normalized and fallback_bytes:
            normalized = [
                {
                    "bytes": bytes(fallback_bytes),
                    "mime_type": str(fallback_mime_type or "image/png"),
                    "label": "Current shot",
                }
            ]
        if not normalized:
            return ()
        # Ensure labels are shot-ordered when missing.
        for index, item in enumerate(normalized, start=1):
            if not str(item.get("label") or "").strip():
                item["label"] = f"Shot {index}"
        limit = max(1, int(max_images or 12))
        if len(normalized) <= limit:
            return tuple(normalized)
        # Always keep first + last, sample intermediates across the arc.
        keep_indexes = {0, len(normalized) - 1}
        middle_slots = limit - 2
        if middle_slots > 0 and len(normalized) > 2:
            step = (len(normalized) - 1) / (middle_slots + 1)
            for slot in range(1, middle_slots + 1):
                keep_indexes.add(min(len(normalized) - 2, max(1, int(round(slot * step)))))
        ordered = sorted(keep_indexes)
        return tuple(normalized[index] for index in ordered)

    def suggested_ideas(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        creative_mode: str,
    ) -> tuple[CreativeRecommendation, ...]:
        mode = self.normalize_mode(creative_mode)
        tags = self.i_feel_lucky(
            creator_profile=creator_profile,
            creative_mode=mode,
            prompt_count=3,
        )
        return tuple(
            CreativeRecommendation(
                title=f"Idea {index}",
                tags=self.normalize_tags(tag_line),
                creative_mode=mode,
                rationale="Derived from Wavespeed Creative Director helper behavior.",
            )
            for index, tag_line in enumerate(tags, start=1)
        )

    def create_session(
        self,
        *,
        creator_profile_id: int,
        creative_tags: str | list[str] | tuple[str, ...],
        creative_mode: str,
        prompt_count: int,
        reference_asset: ReferenceAsset | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CreativeSession:
        session = CreativeSession(
            session_id=new_id("creative_session"),
            creator_profile_id=int(creator_profile_id),
            creative_tags=self.normalize_tags(creative_tags),
            creative_mode=self.normalize_mode(creative_mode),
            prompt_count=max(1, int(prompt_count or 1)),
            reference_asset_id=reference_asset.asset_id if reference_asset else None,
            metadata=dict(metadata or {}),
        )
        self.save_session(session)
        return session

    def build_prompt_plan(
        self,
        session: CreativeSession,
        *,
        reference_asset: ReferenceAsset | None,
        creator_profile: Mapping[str, Any] | None,
    ) -> PromptPlan:
        profile_name = self._profile_name(creator_profile, fallback="Creator")
        raw_tag_text = str(session.metadata.get("raw_creative_tags") or "").strip()
        tag_text = raw_tag_text or ", ".join(session.creative_tags)
        planning_result: CanonicalPromptPlanningResult | None = None
        if session.creative_mode in {
            "premium_teaser", "spicy", "story_sequence", "explicit"
        }:
            planning_result = self.plan_prompts(
                mode=session.creative_mode,
                creative_tags=tag_text,
                prompt_count=session.prompt_count,
                metadata={
                    "source": "prompt_plan",
                    **dict(session.metadata.get("explicit_input") or {}),
                },
            )
            prompt_variations = planning_result.prompts
        else:
            prompt_variations = self.build_diversified_prompt_batch(
                profile_name=profile_name,
                creative_mode=session.creative_mode,
                tag_text=tag_text,
                reference_text=self._reference_text(reference_asset),
                prompt_count=session.prompt_count,
            )
        if not prompt_variations:
            prompt_variations = (tag_text,)
        prompt_text = "\n\n".join(prompt_variations)
        plan = PromptPlan(
            plan_id=new_id("prompt_plan"),
            session_id=session.session_id,
            creator_profile_id=session.creator_profile_id,
            prompt_text=prompt_text,
            creative_mode=session.creative_mode,
            creative_tags=session.creative_tags,
            reference_asset_id=reference_asset.asset_id if reference_asset else None,
            reference_asset_path=self._reference_path(reference_asset),
            creative_rationale=(
                "Prompt Plan created by the Creator_OS canonical planning engine."
            ),
            prompt_metadata={
                "prompt_variations": prompt_variations,
                "generation_brain": (
                    "seedream_premium_canonical"
                    if planning_result and planning_result.mode == "premium"
                    else "creator_os_canonical"
                    if planning_result
                    else "wavespeed_canonical"
                ),
                "reference_conditioning": (
                    "seedream_5_0_pro"
                    if planning_result and planning_result.mode == "premium"
                    else "provider_adapter"
                    if planning_result
                    else "wavespeed"
                ),
                "prompt_builder": planning_result.prompt_builder
                if planning_result
                else self._prompt_builder_name(session.creative_mode),
                **(dict(planning_result.metadata) if planning_result else {
                    "canonical_planner": None,
                    "planning_mode": None,
                }),
                **(
                    {"workflow_origin": session.metadata["workflow_origin"]}
                    if session.metadata.get("workflow_origin") else {}
                ),
                **(
                    {"planner_lineage": dict(session.metadata["planner_lineage"])}
                    if session.metadata.get("planner_lineage") else {}
                ),
            },
        )
        self.save_prompt_plan(plan)
        return plan

    def build_wavespeed_generation_contract(self, *, creative_mode: str, prompt_count: int, tag_text: str) -> str:
        mode = self.normalize_mode(creative_mode)
        count = max(1, int(prompt_count or 1))
        if mode in {"premium_teaser", "spicy", "story_sequence", "explicit"}:
            return self.plan_prompts(
                mode=mode,
                creative_tags=tag_text,
                prompt_count=count,
                metadata={"source": "generation_contract"},
            ).prompts[0]
        generation_mode = GENERATION_MODES["3"] if mode == "story_sequence" else GENERATION_MODES["1"]
        return build_chatgpt_prompt(
            prompt_count=count,
            user_request=tag_text,
            generation_mode=generation_mode,
            platform_mode="Social Content Studio",
            spice_level="Spicy" if mode == "spicy" else "Social Safe",
        )

    def build_diversified_prompt_batch(
        self,
        *,
        profile_name: str,
        creative_mode: str,
        tag_text: str,
        reference_text: str,
        prompt_count: int,
        wavespeed_contract: str = "",
    ) -> tuple[str, ...]:
        count = max(1, int(prompt_count or 1))
        mode = self.normalize_mode(creative_mode)
        if mode == "explicit":
            raise RuntimeError(
                "Explicit Content must use CanonicalPromptPlanner; "
                "social prompt planning is forbidden."
            )
        if mode in {"premium_teaser", "spicy", "story_sequence"}:
            planning_result = self.plan_prompts(
                mode=mode,
                creative_tags=tag_text,
                prompt_count=count,
                metadata={"source": "diversified_prompt_batch"},
            )
            return planning_result.prompts
        if mode == "spicy":
            spice_level = "Spicy"
        else:
            spice_level = "Social Safe"
        generation_mode = GENERATION_MODES["1"]
        meta_prompt = build_chatgpt_prompt(
            prompt_count=count,
            user_request=tag_text,
            generation_mode=generation_mode,
            platform_mode="Social Content Studio",
            spice_level=spice_level,
        )
        prompts = generate_prompts_with_grok(meta_prompt, self._grok_api_key())
        normalized_prompts = tuple(
            normalize_social_prompt_continuity(prompt)
            for prompt in prompts[:count]
            if str(prompt).strip()
        )
        return normalized_prompts or (tag_text,)

    def create_prompt_plan(
        self,
        *,
        creator_profile: Mapping[str, Any],
        creative_tags: str | list[str] | tuple[str, ...],
        creative_mode: str,
        prompt_count: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> PromptPlan:
        creator_profile_id = int((creator_profile or {}).get("id"))
        reference = self.reference_library.get_active_canonical_reference(
            creator_profile_id=creator_profile_id,
        )
        session = self.create_session(
            creator_profile_id=creator_profile_id,
            creative_tags=creative_tags,
            creative_mode=creative_mode,
            prompt_count=prompt_count,
            reference_asset=reference,
            metadata={"raw_creative_tags": creative_tags, **dict(metadata or {})},
        )
        return self.build_prompt_plan(
            session,
            reference_asset=reference,
            creator_profile=creator_profile,
        )

    def create_provider_prompt_plan(
        self,
        *,
        creator_profile: Mapping[str, Any],
        creative_tags: str,
        creative_mode: str,
        prompts: tuple[str, ...],
        metadata: Mapping[str, Any] | None = None,
    ) -> PromptPlan:
        """Persist an already reviewed provider batch without replanning it."""
        clean = tuple(str(prompt).strip() for prompt in prompts if str(prompt).strip())
        if not clean:
            raise ValueError("A provider-ready prompt batch is required.")
        creator_profile_id = int((creator_profile or {}).get("id"))
        reference = self.reference_library.get_active_canonical_reference(
            creator_profile_id=creator_profile_id,
        )
        session_metadata = {
            "raw_creative_tags": creative_tags,
            **dict(metadata or {}),
        }
        session = self.create_session(
            creator_profile_id=creator_profile_id,
            creative_tags=creative_tags,
            creative_mode=creative_mode,
            prompt_count=len(clean),
            reference_asset=reference,
            metadata=session_metadata,
        )
        normalized_mode = self.normalize_mode(creative_mode)
        is_explicit = normalized_mode == "explicit"
        plan = PromptPlan(
            plan_id=new_id("prompt_plan"),
            session_id=session.session_id,
            creator_profile_id=creator_profile_id,
            prompt_text="\n\n".join(clean),
            creative_mode=session.creative_mode,
            creative_tags=session.creative_tags,
            reference_asset_id=reference.asset_id if reference else None,
            reference_asset_path=self._reference_path(reference),
            creative_rationale=(
                "Provider-ready prompt plan approved by Canonical Prompt Preview."
            ),
            prompt_metadata={
                "prompt_variations": clean,
                "prompt_count": len(clean),
                "provider_prompt_preview": True,
                "canonical_planner": "creator_os",
                "planning_mode": "explicit" if is_explicit else "premium",
                "prompt_builder": (
                    "canonical_explicit_prompt_planner"
                    if is_explicit
                    else "canonical_seedream_premium_planner"
                ),
                "provider_target": (
                    "provider_selected" if is_explicit else "seedream_5_0_pro"
                ),
                "provider_optimization": (
                    "explicit_provider_optimization"
                    if is_explicit
                    else "seedream_5_0_pro_native"
                ),
                **dict(metadata or {}),
            },
        )
        self.save_prompt_plan(plan)
        return plan

    def load_settings(self, creator_profile_id: int) -> CreativeDirectorSettings:
        data = self._read_json(self.settings_path, {})
        raw = data.get(str(creator_profile_id)) if isinstance(data, dict) else None
        if not isinstance(raw, Mapping):
            return CreativeDirectorSettings(creator_profile_id=int(creator_profile_id))
        return CreativeDirectorSettings(
            creator_profile_id=int(creator_profile_id),
            default_mode=self.normalize_mode(raw.get("default_mode")),
            default_prompt_count=max(1, int(raw.get("default_prompt_count") or 5)),
            favorite_tags=tuple(raw.get("favorite_tags") or ()),
        )

    def save_settings(self, settings: CreativeDirectorSettings) -> None:
        data = self._read_json(self.settings_path, {})
        data[str(settings.creator_profile_id)] = asdict(settings)
        self._write_json(self.settings_path, data)

    def save_session(self, session: CreativeSession) -> None:
        entries = self._read_json(self.sessions_path, [])
        entries.insert(0, {"session": asdict(session), "prompt_plan": None})
        self._write_json(self.sessions_path, entries)

    def save_prompt_plan(self, plan: PromptPlan) -> None:
        entries = self._read_json(self.sessions_path, [])
        for entry in entries:
            session = entry.get("session") if isinstance(entry, dict) else None
            if isinstance(session, dict) and session.get("session_id") == plan.session_id:
                entry["prompt_plan"] = asdict(plan)
                break
        else:
            entries.insert(0, {"session": None, "prompt_plan": asdict(plan)})
        self._write_json(self.sessions_path, entries)

    def history(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 25,
    ) -> tuple[CreativeHistoryEntry, ...]:
        entries = self._read_json(self.sessions_path, [])
        history = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            session = self._session_from_dict(entry.get("session"))
            plan = self._prompt_plan_from_dict(entry.get("prompt_plan"))
            owner_id = session.creator_profile_id if session else (plan.creator_profile_id if plan else None)
            if creator_profile_id is not None and owner_id != int(creator_profile_id):
                continue
            if session:
                history.append(CreativeHistoryEntry(session=session, prompt_plan=plan))
        return tuple(history[:limit])

    def latest_session(self, *, creator_profile_id: int | None) -> CreativeHistoryEntry | None:
        entries = self.history(creator_profile_id=creator_profile_id, limit=1)
        return entries[0] if entries else None

    def build_prompt_text(
        self,
        *,
        profile_name: str,
        creative_mode: str,
        tag_text: str,
        reference_text: str,
        shot_number: int | None = None,
        shot_count: int | None = None,
        **_: Any,
    ) -> str:
        prompts = self.build_diversified_prompt_batch(
            profile_name=profile_name,
            creative_mode=creative_mode,
            tag_text=tag_text,
            reference_text=reference_text,
            prompt_count=shot_count or 1,
        )
        index = max(1, int(shot_number or 1)) - 1
        return prompts[index] if index < len(prompts) else (prompts[0] if prompts else "")

    @staticmethod
    def normalize_mode(mode: Any) -> str:
        value = str(mode or "social_safe").strip().lower().replace(" ", "_").replace("-", "_")
        return value if value in CREATIVE_MODE_OPTIONS else "social_safe"

    @classmethod
    def _session_from_dict(cls, data: Any) -> CreativeSession | None:
        if not isinstance(data, Mapping):
            return None
        return CreativeSession(
            session_id=str(data.get("session_id")),
            creator_profile_id=int(data.get("creator_profile_id")),
            creative_tags=tuple(data.get("creative_tags") or ()),
            creative_mode=cls.normalize_mode(data.get("creative_mode")),
            prompt_count=int(data.get("prompt_count") or 1),
            reference_asset_id=data.get("reference_asset_id"),
            status=data.get("status") or "planned",
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at"),
            source=data.get("source") or "creative_director",
            metadata=data.get("metadata") or {},
        )

    @classmethod
    def _prompt_plan_from_dict(cls, data: Any) -> PromptPlan | None:
        if not isinstance(data, Mapping):
            return None
        return PromptPlan(
            plan_id=str(data.get("plan_id")),
            session_id=str(data.get("session_id")),
            creator_profile_id=int(data.get("creator_profile_id")),
            prompt_text=str(data.get("prompt_text") or ""),
            creative_mode=cls.normalize_mode(data.get("creative_mode")),
            creative_tags=tuple(data.get("creative_tags") or ()),
            reference_asset_id=data.get("reference_asset_id"),
            reference_asset_path=data.get("reference_asset_path"),
            creative_rationale=str(data.get("creative_rationale") or ""),
            prompt_metadata=data.get("prompt_metadata") or {},
            created_at=data.get("created_at") or "",
            status=data.get("status") or "planned",
        )

    @classmethod
    def _prompt_assistant_batch_from_dict(cls, data: Any) -> PromptAssistantBatch | None:
        if not isinstance(data, Mapping):
            return None
        return PromptAssistantBatch(
            batch_id=str(data.get("batch_id") or ""),
            creator_profile_id=int(data.get("creator_profile_id") or 0),
            request_text=str(data.get("request_text") or ""),
            lane=str(data.get("lane") or "premium"),
            prompts=tuple(str(prompt) for prompt in data.get("prompts") or ()),
            used_prompt_numbers=tuple(int(number) for number in data.get("used_prompt_numbers") or ()),
            created_at=str(data.get("created_at") or ""),
        )

    @staticmethod
    def _profile_name(creator_profile: Mapping[str, Any] | None, *, fallback: str) -> str:
        return (
            (creator_profile or {}).get("display_name")
            or (creator_profile or {}).get("persona_name")
            or fallback
        )

    @staticmethod
    def _grok_api_key() -> str:
        api_key = os.getenv("GROK_API_KEY")
        if not api_key:
            raise ValueError("Missing GROK_API_KEY in .env")
        return api_key

    @staticmethod
    def _shoot_length_context(session_context: Mapping[str, Any] | None) -> dict[str, int | str]:
        """Resolve target shoot length and derived escalation pacing for Photoshoot Studio."""
        context = dict(session_context or {})
        try:
            target_shot_count = normalize_target_shot_count(context.get("target_shot_count"))
        except (TypeError, ValueError):
            target_shot_count = 10
        try:
            current_shot = max(1, int(context.get("current_shot") or 1))
        except (TypeError, ValueError):
            current_shot = 1
        try:
            planning_shot = max(current_shot + 1, int(context.get("planning_shot") or current_shot + 1))
        except (TypeError, ValueError):
            planning_shot = current_shot + 1
        try:
            remaining_raw = context.get("remaining_shots")
            remaining_shots = (
                max(0, int(remaining_raw))
                if remaining_raw is not None
                else max(0, target_shot_count - current_shot)
            )
        except (TypeError, ValueError):
            remaining_shots = max(0, target_shot_count - current_shot)

        if target_shot_count == 0:
            return {
                "target_shot_count": 0, "current_shot": current_shot,
                "planning_shot": planning_shot, "remaining_shots": None,
                "editorial_stage": None, "length_band": "open_ended",
                "default_stage_advance": 0, "max_stage_advance": 0,
                "face_only_forbidden": False, "endgame": False,
                "ladder_stages": 0, "open_ended": True,
                "progression_enabled": False,
            }

        # Target length is planning context, not the pacing authority. The latest
        # approved shot and its observed progression always control the next beat.
        ladder_stages = 8
        if target_shot_count <= 6:
            length_band = "short"
        elif target_shot_count <= 12:
            length_band = "standard"
        else:
            length_band = "long"
        default_stage_advance = 1
        max_stage_advance = 2
        face_only_forbidden = False
        endgame = False

        return {
            "target_shot_count": target_shot_count,
            "current_shot": current_shot,
            "planning_shot": planning_shot,
            "remaining_shots": remaining_shots,
            "editorial_stage": str(context.get("editorial_stage") or "Beginning"),
            "length_band": length_band,
            "default_stage_advance": int(default_stage_advance),
            "max_stage_advance": int(max_stage_advance),
            "face_only_forbidden": face_only_forbidden,
            "endgame": endgame,
            "ladder_stages": ladder_stages,
            "open_ended": False,
            "progression_enabled": True,
        }

    @staticmethod
    def _progression_enabled(session_context: Mapping[str, Any] | None) -> bool:
        context = dict(session_context or {})
        if "progression_enabled" in context:
            return bool(context["progression_enabled"])
        return normalize_target_shot_count(context.get("target_shot_count")) > 0

    @staticmethod
    def _freeflow_facial_performance_block() -> str:
        return """FreeFlow facial performance (REQUIRED):
- Preserve the subject's exact facial identity, anatomy, proportions, and recognizable features. Facial identity continuity remains strict.
- Treat the latest approved facial performance as contrast evidence, not as an expression lock.
- Do not repeat the immediately previous approved shot's facial expression, gaze, and head attitude as a package.
- Select a visibly distinct but natural, scene-appropriate facial performance for this shot; variation must be intentional rather than random.
- Specify the expression, gaze direction, mouth state, and head attitude together in the emotion field.
- Natural options include direct or averted gaze, looking slightly up or down, relaxed or intent eyes, closed or subtly parted lips, a restrained smirk, and small chin or head-angle changes. These are examples, never a fixed rotation.
- Avoid exaggerated emotion, cartoonish performance, forced large smiles, or facial changes that compromise identity.""".strip()

    @classmethod
    def _creative_prompt_context(cls, session_context: Mapping[str, Any] | None) -> dict[str, Any]:
        context = dict(session_context or {})
        if cls._progression_enabled(context):
            context["progression_enabled"] = True
            return context
        for key in ("progression_stage", "planning_shot", "remaining_shots", "editorial_stage", "progress_percent"):
            context.pop(key, None)
        latest_approved_shot = dict(context.get("latest_approved_shot") or {})
        latest_approved_shot.pop("progression_stage", None)
        if latest_approved_shot:
            context["latest_approved_shot"] = latest_approved_shot
        context.update({
            "target_shot_count": 0,
            "open_ended": True,
            "progression_enabled": False,
            "creative_structure": "OPEN_ENDED_NON_PROGRESSIVE",
        })
        return context

    @classmethod
    def _explicit_length_pacing_block(cls, session_context: Mapping[str, Any] | None) -> str:
        pace = cls._shoot_length_context(session_context)
        if not pace["progression_enabled"]:
            return """Creative Freeflow (REQUIRED):
- Preserve the current explicit scenario and intensity unless operator guidance explicitly requests a change.
- Explore a distinct pose, composition, expression, camera angle, framing, or natural action without advancing an intensity ladder.
- Shot position must never cause further undress, greater sexual intensity, climax, afterglow, narrative closure, or wardrobe escalation.
- Approved history is variety evidence: avoid duplicates while preserving identity, scene, wardrobe state, lighting, and visual continuity.""".strip()
        target = pace["target_shot_count"]
        remaining = pace["remaining_shots"]
        target_text = "open-ended" if target == 0 else f"{target} shots ({remaining} remaining after the current shot)"
        return f"""
Natural progression pacing (REQUIRED):
- The latest approved shot is the primary pacing authority.
- The approved history establishes the actual progression rate; match that rate for the immediate next frame.
- Normally advance one small, natural step. A second small step is allowed only when the latest approved shot and operator direction clearly support it.
- Target Photoshoot length is advisory context only: {target_text}. Never use it to force a wardrobe, pose, action, camera, framing, or intensity jump.
- Do not force a finale, climax, narrative closure, or accelerated escalation because few target shots remain.
""".strip()

    @staticmethod
    def _build_photoshoot_creative_director_prompt(
        *,
        session_context: Mapping[str, Any],
        approved_history: tuple[Mapping[str, Any], ...],
        creative_mode: str,
        session_direction: str,
        creative_hint: str,
        continuity_locks: Mapping[str, bool],
    ) -> str:
        lock_lines = "\n".join(
            f"- Keep {name.replace('_', ' ')}: {'yes' if enabled else 'no'}"
            for name, enabled in continuity_locks.items()
        )
        history_lines = "\n".join(
            f"- {item.get('title') or item.get('creative_direction') or item}"
            for item in approved_history[-8:]
        ) or "- No approved AI directions yet."
        progression_enabled = CreativeDirectorService._progression_enabled(session_context)
        context_json = json.dumps(CreativeDirectorService._creative_prompt_context(session_context), ensure_ascii=True, indent=2, default=str)
        override_text = session_direction or "None. Maintain the current setting and outfit."
        hint_text = str(creative_hint or "").strip()
        hint_section = (
            "\nCreative Hint:\n"
            f"{hint_text}\n\n"
            "Creative Hint represents user-approved creative intent. Never reject it because of continuity. "
            "Instead reinterpret continuity around the requested evolution while preserving every remaining locked attribute. "
            "If the Creative Hint intentionally changes wardrobe, location, prop, camera distance, or another locked element, "
            "treat that as an intentional evolution of the photoshoot and preserve all other continuity locks. "
            "The Shot Director still owns pose, composition, camera angle, lighting, emotion, creative variation, and framing.\n"
            if hint_text
            else ""
        )
        mode = str(creative_mode or "premium").strip().lower()
        length_pacing = ""
        if mode == "explicit":
            length_pacing = (
                "\n"
                + CreativeDirectorService._explicit_length_pacing_block(session_context)
                + "\n"
            )
        if progression_enabled:
            session_pacing_rules = """- Use approved history, the latest approved shot, continuity, and operator guidance to plan the strongest natural next frame. Target length is advisory only.
- Plan exactly planning_shot as the immediate next frame; never infer or renumber the shot.
- The latest approved shot is the primary pacing and scene-continuity authority. Target shot count is advisory only.
- Recommend a natural progression from the current selected image and approved session history.
- Every approved image should feel like the next frame of a professionally directed photoshoot.
- Progression must be based primarily on the latest approved shot, session history, creative mode, Creative Hint if provided, and approved history; target length must never override their observed pace.
- In safe mode, progress through expression, eye contact, confidence, pose variety, body language, framing, camera angles, composition, and storytelling while remaining SFW.
- In premium mode, progress through tasteful intimacy, confidence, body language, wardrobe styling, pose sophistication, emotional connection, framing, and atmosphere.
- In explicit mode, recommend the next logical small stage from the latest approved frame."""
        else:
            session_pacing_rules = """- CREATIVE FREEFLOW: recommend another strong, visually distinct photograph belonging to the same Photoshoot.
- Use approved history and unexplored opportunities for variety, not as an intensity, wardrobe, emotional, sexual, or narrative ladder.
- Explore another composition, pose, expression, camera angle, natural action, or framing while preserving scene and visual continuity.
- Do not infer pacing from the current or approved shot count. Do not advance a stage, arc, intensity, undress, climax, or finale merely because another shot was approved.
- Preserve the current scenario and intensity unless the operator explicitly requests a change; operator-requested evolution remains authoritative."""
        facial_performance_rules = (
            "\n" + CreativeDirectorService._freeflow_facial_performance_block() + "\n"
            if not progression_enabled else ""
        )
        latest_expression_rule = (
            "- Preserve the latest approved environment, location, wardrobe, clothing state, pose, body orientation, hand placement, camera angle, framing, and lighting unless the operator explicitly directs a change. Its facial performance is contrast context governed by the FreeFlow facial-performance rules."
            if not progression_enabled else
            "- Preserve its environment, location, wardrobe, clothing state, pose, body orientation, hand placement, facial expression, camera angle, framing, and lighting unless the operator explicitly directs a change."
        )
        return f"""
You are the Shot Director for a continuity-locked Creator OS Photoshoot Studio session.

Analyze the current image and recommend exactly one next scene direction. Do not write a renderer prompt.
The Canonical Prompt Planner will convert your creative direction into renderer-ready wording later.

Creative mode: {creative_mode}
Session Direction override: {override_text}
{hint_section}

Priority Order:
1. Creative Hint, if provided.
2. Session Direction.
3. Continuity Locks.
4. AI Creative Direction.

Continuity locks:
{lock_lines}

Session defaults and memory:
{context_json}

Approved direction history:
{history_lines}
{length_pacing}
Rules:
{session_pacing_rules}
{facial_performance_rules}
- Treat latest_approved_shot in Session memory as a structured continuity contract.
{latest_expression_rule}
- Change at most one small natural beat by default. Never begin a new composition, wardrobe, location, or camera setup without explicit operator direction.
- Preserve identity, face continuity, body continuity, hairstyle, makeup, wardrobe, lighting, camera style, and location by default.
- When a Creative Hint is provided, it has higher priority than continuity locks for the hinted element only.
- Never reject the Creative Hint because of continuity; evolve the hinted element naturally and preserve every remaining locked attribute.
- Only change locked elements when the Session Direction explicitly asks for that change.
- If the Session Direction is blank, keep the same room, outfit, lighting, hairstyle, makeup, camera style, and visual tone.
- Safe mode must remain platform-safe. Premium mode can be sensual and subscription-content coded. Explicit mode may include explicit adult direction only when consistent with the session.
- Avoid an exact duplicate through one subtle natural change. Do not change framing, camera distance, scene, wardrobe, or pose category merely to create novelty.

        Return only valid JSON with these string keys:
title
creative_direction
reasoning
continuity_notes
camera_framing
lighting
emotion
pose_composition
""".strip()

    @staticmethod
    def _build_photoshoot_grok_inspiration_prompt(
        *,
        session_context: Mapping[str, Any],
        approved_history: tuple[Mapping[str, Any], ...],
        creative_mode: str,
        session_direction: str,
        creative_hint: str,
        continuity_locks: Mapping[str, bool],
        provider_context: str,
        idea_count: int = 8,
        timeline_labels: tuple[str, ...] = (),
        grok_guidance: str = "",
    ) -> str:
        lock_lines = "\n".join(
            f"- Keep {name.replace('_', ' ')}: {'yes' if enabled else 'no'}"
            for name, enabled in continuity_locks.items()
        )
        history_lines = "\n".join(
            f"- {item.get('title') or item.get('creative_direction') or item}"
            for item in approved_history[-8:]
        ) or "- No approved directions yet."
        progression_enabled = CreativeDirectorService._progression_enabled(session_context)
        context_json = json.dumps(CreativeDirectorService._creative_prompt_context(session_context), ensure_ascii=True, indent=2, default=str)
        guidance_text = str(grok_guidance or "").strip()
        hint_text = str(creative_hint or "").strip() or "None."
        direction_text = str(session_direction or "").strip() or "None."
        provider_text = str(provider_context or "").strip() or "Default Photoshoot Studio provider."
        mode = str(creative_mode or "premium").strip().lower()
        count = max(5, min(10, int(idea_count or 8)))
        labels = tuple(str(label).strip() for label in timeline_labels if str(label or "").strip())
        image_count = len(labels) or 1
        shot_count = max(len(tuple(approved_history or ())), image_count)
        progression_stage = 0
        if progression_enabled and isinstance(session_context, Mapping):
            try:
                progression_stage = int(session_context.get("progression_stage") or 0)
            except Exception:
                progression_stage = 0
        if labels:
            timeline_lines = "\n".join(
                f"- Image {index}: {label}" + ("  ← current/latest approved shot" if index == len(labels) else "")
                for index, label in enumerate(labels, start=1)
            )
        else:
            timeline_lines = "- Image 1: Current/latest approved shot"
        if guidance_text and progression_enabled:
            guidance_section = f"""
User guidance for these suggestions (optional steering — high priority):
"{guidance_text}"

Guidance rules:
- The creator is steering paid NSFW content direction with this short note.
- Every suggestion should clearly move toward that guidance (e.g. if they wrote "topless", all ideas should be topless or immediately arriving at topless).
- Keep continuity with the summarized approved shoot (same person, room, lighting, hair, makeup) unless the guidance itself changes wardrobe/location.
- Still vary pose, hands, and especially facial expression across the list.
- Do not ignore the guidance. Do not water it down into a weaker stage unless the current image is already past it — then advance one natural step beyond it.
- Short tags are fine: "topless", "panties off", "playing with herself", "more horny face", etc.
""".strip()
        elif guidance_text:
            guidance_section = f"""
User guidance for these suggestions (high priority):
"{guidance_text}"

Guidance rules:
- Honor the operator's requested change exactly; operator direction is the only reason to change the established intensity, wardrobe state, or scenario.
- Preserve identity and all unaffected continuity attributes.
- Create varied alternatives around the requested idea without inventing further escalation.
""".strip()
        elif progression_enabled:
            guidance_section = """
User guidance for these suggestions: None.
Continue the natural next beat from the summarized approved arc and creative mode.
""".strip()
        else:
            guidance_section = """
User guidance for these suggestions: None.
Explore distinct visual opportunities within the established scene and intensity.
""".strip()
        if not progression_enabled:
            intensity_rules = f"""
Creative Freeflow (required):
- Produce varied alternatives within the established scene, wardrobe state, mood, and intensity.
- Seek distinct compositions, poses, expressions, camera angles, natural actions, and framings that have not already been approved.
- Approved history and the Photoshoot Summary are anti-repetition evidence, not a staged arc.
- Do not advance intensity, undress, narrative stage, emotional stage, sexual stage, climax, afterglow, or finale because of shot position.
- In explicit mode, omit every automatic explicit progression ladder. Maintain the current explicit scenario/intensity unless the operator explicitly requests a change.
- Preserve location, lighting, hairstyle, makeup, camera style, identity, and all continuity locks unless operator guidance changes a specific element.

{CreativeDirectorService._freeflow_facial_performance_block()}

{CreativeDirectorService._explicit_length_pacing_block(session_context) if mode == "explicit" else ""}
""".strip()
        elif mode == "explicit":
            length_pacing = CreativeDirectorService._explicit_length_pacing_block(session_context)
            pacing_hard_rules = """
- The latest approved shot and approved history are the primary pace controller.
- Measure the actual rate of progression across approved shots and match it for the next frame.
- Idea 1 must be the single best natural immediate next beat. Ideas 2–N are nearby alternatives.
- Normally advance only one small progression stage. A minority alternative may advance two small stages only when the latest frame and operator guidance clearly support it.
- Never accelerate wardrobe removal, explicitness, pose, camera, or framing to satisfy the target shot count.
- Do not force climax, afterglow, or narrative closure because few target shots remain.
""".strip()
            intensity_rules = f"""
Explicit mode — progressive photoshoot ladder:
This is a multi-shot photoshoot that evolves naturally shot-by-shot. Place the latest approved shot on this ladder, then normally advance only one small stage at the pace established by approved history:

1. Clothed / dressed tease (outfit still on; pose, locked teasing/naughty eye contact, soft coy appeal)
2. Partial undress (unbutton, pull straps, lift top, lower bottoms slightly; seductive smirk, bitten lip, fully open appealing eyes)
3. Topless / breasts exposed (bottoms may still be on; sexually enticing open-eyed stare, parted lips)
4. Bottoms off / nude reveal (full or nearly full nudity, still more pose than sex act; open-mouth tease, locked seductive salacious eyes fully open)
5. Sexual teasing (hands near breasts/pussy, spreading, showing, light touch; naughty/horny expression with sharp teasing eye contact)
6. Active masturbation (rubbing, fingering, grinding; pleasure face with awake lustful eyes, moan-ready mouth)
7. Intensified play (deeper fingering, toys, more frantic motion; lost-in-it / desperate lust face still locking eyes)
8. Climax / afterglow (orgasm build, shaking, spent pose; orgasmic or wrecked afterglow expression)

{length_pacing}

Facial expression progression (required):
- Face must evolve every shot. Do NOT keep the same neutral model face, same soft smile, or same calm eye contact.
- Each idea must name a specific facial change that remains a small natural evolution of the latest approved expression.
- PPV face mood stack (combine, do not pick only one): teasing + naughty + seductive + sexually enticing + appealing + salacious.
- Progress expressions along a path like: polite/soft → teasing smirk → bitten lip → locked seductive stare → parted lips → open-mouth moan → orgasmic / afterglow wrecked.
- Eyes are critical: fully open, alert, locked camera eye contact with that combined PPV mood. Never droopy, sleepy, heavy-lidded, half-lidded, half-closed, or vacant — even during heat; only true afterglow/orgasm collapse may soften lids.
- Vary eyes, mouth, brow, and jaw: e.g. locked teasing stare, looking up through lashes with eyes still fully open, tongue tip, o-face building, brow furrow of pleasure.
- Same face reused across the timeline is a failure. Match expression intensity to the body/wardrobe stage.

Hard rules for the next shot:
{pacing_hard_rules}
- Progressive wardrobe removal is allowed only when it is the next natural beat supported by the latest approved shot or explicit operator direction.
- Preserve location, lighting, hairstyle, makeup, and camera style unless Session Direction or Creative Hint changes them.
- Avoid repeating poses, actions, OR facial expressions recorded in the Photoshoot Summary.
- Current approved frame attached: {image_count}. Progression stage: {progression_stage}.
""".strip()
        elif mode == "premium":
            intensity_rules = """
Premium mode intensity rules:
- Keep suggestions sensual, subscription-content coded, teasing, and intimate.
- Read the Photoshoot Summary and continue that sensual arc one step at a time.
- Progress shot-by-shot through confidence, body language, wardrobe tension, erotic atmosphere, and facial expression without full explicit sex acts.
- Face must change each shot: soft → teasing → bitten lip → seductive locked eye contact (teasing/naughty/sexually enticing/appealing) — never the same neutral look twice, and never droopy, sleepy, or half-lidded eyes.
- Prefer one-step escalation from the latest image, not sudden jumps or end-of-shoot climax ideas.
""".strip()
        else:
            intensity_rules = """
Safe mode intensity rules:
- Stay platform-safe and SFW.
- Read the Photoshoot Summary and continue the same story/pose progression.
- Progress through expression, pose variety, framing, confidence, and storytelling only.
- Each idea should change the facial expression slightly (smile, glance, confidence) so faces do not look identical shot to shot.
""".strip()
        workflow_description = (
            "This is a continuity-locked Photoshoot in Creative Freeflow. It explores varied photographs within the established visual world."
            if not progression_enabled else
            "This is a continuity-locked photoshoot that evolves frame by frame from one seed subject."
        )
        idea_goal = (
            "Propose distinct alternatives for another photograph in this Photoshoot."
            if not progression_enabled else
            "Propose the immediate next photoshoot frames that continue this same arc."
        )
        output_rules = (
            """- Use Session memory and approved history to avoid repetition while preserving continuity.
- Do not use shot count as pacing authority and do not create staged progression.
- Each idea is one or two short conversational sentences describing a distinct visual opportunity.
- In explicit mode, keep alternatives at the established scenario/intensity unless operator guidance explicitly requests a change."""
            if not progression_enabled else
            """- Use Session memory to continue the immediate next frame. Target and remaining shots are advisory context, never a pacing override.
- Every idea must describe planning_shot as the immediate next frame; never restart or renumber the Photoshoot.
- Each idea is one or two short conversational sentences describing the next evolving scene.
- In explicit mode, put the recommended natural next progression first as idea 1; the UI pre-selects it for the creator.
- Keep alternatives close to the same immediate next beat. Do not create unrelated compositions merely to make ideas different."""
        )
        freeflow_output_rule = (
            "- In Creative FreeFlow, put the complete expression, gaze, mouth state, and head attitude in each idea so the immediately previous facial-performance package is not repeated."
            if not progression_enabled else ""
        )
        progression_display = f"Progression stage: {progression_stage}" if progression_enabled else "Creative structure: OPEN_ENDED_NON_PROGRESSIVE"
        return f"""
You are Grok helping with creative inspiration for a Creator OS Photoshoot Studio session.

{workflow_description}
You are given the current/latest approved image plus a compact Photoshoot Summary in Session memory.
Use that summary as the authoritative record of established setting, wardrobe, lighting, style,
approved poses/compositions, and remaining creative opportunities. Do not request or reconstruct complete prompt history.

The attached image is the current/latest approved shot. {idea_goal}

Current approved image attachment:
{timeline_lines}

{guidance_section}

Propose exactly {count} distinct next-scene ideas for the following shot.

{intensity_rules}

Output rules:
{output_rules}
- Use latest_approved_shot as a structured continuity contract. Preserve every listed scene and camera attribute unless one small evolution or an explicit operator direction changes it.
- Return exactly {count} ideas as a plain numbered list: 1. ... through {count}. ...
- Every idea MUST include a concrete facial expression or eye/mouth change (not just "looks at the camera").
{freeflow_output_rule}
- If user guidance is provided, every idea must honor that guidance.
- Creative inspiration only.
- Do not write a renderer prompt.
- Do not include camera settings.
- Do not include prompt engineering.
- Do not explain the workflow or name the ladder stage.
- Do not wrap the list in markdown code fences or JSON.

Creative mode: {mode}
Provider context: {provider_text}
Session direction: {direction_text}
User guidance: {guidance_text or "None."}
Creative hint: {hint_text}
Approved shot/direction count: {shot_count}
Current images attached: {image_count}
{progression_display}

Continuity locks:
{lock_lines}

Session memory:
{context_json}

Approved direction history:
{history_lines}
""".strip()

    @staticmethod
    def _build_full_photoshoot_plan_prompt(
        *,
        session_context: Mapping[str, Any],
        creative_mode: str,
        session_direction: str,
        creator_guidance: str,
        continuity_locks: Mapping[str, bool],
        frame_count: int,
    ) -> str:
        lock_lines = "\n".join(
            f"- Keep {name.replace('_', ' ')}: {'yes' if enabled else 'no'}"
            for name, enabled in continuity_locks.items()
        )
        progression_enabled = CreativeDirectorService._progression_enabled(session_context)
        context_json = json.dumps(CreativeDirectorService._creative_prompt_context(session_context), ensure_ascii=True, indent=2, default=str)
        mode = str(creative_mode or "premium").strip().lower()
        guidance = str(creator_guidance or "").strip() or "None."
        direction = str(session_direction or "").strip() or "None."
        if not progression_enabled:
            progression = f"""
Creative Freeflow variety batch (required):
Plan {frame_count} distinct photographs within the established scene and visual continuity.
Use approved continuity, history, and unexplored opportunities to vary pose, expression, natural action, composition, angle, and framing.
Do not create a staged arc. Do not escalate intensity, undress, wardrobe state, narrative, emotion, sexual activity, climax, afterglow, or finale because of frame order.
For explicit mode, preserve the current explicit scenario and intensity unless operator guidance explicitly requests a change.
""".strip()
        elif mode == "explicit":
            length_pacing = CreativeDirectorService._explicit_length_pacing_block(session_context)
            progression = f"""
Explicit progression (required):
Plan {frame_count} natural next frames as a continuation batch, not as the complete Photoshoot or a forced finale.
Use the seed/current image, approved continuity, and operator guidance to choose the strongest coherent progression.
Advance one small natural beat per frame. Do not accelerate explicitness because of shot numbers and do not force a climax or ending in the final frame of this batch.

{length_pacing}
""".strip()
        elif mode == "premium":
            progression = """
Premium progression (required):
Plan a sensual subscription-content arc. Escalate through confidence, wardrobe tension, body language, and bedroom-eye intensity without full explicit sex acts.
""".strip()
        else:
            progression = """
Safe progression (required):
Stay platform-safe. Progress through expression, pose variety, framing, confidence, and storytelling only.
""".strip()
        fixed_length_rules = (
            "- Treat approved history as variety evidence, never as pressure to advance a stage."
            if not progression_enabled else
            "- Treat target_shot_count as advisory planning context only. It must never force faster progression or a finale."
        )
        wardrobe_rule = (
            "- In explicit Freeflow, preserve the established wardrobe and intensity unless operator guidance explicitly changes them."
            if not progression_enabled else
            "- In explicit sessions, let wardrobe progression follow the current frame, approved arc, and operator guidance rather than a remaining-shot schedule."
        )
        sequence_rule = (
            "- Each frame must be visually distinct from the others without implying that later frames are more intense or narratively advanced."
            if not progression_enabled else
            "- Each later shot is one small natural progression from the preceding frame, never a new concept."
        )
        planning_role = (
            "planning a finite Creative Freeflow variety batch"
            if not progression_enabled else
            "planning an entire Creator OS Photoshoot Studio session from one seed image"
        )
        reasoning_description = (
            "why this is a strong distinct opportunity within the established Photoshoot"
            if not progression_enabled else
            "why this is the right beat in the arc"
        )
        facial_performance_rules = (
            CreativeDirectorService._freeflow_facial_performance_block()
            if not progression_enabled else ""
        )
        emotion_schema = (
            "specific facial performance: expression, gaze, mouth state, and head attitude"
            if not progression_enabled else "specific facial expression"
        )
        return f"""
You are the Shot Director {planning_role}.

Analyze the attached seed/current image and return exactly {frame_count} ordered shot plans that form one continuous photoshoot.

Creative mode: {mode}
Session direction: {direction}
Creator guidance: {guidance}

Continuity locks:
{lock_lines}

Session memory:
{context_json}

{progression}

{facial_performance_rules}

Rules:
{fixed_length_rules}
- Shot 1 must begin from the seed's real visual state (same wardrobe level, location, lighting, identity).
{sequence_rule}
- Preserve the preceding frame's environment, location, wardrobe/clothing state, body orientation, camera setup, framing, and lighting unless operator guidance explicitly changes one.
- Preserve identity, face, body, hairstyle, makeup, location, lighting, and camera style unless guidance changes them.
- Vary pose, hands, framing, and especially facial expression every shot.
{wardrobe_rule}
- If creator guidance is provided, honor it without ignoring continuity or inventing changes beyond it.
- Do not write renderer prompts. Do not include camera settings or prompt engineering.

Return ONLY valid JSON:
{{
  "shots": [
    {{
      "shot_number": 1,
      "title": "short title",
      "creative_direction": "1-2 sentences describing this shot",
      "reasoning": "{reasoning_description}",
      "emotion": "{emotion_schema}",
      "camera_framing": "framing",
      "lighting": "lighting note",
      "pose_composition": "pose/composition",
      "continuity_notes": "what stays locked"
    }}
  ]
}}

Exactly {frame_count} objects in shots, numbered 1..{frame_count} in order.
""".strip()

    @classmethod
    def _parse_full_photoshoot_plan(cls, response: str, *, frame_count: int) -> tuple[dict[str, Any], ...]:
        text = str(response or "").strip()
        count = max(4, min(12, int(frame_count or 8)))
        data: Any = None
        cleaned = text
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned.strip(), flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            data = json.loads(cleaned)
        except Exception:
            data = None
        raw_shots: list[Any] = []
        if isinstance(data, Mapping):
            for key in ("shots", "plan", "frames", "scenes"):
                value = data.get(key)
                if isinstance(value, list):
                    raw_shots = list(value)
                    break
        elif isinstance(data, list):
            raw_shots = list(data)
        if not raw_shots:
            # Fallback: numbered prose lines become simple plan beats.
            numbered = re.findall(
                r"(?:^|\n)\s*(?:\d+[\).\:\-])\s+(.+?)(?=(?:\n\s*\d+[\).\:\-]\s+)|\Z)",
                cleaned,
                flags=re.IGNORECASE | re.DOTALL,
            )
            raw_shots = [{"creative_direction": line.strip()} for line in numbered if str(line or "").strip()]
        shots: list[dict[str, Any]] = []
        for index, item in enumerate(raw_shots[:count], start=1):
            if isinstance(item, Mapping):
                direction = str(
                    item.get("creative_direction")
                    or item.get("direction")
                    or item.get("description")
                    or ""
                ).strip()
                title = str(item.get("title") or f"Shot {index}").strip()
                shots.append({
                    "shot_number": index,
                    "title": title or f"Shot {index}",
                    "creative_direction": direction or f"Continue the photoshoot for shot {index}.",
                    "reasoning": str(item.get("reasoning") or "").strip(),
                    "emotion": str(item.get("emotion") or "").strip(),
                    "camera_framing": str(item.get("camera_framing") or item.get("camera") or "").strip(),
                    "lighting": str(item.get("lighting") or "").strip(),
                    "pose_composition": str(item.get("pose_composition") or item.get("pose") or "").strip(),
                    "continuity_notes": str(item.get("continuity_notes") or "").strip(),
                    "status": "pending",
                })
            else:
                text_item = cls._short_inspiration_text(str(item))
                shots.append({
                    "shot_number": index,
                    "title": f"Shot {index}",
                    "creative_direction": text_item,
                    "reasoning": "",
                    "emotion": "",
                    "camera_framing": "",
                    "lighting": "",
                    "pose_composition": text_item,
                    "continuity_notes": "",
                    "status": "pending",
                })
        while len(shots) < count:
            index = len(shots) + 1
            shots.append({
                "shot_number": index,
                "title": f"Shot {index}",
                "creative_direction": f"Advance the session naturally for shot {index} while preserving continuity.",
                "reasoning": "Filled to match the requested frame count.",
                "emotion": "",
                "camera_framing": "",
                "lighting": "",
                "pose_composition": "",
                "continuity_notes": "Preserve locked continuity.",
                "status": "pending",
            })
        if shots:
            shots[0]["status"] = "current"
        return tuple(shots)

    @staticmethod
    def _short_inspiration_text(response: str) -> str:
        text = re.sub(r"\s+", " ", str(response or "").strip())
        if not text:
            return "Try a natural next variation that keeps the session feeling continuous."
        sentences = re.split(r"(?<=[.!?])\s+", text)
        short = " ".join(sentence for sentence in sentences[:2] if sentence).strip()
        return short or text

    @classmethod
    def _parse_inspiration_ideas(cls, response: str, *, idea_count: int = 8) -> tuple[str, ...]:
        text = str(response or "").strip()
        if not text:
            return (cls._short_inspiration_text(""),)

        cleaned = text
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json|text)?", "", cleaned.strip(), flags=re.IGNORECASE).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()

        # JSON array of strings, or object with ideas/suggestions.
        try:
            parsed = json.loads(cleaned)
        except Exception:
            parsed = None
        if isinstance(parsed, list):
            ideas = [cls._short_inspiration_text(str(item)) for item in parsed if str(item or "").strip()]
            if ideas:
                return tuple(ideas[: max(5, min(10, int(idea_count or 8)))])
        if isinstance(parsed, Mapping):
            for key in ("ideas", "suggestions", "options", "scenes"):
                value = parsed.get(key)
                if isinstance(value, list):
                    ideas = [cls._short_inspiration_text(str(item)) for item in value if str(item or "").strip()]
                    if ideas:
                        return tuple(ideas[: max(5, min(10, int(idea_count or 8)))])

        numbered = re.findall(
            r"(?:^|\n)\s*(?:\d+[\).\:\-]|[-*•])\s+(.+?)(?=(?:\n\s*(?:\d+[\).\:\-]|[-*•])\s+)|\Z)",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL,
        )
        ideas = []
        for raw in numbered:
            idea = cls._short_inspiration_text(raw)
            if idea and idea not in ideas:
                ideas.append(idea)
        if ideas:
            return tuple(ideas[: max(5, min(10, int(idea_count or 8)))])

        # Fallback: split on blank lines or treat as a single idea.
        blocks = [block.strip() for block in re.split(r"\n\s*\n", cleaned) if block.strip()]
        if len(blocks) > 1:
            ideas = [cls._short_inspiration_text(block) for block in blocks]
            ideas = [idea for idea in ideas if idea]
            if ideas:
                return tuple(ideas[: max(5, min(10, int(idea_count or 8)))])
        return (cls._short_inspiration_text(cleaned),)

    @classmethod
    def _photoshoot_direction_from_response(
        cls,
        *,
        response: str,
        creative_mode: str,
        session_direction: str,
        continuity_locks: Mapping[str, bool],
    ) -> PhotoshootCreativeDirection:
        text = str(response or "").strip()
        data: Mapping[str, Any] = {}
        try:
            cleaned = text
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?", "", cleaned.strip(), flags=re.IGNORECASE).strip()
                cleaned = re.sub(r"```$", "", cleaned).strip()
            parsed = json.loads(cleaned)
            if isinstance(parsed, Mapping):
                data = parsed
        except Exception:
            data = {}
        if not data:
            lines = [line.strip(" -") for line in text.splitlines() if line.strip()]
            fallback = lines[0] if lines else "Continue the photoshoot with a natural next pose."
            data = {
                "title": "Next Photoshoot Direction",
                "creative_direction": fallback,
                "reasoning": "Derived from the Shot Director response.",
                "continuity_notes": "Maintain the current session continuity unless the creator supplied an override.",
                "camera_framing": "Use close creator framing with the subject as the visual priority.",
                "lighting": "Preserve the current lighting style.",
                "emotion": "Keep the expression natural and connected.",
                "pose_composition": fallback,
            }
        return PhotoshootCreativeDirection(
            title=str(data.get("title") or "Next Photoshoot Direction").strip(),
            creative_direction=str(data.get("creative_direction") or "").strip(),
            reasoning=str(data.get("reasoning") or "").strip(),
            continuity_notes=str(data.get("continuity_notes") or "").strip(),
            camera_framing=str(data.get("camera_framing") or "").strip(),
            lighting=str(data.get("lighting") or "").strip(),
            emotion=str(data.get("emotion") or "").strip(),
            pose_composition=str(data.get("pose_composition") or "").strip(),
            creative_mode=str(creative_mode or "premium").strip().lower(),
            session_direction=str(session_direction or "").strip(),
            continuity_locks=dict(continuity_locks or {}),
            raw_response=text,
        )

    @classmethod
    def _prompt_builder_name(cls, creative_mode: str) -> str:
        mode = cls.normalize_mode(creative_mode)
        if mode in {"premium_teaser", "spicy", "story_sequence"}:
            return "canonical_seedream_premium_planner"
        return "wavespeed_social_prompt_builder"

    @staticmethod
    def _reference_text(reference_asset: ReferenceAsset | None) -> str:
        if not reference_asset:
            return "Reference asset: none."
        return f"Reference asset id: {reference_asset.asset_id}."

    @staticmethod
    def _reference_path(reference_asset: ReferenceAsset | None) -> str | None:
        if not reference_asset:
            return None
        value = getattr(reference_asset, "file_path", None)
        if value:
            return str(value)
        asset = getattr(reference_asset, "asset", None)
        return str(getattr(asset, "original_path", "") or getattr(asset, "preview_path", "") or "") or None

    @staticmethod
    def _read_json(path: Path, default):
        try:
            if not path.exists():
                return default
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, default=str)
