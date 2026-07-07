"""Provider-neutral Customer read-model repository.

C.3.3 introduces a unified retrieval boundary without moving persistence or
changing runtime workflows. Existing repositories continue to own their tables;
this repository only assembles Customer domain read models.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.models.customer import (
    Customer,
    CustomerConversationSummary,
    CustomerOwnershipSummary,
    CustomerProgressionSummary,
    CustomerProviderIdentity,
    CustomerRecommendationSummary,
    CustomerRelationshipStatus,
    CustomerRelationshipSummary,
)
from app.repositories.chat_message_repository import get_thread_messages_for_user
from app.repositories.content_ownership_repository import get_owned_content_tags
from app.repositories.memory_repository import get_user_memory_row
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.repositories.user_repository import (
    get_user_by_account_and_fanvue_uuid,
    get_user_by_account_and_id,
)


def _get(row: Mapping[str, Any] | None, key: str, default: Any = None) -> Any:
    if not row:
        return default
    return row.get(key, default)


class CustomerRepository:
    """Aggregate existing customer persistence into Customer read models."""

    def __init__(
        self,
        *,
        fanvue_user_by_id_fetcher: Callable[[int, int], Mapping[str, Any] | None]
        = get_user_by_account_and_id,
        fanvue_user_by_uuid_fetcher: Callable[[int, str], Mapping[str, Any] | None]
        = get_user_by_account_and_fanvue_uuid,
        memory_fetcher: Callable[[int, int], Mapping[str, Any] | None]
        = get_user_memory_row,
        chat_messages_fetcher: Callable[[int, int], Sequence[Mapping[str, Any]]]
        = get_thread_messages_for_user,
        owned_content_tags_fetcher: Callable[[int, int], Sequence[str]]
        = get_owned_content_tags,
        telegram_identity_repository: Any | None = None,
    ):
        self._fanvue_user_by_id_fetcher = fanvue_user_by_id_fetcher
        self._fanvue_user_by_uuid_fetcher = fanvue_user_by_uuid_fetcher
        self._memory_fetcher = memory_fetcher
        self._chat_messages_fetcher = chat_messages_fetcher
        self._owned_content_tags_fetcher = owned_content_tags_fetcher
        self._telegram_identity_repository = (
            telegram_identity_repository or TelegramIdentityRepository()
        )

    def get_by_legacy_fanvue_user(
        self,
        *,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> Customer | None:
        """Build a Customer from the existing local Fanvue user identity."""

        fanvue_user = self._fanvue_user_by_id_fetcher(
            fanvue_account_id,
            fanvue_user_id,
        )
        if not fanvue_user:
            return None

        memory = self._memory_fetcher(fanvue_account_id, fanvue_user_id) or {}
        chat_messages = self._chat_messages_fetcher(
            fanvue_account_id,
            fanvue_user_id,
        ) or ()
        owned_content_tags = self._owned_content_tags_fetcher(
            fanvue_account_id,
            fanvue_user_id,
        ) or ()
        telegram_identity = self._get_telegram_identity(
            fanvue_account_id,
            fanvue_user_id,
        )

        return self.build_customer(
            fanvue_user=fanvue_user,
            memory=memory,
            chat_messages=chat_messages,
            owned_content_tags=owned_content_tags,
            telegram_identity=telegram_identity,
        )

    def get_by_provider_identity(
        self,
        *,
        provider: str,
        provider_customer_id: str | int,
        provider_account_id: str | int | None = None,
    ) -> Customer | None:
        """Resolve a provider identity when current compatibility sources allow it."""

        normalized_provider = str(provider).strip().lower()
        if normalized_provider == "fanvue":
            if provider_account_id is None:
                return None
            fanvue_user = self._fanvue_user_by_uuid_fetcher(
                int(provider_account_id),
                str(provider_customer_id),
            )
            if not fanvue_user:
                return None
            return self.get_by_legacy_fanvue_user(
                fanvue_account_id=int(provider_account_id),
                fanvue_user_id=int(fanvue_user["id"]),
            )

        if normalized_provider == "telegram":
            getter = getattr(
                self._telegram_identity_repository,
                "get_by_telegram_user_id",
                None,
            )
            if getter is None:
                return None
            mapping = getter(int(provider_customer_id))
            if not mapping:
                return None
            return self.get_by_legacy_fanvue_user(
                fanvue_account_id=mapping.fanvue_account_id,
                fanvue_user_id=mapping.local_fanvue_user_id,
            )

        return None

    def build_customer(
        self,
        *,
        fanvue_user: Mapping[str, Any],
        memory: Mapping[str, Any] | None = None,
        chat_messages: Sequence[Mapping[str, Any]] = (),
        owned_content_tags: Sequence[str] = (),
        telegram_identity: Any | None = None,
    ) -> Customer:
        """Assemble a Customer read model from existing repository rows."""

        fanvue_account_id = int(_get(fanvue_user, "fanvue_account_id"))
        fanvue_user_id = int(_get(fanvue_user, "id"))
        memory = memory or {}

        return Customer(
            customer_id=f"{fanvue_account_id}:{fanvue_user_id}",
            display_name=(
                _get(fanvue_user, "display_name")
                or _get(fanvue_user, "username")
                or str(fanvue_user_id)
            ),
            provider_identities=self._provider_identities(
                fanvue_user,
                telegram_identity,
            ),
            relationship=self._relationship_summary(fanvue_user, memory),
            conversation=self._conversation_summary(chat_messages, memory),
            progression=self._progression_summary(memory),
            ownership=self._ownership_summary(memory, owned_content_tags),
            recommendation=self._recommendation_summary(memory),
            metadata={
                "source": "CustomerRepository",
                "legacy_engine_user_id": f"{fanvue_account_id}:{fanvue_user_id}",
            },
            created_at=_get(fanvue_user, "created_at"),
            updated_at=(
                _get(memory, "updated_at")
                or _get(fanvue_user, "updated_at")
            ),
        )

    def _get_telegram_identity(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> Any | None:
        getter = getattr(
            self._telegram_identity_repository,
            "get_by_local_user_id",
            None,
        )
        if getter is None:
            return None
        return getter(fanvue_account_id, fanvue_user_id)

    def _provider_identities(
        self,
        fanvue_user: Mapping[str, Any],
        telegram_identity: Any | None,
    ) -> tuple[CustomerProviderIdentity, ...]:
        identities = [
            CustomerProviderIdentity(
                provider="fanvue",
                provider_customer_id=str(_get(fanvue_user, "fanvue_user_uuid")),
                provider_account_id=str(_get(fanvue_user, "fanvue_account_id")),
                channel="fanvue",
                username=_get(fanvue_user, "username"),
                display_name=_get(fanvue_user, "display_name"),
                is_active=_get(fanvue_user, "relationship_status") != "missing",
            )
        ]

        if telegram_identity is not None:
            identities.append(
                CustomerProviderIdentity(
                    provider="telegram",
                    provider_customer_id=str(telegram_identity.telegram_user_id),
                    provider_account_id=str(telegram_identity.telegram_chat_id),
                    channel="telegram",
                    is_active=bool(getattr(telegram_identity, "is_active", True)),
                    metadata={
                        "mapped_customer_id": str(
                            getattr(telegram_identity, "local_fanvue_user_id", "")
                        ),
                    },
                )
            )

        return tuple(identities)

    def _relationship_summary(
        self,
        fanvue_user: Mapping[str, Any],
        memory: Mapping[str, Any],
    ) -> CustomerRelationshipSummary:
        status = self._relationship_status(
            _get(fanvue_user, "relationship_status")
            or _get(memory, "relationship_status")
        )
        return CustomerRelationshipSummary(
            status=status,
            is_follower=bool(
                _get(fanvue_user, "is_follower")
                or _get(memory, "is_follower")
            ),
            is_subscriber=bool(
                _get(fanvue_user, "is_subscriber")
                or _get(memory, "is_subscriber")
            ),
            value_tier=_get(memory, "user_value_tier"),
            buyer_tier=_get(memory, "buyer_tier"),
            total_spend_cents=self._cents_value(
                _get(memory, "total_spend_cents")
                or _get(memory, "total_spend")
            ),
            purchase_count=self._int_value(_get(memory, "purchase_count")),
            last_active_at=_get(memory, "last_active_at"),
            metadata={
                "subscriber_profile": _get(memory, "subscriber_profile"),
                "relationship_status": _get(fanvue_user, "relationship_status"),
            },
        )

    def _conversation_summary(
        self,
        chat_messages: Sequence[Mapping[str, Any]],
        memory: Mapping[str, Any],
    ) -> CustomerConversationSummary:
        last_message = chat_messages[-1] if chat_messages else {}
        return CustomerConversationSummary(
            thread_count=1 if chat_messages else 0,
            message_count=(
                self._int_value(_get(memory, "message_count"))
                or len(chat_messages)
            ),
            inbound_message_count=self._int_value(
                _get(memory, "inbound_message_count")
            ),
            outbound_message_count=self._int_value(
                _get(memory, "outbound_message_count")
            ),
            last_message_at=(
                _get(last_message, "sent_at")
                or _get(memory, "last_active_at")
            ),
            last_inbound_at=_get(memory, "last_inbound_at"),
            last_outbound_at=_get(memory, "last_outbound_at"),
            current_mode=_get(memory, "conversation_mode"),
            metadata={
                "last_user_message": _get(memory, "last_user_message"),
                "last_bot_response": _get(memory, "last_bot_response"),
            },
        )

    def _progression_summary(
        self,
        memory: Mapping[str, Any],
    ) -> CustomerProgressionSummary:
        return CustomerProgressionSummary(
            current_experience_id=_get(memory, "current_experience_id"),
            current_position=(
                _get(memory, "current_position")
                or _get(memory, "buyer_session_last_action")
            ),
            seen_experience_ids=_get(memory, "seen_experience_ids") or (),
            seen_content_tags=_get(memory, "seen_content_tags") or (),
            active_session=bool(
                _get(memory, "active_buyer_session")
                or _get(memory, "buyer_session_active")
            ),
            session_step=self._int_value(_get(memory, "buyer_session_step")),
            metadata={
                "relationship_progression_mode": _get(
                    memory,
                    "relationship_progression_mode",
                ),
            },
        )

    def _ownership_summary(
        self,
        memory: Mapping[str, Any],
        owned_content_tags: Sequence[str],
    ) -> CustomerOwnershipSummary:
        return CustomerOwnershipSummary(
            owned_product_ids=_get(memory, "owned_product_ids") or (),
            owned_experience_ids=_get(memory, "owned_experience_ids") or (),
            entitlement_count=self._int_value(_get(memory, "entitlement_count")),
            purchase_count=self._int_value(_get(memory, "purchase_count")),
            last_purchase_at=(
                _get(memory, "last_purchase_at")
                or _get(memory, "last_ppv_purchase_at")
            ),
            metadata={
                "owned_content_tags": tuple(str(tag) for tag in owned_content_tags),
                "owned_content_count": self._int_value(
                    _get(memory, "owned_content_count")
                ),
            },
        )

    def _recommendation_summary(
        self,
        memory: Mapping[str, Any],
    ) -> CustomerRecommendationSummary:
        return CustomerRecommendationSummary(
            seen_offer_ids=_get(memory, "seen_offer_ids") or (),
            recent_product_ids=_get(memory, "recently_offered_product_ids") or (),
            last_offer_id=_get(memory, "last_offer_id"),
            last_offer_kind=(
                _get(memory, "last_offer_kind")
                or _get(memory, "last_offer_type")
            ),
            last_offer_at=_get(memory, "last_offer_timestamp"),
            offer_count=(
                self._int_value(_get(memory, "offer_count"))
                or self._int_value(_get(memory, "offers_shown_count"))
            ),
            accepted_offer_count=self._int_value(
                _get(memory, "accepted_offer_count")
            ),
            rejected_offer_count=self._int_value(
                _get(memory, "rejected_offer_count")
            ),
            preferred_tags=(
                _get(memory, "preferred_tags")
                or _get(memory, "favorite_content_tags")
                or _get(memory, "seen_content_tags")
                or ()
            ),
            preferred_themes=self._text_tuple(
                _get(memory, "preferred_themes")
                or _get(memory, "preferred_content_theme")
            ),
            metadata={
                "last_offer_content_tag": _get(memory, "last_offer_content_tag"),
                "last_selected_content_tag": _get(
                    memory,
                    "last_selected_content_tag",
                ),
            },
        )

    @staticmethod
    def _relationship_status(value: Any) -> CustomerRelationshipStatus:
        normalized = str(value or "").strip().lower()
        if normalized in {"subscriber", "subscribed"}:
            return CustomerRelationshipStatus.SUBSCRIBER
        if normalized == "follower":
            return CustomerRelationshipStatus.FOLLOWER
        if normalized in {"customer", "buyer"}:
            return CustomerRelationshipStatus.CUSTOMER
        if normalized in {"lapsed", "expired"}:
            return CustomerRelationshipStatus.LAPSED
        if normalized == "missing":
            return CustomerRelationshipStatus.MISSING
        if normalized in {"prospect", "lead"}:
            return CustomerRelationshipStatus.PROSPECT
        return CustomerRelationshipStatus.UNKNOWN

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _cents_value(cls, value: Any) -> int:
        numeric = cls._int_value(value)
        return numeric if numeric >= 1000 else numeric * 100

    @staticmethod
    def _text_tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            values = (value,)
        else:
            values = tuple(value)
        return tuple(str(item) for item in values if item is not None)
