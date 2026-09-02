"""Background executor for source-neutral assembled Photoshoot intake."""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.models.content_intelligence_profile import is_content_intelligence_complete
from app.repositories.assembled_photoshoot_intake_repository import AssembledPhotoshootIntakeRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.generation_library_service import GenerationLibraryService
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService
from app.services.staged_asset_registration_service import StagedAssetRegistrationService


class AssembledPhotoshootBackgroundExecutor:
    executor_key = "assembled_photoshoot_intake"

    def __init__(self, *, repository=None, library=None, registration=None,
                 photoshoots=None, deliverables=None):
        self.repository = repository or AssembledPhotoshootIntakeRepository()
        self.library = library or GenerationLibraryService()
        self.registration = registration or StagedAssetRegistrationService(
            generation_library_service=self.library)
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.deliverables = deliverables or PhotoshootCommerceDeliverableService(
            repository=self.photoshoots)

    def execute(self, operation, operations, *, worker_id: str):
        intake_id = str(dict(operation.metadata or {}).get("intake_id") or operation.subject_id)
        intake = self.repository.get(intake_id)
        if intake is None:
            raise KeyError("Assembled Photoshoot intake not found.")
        if intake["status"] == "SUCCEEDED":
            self.repository.reconcile_dispositions(intake_id)
            operations.succeed(
                operation.operation_id, result_reference=str(intake["deliverable_id"]),
                metadata={"deliverable_id": str(intake["deliverable_id"]), "intake_id": intake_id})
            return
        self.repository.start(intake_id)
        members = self.repository.members(intake_id)
        ready = True
        asset_ids = []
        records = []
        try:
            for index, member in enumerate(members, 1):
                record = self.library.get(str(member["image_id"]))
                records.append(record)
                result = self.registration.register(
                    record, creator_profile_id=int(intake["creator_profile_id"]),
                    registration_purpose="PHOTOSHOOT_MEMBER", finalize_generation=False,
                )
                if not result.success or result.asset_id is None:
                    raise RuntimeError(result.message or "Canonical Asset registration failed.")
                asset_ids.append(int(result.asset_id))
                self.repository.record_asset(intake_id, record.image_id, int(result.asset_id))
                self.library.mark_registered(record.image_id, int(result.asset_id))
                ready = ready and result.analysis_status == "READY"
                operations.progress(
                    operation.operation_id, current=index, total=len(members) + 2,
                    percent=(index / (len(members) + 2)) * 100,
                    stage="REGISTERING_ASSETS", message=f"Registered image {index} of {len(members)}")
            if not ready:
                self.repository.waiting(intake_id)
                operations.repository.transition(
                    operation.operation_id, "WAITING_EXTERNAL", stage="WAITING_INTELLIGENCE",
                    message="Waiting for canonical Asset Intelligence")
                return

            session_key = f"assembled:{intake_id}"
            intelligence = self.photoshoots.content_intelligence_for_assets(tuple(asset_ids))
            by_asset = {int(row["asset_id"]): row for row in intelligence}
            if any(not is_content_intelligence_complete(
                       by_asset.get(asset_id, {}).get("content_intelligence_status"))
                   for asset_id in asset_ids):
                self.repository.waiting(intake_id)
                operations.repository.transition(
                    operation.operation_id, "WAITING_EXTERNAL", stage="WAITING_INTELLIGENCE",
                    message="Waiting for canonical Content Intelligence")
                return
            chapters = tuple({
                "asset_id": asset_id,
                "shot_order": position,
                "is_seed": records[position - 1].image_id == str(intake["hero_image_id"]),
                "image_reference": records[position - 1].output_reference,
                "approved_prompt": records[position - 1].prompt_text,
                "approved_metadata": {
                    "source_generation_image_id": records[position - 1].image_id,
                    "generation_recipe_id": records[position - 1].generation_recipe_id,
                    "generation_metadata": dict(records[position - 1].generation_metadata or {}),
                    "prompt_metadata": dict(records[position - 1].prompt_metadata or {}),
                },
                "canonical_content_intelligence": dict(by_asset[asset_id].get("content_profile") or {}),
                "canonical_normalized_context": dict(by_asset[asset_id].get("normalized_context") or {}),
            } for position, asset_id in enumerate(asset_ids, 1))
            hero_index = next(index for index, record in enumerate(records)
                              if record.image_id == str(intake["hero_image_id"]))
            hero_asset_id = asset_ids[hero_index]
            operations.stage(operation.operation_id, "AGGREGATE_INTELLIGENCE",
                             "Building canonical Photoshoot Intelligence")
            profile = self.deliverables.run_source_neutral_intelligence(
                session_key=session_key, chapters=chapters,
                display_name="", hero_asset_id=hero_asset_id)
            # The canonical intelligence service already owns required-field
            # validation and its existing failure/retry policy.
            canonical_title = str(profile["commercial_title"]).strip()
            deliverable_id = uuid5(NAMESPACE_URL, f"creator-os:photoshoot-deliverable:{session_key}")
            self.repository.finalize(
                intake_id=intake_id, deliverable_id=deliverable_id, session_key=session_key,
                creator_profile_id=int(intake["creator_profile_id"]),
                display_name=canonical_title, asset_ids=asset_ids,
                hero_asset_id=hero_asset_id)
            operations.succeed(
                operation.operation_id, result_reference=str(deliverable_id),
                metadata={"deliverable_id": str(deliverable_id), "intake_id": intake_id,
                          "source_kind": "GENERATION_LIBRARY_IMPORT", "image_count": len(asset_ids)},
                message="Photoshoot created in Asset Library")
        except Exception as error:
            self.repository.fail(intake_id, error)
            raise
