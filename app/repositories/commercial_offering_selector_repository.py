"""Read-only persistence boundary for deterministic offering selection."""
from app.repositories.commercial_fulfillment_repository import (
    CommercialFulfillmentRepository,
)
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.commerce_learning_repository import CommerceLearningRepository


class CommercialOfferingSelectorRepository:
    def __init__(
        self, *, fulfillment_repository=None, intent_repository=None,
        learning_repository=None,
    ) -> None:
        self.fulfillments = (
            fulfillment_repository or CommercialFulfillmentRepository()
        )
        self.intents = intent_repository or PurchaseIntentRepository()
        self.learning = learning_repository or CommerceLearningRepository()

    def list_candidates(
        self, *, creator_profile_id: int, primary_sales_channel: str,
    ):
        return self.fulfillments.list_candidates(
            creator_profile_id=creator_profile_id,
            primary_sales_channel=primary_sales_channel,
        )

    def get_candidate(self, offering_id, *, creator_profile_id: int):
        return self.fulfillments.get(
            offering_id, creator_profile_id=creator_profile_id
        )

    def list_purchased_offering_ids(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid, telegram_user_id: int | None,
    ):
        return self.intents.list_attributed_purchased_offering_ids(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=external_fanvue_user_uuid,
            telegram_user_id=telegram_user_id,
        )

    def list_recommendation_history(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid, telegram_user_id: int | None,
    ):
        return self.intents.list_recommendation_history(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=external_fanvue_user_uuid,
            telegram_user_id=telegram_user_id,
            limit=10,
        )

    def get_commerce_learning_profile(
        self, *, creator_profile_id, fanvue_account_id,
        external_fanvue_user_uuid,
    ):
        if external_fanvue_user_uuid is None:
            return None
        return self.learning.get_profile(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=external_fanvue_user_uuid,
        )
