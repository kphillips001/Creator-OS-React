"""Canonical customer automation permissions beneath Session 1 global ceilings."""

from __future__ import annotations

import logging
from typing import Any

from app.models.telegram_relationship_control import TelegramRelationshipMode
from app.services.ava_bot_control_service import AvaBotControlService
from app.services.global_selling_permissions_service import GlobalSellingPermissionsService
from app.services.telegram_relationship_control_service import TelegramRelationshipControlService


logger = logging.getLogger("customer-effective-permissions")


class CustomerEffectivePermissionsService:
    def __init__(self, *, relationship_controls: Any | None = None,
                 ava_bot_controls: Any | None = None,
                 global_selling_permissions: Any | None = None) -> None:
        self.relationships = relationship_controls or TelegramRelationshipControlService()
        self.ava = ava_bot_controls or AvaBotControlService()
        self.global_selling = (
            global_selling_permissions or GlobalSellingPermissionsService())

    def read(self, *, creator_profile_id: int, fanvue_account_id: int,
             telegram_user_id: int, telegram_chat_id: int | None = None) -> dict[str, Any]:
        scope = dict(creator_profile_id=creator_profile_id,
                     fanvue_account_id=fanvue_account_id,
                     telegram_user_id=telegram_user_id,
                     telegram_chat_id=telegram_chat_id)
        control = self.relationships.get(**scope)
        ava = self.ava.read(creator_profile_id=creator_profile_id)["avaBot"]
        global_permissions = self.global_selling.read()
        configured_chat = control.mode is TelegramRelationshipMode.AVA_AUTO
        chat_allowed = ava["effective"] == "ON" and configured_chat
        chat_reason = (
            None if chat_allowed else
            "CUSTOMER_AVA_CHAT_DISABLED" if not configured_chat else
            "GLOBAL_AVA_BOT_DISABLED" if ava["desired"] == "OFF" else
            "GLOBAL_AVA_BOT_ATTENTION"
        )
        content_allowed = bool(chat_allowed
                               and global_permissions["contentSellingEnabled"]
                               and control.content_selling_enabled)
        session_allowed = bool(chat_allowed
                               and global_permissions["sessionSellingEnabled"]
                               and control.session_selling_enabled)
        content_reason = (
            None if content_allowed else
            "GLOBAL_CONTENT_SELLING_DISABLED"
            if not global_permissions["contentSellingEnabled"] else
            chat_reason if not chat_allowed else
            "CUSTOMER_CONTENT_SELLING_DISABLED"
        )
        session_reason = (
            None if session_allowed else
            "GLOBAL_SESSION_SELLING_DISABLED"
            if not global_permissions["sessionSellingEnabled"] else
            chat_reason if not chat_allowed else
            "CUSTOMER_SESSION_SELLING_DISABLED"
        )
        return {
            "identity": {
                "creatorProfileId": creator_profile_id,
                "fanvueAccountId": fanvue_account_id,
                "telegramUserId": telegram_user_id,
                "telegramChatId": control.telegram_chat_id,
                "telegramIdentityMappingId": control.telegram_identity_mapping_id,
                "localFanvueUserId": control.local_fanvue_user_id,
            },
            "configured": {
                "avaChatEnabled": configured_chat,
                "contentSellingEnabled": control.content_selling_enabled,
                "sessionSellingEnabled": control.session_selling_enabled,
                "relationshipMode": control.mode.value,
                "controlVersion": control.control_version,
            },
            "effective": {
                "chatAllowed": chat_allowed,
                "chatReason": chat_reason,
                "contentSellingAllowed": content_allowed,
                "contentSellingReason": content_reason,
                "sessionSellingAllowed": session_allowed,
                "sessionSellingReason": session_reason,
            },
            "global": {
                "avaBotDesired": ava["desired"],
                "avaBotEffective": ava["effective"],
                **global_permissions,
            },
        }

    def set_chat(self, value: bool, *, changed_by: str, reason: str | None = None,
                 **scope) -> dict[str, Any]:
        if not isinstance(value, bool): raise ValueError("Ava Chat must be boolean.")
        before = self.read(**self._read_scope(scope))
        action = self.relationships.return_to_ava if value else self.relationships.takeover
        action(changed_by=changed_by, reason=reason, **scope)
        return self._logged("ava_chat", before, self.read(**self._read_scope(scope)))

    def set_content(self, value: bool, *, changed_by: str,
                    reason: str | None = None, **scope) -> dict[str, Any]:
        before = self.read(**self._read_scope(scope))
        self.relationships.set_content_selling(
            value, changed_by=changed_by, reason=reason, **scope)
        return self._logged("content_selling", before,
                            self.read(**self._read_scope(scope)))

    def set_session(self, value: bool, *, changed_by: str,
                    reason: str | None = None, **scope) -> dict[str, Any]:
        before = self.read(**self._read_scope(scope))
        self.relationships.set_session_selling(
            value, changed_by=changed_by, reason=reason, **scope)
        return self._logged("session_selling", before,
                            self.read(**self._read_scope(scope)))

    @staticmethod
    def _read_scope(scope):
        return {key: scope.get(key) for key in (
            "creator_profile_id", "fanvue_account_id", "telegram_user_id",
            "telegram_chat_id")}

    @staticmethod
    def _logged(control, before, after):
        result = {"changed": before["configured"] != after["configured"],
                  "control": control, "state": after}
        logger.info(
            "event=customer_control_changed identity=%s control=%s previous=%s new=%s effective=%s",
            after["identity"], control, before["configured"],
            after["configured"], after["effective"],
        )
        return result
