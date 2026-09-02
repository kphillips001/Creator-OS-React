"""Controlled delivery foundation for standalone Free Engagement Teasers.

This service exposes capability only. It contains no autonomous timing policy.
"""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.models.free_engagement_teaser import (
    FreeEngagementTeaserDeliveryState,
    FreeEngagementTeaserExecution,
    FreeEngagementTeaserPreparation,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.chat_message_repository import save_chat_message
from app.repositories.free_engagement_teaser_repository import FreeEngagementTeaserRepository
from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.runtime_media_resolver import RuntimeMediaResolver
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor


class FreeEngagementTeaserService:
    def __init__(self, *, repository=None, asset_repository=None,
                 media_resolver=None, customer_safety_service=None,
                 global_safety_service=None, delivery_executor=None,
                 conversation_message_saver=save_chat_message):
        self.repository = repository or FreeEngagementTeaserRepository()
        self.assets = asset_repository or AssetRepository()
        self.media = media_resolver or RuntimeMediaResolver()
        self.customer_safety = customer_safety_service or CustomerInteractionSafetyService()
        self.global_safety = global_safety_service or GlobalAutomationSafetyService()
        self.delivery = delivery_executor or TelegramDeliveryExecutor(
            global_safety_service=self.global_safety,
            customer_safety_service=self.customer_safety,
        )
        self.save_message = conversation_message_saver

    def prepare(self, *, creator_profile_id: int, fanvue_account_id: int,
                fanvue_user_id: int, telegram_user_id: int,
                telegram_chat_id: int, conversation_thread_id: int,
                correlation_id: str, inbound_telegram_message_id: int | None = None,
                caption: str = "", engagement_strategy: str | None = None,
                decision_reason_code: str | None = None,
                decision_evidence: dict | None = None,
                policy_version: str | None = None) -> FreeEngagementTeaserPreparation:
        context_error = self.repository.validate_context(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            telegram_user_id=telegram_user_id,
            conversation_thread_id=conversation_thread_id,
        )
        if context_error:
            return FreeEngagementTeaserPreparation(status="SUPPRESSED", reason=context_error)
        safety = self.customer_safety.decide(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )
        if not safety.allowed:
            return FreeEngagementTeaserPreparation(status="SUPPRESSED", reason=safety.code)
        global_safety = self.global_safety.check_global_safety()
        if not global_safety.get("allowed", False):
            return FreeEngagementTeaserPreparation(
                status="SUPPRESSED",
                reason=str(global_safety.get("reason") or "GLOBAL_AUTOMATION_BLOCKED"),
            )
        conflict = self.repository.funnel_conflict(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            telegram_chat_id=telegram_chat_id,
        )
        if conflict:
            return FreeEngagementTeaserPreparation(status="SUPPRESSED", reason=conflict)
        operation = self.repository.reserve_next(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            conversation_thread_id=conversation_thread_id,
            telegram_chat_id=telegram_chat_id,
            correlation_id=correlation_id,
            inbound_telegram_message_id=inbound_telegram_message_id,
            caption=caption,
            media_resolver=self._resolve_media,
            engagement_strategy=engagement_strategy,
            decision_reason_code=decision_reason_code,
            decision_evidence=decision_evidence,
            policy_version=policy_version,
        )
        if operation is None:
            return FreeEngagementTeaserPreparation(
                status="NO_ELIGIBLE_TEASER", reason="NO_ELIGIBLE_TEASER",
            )
        return FreeEngagementTeaserPreparation(status="CREATED", operation=operation)

    async def execute_async(self, operation_id, *, transport) -> FreeEngagementTeaserExecution:
        operation = self.repository.get(operation_id)
        if operation is None:
            return FreeEngagementTeaserExecution(status="NOT_FOUND", executed=False, reason="OPERATION_NOT_FOUND")
        if operation.state in {
            FreeEngagementTeaserDeliveryState.SENDING,
            FreeEngagementTeaserDeliveryState.AMBIGUOUS,
            FreeEngagementTeaserDeliveryState.FAILED,
            FreeEngagementTeaserDeliveryState.CONFIRMED,
        }:
            return FreeEngagementTeaserExecution(
                status=operation.state.value, executed=False, operation=operation,
                reason="NO_RESEND_TERMINAL_OR_UNCERTAIN_STATE",
            )
        if operation.state is FreeEngagementTeaserDeliveryState.TELEGRAM_ACCEPTED:
            confirmed = self._confirm(operation)
            return FreeEngagementTeaserExecution(status="CONFIRMED", executed=False, operation=confirmed)

        safety = self.customer_safety.decide(
            creator_profile_id=operation.creator_profile_id,
            fanvue_account_id=operation.fanvue_account_id,
            fanvue_user_id=operation.fanvue_user_id,
        )
        if not safety.allowed:
            failed = self.repository.failed(operation.operation_id, safety.code)
            return FreeEngagementTeaserExecution(status="SUPPRESSED", executed=False, operation=failed, reason=safety.code)
        global_safety = self.global_safety.check_global_safety()
        if not global_safety.get("allowed", False):
            reason = str(global_safety.get("reason") or "GLOBAL_AUTOMATION_BLOCKED")
            failed = self.repository.failed(operation.operation_id, reason)
            return FreeEngagementTeaserExecution(status="SUPPRESSED", executed=False, operation=failed, reason=reason)
        conflict = self.repository.funnel_conflict(
            creator_profile_id=operation.creator_profile_id,
            fanvue_account_id=operation.fanvue_account_id,
            fanvue_user_id=operation.fanvue_user_id,
            telegram_chat_id=operation.telegram_chat_id,
        )
        if conflict:
            failed = self.repository.failed(operation.operation_id, conflict)
            return FreeEngagementTeaserExecution(status="SUPPRESSED", executed=False, operation=failed, reason=conflict)
        claimed = self.repository.claim(operation.operation_id)
        if claimed is None:
            current = self.repository.get(operation.operation_id)
            return FreeEngagementTeaserExecution(status=current.state.value, executed=False, operation=current)
        try:
            result = await self.delivery.execute_async({
                "delivery_type": "FREE_ENGAGEMENT_TEASER",
                "message_text": claimed.caption,
                "asset_path": claimed.media_reference,
                "delivery_method": "free_engagement_asset",
                "delivery_reason": "controlled_free_engagement_teaser",
                "metadata": {
                    "action": "SEND_FREE_ENGAGEMENT_TEASER",
                    "asset_id": claimed.teaser_asset_id,
                    "operation_id": str(claimed.operation_id),
                    "free": True,
                },
            }, context={
                "transport": transport,
                "telegram_chat_id": claimed.telegram_chat_id,
                "creator_profile_id": claimed.creator_profile_id,
                "fanvue_account_id": claimed.fanvue_account_id,
                "fanvue_user_id": claimed.fanvue_user_id,
                "raise_on_failure": True,
            })
            message_id = result.metadata.get("telegram_message_id")
            if not result.executed or message_id is None:
                reason = result.blocking_reason or result.status or "TELEGRAM_SEND_NOT_ACCEPTED"
                failed = self.repository.failed(claimed.operation_id, reason)
                return FreeEngagementTeaserExecution(status="FAILED", executed=False, operation=failed, reason=reason)
            accepted = self.repository.accepted(claimed.operation_id, message_id)
            try:
                confirmed = self._confirm(accepted)
            except Exception as error:
                return FreeEngagementTeaserExecution(
                    status="TELEGRAM_ACCEPTED", executed=True, operation=accepted,
                    reason=f"TRANSCRIPT_CONFIRMATION_PENDING: {type(error).__name__}",
                )
            return FreeEngagementTeaserExecution(status="CONFIRMED", executed=True, operation=confirmed)
        except (TimeoutError, ConnectionError, OSError) as error:
            ambiguous = self.repository.ambiguous(claimed.operation_id, f"{type(error).__name__}: provider outcome unknown")
            return FreeEngagementTeaserExecution(status="AMBIGUOUS", executed=False, operation=ambiguous, reason="PROVIDER_OUTCOME_UNKNOWN")
        except Exception as error:
            failed = self.repository.failed(claimed.operation_id, f"{type(error).__name__}: {str(error)[:500]}")
            return FreeEngagementTeaserExecution(status="FAILED", executed=False, operation=failed, reason="DEFINITE_PROVIDER_FAILURE")

    def recover_startup(self):
        ambiguous = self.repository.mark_sending_ambiguous()
        confirmed = tuple(self._confirm(item) for item in self.repository.list_accepted())
        return {"ambiguous": ambiguous, "confirmed": confirmed}

    def _resolve_media(self, asset_id: int) -> str:
        asset = self.assets.get_by_id(int(asset_id))
        if asset is None:
            return ""
        resolved = self.media.resolve_original(asset, require_exists=True)
        return str(resolved.path) if resolved.path else ""

    def _confirm(self, operation):
        if operation is None or operation.outbound_telegram_message_id is None:
            raise ValueError("Accepted engagement Teaser delivery lacks Telegram message ID.")
        message_uuid = uuid5(
            NAMESPACE_URL,
            f"telegram:{operation.telegram_chat_id}:outbound:{operation.outbound_telegram_message_id}",
        )
        self.save_message(
            fanvue_account_id=operation.fanvue_account_id,
            thread_id=operation.conversation_thread_id,
            fanvue_user_id=operation.fanvue_user_id,
            direction="outbound", sender_type="bot", text=operation.caption,
            fanvue_message_uuid=message_uuid, has_media=True,
            media_uuids=[f"asset:{operation.teaser_asset_id}"],
            is_paid_message=False,
            raw_payload={
                "provider": "TELEGRAM", "channel": "PRIVATE_CHAT",
                "telegram_chat_id": operation.telegram_chat_id,
                "telegram_message_id": operation.outbound_telegram_message_id,
                "delivery_kind": "FREE_ENGAGEMENT_TEASER",
                "action": "SEND_FREE_ENGAGEMENT_TEASER",
                "asset_id": operation.teaser_asset_id,
                "engagement_strategy": operation.engagement_strategy,
                "free": True, "operation_id": str(operation.operation_id),
            },
        )
        return self.repository.confirmed(operation.operation_id)
