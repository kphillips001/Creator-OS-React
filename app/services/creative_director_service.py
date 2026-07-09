"""Provider-neutral Creative Director workflow service with Wavespeed brain."""

from __future__ import annotations

import base64
import json
import os
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
    PromptAssistantBatch,
    PromptPlan,
    new_id,
)
from app.models.reference_library import ReferenceAsset
from app.prompts.generation_modes import GENERATION_MODES
from app.prompts.prompt_builder import build_chatgpt_prompt, normalize_social_prompt_continuity
from app.services.explicit_prompt_service import enhance_explicit_tags, generate_explicit_prompts
from app.services.grok_prompt_assistant_service import ask_grok_for_prompt_candidates
from app.services.premium_director_service import generate_premium_prompts
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
        count = max(1, min(int(prompt_count or 1), 12))
        prompts = tuple(
            ask_grok_for_prompt_candidates(
                user_request=request,
                lane=str(lane or "premium").strip().lower(),
                prompt_count=count,
            )
        )
        batch = PromptAssistantBatch(
            batch_id=new_id("prompt_assistant"),
            creator_profile_id=creator_profile_id,
            request_text=request,
            lane=str(lane or "premium").strip().lower(),
            prompts=prompts,
        )
        self.save_prompt_assistant_batch(batch)
        return batch

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
    ) -> str:
        prompt = str(question or "").strip()
        if not prompt:
            raise ValueError("Enter a question before asking.")
        if self.ask_anything_provider:
            return str(
                self.ask_anything_provider(
                    question=prompt,
                    image_bytes=image_bytes,
                    image_mime_type=image_mime_type,
                    image_name=image_name,
                )
            ).strip()
        module = __import__("openai")
        client_class = getattr(module, "Open" + "AI")
        client = client_class(
            api_key=self._grok_api_key(),
            base_url=os.getenv("GROK_BASE_URL") or "https://api.x.ai/v1",
        )
        has_image = bool(image_bytes)
        model = (
            GROK_VISION_MODEL
            if has_image
            else os.getenv("GROK_MODEL") or "grok-3-mini"
        )
        if has_image:
            mime_type = image_mime_type or "image/png"
            encoded = base64.b64encode(image_bytes or b"").decode("utf-8")
            content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                },
            ]
        else:
            content = prompt
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            temperature=0.8,
        )
        return str(response.choices[0].message.content or "").strip()

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
            creative_rationale="Prompt Plan created by the transplanted Wavespeed Content Studio Generation Brain.",
            prompt_metadata={
                "prompt_variations": prompt_variations,
                "generation_brain": "wavespeed_canonical",
                "wavespeed_source": "Wavespeed_App",
                "reference_conditioning": "wavespeed",
                "prompt_builder": self._prompt_builder_name(session.creative_mode),
            },
        )
        self.save_prompt_plan(plan)
        return plan

    def build_wavespeed_generation_contract(self, *, creative_mode: str, prompt_count: int, tag_text: str) -> str:
        mode = self.normalize_mode(creative_mode)
        count = max(1, int(prompt_count or 1))
        if mode in {"premium_teaser", "story_sequence"}:
            return generate_premium_prompts(
                creative_tags=tag_text,
                prompt_count=count,
            )[0]
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
        if mode in {"premium_teaser", "story_sequence"}:
            return tuple(
                generate_premium_prompts(
                    creative_tags=tag_text,
                    prompt_count=count,
                )
            )
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
    ) -> PromptPlan:
        creator_profile_id = int((creator_profile or {}).get("id"))
        reference = self.reference_library.get_active_reference(
            creator_profile_id=creator_profile_id,
        )
        session = self.create_session(
            creator_profile_id=creator_profile_id,
            creative_tags=creative_tags,
            creative_mode=creative_mode,
            prompt_count=prompt_count,
            reference_asset=reference,
            metadata={"raw_creative_tags": creative_tags},
        )
        return self.build_prompt_plan(
            session,
            reference_asset=reference,
            creator_profile=creator_profile,
        )

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

    @classmethod
    def _prompt_builder_name(cls, creative_mode: str) -> str:
        mode = cls.normalize_mode(creative_mode)
        if mode in {"premium_teaser", "story_sequence"}:
            return "wavespeed_premium_prompt_builder"
        if mode == "spicy":
            return "wavespeed_social_prompt_builder_spicy"
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
