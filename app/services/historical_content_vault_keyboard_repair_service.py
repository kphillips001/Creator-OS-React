"""Restore Content Vault keyboards lost during historical media normalization."""
from datetime import datetime, timezone
from uuid import UUID

from app.database import get_db_connection
from app.providers.social.telegram_provider import TelegramPublishingProvider
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.services.commerce_telegram_vault_service import CommerceTelegramVaultService


class HistoricalContentVaultKeyboardRepairService:
    def __init__(self, *, connection_factory=get_db_connection, publications=None, telegram=None):
        self.connection_factory=connection_factory
        self.publications=publications or CommercialPublicationRepository(connection_factory)
        self.telegram=telegram or TelegramPublishingProvider()

    def repair_missing(self, *, creator_profile_id:int, confirmed:bool=False):
        if not confirmed: raise ValueError("Explicit keyboard restoration confirmation is required.")
        results=[]
        for row in self._candidates(creator_profile_id):
            repair=dict(row["repair"] or {})
            if repair.get("keyboard_result")=="SUCCEEDED":
                if repair.get("lifecycle_result") != "SUCCEEDED":
                    repair.update({"media_result": repair.get("result"), "lifecycle_result":"SUCCEEDED"})
                    metadata=dict(row["publication_metadata"] or {}); metadata["content_vault_historical_normalization"]=repair
                    self.publications.update_metadata(UUID(str(row["publication_id"])),creator_profile_id=creator_profile_id,metadata=metadata)
                results.append({"message_id":repair["telegram_message_id"],"status":"SKIPPED"}); continue
            label=CommerceTelegramVaultService.unlock_cta_label(row["price_minor"],row["currency"])
            keyboard=TelegramPublishingProvider.build_inline_keyboard(cta_enabled=True,cta_label=label,cta_url=row["url"])
            response=self.telegram.edit_message_reply_markup(chat_id=repair["telegram_chat_id"],message_id=repair["telegram_message_id"],reply_markup=keyboard)
            expected_chat=str(repair["telegram_chat_id"]); expected_message=str(repair["telegram_message_id"])
            actual_keyboard=response.get("reply_markup")
            ok=(response.get("ok") and str(response.get("chat_id"))==expected_chat
                and str(response.get("message_id"))==expected_message and actual_keyboard==keyboard)
            repair.update({"keyboard_result":"SUCCEEDED" if ok else "FAILED",
                           "media_result":repair.get("result"),
                           "lifecycle_result":"SUCCEEDED" if ok else "FAILED",
                           "keyboard_restored_at":datetime.now(timezone.utc).isoformat() if ok else None,
                           "keyboard_error":None if ok else str(response.get("error") or "Telegram keyboard/identity verification failed.")})
            metadata=dict(row["publication_metadata"] or {}); metadata["content_vault_historical_normalization"]=repair
            self.publications.update_metadata(UUID(str(row["publication_id"])),creator_profile_id=creator_profile_id,metadata=metadata)
            results.append({"message_id":expected_message,"status":repair["keyboard_result"],"label":label,"url":row["url"],"error":repair["keyboard_error"]})
        return results

    def _candidates(self, creator_profile_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT publication.publication_id,publication.publication_metadata,
                publication.publication_metadata->'content_vault_historical_normalization' repair,
                offering.price_minor,offering.currency,
                publication.publication_metadata#>>'{media_link,url}' url
              FROM public.commercial_publications publication
              JOIN public.commercial_offerings offering ON offering.offering_id=publication.commercial_offering_id
              WHERE offering.creator_profile_id=%s
                AND publication.publication_metadata->'content_vault_historical_normalization'->>'result'='SUCCEEDED'
                AND COALESCE(publication.publication_metadata#>>'{media_link,url}','')<>''
              ORDER BY (publication.publication_metadata->'content_vault_historical_normalization'->>'telegram_message_id')::int""",(creator_profile_id,))
            return tuple(dict(row) for row in cursor.fetchall())
