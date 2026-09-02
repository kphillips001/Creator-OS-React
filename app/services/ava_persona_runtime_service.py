"""Canonical, public-safe Ava persona projection for runtime generation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.repositories.creator_lifestyle_repository import CreatorLifestyleRepository
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.creator_world_model_repository import CreatorWorldModelRepository
from app.repositories.social_creative_direction_repository import (
    SocialCreativeDirectionRepository,
)


_BOOK_PATTERN = re.compile(r"\b(?:books?|reading|bookstores?|libraries?)\b", re.I)
_PRIVATE_PATTERN = re.compile(r"\bWilmington\b|internal_home_base", re.I)


@dataclass(frozen=True)
class AvaPersonaRuntimeProjection:
    schema: str
    source_profile_id: int
    source_account_id: str
    canonical_authority: str
    identity: dict[str, Any]
    stable_public: tuple[str, ...]
    stable_private_excluded: tuple[str, ...]
    low_stakes_texture: tuple[str, ...]
    consequential_requires_authority: tuple[str, ...]
    selected_persona_facts: tuple[str, ...]
    selected_lifestyle_facts: tuple[str, ...]
    relevance_domains: tuple[str, ...]
    voice_contract: tuple[str, ...]
    boundaries: tuple[str, ...]
    legacy_persona_fallback_used: bool
    books_removed_from_canon: bool

    def diagnostics(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("identity", None)
        data["worldModelIncluded"] = True
        data["publicSafeProjection"] = True
        data["privateFactsExcluded"] = True
        data["legacyPersonaSources"] = []
        data["reason"] = "ACCOUNT_SCOPED_CANONICAL_PERSONA"
        return data

    def prompt_block(self) -> str:
        facts = "\n".join(f"- {item}" for item in self.selected_persona_facts)
        lifestyle = "\n".join(f"- {item}" for item in self.selected_lifestyle_facts)
        voice = "\n".join(f"- {item}" for item in self.voice_contract)
        boundaries = "\n".join(f"- {item}" for item in self.boundaries)
        return f"""CANONICAL AVA PERSONA RUNTIME — PUBLIC SAFE
Authority: active account-scoped Creator Profile; canonical persisted sources outrank legacy persona files.
Identity: {self.identity.get('name')} is an adult {self.identity.get('age')}-year-old woman.

RELEVANT AVA GROUNDING (optional; never force a fact statement)
{facts or '- No explicit Ava fact is needed for this turn.'}
{lifestyle}
- Normally surface at most one or two relevant Ava facts in short conversation.
- Never claim books, reading, bookstores, or libraries are Ava interests.

VOICE
{voice}
- Persona controls HOW authorized behavior sounds. Sales Brain and deterministic commerce own WHAT is authorized.
- Questions are optional. Do not manufacture a question, biography dump, therapist response, or polished marketing copy.
- Casual means low intensity, not personality disabled.

PRIVACY AND FACT SAFETY
- Public location is coastal East Coast only. Never reveal or infer an exact home city or private location.
- Ephemeral coffee, couch, chores, music, getting-ready, or winding-down texture may be used when plausible but must not become biography.
- Do not invent appointments, trips, relationships, named people, pets, jobs, purchases, medical facts, commitments, or exact-location events.
{boundaries}
"""


class AvaPersonaRuntimeService:
    """Build a side-effect-free projection from existing canonical stores."""

    SCHEMA = "ava_persona_runtime_v1"
    _DOMAINS = {
        "outdoors": re.compile(r"\b(?:hik|trail|camp|mountain|lake|outdoor|cabin)\w*\b", re.I),
        "coastal": re.compile(r"\b(?:coast|beach|ocean|water|dock|marsh|boardwalk|weather)\w*\b", re.I),
        "home": re.compile(r"\b(?:home|couch|coffee|lazy|morning|evening|chores|music)\w*\b", re.I),
        "work": re.compile(r"\b(?:work|office|job|shift|event)\w*\b", re.I),
        "identity": re.compile(r"\b(?:you|yourself|where are you from|what do you like)\b", re.I),
        "sexual": re.compile(r"\b(?:horny|naked|sexy|fuck|pussy|cock|cum)\w*\b", re.I),
    }

    def __init__(self, *, profile_loader=get_active_creator_profile,
                 world_repository=None, lifestyle_repository=None,
                 social_repository=None):
        self.profile_loader = profile_loader
        self.worlds = world_repository or CreatorWorldModelRepository()
        self.lifestyles = lifestyle_repository or CreatorLifestyleRepository()
        self.social = social_repository or SocialCreativeDirectionRepository()

    @staticmethod
    def _safe(value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if _PRIVATE_PATTERN.search(text) or _BOOK_PATTERN.search(text):
            return ""
        return text

    @classmethod
    def _domains(cls, topic: str) -> tuple[str, ...]:
        found = tuple(name for name, pattern in cls._DOMAINS.items() if pattern.search(topic or ""))
        return found or ("ordinary",)

    def build(self, *, fanvue_account_id: int | str, topic: str = "",
              creator_profile: dict | None = None) -> AvaPersonaRuntimeProjection:
        account_id = str(fanvue_account_id)
        profile = dict(creator_profile or self.profile_loader(account_id) or {})
        if not profile:
            raise LookupError(f"No active creator profile exists for account {account_id}.")
        profile_id = int(profile["id"])
        world = self.worlds.get(creator_profile_id=profile_id, fanvue_account_id=account_id) or {}
        lifestyle = self.lifestyles.get(creator_profile_id=profile_id, fanvue_account_id=account_id) or {}
        social = self.social.get(creator_profile_id=profile_id, fanvue_account_id=account_id) or {}
        domains = self._domains(topic)

        base = [self._safe(profile.get("personality_description")),
                self._safe(profile.get("archetype"))]
        domain_facts: dict[str, list[str]] = {
            "outdoors": [self._safe(lifestyle.get("outdoor_lifestyle")),
                         self._safe(lifestyle.get("weekend_escapes"))],
            "coastal": [self._safe(world.get("public_location_description")),
                        self._safe(world.get("coastal_environments"))],
            "home": [self._safe(world.get("home_and_indoor_environments"))],
            "work": [self._safe(lifestyle.get("career"))],
            "identity": [self._safe(profile.get("backstory")),
                         self._safe(lifestyle.get("small_town_roots"))],
        }
        selected = [item for item in base if item]
        lifestyle_selected: list[str] = []
        if "sexual" not in domains:
            for domain in domains:
                lifestyle_selected.extend(item for item in domain_facts.get(domain, []) if item)
        selected = selected[:2]
        lifestyle_selected = lifestyle_selected[:2]
        boundaries = tuple(filter(None, (
            self._safe(profile.get("boundaries")),
            self._safe(profile.get("sexual_boundaries")),
            self._safe(profile.get("hard_limits")),
            self._safe(social.get("things_to_avoid")),
        )))
        return AvaPersonaRuntimeProjection(
            schema=self.SCHEMA, source_profile_id=profile_id,
            source_account_id=account_id,
            canonical_authority="ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE",
            identity={"name": profile.get("persona_name") or "Ava", "age": profile.get("age"),
                      "adult": bool(int(profile.get("age") or 0) >= 18),
                      "publicLocation": "Coastal East Coast"},
            stable_public=("adult female creator", "coastal East Coast",
                           "small-town/down-home roots", "outdoors-oriented"),
            stable_private_excluded=("precise home city", "internal home base"),
            low_stakes_texture=("coffee", "couch", "chores", "music", "getting ready", "winding down"),
            consequential_requires_authority=("appointments", "travel plans", "relationships",
                "named people", "pets", "employment events", "purchases", "medical facts",
                "commitments", "exact locations"),
            selected_persona_facts=tuple(selected),
            selected_lifestyle_facts=tuple(lifestyle_selected), relevance_domains=domains,
            voice_contract=("short private-phone texting", "warm, relaxed, feminine, grounded",
                "playful and approachable with a subtle natural flirt signature",
                "down-home demeanor without a cartoon dialect", "confident without arrogance",
                "sexy without porn-bot, escort, influencer, therapist, or customer-service voice"),
            boundaries=boundaries, legacy_persona_fallback_used=False,
            books_removed_from_canon=True,
        )
