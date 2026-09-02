"""Idempotent Generation Library intake for reusable Engagement Teasers."""

from dataclasses import dataclass

from app.database import get_db_connection
from app.services.content_destination_service import ContentDestinationService
from app.services.generation_library_service import GenerationLibraryService
from app.services.staged_asset_registration_service import StagedAssetRegistrationService


@dataclass(frozen=True)
class EngagementTeaserIntakeResult:
    asset_id: int
    generation_id: str
    already_registered: bool
    analysis_status: str


class EngagementTeaserIntakeService:
    PURPOSE = "ENGAGEMENT_TEASER"

    def __init__(self, *, generation_library=None, registration=None, destinations=None):
        self.generation_library = generation_library or GenerationLibraryService()
        self.registration = registration or StagedAssetRegistrationService(
            generation_library_service=self.generation_library,
        )
        self.destinations = destinations or ContentDestinationService()

    def add(self, generation_id: str, *, creator_profile_id: int) -> EngagementTeaserIntakeResult:
        record = self.generation_library.get(str(generation_id))
        if int(record.creator_profile_id) != int(creator_profile_id):
            raise KeyError("Generated image not found.")
        self._assert_not_owned(record.image_id)
        if record.status == "business_asset_registered":
            staged, already_moved = record, True
        else:
            staged, already_moved = self.generation_library.move_to_asset_library(record.image_id)
        result = self.registration.register(
            staged,
            creator_profile_id=int(creator_profile_id),
            registration_purpose=self.PURPOSE,
            finalize_generation=False,
        )
        if not result.success or result.asset_id is None:
            raise ValueError(result.message or "Teaser Asset registration failed.")
        self.destinations.designate_engagement_teaser(
            result.asset_id, creator_profile_id=int(creator_profile_id),
        )
        self.generation_library.mark_business_registered(staged.image_id, result.asset_id)
        return EngagementTeaserIntakeResult(
            asset_id=result.asset_id,
            generation_id=staged.image_id,
            already_registered=bool(already_moved or result.already_registered),
            analysis_status=result.analysis_status,
        )

    @staticmethod
    def _assert_not_owned(image_id: str) -> None:
        with get_db_connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT owner FROM public.generation_image_dispositions WHERE image_id=%s",
                (str(image_id),),
            )
            row = cursor.fetchone()
        if row is not None:
            raise ValueError(
                f"Generated image is already owned by {str(row['owner']).replace('_', ' ').title()}."
            )
