"""Durable, idempotent Generation Library to Photoshoot intake."""
from __future__ import annotations

from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from app.repositories.assembled_photoshoot_intake_repository import AssembledPhotoshootIntakeRepository
from app.services.background_operation_service import BackgroundOperationService
from app.services.generation_library_service import GenerationLibraryService


class AssembledPhotoshootIntakeService:
    ORIGIN = "GENERATION_LIBRARY_IMPORT"
    EXECUTOR_KEY = "assembled_photoshoot_intake"

    def __init__(self, *, repository=None, generation_library=None, operations=None):
        self.repository = repository or AssembledPhotoshootIntakeRepository()
        self.library = generation_library or GenerationLibraryService()
        self.operations = operations or BackgroundOperationService()

    def create(self, *, creator_profile_id: int, account_id: int | None,
               image_ids, hero_image_id: str | None = None,
               idempotency_key: str | None = None):
        ordered = tuple(str(value).strip() for value in image_ids)
        if len(ordered) < 2:
            raise ValueError("Select at least two Generation Library images.")
        if any(not value for value in ordered) or len(set(ordered)) != len(ordered):
            raise ValueError("Generation Library image IDs must be unique and non-empty.")
        hero = str(hero_image_id or ordered[0]).strip()
        if hero not in ordered:
            raise ValueError("Hero image must be one of the selected images.")
        for image_id in ordered:
            try:
                record = self.library.get(image_id)
            except KeyError as error:
                raise ValueError(f"Generation Library image not found: {image_id}") from error
            if int(record.creator_profile_id) != int(creator_profile_id):
                raise ValueError("All selected images must belong to the active Creator Profile.")
            if record.status != "active":
                raise ValueError("Only active Generation Library images can create a Photoshoot.")

        key = str(idempotency_key or "").strip() or sha256(
            f"assembled-photoshoot:{creator_profile_id}:{'|'.join(ordered)}".encode()
        ).hexdigest()
        intake_id = uuid5(NAMESPACE_URL, f"creator-os:assembled-photoshoot-intake:{creator_profile_id}:{key}")
        # The current schema requires a non-null pre-intelligence value. Keep it
        # explicitly technical and out of all AI/operator-facing title inputs.
        provisional_name = f"internal:assembled-photoshoot:{intake_id}"
        try:
            intake, created = self.repository.create(
                intake_id=intake_id, creator_profile_id=creator_profile_id,
                idempotency_key=key, display_name=provisional_name, image_ids=ordered,
                hero_image_id=hero,
            )
        except Exception as error:
            if "assembled_photoshoot_intake_members_image_id_key" in str(error):
                raise ValueError(
                    "One or more selected images already belong to an assembled Photoshoot intake."
                ) from error
            raise
        if not created and tuple(intake["ordered_image_ids"]) != ordered:
            raise ValueError("Idempotency key is already associated with another Photoshoot intake.")
        if intake.get("operation_id"):
            existing = self.operations.get(
                intake["operation_id"], creator_profile_id=creator_profile_id,
                account_id=None,
            )
            if existing is not None:
                return intake, existing, False
        operation, operation_created = self.operations.create(
            operation_type="assembled_photoshoot_intake",
            originating_workspace="generation_library",
            creator_profile_id=creator_profile_id,
            account_id=account_id,
            subject_type="assembled_photoshoot_intake",
            subject_id=str(intake_id),
            idempotency_key=f"assembled-photoshoot:{key}",
            executor_key=self.EXECUTOR_KEY,
            progress_total=len(ordered) + 2,
            current_stage="QUEUED",
            stage_message="Photoshoot creation queued",
            cancellation_supported=False,
            metadata={"intake_id": str(intake_id), "image_ids": list(ordered),
                      "provisional_display_name": provisional_name, "source_kind": self.ORIGIN},
        )
        self.repository.attach_operation(intake_id, operation.operation_id)
        return self.repository.get(intake_id), operation, operation_created
