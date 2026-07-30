"""Shared Content Studio control configuration."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.creative_director_service import CreativeDirectorService
from app.services.generation_engine_service import GenerationEngineService


PREMIUM_PROVIDER_LABELS = {
    "seedream_5_0_pro": "Seedream 5.0 Pro",
    "future_provider": "Future Provider",
}

PREMIUM_CREATIVE_MODE_LABELS = {
    "premium_teaser": "Premium Teaser",
    "spicy": "Spicy",
    "story_sequence": "Story Sequence",
}

PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM = 1
PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM = 20
PREMIUM_STUDIO_PREFERRED_PROVIDER_ID = "seedream_5_0_pro"
PREMIUM_STUDIO_PROVIDER_ORDER = (
    "seedream_5_0_pro",
)


def premium_studio_provider_options(
    generation_engine: GenerationEngineService,
) -> tuple[tuple[str, str], ...]:
    registry = getattr(generation_engine, "provider_registry", None)
    provider_ids = tuple(getattr(registry, "provider_ids", lambda: ())())
    if not provider_ids:
        return (("future_provider", PREMIUM_PROVIDER_LABELS["future_provider"]),)
    registered_provider_ids = set(provider_ids)
    options = [
        (provider_id, PREMIUM_PROVIDER_LABELS[provider_id])
        for provider_id in PREMIUM_STUDIO_PROVIDER_ORDER
        if provider_id in registered_provider_ids
    ]
    return tuple(options) or (("future_provider", PREMIUM_PROVIDER_LABELS["future_provider"]),)


def default_provider_index(
    provider_ids: tuple[str, ...],
    *,
    preferred_provider_id: str = PREMIUM_STUDIO_PREFERRED_PROVIDER_ID,
) -> int:
    return provider_ids.index(preferred_provider_id) if preferred_provider_id in provider_ids else 0


@dataclass(frozen=True)
class ContentStudioConfiguration:
    modes: tuple[tuple[str, str], ...]
    prompt_count_minimum: int
    prompt_count_maximum: int
    default_mode: str
    default_prompt_count: int
    providers: tuple[tuple[str, str], ...]
    default_provider: str


class ContentStudioConfigurationService:
    def __init__(
        self,
        *,
        creative_director: CreativeDirectorService,
        generation_engine: GenerationEngineService,
    ) -> None:
        self.creative_director = creative_director
        self.generation_engine = generation_engine

    def load(self, creator_profile_id: int) -> ContentStudioConfiguration:
        settings = self.creative_director.load_settings(creator_profile_id)
        modes = tuple(PREMIUM_CREATIVE_MODE_LABELS.items())
        default_mode = (
            settings.default_mode
            if settings.default_mode in PREMIUM_CREATIVE_MODE_LABELS
            else modes[0][0]
        )
        default_prompt_count = min(
            max(settings.default_prompt_count, PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM),
            PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
        )
        providers = premium_studio_provider_options(self.generation_engine)
        provider_ids = tuple(provider_id for provider_id, _ in providers)
        default_provider = provider_ids[
            default_provider_index(
                provider_ids,
                preferred_provider_id=PREMIUM_STUDIO_PREFERRED_PROVIDER_ID,
            )
        ]
        return ContentStudioConfiguration(
            modes=modes,
            prompt_count_minimum=PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
            prompt_count_maximum=PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
            default_mode=default_mode,
            default_prompt_count=default_prompt_count,
            providers=providers,
            default_provider=default_provider,
        )
