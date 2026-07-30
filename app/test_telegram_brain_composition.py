import ast
import logging
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import settings
from app.engine.decision_engine import DecisionEngine
from app.engine.mode_engine import ModeEngine
from app.models.commerce_mode import CommerceMode
from app.models.conversation_gateway import ConversationGatewayInput
from app.models.telegram_identity import TelegramMvpIdentityInput
from app.services.content_service import ContentService
from app.services.conversation_gateway import ConversationGateway
from app.services.intent_service import IntentService
from app.services.offer_service import OfferService
from app.services.post_offer_service import PostOfferService
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.timing_engine import TimingEngine
from app.services.user_value_service import UserValueService


FANVUE_LINK = "https://fanvue.com/ava/offline-offer"


class LiveCommerceMode:
    def get_mode(self):
        return CommerceMode.LIVE


class InMemoryMemoryService:
    def __init__(self):
        self.rows = {}

    def get_user_memory(self, user_id):
        return dict(self.rows.get(user_id, {}))

    def update_user_memory(self, user_id, data):
        self.rows.setdefault(user_id, {}).update(data)

    def set_field(self, user_id, key, value):
        self.rows.setdefault(user_id, {})[key] = value

    def get_field(self, user_id, key, default=None):
        return self.rows.get(user_id, {}).get(key, default)

    def increment_inbound_message(self, user_id):
        row = self.rows.setdefault(user_id, {})
        row["message_count"] = int(row.get("message_count", 0) or 0) + 1
        return dict(row)

    def increment_outbound_message(self, user_id):
        row = self.rows.setdefault(user_id, {})
        row["outbound_message_count"] = (
            int(row.get("outbound_message_count", 0) or 0) + 1
        )
        return dict(row)


class OfflineGptService:
    def generate_response(self, *args, **kwargs):
        return "Offline Ava response"


class ProfileRecordingOfflineGptService:
    def __init__(self):
        self.creator_profiles = []
        self.user_memories = []

    def generate_response(self, *args, **kwargs):
        user_memory = args[3]
        self.creator_profiles.append(user_memory.get("creator_profile"))
        self.user_memories.append(dict(user_memory))
        return "Offline Ava response"


class OfflineIntentClassifier:
    def __init__(self, *, buying=False):
        self.buying = buying

    def classify_message(self, **kwargs):
        return {
            "confidence": 0.99,
            "route": "sales" if self.buying else "chat",
            "recommended_action": "close" if self.buying else "chat",
            "buying_intent": self.buying,
            "close_ready": self.buying,
            "user_state": "ready_to_buy" if self.buying else "casual",
            "signals": ["buying"] if self.buying else [],
            "curiosity_level": "high" if self.buying else "low",
            "escalation_ready": self.buying,
        }


class OfflineObjectionClassifier:
    def classify_objection(self, **kwargs):
        return {
            "has_objection": False,
            "objection_type": "none",
            "confidence": 1.0,
            "reason": "offline fixture",
        }


class OfflineDependencyClassifier:
    def classify_dependency_risk(self, *args, **kwargs):
        return {
            "dependency_risk_level": "low",
            "dependency_risk_score": 0,
        }


class OfflineContentService:
    def get_content(self, *args, **kwargs):
        return {
            "id": 1,
            "content_item_id": 1,
            "tag": "offline_vip_1",
            "type": "vip",
            "tier": "high",
            "price": 10,
            "caption": "Offline offer",
            "fanvue_link": FANVUE_LINK,
        }


class NeverOwnedContentService:
    def user_already_owns_content(self, *args, **kwargs):
        return False


class NeverUsedContentService:
    def has_seen_content(self, *args, **kwargs):
        return False

    def has_seen_content_tag(self, *args, **kwargs):
        return False

    def mark_content_seen(self, *args, **kwargs):
        return None


class TelegramBrainCompositionTests(unittest.TestCase):
    def setUp(self):
        self.adapter = TelegramIdentityAdapter(engine_account_id=7)

    def build_engine(
        self,
        *,
        content_service=None,
        buying=False,
        gpt_service=None,
        require_creator_profile=True,
    ):
        memory = InMemoryMemoryService()
        engine_settings = type(
            "OfflineSettings",
            (),
            {
                "OPENAI_API_KEY": settings.OPENAI_API_KEY,
                "DEFAULT_PERSONA": settings.DEFAULT_PERSONA,
                "REQUIRE_CREATOR_PROFILE": require_creator_profile,
            },
        )()
        with (
            patch(
                "app.engine.decision_engine.GPTIntentClassifierService",
                return_value=OfflineIntentClassifier(buying=buying),
            ),
            patch(
                "app.engine.decision_engine.ObjectionClassifierService",
                return_value=OfflineObjectionClassifier(),
            ),
            patch(
                "app.engine.decision_engine.EmotionalDependencyClassifierService",
                return_value=OfflineDependencyClassifier(),
            ),
        ):
            engine = DecisionEngine(
                memory_service=memory,
                intent_service=IntentService(),
                user_value_service=UserValueService(),
                mode_engine=ModeEngine(),
                offer_service=OfferService(),
                content_service=content_service or ContentService(),
                post_offer_service=PostOfferService(),
                timing_engine=TimingEngine(),
                gpt_service=gpt_service or OfflineGptService(),
                settings=engine_settings,
                logger=logging.getLogger("telegram-brain-composition"),
            )
        engine.content_ownership_service = NeverOwnedContentService()
        engine.content_usage_service = NeverUsedContentService()
        return engine, memory

    @staticmethod
    def creator_profile():
        return {
            "persona_name": "Ava",
            "system_prompt": "Offline composition fixture",
            "tone_profile": {},
            "boundaries": {},
            "style_rules": {},
        }

    def identity(self):
        return self.adapter.adapt(
            TelegramMvpIdentityInput(
                telegram_user_id=123456789,
                telegram_chat_id=123456789,
            )
        )

    def execute_gateway(
        self,
        engine,
        *,
        correlation_id,
        message_text="hello there",
        commerce_mode_service=None,
    ):
        gateway = ConversationGateway(
            engine,
            allowed_fanvue_hostnames=["fanvue.com"],
            commerce_mode_service=(
                commerce_mode_service or LiveCommerceMode()
            ),
        )
        identity = self.identity()
        return gateway.execute(
            ConversationGatewayInput(
                engine_user_id=identity.engine_user_id,
                message_text=message_text,
                chat_history=[],
                correlation_id=correlation_id,
            )
        )

    def test_real_brain_accepts_stable_telegram_compatibility_key(self):
        engine, memory = self.build_engine()
        identity = self.identity()
        repeated_identity = self.identity()
        received_engine_keys = []
        real_process_message = engine.process_message

        def recording_process_message(user_id, message, chat_history=None):
            received_engine_keys.append(user_id)
            return real_process_message(
                user_id,
                message,
                chat_history=chat_history,
            )

        engine.process_message = recording_process_message

        with (
            patch.object(
                engine.decision_runtime_boundary,
                "get_active_creator_profile",
                return_value=self.creator_profile(),
            ),
            patch.object(
                engine.decision_runtime_boundary,
                "get_user_by_account_and_id",
                return_value=None,
            ),
            patch.object(engine.decision_runtime_boundary, "log_send_event"),
            patch("builtins.print"),
        ):
            output = self.execute_gateway(
                engine,
                correlation_id="offline-normal",
            )

        self.assertEqual(identity, repeated_identity)
        self.assertEqual(identity.engine_user_id, "7:-123456789")
        self.assertEqual(received_engine_keys, [identity.engine_user_id])
        self.assertIn(identity.engine_user_id, memory.rows)
        self.assertEqual(output.correlation_id, "offline-normal")
        self.assertEqual(output.response_text, "Offline Ava response")
        self.assertFalse(output.blocked, output)
        self.assertIsNone(output.error_code)
        self.assertFalse(output.offer_authorized)
        self.assertIsNone(output.offer_link)

    def test_real_brain_authorized_offer_is_preserved(self):
        engine, memory = self.build_engine(
            content_service=OfflineContentService(),
            buying=True,
        )
        identity = self.identity()
        memory.rows[identity.engine_user_id] = {
            "fanvue_account_id": 7,
            "fanvue_user_id": -123456789,
            "buyer_session_active": True,
            "buyer_session_step": 2,
            "buyer_session_ppv_count": 0,
            "intent_score": 90,
            "messages_since_last_offer": 5,
            "conversation_streak": 5,
            "engagement_depth_score": 6,
            "offers_shown_count": 0,
        }

        with (
            patch.object(
                engine.decision_runtime_boundary,
                "get_active_creator_profile",
                return_value=self.creator_profile(),
            ),
            patch.object(
                engine.decision_runtime_boundary,
                "get_user_by_account_and_id",
                return_value=None,
            ),
            patch.object(engine.decision_runtime_boundary, "log_send_event"),
            patch("builtins.print"),
        ):
            output = self.execute_gateway(
                engine,
                correlation_id="offline-offer",
                message_text="yes, send it now",
            )

        self.assertFalse(output.blocked)
        self.assertTrue(output.offer_authorized)
        self.assertEqual(output.offer_link, FANVUE_LINK)

    def test_authoritative_wait_skips_legacy_commerce_side_effects(self):
        engine, memory = self.build_engine(
            content_service=OfflineContentService(),
            buying=True,
        )
        identity = self.identity()
        original_commerce = {
            "offers_shown_count": 2,
            "last_offer_timestamp": "2026-07-20T12:00:00",
            "last_offer_type": "vip",
            "offer_state": "offered",
            "post_offer_nudge_count": 1,
        }
        memory.rows[identity.engine_user_id] = {
            "fanvue_account_id": 7,
            "fanvue_user_id": -123456789,
            **original_commerce,
        }
        injection = {
            "commerce_execution_policy": "COMMERCE_DISABLED_FOR_TURN",
            "commerce_decision": {
                "decision": "WAIT",
                "reason_code": "ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE",
                "buyer_stage": "FIRST_TIME_BUYER",
                "current_offer_status": "PRESENTED",
                "conversion_state": "OFFER_PRESENTED",
            },
        }

        with (
            patch.object(
                engine.decision_runtime_boundary,
                "get_active_creator_profile",
                return_value=self.creator_profile(),
            ),
            patch.object(
                engine.decision_runtime_boundary,
                "get_user_by_account_and_id",
                return_value=None,
            ),
            patch.object(engine.decision_runtime_boundary, "log_send_event"),
            patch.object(
                engine.offer, "determine_offer",
                wraps=engine.offer.determine_offer,
            ) as determine_offer,
            patch.object(
                engine.timing, "evaluate_timing",
                wraps=engine.timing.evaluate_timing,
            ) as evaluate_timing,
            patch.object(
                engine.product_recommendation_service, "get_content",
                wraps=engine.product_recommendation_service.get_content,
            ) as select_product,
            patch.object(
                engine.post_offer, "increment_post_offer_message_count",
                wraps=engine.post_offer.increment_post_offer_message_count,
            ) as increment_post_offer,
            patch.object(
                engine.post_offer, "expire_offer_if_needed",
                wraps=engine.post_offer.expire_offer_if_needed,
            ) as expire_offer,
            patch.object(
                engine.post_offer, "build_nudge_payload",
                wraps=engine.post_offer.build_nudge_payload,
            ) as build_nudge,
            patch("builtins.print"),
        ):
            result = engine.process_message(
                identity.engine_user_id,
                "yes, send it now",
                chat_history=[],
                runtime_injection=injection,
            )

        self.assertFalse(result["send_offer"])
        self.assertEqual(
            result["commerce_execution_policy"],
            "COMMERCE_DISABLED_FOR_TURN",
        )
        determine_offer.assert_not_called()
        evaluate_timing.assert_not_called()
        select_product.assert_not_called()
        increment_post_offer.assert_not_called()
        expire_offer.assert_not_called()
        build_nudge.assert_not_called()
        row = memory.rows[identity.engine_user_id]
        for key, value in original_commerce.items():
            self.assertEqual(row.get(key), value)

    def test_authoritative_presentation_never_selects_legacy_content(self):
        engine, memory = self.build_engine(
            content_service=OfflineContentService(),
            buying=True,
        )
        identity = self.identity()
        memory.rows[identity.engine_user_id] = {
            "fanvue_account_id": 7,
            "fanvue_user_id": -123456789,
            "intent_score": 90,
            "messages_since_last_offer": 5,
            "conversation_streak": 5,
            "engagement_depth_score": 6,
            "offers_shown_count": 0,
        }
        injection = {
            "commerce_execution_policy": "COMMERCE_PRESENTATION_ALLOWED",
            "commerce_decision": {
                "decision": "PRESENT_OFFER",
                "reason_code": "NO_ACTIVE_OFFER",
                "buyer_stage": "PROSPECT",
                "current_offer_status": None,
                "conversion_state": "NO_ACTIVE_OFFER",
            },
        }

        with (
            patch.object(
                engine.decision_runtime_boundary,
                "get_active_creator_profile",
                return_value=self.creator_profile(),
            ),
            patch.object(
                engine.decision_runtime_boundary,
                "get_user_by_account_and_id",
                return_value=None,
            ),
            patch.object(engine.decision_runtime_boundary, "log_send_event"),
            patch.object(
                engine.product_recommendation_service, "get_content",
                wraps=engine.product_recommendation_service.get_content,
            ) as select_product,
            patch.object(
                engine.post_offer, "mark_offer_sent",
                wraps=engine.post_offer.mark_offer_sent,
            ) as mark_offer_sent,
            patch("builtins.print"),
        ):
            result = engine.process_message(
                identity.engine_user_id,
                "yes, send it now",
                chat_history=[],
                runtime_injection=injection,
            )

        self.assertEqual(
            result["send_offer"],
            result["legacy_offer_requested"],
        )
        self.assertIsNone(result["offer"]["content"])
        select_product.assert_not_called()
        mark_offer_sent.assert_not_called()
        self.assertEqual(
            memory.rows[identity.engine_user_id].get("offers_shown_count"),
            0,
        )
        self.assertIsNone(
            memory.rows[identity.engine_user_id].get("last_offer_timestamp")
        )

    def test_real_brain_creator_profile_block_is_normalized(self):
        engine, _ = self.build_engine()
        received_engine_keys = []
        real_process_message = engine.process_message

        def recording_process_message(user_id, message, chat_history=None):
            received_engine_keys.append(user_id)
            return real_process_message(
                user_id,
                message,
                chat_history=chat_history,
            )

        engine.process_message = recording_process_message

        with (
            patch.object(
                engine.decision_runtime_boundary,
                "get_active_creator_profile",
                return_value=None,
            ),
            patch("builtins.print"),
        ):
            output = self.execute_gateway(
                engine,
                correlation_id="offline-blocked",
            )

        self.assertEqual(received_engine_keys, ["7:-123456789"])
        self.assertTrue(output.blocked)
        self.assertEqual(output.error_code, "creator_profile_required")
        self.assertFalse(output.offer_authorized)
        self.assertIsNone(output.offer_link)
        self.assertIn("Creator Profile", output.response_text)

    def test_real_brain_can_bypass_missing_creator_profile_when_disabled(self):
        gpt_service = ProfileRecordingOfflineGptService()
        engine, _ = self.build_engine(
            gpt_service=gpt_service,
            require_creator_profile=False,
        )

        with (
            patch.object(
                engine.decision_runtime_boundary,
                "get_active_creator_profile",
                return_value=None,
            ),
            patch.object(
                engine.decision_runtime_boundary,
                "get_user_by_account_and_id",
                return_value=None,
            ),
            patch.object(engine.decision_runtime_boundary, "log_send_event"),
            patch("builtins.print"),
        ):
            output = self.execute_gateway(
                engine,
                correlation_id="offline-profile-bypass",
            )

        self.assertFalse(output.blocked, output)
        self.assertIsNone(output.error_code)
        self.assertEqual(output.response_text, "Offline Ava response")
        self.assertEqual(len(gpt_service.creator_profiles), 1)
        self.assertEqual(
            gpt_service.creator_profiles[0],
            {
                "persona_name": settings.DEFAULT_PERSONA,
                "display_name": settings.DEFAULT_PERSONA,
            },
        )
        self.assertEqual(
            gpt_service.user_memories[0]["fanvue_user_id"],
            "-123456789",
        )
        self.assertIsNone(
            gpt_service.user_memories[0]["mapped_fanvue_user_id"]
        )

    def test_composition_test_introduces_no_transport_or_sdk_imports(self):
        path = Path(__file__).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        forbidden_fragments = (
            "telegram.ext",
            "telegram.bot",
            "telethon",
            "aiogram",
            "listener",
            "sender",
            "polling",
            "kviqa",
        )
        for module in imports:
            with self.subTest(module=module):
                self.assertFalse(
                    any(fragment in module.lower() for fragment in forbidden_fragments),
                    module,
                )


if __name__ == "__main__":
    unittest.main()
