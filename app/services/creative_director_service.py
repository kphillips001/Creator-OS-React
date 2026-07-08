"""Provider-neutral Creative Director workflow service."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

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
from app.services.reference_library_service import ReferenceLibraryService


class CreativeDirectorService:
    """Owns creative tags, sessions, prompt plans, and recommendations."""

    DEFAULT_STORAGE_DIR = Path("data") / "creative_director"

    SOCIAL_LUCKY_IDEAS = (
        "candid around the house, fitted tee, denim shorts, soft window light, relaxed smile",
        "coffee at home, cozy kitchen counter, casual tank top, waist-up framing, playful glance",
        "bookstore visit, sundress, warm aisle lighting, close creator portrait, approachable energy",
        "beach walk, wind in loose hair, fitted casual top, golden hour, natural smile",
        "porch afternoon, cutoff shorts, soft tee, seated close framing, warm eye contact",
    )

    PREMIUM_LUCKY_IDEAS = (
        "bedroom doorway, fitted crop top, tiny lounge shorts, visible cleavage, warm curtain light",
        "sheer robe over matching lingerie, bathroom vanity, private eye contact, soft morning light",
        "black lace lingerie, thigh-high stockings, heels, head-to-upper-thigh framing, playful confidence",
        "hotel balcony, satin robe loosely tied, low neckline, golden hour, premium teaser mood",
        "kitchen island, bralette under cardigan, hip angle, realistic fabric tension, warm smile",
    )

    EXPLICIT_LUCKY_IDEAS = (
        "private bedroom, topless implied premium set, soft sheets, warm lamp light, confident eye contact",
        "shower glass, wet hair, wet skin, close-medium framing, intimate premium mood",
        "hotel mirror, open robe, lingerie tension, direct private gaze, realistic phone-camera feel",
        "low-lit bedroom, satin sheets, bare shoulder styling, soft teasing expression",
        "bathroom vanity, robe falling off shoulder, warm skin highlights, subscriber-focused framing",
    )

    PREMIUM_GUIDANCE = (
        "Use the active reference as the identity, face, hair, skin tone, body shape, and continuity anchor only. "
        "Do not copy the reference setting, background, outfit, pose, lighting, camera angle, or props unless the "
        "creator explicitly asks for those exact elements. Keep medium-close creator framing with the full face, "
        "full head, natural hair top, and visible body-continuity cues. Premium concepts should feel sensual, "
        "teasing, private, varied, and paid-content-ready while preserving the creator profile's tone."
    )

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        reference_library_service: ReferenceLibraryService | None = None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self.reference_library = reference_library_service or ReferenceLibraryService()

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
        if isinstance(creative_tags, (list, tuple)):
            candidates = [str(item) for item in creative_tags]
        else:
            text = str(creative_tags or "")
            text = re.sub(r"\n\s*(?:\d+[\.\)]|[-*])\s*", ", ", text)
            candidates = re.split(r"[,;\n]+", text)

        tags = []
        seen = set()
        for candidate in candidates:
            tag = re.sub(r"\s+", " ", str(candidate).strip(" .,\t\r\n"))
            key = tag.lower()
            if not tag or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
        return tuple(tags)

    def i_feel_lucky(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        creative_mode: str,
        prompt_count: int = 5,
    ) -> tuple[str, ...]:
        mode = self.normalize_mode(creative_mode)
        source = (
            self.PREMIUM_LUCKY_IDEAS
            if mode in {"premium_teaser", "spicy", "story_sequence"}
            else self.SOCIAL_LUCKY_IDEAS
        )
        profile_name = (
            (creator_profile or {}).get("display_name")
            or (creator_profile or {}).get("persona_name")
            or "creator"
        )
        selected = source[: max(1, min(int(prompt_count or 1), len(source)))]
        return tuple(f"{idea}, {profile_name} style" for idea in selected)

    def premium_lucky_tags(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        prompt_count: int = 5,
        explicit: bool = False,
    ) -> str:
        source = self.EXPLICIT_LUCKY_IDEAS if explicit else self.PREMIUM_LUCKY_IDEAS
        profile_name = self._profile_name(creator_profile, fallback="creator")
        selected = source[: max(1, min(int(prompt_count or 1), len(source)))]
        return "\n".join(
            f"{idea}, {profile_name} style, reference identity continuity"
            for idea in selected
        )

    def enhance_premium_tags(
        self,
        *,
        simple_tags: str,
        creator_profile: Mapping[str, Any] | None = None,
        explicit: bool = False,
    ) -> str:
        tags = self.normalize_tags(simple_tags)
        if not tags:
            return ""
        profile_name = self._profile_name(creator_profile, fallback="creator")
        lane = "explicit-ready premium" if explicit else "premium teaser"
        base = ", ".join(tags)
        safeguards = (
            "visible requested nudity preserved, intimate subscriber framing, no platform UI"
            if explicit
            else "sensual but not explicit by default, paid-wall teaser mood, no platform UI"
        )
        return (
            f"{base}, {profile_name} style, {lane}, varied wardrobe and setting details, "
            "medium-close creator framing with full face and clean space above loose hair, "
            "same reference identity, same natural skin tone, same body-continuity cues, "
            f"{safeguards}, realistic phone-camera creator content"
        )

    def surprise_premium_tags(
        self,
        *,
        simple_tags: str,
        creator_profile: Mapping[str, Any] | None = None,
    ) -> str:
        tags = self.normalize_tags(simple_tags)
        profile_name = self._profile_name(creator_profile, fallback="creator")
        anchor = ", ".join(tags) if tags else "premium private creator concept"
        return (
            f"{anchor}, unexpected premium variation, private hotel suite after sunset, "
            "satin robe slipping off one shoulder, warm practical lamp light, direct teasing eye contact, "
            f"{profile_name} style, same reference identity, realistic fabric tension, "
            "head-to-upper-thigh creator framing"
        )

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
        lane_value = str(lane or "premium").strip().lower()
        profile_name = self._profile_name(creator_profile, fallback="creator")
        prompts = tuple(
            self._build_prompt_assistant_card(
                request=request,
                index=index,
                lane=lane_value,
                profile_name=profile_name,
            )
            for index in range(1, count + 1)
        )
        batch = PromptAssistantBatch(
            batch_id=new_id("prompt_assistant"),
            creator_profile_id=creator_profile_id,
            request_text=request,
            lane=lane_value,
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

    def suggested_ideas(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        creative_mode: str,
    ) -> tuple[CreativeRecommendation, ...]:
        tags = self.i_feel_lucky(
            creator_profile=creator_profile,
            creative_mode=creative_mode,
            prompt_count=3,
        )
        return tuple(
            CreativeRecommendation(
                title=f"Idea {index}",
                tags=self.normalize_tags(tag_line),
                creative_mode=self.normalize_mode(creative_mode),
                rationale="Derived from creator profile, selected mode, and reference-led planning.",
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
        profile_name = (
            (creator_profile or {}).get("display_name")
            or (creator_profile or {}).get("persona_name")
            or "Creator"
        )
        tag_text = ", ".join(session.creative_tags)
        reference_text = (
            f"Use Reference Asset #{reference_asset.asset_id} as identity and continuity anchor."
            if reference_asset
            else "No active Reference Asset selected."
        )
        prompt_text = self.build_prompt_text(
            profile_name=profile_name,
            creative_mode=session.creative_mode,
            tag_text=tag_text,
            reference_text=reference_text,
        )
        rationale = (
            "Prompt Plan created from Creative Director tags, selected creative mode, "
            "Creator Profile context, and the active Reference Library asset."
        )
        plan = PromptPlan(
            plan_id=new_id("prompt_plan"),
            session_id=session.session_id,
            creator_profile_id=session.creator_profile_id,
            prompt_text=prompt_text,
            creative_mode=session.creative_mode,
            creative_tags=session.creative_tags,
            reference_asset_id=reference_asset.asset_id if reference_asset else None,
            reference_asset_path=reference_asset.asset.original_path if reference_asset else None,
            creative_rationale=rationale,
            prompt_metadata={
                "owner": "Creative Director",
                "provider_neutral": True,
                "generation_execution": "future",
                "prompt_count": session.prompt_count,
                "reference_required": reference_asset is not None,
                "premium_guidance": self.PREMIUM_GUIDANCE
                if session.creative_mode in {"premium_teaser", "spicy", "story_sequence"}
                else None,
            },
        )
        self.save_prompt_plan(plan)
        return plan

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
    ) -> str:
        mode = self.normalize_mode(creative_mode)
        premium_guidance = (
            f"Premium guidance: {self.PREMIUM_GUIDANCE} "
            if mode in {"premium_teaser", "spicy", "story_sequence"}
            else ""
        )
        return (
            f"{profile_name} creator-content concept. "
            f"Creative mode: {mode}. "
            f"Creative tags: {tag_text}. "
            f"{reference_text} "
            f"{premium_guidance}"
            "Keep the subject primary, use natural creator framing, preserve creator identity from the reference, "
            "and produce a provider-neutral prompt plan for future generation."
        )

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
    def _build_prompt_assistant_card(
        *,
        request: str,
        index: int,
        lane: str,
        profile_name: str,
    ) -> str:
        mood_options = (
            "warm private eye contact",
            "playful teasing confidence",
            "soft intimate subscriber energy",
            "relaxed premium girlfriend mood",
            "cinematic but realistic creator framing",
        )
        setting_options = (
            "hotel room window light",
            "bedroom doorway",
            "bathroom vanity",
            "mirror selfie corner",
            "soft couch morning light",
        )
        mood = mood_options[(index - 1) % len(mood_options)]
        setting = setting_options[(index - 1) % len(setting_options)]
        lane_label = "explicit-ready premium" if lane == "explicit" else "premium teaser"
        return (
            f"{request}, {setting}, {mood}, {profile_name} style, {lane_label}, "
            "same reference identity, same natural skin tone, same body-continuity cues, "
            "medium-close creator framing with full face and clean space above loose hair, "
            "realistic phone-camera creator content, no platform UI, no captions, no watermarks"
        )

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
