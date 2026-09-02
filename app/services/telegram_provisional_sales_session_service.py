"""Application boundary for Telegram-owned provisional Sessions."""
from app.repositories.telegram_provisional_sales_session_repository import TelegramProvisionalSalesSessionRepository


class TelegramProvisionalSalesSessionService:
    def __init__(self, repository=None, prospect_service=None):
        self.repository = repository or TelegramProvisionalSalesSessionRepository()
        if prospect_service is None:
            from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService
            prospect_service = UnmappedTelegramProspectService()
        self.prospects = prospect_service

    def create_or_get(self, *, creator_profile_id, fanvue_account_id,
                      telegram_user_id, telegram_chat_id, photoshoot_reference,
                      session_strategy, configured_base_price_minor,
                      commercial_context=None):
        prospect = self.prospects.context(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id, telegram_chat_id=telegram_chat_id).prospect
        return self.repository.create_or_get(
            prospect=prospect, photoshoot_reference=photoshoot_reference,
            session_strategy=session_strategy,
            configured_base_price_minor=configured_base_price_minor,
            commercial_context=commercial_context or {})

    def associate_intent(self, provisional_session_id, purchase_intent_id):
        return self.repository.associate_intent(provisional_session_id, purchase_intent_id)

    def graduate(self, **values):
        return self.repository.graduate(**values)
