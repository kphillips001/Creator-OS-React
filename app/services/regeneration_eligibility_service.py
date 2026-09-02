"""Authoritative regeneration eligibility and stable reference resolution."""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.models.regeneration import RegenerationEligibility
from app.providers.generation.provider_registry import create_default_registry
from app.repositories.generation_recipe_repository import GenerationRecipeRepository
from app.services.generation_library_service import GenerationLibraryService
from app.services.reference_library_service import ReferenceLibraryService


class RegenerationEligibilityService:
    SUPPORTED_SCHEMA_VERSIONS = frozenset({"generation_recipe_v1"})
    SUPPORTED_WORKFLOWS = frozenset({"premium", "content_studio", "photoshoot", "REGENERATION_STUDIO"})

    def __init__(self, *, generation_library=None, recipes=None, references=None,
                 provider_registry=None):
        self.library = generation_library or GenerationLibraryService()
        self.recipes = recipes or GenerationRecipeRepository()
        self.references = references or ReferenceLibraryService()
        self.providers = provider_registry or create_default_registry()

    def inspect(self, source_generated_image_id: str, *, creator_profile_id: int | None = None) -> RegenerationEligibility:
        source_id = str(source_generated_image_id or "").strip()
        try:
            record = self.library.get(source_id)
        except KeyError:
            return self._no("SOURCE_NOT_FOUND", "Generated image was not found.", source_id)
        return self._inspect_record(record, creator_profile_id=creator_profile_id)

    def _inspect_record(self, record, *, creator_profile_id: int | None = None) -> RegenerationEligibility:
        source_id = str(record.image_id)
        if creator_profile_id is not None and int(record.creator_profile_id) != int(creator_profile_id):
            return self._no("SOURCE_NOT_OWNED", "Generated image does not belong to the active Creator Profile.", source_id)
        if not record.generation_recipe_id:
            return self._no("RECIPE_NOT_CAPTURED", "This historical generation has no captured recipe.", source_id)
        recipe = self.recipes.get(record.generation_recipe_id)
        if recipe is None:
            return self._no("RECIPE_NOT_FOUND", "The linked Generation Recipe was not found.", source_id)
        if recipe.schema_version not in self.SUPPORTED_SCHEMA_VERSIONS:
            return self._no("UNSUPPORTED_RECIPE_SCHEMA", "The Generation Recipe schema is not supported.", source_id, recipe.recipe_id)
        execution = self.recipes.get_execution(recipe.recipe_id)
        if execution is None or execution.status != "SUCCEEDED":
            return self._no("ORIGINAL_EXECUTION_NOT_SUCCESSFUL", "The original provider execution was not successful.", source_id, recipe.recipe_id)
        outputs = self.recipes.outputs(recipe.recipe_id)
        if not any(item.generated_image_id == record.image_id for item in outputs):
            return self._no("OUTPUT_LINK_MISSING", "The recipe is not linked to the selected generated image.", source_id, recipe.recipe_id)
        if not recipe.final_prompt or hashlib.sha256(recipe.final_prompt.encode("utf-8")).hexdigest() != recipe.final_prompt_sha256:
            return self._no("FINAL_PROMPT_INVALID", "The captured final provider prompt is incomplete.", source_id, recipe.recipe_id)
        if recipe.generation_type != "image_to_image" or recipe.media_type != "image" or recipe.source_workflow not in self.SUPPORTED_WORKFLOWS:
            return self._no("UNSUPPORTED_WORKFLOW", "This generative workflow is not supported for regeneration.", source_id, recipe.recipe_id)
        provider = self.providers.get(recipe.provider_id)
        if provider is None:
            return self._no("PROVIDER_UNAVAILABLE", "The captured provider is unavailable.", source_id, recipe.recipe_id)
        metadata = getattr(getattr(provider, "capabilities", None), "metadata", {}) or {}
        adapter = f"{provider.__class__.__module__}.{provider.__class__.__qualname__}"
        if (
            recipe.provider_adapter != adapter
            or (recipe.provider_family and recipe.provider_family != getattr(provider, "provider_family", None))
            or recipe.generation_type not in tuple(getattr(provider.capabilities, "supported_generation_types", ()))
            or (recipe.provider_endpoint and recipe.provider_endpoint != getattr(provider, "endpoint", None))
            or (
            recipe.provider_model and recipe.provider_model != metadata.get("model")
            )
        ):
            return self._no("PROVIDER_INCOMPATIBLE", "The captured provider/model is no longer compatible.", source_id, recipe.recipe_id)
        unsupported_settings = set(dict(recipe.normalized_settings or {})) - {"output_format"}
        if unsupported_settings or any(
            value is not None
            for value in (recipe.width, recipe.height, recipe.aspect_ratio, recipe.resolution)
        ):
            return self._no(
                "SETTINGS_REPLAY_UNSUPPORTED",
                "The captured provider settings cannot yet be replayed safely.",
                source_id, recipe.recipe_id,
            )
        try:
            self.resolve_references(recipe, record.creator_profile_id)
        except ValueError as error:
            return self._no("REFERENCE_UNAVAILABLE", str(error), source_id, recipe.recipe_id)
        return RegenerationEligibility(True, source_generated_image_id=source_id, source_recipe_id=recipe.recipe_id)

    def inspect_many(self, records, *, creator_profile_id: int | None = None):
        records = tuple(records)
        recipe_ids = tuple(record.generation_recipe_id for record in records if record.generation_recipe_id)
        if not recipe_ids or not hasattr(self.recipes, "prefetch"):
            return {
                record.image_id: self._inspect_record(
                    record, creator_profile_id=creator_profile_id,
                )
                for record in records
            }
        prefetched = self.recipes.prefetch(recipe_ids)
        cached_references = _CachedReferenceLibrary(self.references)
        service = RegenerationEligibilityService(
            generation_library=_RecordLookupGenerationLibrary(records, self.library), recipes=prefetched,
            references=cached_references, provider_registry=self.providers,
        )
        return {
            record.image_id: service._inspect_record(
                record, creator_profile_id=creator_profile_id,
            )
            for record in records
        }

    def resolve_references(self, recipe, creator_profile_id: int):
        resolved = []
        positions = [item.position for item in recipe.references]
        if not positions or positions != list(range(1, len(positions) + 1)):
            raise ValueError("Recipe references are missing or out of order.")
        for item in recipe.references:
            if item.role == "CANONICAL_IDENTITY" and item.asset_id:
                reference = self.references.get_owned_reference(
                    item.asset_id, creator_profile_id=int(creator_profile_id),
                )
                path = reference.asset.original_path if reference else None
            elif item.source_type == "GENERATED_IMAGE" and item.generated_image_id:
                try:
                    generated = self.library.get(item.generated_image_id)
                except KeyError:
                    generated = None
                path = generated.output_reference if generated else None
            else:
                path = None
            if not path or not Path(path).expanduser().is_file():
                raise ValueError(f"Required recipe reference at position {item.position} is unavailable.")
            resolved.append((item, str(Path(path).expanduser())))
        if len(resolved) > int(getattr(self.providers.get(recipe.provider_id).capabilities, "max_reference_images", 1)):
            raise ValueError("The captured provider cannot accept all required recipe references.")
        return tuple(resolved)

    @staticmethod
    def _no(code, reason, source_id, recipe_id=None):
        return RegenerationEligibility(False, code, reason, source_id, recipe_id)


class _CachedReferenceLibrary:
    def __init__(self, source):
        self.source = source
        self.cache = {}

    def get_owned_reference(self, asset_id, *, creator_profile_id):
        key = (int(asset_id), int(creator_profile_id))
        if key not in self.cache:
            self.cache[key] = self.source.get_owned_reference(asset_id, creator_profile_id=creator_profile_id)
        return self.cache[key]


class _RecordLookupGenerationLibrary:
    """Reuse records already loaded for a page, falling back only for other IDs."""

    def __init__(self, records, source):
        self.records = {str(record.image_id): record for record in records}
        self.source = source

    def get(self, image_id):
        key = str(image_id)
        if key in self.records:
            return self.records[key]
        return self.source.get(key)
