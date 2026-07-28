"""Developer-only conversation harness for the real Sales Agent brain."""

from __future__ import annotations

from threading import RLock
import traceback
from typing import Any
from uuid import uuid4

from app.main import decision_engine, memory_service
from app.models.conversation_gateway import (
    ConversationBrainContext,
    ConversationGatewayInput,
)
from app.repositories.fanvue_account_repository import get_account_by_id
from app.repositories.user_repository import get_or_create_user_with_memory
from app.services.conversation_gateway import ConversationGateway
from app.services.chat_commerce_service import ChatCommerceService
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.commerce_learning_repository import CommerceLearningRepository


__test__ = False


class TestChatService:
    """Run persistent synthetic-user turns without any messaging transport."""

    TEST_USER_UUID = "11111111-1111-1111-1111-111111111111"
    _sessions: dict[str, list[dict[str, str]]] = {}
    _lock = RLock()

    def __init__(
        self, *, account_id: int, engine: Any = decision_engine,
        chat_commerce_service=None,
        customer_sales_brain_service=None,
        commerce_learning_repository=None,
    ) -> None:
        account = get_account_by_id(account_id)
        if not account:
            raise ValueError("Active account not found")
        self._account = dict(account)
        self._account_id = int(account_id)
        context = get_or_create_user_with_memory(
            fanvue_account_id=account_id,
            fanvue_user_uuid=self.TEST_USER_UUID,
            username="test_user",
            display_name="Test User",
            relationship_status="follower",
            is_subscriber=False,
            is_follower=True,
            source="react_test_chat",
        )
        self._user = dict(context["user"])
        self._engine_user_id = f"{account_id}:{self._user['id']}"
        profile = get_active_creator_profile(str(account_id)) or {}
        self._creator_profile_id = int(profile.get("id") or 0)
        self._chat_commerce = chat_commerce_service or ChatCommerceService(
            commerce_mode=ChatCommerceService.AUTHORITATIVE_MODE
        )
        self._customer_sales_brain = (
            customer_sales_brain_service or CustomerSalesBrainService()
        )
        self._commerce_learning = (
            commerce_learning_repository or CommerceLearningRepository()
        )
        # Deliberately omit TelegramCommerceService and RuntimeControlService.
        # The gateway can only execute the brain and cannot send or fulfill.
        self._gateway = ConversationGateway(
            engine,
            allowed_fanvue_hostnames=("fanvue.com", "www.fanvue.com"),
            chat_commerce_service=self._chat_commerce,
            customer_sales_brain_service=self._customer_sales_brain,
            creator_profile_id=self._creator_profile_id,
            raise_engine_exceptions=True,
        )

    def new_session(self) -> dict[str, Any]:
        session_id = str(uuid4())
        with self._lock:
            self._sessions[session_id] = []
        return self.snapshot(session_id)

    def snapshot(self, session_id: str) -> dict[str, Any]:
        history = self._history(session_id)
        memory = memory_service.get_user_memory(self._engine_user_id) or {}
        return {
            "session_id": session_id,
            "test_user": self._test_user(memory),
            "messages": list(history),
            "external_sends_disabled": True,
        }

    def process(self, session_id: str, message: str) -> dict[str, Any]:
        history = self._history(session_id)
        try:
            output = self._gateway.execute(
                ConversationGatewayInput(
                    engine_user_id=self._engine_user_id,
                    message_text=message.strip(),
                    chat_history=list(history),
                    correlation_id=f"test-chat:{session_id}:{uuid4()}",
                    brain_context=ConversationBrainContext(
                        creator_profile_id=self._creator_profile_id or None,
                        customer_identifier=self._engine_user_id,
                        conversation_identifier=session_id,
                        developer_mode=True,
                        fanvue_account_id=self._account_id,
                        external_fanvue_buyer_uuid=self.TEST_USER_UUID,
                    ),
                )
            )
        except Exception as error:
            raise TestChatExecutionError.from_exception(error) from error
        if output.error_code:
            raise RuntimeError(output.error_code)

        diagnostics = output.diagnostic_metadata
        decision = self._decision_summary(diagnostics)
        commerce = self._commerce_diagnostics(diagnostics)
        reply = output.response_text

        with self._lock:
            history.extend(
                (
                    {"role": "user", "content": message.strip()},
                    {"role": "assistant", "content": reply},
                )
            )

        return {
            "reply": reply,
            **decision,
            **commerce,
            "recommendation_diagnostics": diagnostics.get(
                "recommendation_diagnostics"
            ),
            "commerce_learning_profile": self._learning_profile(),
        }

    def _learning_profile(self):
        try:
            available = getattr(self._commerce_learning, "is_available", None)
            if callable(available) and not available():
                return None
            profile = self._commerce_learning.get_profile(
                creator_profile_id=self._creator_profile_id,
                fanvue_account_id=self._account_id,
                external_fanvue_user_uuid=self.TEST_USER_UUID,
            )
        except Exception:
            return None
        if profile is None:
            return None
        return {
            "preferences": dict(profile.preferences),
            "outcomeCounts": dict(profile.outcome_counts),
            "preferredOfferingType": profile.preferred_offering_type,
            "preferredPriceMinMinor": profile.preferred_price_min_minor,
            "preferredPriceMaxMinor": profile.preferred_price_max_minor,
            "repeatPurchaseFrequency": profile.repeat_purchase_frequency,
            "confidence": profile.confidence,
            "evidenceCount": profile.evidence_count,
        }

    @staticmethod
    def _commerce_diagnostics(diagnostics):
        keys = (
            "commerce_lookup_attempted", "requested_media_type",
            "requested_themes", "offering_selected", "offering_id",
            "offering_type", "offering_title", "price_minor", "currency",
            "primary_sales_channel", "provider", "fulfillable",
            "recommendation_reason", "no_offering_reason", "delivery_url",
            "legacy_offer_requested", "commerce_offer_authorized",
            "final_offer_authorized", "commerce_execution_policy",
            "customer_sales_decision", "customer_sales_reason_code",
            "authoritative_offering_selected", "selection_source",
            "commerce_prompt_mode", "legacy_recommendation_used",
            "commerce_mode", "compatibility_mode", "delivery_source",
            "memory_source", "eligibility_source", "recommendation_source",
            "legacy_memory_mutated", "legacy_delivery_used",
        )
        return {key: diagnostics.get(key) for key in keys}

    def clear_chat(self, session_id: str) -> dict[str, Any]:
        self._history(session_id)
        with self._lock:
            self._sessions[session_id] = []
        return self.snapshot(session_id)

    def reset_memory(self, session_id: str) -> dict[str, Any]:
        self._history(session_id)
        memory_service.clear_user_memory(self._engine_user_id)
        return self.snapshot(session_id)

    def _history(self, session_id: str) -> list[dict[str, str]]:
        with self._lock:
            history = self._sessions.get(session_id)
        if history is None:
            raise KeyError("Test Chat session not found")
        return history

    def _test_user(self, memory: dict[str, Any]) -> dict[str, str]:
        return {
            "name": str(self._user.get("display_name") or "Test User"),
            "relationship": str(
                memory.get("relationship_stage")
                or memory.get("relationship_status")
                or self._user.get("relationship_status")
                or "follower"
            ),
            "buyer_tier": str(
                memory.get("buyer_tier") or memory.get("user_value_tier") or "unknown"
            ),
        }

    @staticmethod
    def _decision_summary(diagnostics: dict[str, Any]) -> dict[str, Any]:
        route = diagnostics.get("route") or {}
        intent = diagnostics.get("intent") or {}
        selected = diagnostics.get("selected_content") or {}
        offer = diagnostics.get("final_offer") or {}
        wants_to_sell = bool(
            diagnostics.get("offer_authorized")
            if "offer_authorized" in diagnostics
            else diagnostics.get("send_offer")
        )
        product = selected.get("product_id") or offer.get("product_id")
        asset = selected.get("content_item_id") or selected.get("asset_id") or selected.get("id")

        if diagnostics.get("recommendation_reason"):
            reason = str(diagnostics["recommendation_reason"])
        elif diagnostics.get("no_offering_reason"):
            reason = str(diagnostics["no_offering_reason"])
        elif diagnostics.get("ownership_blocked"):
            reason = "Owned content was not eligible"
        elif diagnostics.get("delivery_prepared") is False:
            reason = str(diagnostics.get("delivery_blocking_reason") or "Fulfillment not ready")
        else:
            reason = str(route.get("reason") if isinstance(route, dict) else "") or (
                "Sale selected" if wants_to_sell else "The brain chose not to sell"
            )

        return {
            "intent": str(intent.get("tier") or intent.get("intent") or "unknown")
            if isinstance(intent, dict)
            else str(intent),
            "relationship": str(
                diagnostics.get("effective_route")
                or diagnostics.get("relationship_route")
                or (route.get("route") if isinstance(route, dict) else route)
                or "unknown"
            ),
            "sell": wants_to_sell,
            "reason": reason,
            "product": str(product) if product is not None else None,
            "asset": str(asset) if asset is not None else None,
            "provider_selected": (
                diagnostics.get("selected_provider")
                or diagnostics.get("provider")
            ),
        }


class TestChatExecutionError(RuntimeError):
    """Original engine failure formatted only for the developer Test Chat."""

    __test__ = False

    def __init__(self, diagnostics: dict[str, str]) -> None:
        super().__init__(diagnostics["exception_message"])
        self.diagnostics = diagnostics

    @classmethod
    def from_exception(cls, error: Exception) -> "TestChatExecutionError":
        rendered = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        frames = traceback.extract_tb(error.__traceback__)
        frame = frames[-1] if frames else None
        file_name = frame.filename if frame else "unknown"
        line_number = frame.lineno if frame else 0
        return cls(
            {
                "exception_type": type(error).__name__,
                "exception_message": str(error),
                "file": file_name,
                "line_number": str(line_number),
                "stack_trace": rendered,
                "root_cause": f"{type(error).__name__} raised at {file_name}:{line_number}: {error}",
            }
        )
