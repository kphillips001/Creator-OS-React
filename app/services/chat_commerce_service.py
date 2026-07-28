"""Narrow adapter from existing conversation decisions to CommerceSalesService."""
from __future__ import annotations

import logging
import re

from app.models.chat_commerce import (
    ChatCommerceDecision,
    CommerceConversationContext,
)
from app.services.commerce_sales_service import (
    CommerceSalesDecisionError,
    CommerceSalesService,
)
from app.models.customer_sales_decision import (
    CustomerSalesDecision,
    CustomerSalesDecisionType,
)

logger = logging.getLogger(__name__)


class ChatCommerceService:
    AUTHORITATIVE_MODE = "AUTHORITATIVE"
    COMPATIBILITY_MODE = "COMPATIBILITY"
    MEDIA_PATTERNS = (
        ("STORY", re.compile(r"\b(?:story|stories)\b", re.IGNORECASE)),
        ("VIDEO", re.compile(r"\b(?:video|clip)\b", re.IGNORECASE)),
        (
            "PHOTOSET",
            re.compile(
                r"\b(?:photo\s*set|photoset|set|collection|photoshoot|more\s+photos)\b",
                re.IGNORECASE,
            ),
        ),
        (
            "SINGLE_IMAGE",
            re.compile(r"\b(?:a|one|single)\s+(?:photo|picture|image)\b", re.IGNORECASE),
        ),
    )

    def __init__(
        self, sales_service=None, *,
        commerce_mode: str,
    ) -> None:
        self.sales = sales_service or CommerceSalesService()
        normalized_mode = str(commerce_mode or "").strip().upper()
        if normalized_mode not in {
            self.AUTHORITATIVE_MODE,
            self.COMPATIBILITY_MODE,
        }:
            raise ValueError(
                "commerce_mode must be AUTHORITATIVE or COMPATIBILITY"
            )
        self.commerce_mode = normalized_mode

    def build_context(
        self, *, creator_profile_id: int, purchase_intent: bool,
        message_text: str, diagnostics, customer_identifier: str,
        conversation_identifier: str, relationship_level: str,
        recommendation_reason: str,
    ) -> CommerceConversationContext:
        requested_media_type = self.requested_media_type(message_text)
        intent = diagnostics.get("intent") or {}
        themes = intent.get("themes") if isinstance(intent, dict) else ()
        safe_themes = tuple(
            str(value).strip() for value in (themes or ())
            if isinstance(value, str) and value.strip()
        )
        return CommerceConversationContext(
            creator_profile_id=int(creator_profile_id),
            purchase_intent=bool(purchase_intent),
            requested_media_type=requested_media_type,
            requested_themes=safe_themes,
            relationship_level=relationship_level,
            customer_identifier=customer_identifier,
            conversation_identifier=conversation_identifier,
            recommendation_reason=recommendation_reason,
        )

    def recommend(
        self, context: CommerceConversationContext, *,
        customer_sales_decision: CustomerSalesDecision | None = None,
    ) -> ChatCommerceDecision:
        if customer_sales_decision is not None:
            return self._consume_customer_sales_decision(
                context, customer_sales_decision
            )
        if self.commerce_mode == self.AUTHORITATIVE_MODE:
            logger.warning(
                "event=compatibility_fallback_blocked "
                "reason=authoritative_commerce_context_required"
            )
            return ChatCommerceDecision(
                False, context.requested_media_type, context.requested_themes,
                None, None, "AUTHORITATIVE_COMMERCE_CONTEXT_REQUIRED",
                "NONE", False,
            )
        if not context.purchase_intent:
            return ChatCommerceDecision(
                False, context.requested_media_type, context.requested_themes,
                None, None, "SALE_NOT_AUTHORIZED_BY_DECISION_ENGINE",
            )
        if context.requested_media_type == "STORY":
            logger.info(
                "commerce_lookup_attempted=false requested_type=STORY "
                "no_offering_reason=UNSUPPORTED_OFFERING_TYPE"
            )
            return ChatCommerceDecision(
                False, "STORY", context.requested_themes, None, None,
                "UNSUPPORTED_OFFERING_TYPE",
            )
        try:
            logger.warning(
                "event=compatibility_mode_entered "
                "recommendation_source=recommend_best"
            )
            offering = self.sales.recommend_best(
                creator_profile_id=context.creator_profile_id,
                primary_sales_channel="AI_CHAT",
                conversation_context={
                    "relationship_level": context.relationship_level,
                    "reason": context.recommendation_reason,
                },
                requested_media_type=context.requested_media_type,
                requested_themes=context.requested_themes,
                customer_history=None,
            )
        except CommerceSalesDecisionError as error:
            logger.info(
                "commerce_lookup_attempted=true requested_type=%s "
                "no_offering_reason=%s",
                context.requested_media_type, error.code,
            )
            return ChatCommerceDecision(
                True, context.requested_media_type, context.requested_themes,
                None, None, error.code,
            )
        if offering is None:
            logger.info(
                "commerce_lookup_attempted=true requested_type=%s "
                "eligible_results=0 no_offering_reason=NO_ELIGIBLE_OFFERING",
                context.requested_media_type,
            )
            return ChatCommerceDecision(
                True, context.requested_media_type, context.requested_themes,
                None, None, "NO_ELIGIBLE_OFFERING",
            )
        logger.info(
            "commerce_lookup_attempted=true requested_type=%s eligible_results=1 "
            "selected_offering_id=%s",
            context.requested_media_type, offering.offering_id,
        )
        reason = (
            "EXACT_MEDIA_TYPE_MATCH"
            if context.requested_media_type == offering.offering_type
            else "DETERMINISTIC_FALLBACK"
        )
        return ChatCommerceDecision(
            True, context.requested_media_type, context.requested_themes,
            offering, reason, None, "COMPATIBILITY_RECOMMEND_BEST", True,
        )

    def _consume_customer_sales_decision(
        self, context: CommerceConversationContext,
        decision: CustomerSalesDecision,
    ) -> ChatCommerceDecision:
        if (
            not context.purchase_intent
            or
            decision.decision is not CustomerSalesDecisionType.PRESENT_OFFER
            or not decision.sell_allowed
            or decision.recommended_offering_id is None
        ):
            if (
                decision.decision is CustomerSalesDecisionType.PRESENT_OFFER
                and decision.recommended_offering_id is None
            ):
                logger.warning(
                    "event=missing_authoritative_selection decision=%s",
                    decision.decision.value,
                )
            return ChatCommerceDecision(
                False, context.requested_media_type, context.requested_themes,
                None, None, decision.reason_code.value,
                (
                    "COMMERCIAL_OFFERING_SELECTOR"
                    if decision.recommended_offering_id is not None
                    else "NONE"
                ),
                False,
            )
        try:
            offering = self.sales.resolve_recommended_offering(
                offering_id=decision.recommended_offering_id,
                creator_profile_id=context.creator_profile_id,
            )
        except CommerceSalesDecisionError as error:
            return ChatCommerceDecision(
                True, context.requested_media_type, context.requested_themes,
                None, None, error.code,
            )
        if offering is None:
            return ChatCommerceDecision(
                True, context.requested_media_type, context.requested_themes,
                None, None, "OFFERING_UNAVAILABLE",
            )
        logger.info(
            "event=customer_sales_decision_consumed decision=%s "
            "selected_offering_id=%s",
            decision.decision.value, offering.offering_id,
        )
        return ChatCommerceDecision(
            True, context.requested_media_type, context.requested_themes,
            offering, decision.reason_code.value, None,
            "COMMERCIAL_OFFERING_SELECTOR", False,
        )

    @classmethod
    def requested_media_type(cls, message_text: str) -> str | None:
        for offering_type, pattern in cls.MEDIA_PATTERNS:
            if pattern.search(message_text or ""):
                return offering_type
        return None

    @staticmethod
    def compose_reply(existing_reply: str, decision: ChatCommerceDecision) -> str:
        offering = decision.offering
        if offering is None:
            return existing_reply
        price = f"{offering.currency} {offering.price_minor / 100:.2f}"
        description = f" — {offering.description.strip()}" if offering.description else ""
        return (
            f"{existing_reply.rstrip()}\n\n"
            f"{offering.title}{description} is available for {price}: "
            f"{offering.delivery_url}"
        )
