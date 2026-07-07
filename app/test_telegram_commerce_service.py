import unittest
from pathlib import Path

from app.models.commerce_execution import RuntimeExecutionIntent, RuntimeExecutionPayload
from app.models.runtime_decision import DecisionEngineResult, RuntimeDecision
from app.models.telegram_commerce import (
    TelegramDeliveryDecision,
    TelegramDeliveryPayload,
    TelegramExperienceProgression,
)
from app.services.telegram_commerce_service import TelegramCommerceService


class FakeDecisionEngine:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def process_message(self, user_id, message, chat_history=None):
        self.calls.append(
            {
                "user_id": user_id,
                "message": message,
                "chat_history": chat_history,
            }
        )
        return self.result


class FakeMemoryService:
    def __init__(self):
        self.calls = []

    def get_or_create_user_memory(self, user_id):
        self.calls.append(user_id)
        return {
            "user_id": user_id,
            "current_product_id": "memory-product",
            "current_asset_id": "memory-asset",
            "delivery_type": "FREE",
            "conversation_mode": "memory-mode",
            "current_story_position": "scene-1",
            "current_asset_position": "asset-step-1",
            "experience_progress_percentage": 20,
            "last_progression_event": {
                "action": "continue_experience",
                "token": "must-not-leak",
            },
            "last_delivery": {
                "delivery_type": "FREE",
                "token": "must-not-leak",
            },
        }


class FakeCustomerService:
    def get_customer_summary(self, customer_id):
        return {
            "customer_id": customer_id,
            "current_experience_id": "experience-1",
            "current_position": "customer-scene",
            "session_step": 2,
            "relationship_status": "known",
            "buyer_tier": "warm",
            "active_session": True,
            "message_count": 12,
            "offer_count": 3,
        }

    def get_customer_commerce_summary(self, customer_id):
        return {
            "customer_id": customer_id,
            "products_purchased": ("product-owned",),
            "purchased_experiences": ("experience-old",),
            "purchase_summary": {
                "purchase_count": 1,
                "total_spend_cents": 2499,
                "last_purchase_at": "2026-01-04",
            },
        }


class FakeProductRecommendationService:
    def __init__(self):
        self.calls = []

    def get_offer_candidate(self, *, offer_type):
        self.calls.append(offer_type)
        return {
            "offer_id": "recommended-offer",
            "offer_kind": "premium",
            "title": "Recommended Product",
            "reason": "best_match",
            "score": 88,
            "product": {"product_id": "recommended-product"},
        }


class FakeCMSContractService:
    def __init__(self):
        self.calls = []

    def build_delivery_permission(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "allowed": True,
            "delivery_mode": kwargs["delivery_mode"],
            "requires_payment": kwargs["delivery_mode"] == "paid",
            "reason": "allowed_by_contract",
            "price_cents": 1299,
            "currency": "USD",
        }


class FakePublishingService:
    def __init__(self):
        self.calls = []

    def get_by_product_id(self, product_id):
        self.calls.append(product_id)
        return {
            "product_id": product_id,
            "media_link": "https://fanvue.example/media/recommended-product",
        }


class FakeAssetService:
    def __init__(self):
        self.calls = []

    def get_asset_details(self, asset_id):
        self.calls.append(asset_id)
        return {
            "item": {
                "local_vault_path": f"C:/vault/{asset_id}.jpg",
                "legacy_file_path": f"C:/legacy/{asset_id}.jpg",
            }
        }


class BlockingGuardService:
    def validate(self, _payload):
        return {"allowed": False, "reason": "guard_blocked"}


class FakeDeliveryExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, payload, *, context=None):
        telegram_payload = (
            payload.payload
            if isinstance(payload, RuntimeExecutionIntent)
            else payload
        )
        self.calls.append({"payload": payload, "context": context})
        return type(
            "ExecutionResult",
            (),
            {
                "status": "deferred",
                "executed": False,
                "delivery_method": telegram_payload.delivery_method,
                "blocking_reason": telegram_payload.blocking_reason,
            },
        )()


def engine_result(**overrides):
    values = {
        "response": "Here you go",
        "send_offer": True,
        "effective_route": "experience",
        "experience_progression": {
            "action": "continue_experience",
            "experience_id": "experience-1",
            "story_position": "scene-2",
            "asset_position": "asset-2",
            "progress_percentage": 40,
        },
        "offer": {
            "offer_type": "premium",
            "content": {
                "product_id": "product-1",
                "asset_id": "asset-1",
                "fanvue_link": "https://share.fanvue.com/ava/product-1",
                "delivery_type": "PAID",
                "delivery_permission_mode": "paid",
                "delivery_requires_payment": True,
            },
        },
    }
    values.update(overrides)
    return values


class TelegramCommerceServiceTests(unittest.TestCase):
    def build_service(
        self,
        decision_engine,
        *,
        product_recommendation_service=None,
        cms_contract_service=None,
        publishing_service=None,
        asset_service=None,
        content_delivery_guard_service=None,
        delivery_executor=None,
    ):
        self.memory_service = FakeMemoryService()
        return TelegramCommerceService(
            decision_engine=decision_engine,
            experience_service=object(),
            product_recommendation_service=(
                product_recommendation_service or object()
            ),
            cms_contract_service=cms_contract_service or object(),
            publishing_service=publishing_service or object(),
            customer_service=FakeCustomerService(),
            memory_service=self.memory_service,
            asset_service=asset_service,
            content_delivery_guard_service=content_delivery_guard_service,
            delivery_executor=delivery_executor,
        )

    def test_execute_coordinates_existing_services_without_owning_runtime(self):
        decision_engine = FakeDecisionEngine(engine_result())
        service = self.build_service(decision_engine)
        history = [{"role": "user", "content": "previous"}]

        result = service.execute(
            engine_user_id="7:-123456789",
            message_text="show me",
            chat_history=history,
            correlation_id="telegram:1:2",
        )

        self.assertEqual(decision_engine.calls[0]["user_id"], "7:-123456789")
        self.assertEqual(decision_engine.calls[0]["chat_history"][0], history[0])
        commerce_context = decision_engine.calls[0]["chat_history"][-1]
        self.assertEqual(commerce_context["content"], "telegram_commerce_memory")
        self.assertEqual(
            commerce_context["commerce_memory"]["purchased_products"],
            ("product-owned",),
        )
        self.assertIn("7:-123456789", self.memory_service.calls)
        self.assertEqual(result.response_text, "Here you go")
        self.assertIsInstance(result.decision_engine_result, DecisionEngineResult)
        self.assertEqual(
            result.decision_engine_result.runtime_decision.response_text,
            "Here you go",
        )
        self.assertEqual(result.decision_engine_result, engine_result())
        self.assertEqual(result.delivery_decision.delivery_type, "PAID")
        self.assertTrue(result.delivery_decision.requires_payment)
        self.assertEqual(
            result.customer_progress.current_experience_id,
            "experience-1",
        )
        self.assertEqual(result.customer_progress.current_product_id, "product-1")
        self.assertEqual(
            result.customer_progress.commerce_state,
            "paid_media_link_delivery",
        )
        self.assertEqual(
            result.previous_conversation_state.current_product_id,
            "memory-product",
        )
        self.assertEqual(result.conversation_state.current_product_id, "product-1")
        self.assertEqual(result.conversation_state.current_asset_id, "asset-1")
        self.assertEqual(result.conversation_state.current_delivery_type, "PAID")
        self.assertEqual(result.conversation_state.conversation_mode, "experience")
        self.assertEqual(result.conversation_state.current_offer_kind, "premium")
        self.assertEqual(
            result.conversation_state.next_recommended_action,
            "deliver_paid_media_link",
        )
        self.assertEqual(
            result.state.telegram_conversation_state,
            result.conversation_state,
        )
        self.assertEqual(result.experience_progression.current_experience_id, "experience-1")
        self.assertEqual(result.experience_progression.current_story_position, "scene-2")
        self.assertEqual(result.experience_progression.current_asset_position, "asset-2")
        self.assertEqual(result.experience_progression.progress_percentage, 40)
        self.assertEqual(result.commerce_memory.purchased_products, ("product-owned",))
        self.assertEqual(
            result.commerce_memory.customer_spending_summary["total_spend_cents"],
            2499,
        )
        self.assertEqual(result.delivery_decision.current_product_id, "product-1")
        self.assertEqual(result.delivery_decision.delivery_method, "paid_media_link")
        self.assertEqual(
            result.delivery_decision.next_suggested_action,
            "deliver_paid_media_link",
        )
        self.assertEqual(
            result.state.experience_progression,
            result.experience_progression,
        )
        self.assertEqual(
            result.diagnostic_metadata["orchestrator"],
            "TelegramCommerceService",
        )

    def test_execute_delegates_runtime_execution_to_delivery_executor(self):
        delivery_executor = FakeDeliveryExecutor()
        service = self.build_service(
            FakeDecisionEngine(engine_result()),
            delivery_executor=delivery_executor,
        )

        result = service.execute(
            engine_user_id="7:-123456789",
            message_text="show me",
            correlation_id="telegram:1:2",
        )

        self.assertEqual(len(delivery_executor.calls), 1)
        self.assertIsInstance(
            delivery_executor.calls[0]["payload"],
            RuntimeExecutionIntent,
        )
        self.assertEqual(
            delivery_executor.calls[0]["payload"].payload,
            RuntimeExecutionPayload(
                delivery_type=result.delivery_payload.delivery_type,
                message_text=result.delivery_payload.message_text,
                asset_path=result.delivery_payload.asset_path,
                media_link=result.delivery_payload.media_link,
                product_reference=result.delivery_payload.product_reference,
                experience_reference=result.delivery_payload.experience_reference,
                delivery_reason=result.delivery_payload.delivery_reason,
                blocking_reason=result.delivery_payload.blocking_reason,
                next_suggested_action=(
                    result.delivery_payload.next_suggested_action
                ),
                delivery_method=result.delivery_payload.delivery_method,
                metadata=result.delivery_payload.metadata,
            ),
        )
        self.assertEqual(
            delivery_executor.calls[0]["context"],
            {
                "correlation_id": "telegram:1:2",
                "engine_user_id": "7:-123456789",
            },
        )
        self.assertEqual(
            result.diagnostic_metadata["telegram_delivery_execution_boundary"],
            "FakeDeliveryExecutor",
        )
        self.assertEqual(
            result.diagnostic_metadata["commerce_execution_boundary"],
            "CommerceExecutionService",
        )
        self.assertEqual(
            result.diagnostic_metadata["commerce_execution_status"],
            "deferred",
        )
        self.assertIn(
            "DELIVER_MEDIA_LINK",
            result.diagnostic_metadata["commerce_runtime_actions"],
        )
        self.assertEqual(
            result.diagnostic_metadata["telegram_delivery_execution_status"],
            "deferred",
        )

    def test_process_message_preserves_conversation_gateway_compatibility(self):
        original = engine_result(response="Gateway sees this")
        decision_engine = FakeDecisionEngine(original)
        service = self.build_service(decision_engine)

        result = service.process_message(
            "7:-123456789",
            "hello",
            chat_history=[],
        )

        self.assertEqual(result["response"], original["response"])
        self.assertEqual(result["offer"], original["offer"])
        self.assertIn("telegram_delivery_payload", result)

    def test_execute_consumes_typed_decision_engine_result(self):
        typed_result = DecisionEngineResult.from_mapping(
            engine_result(response="Typed response")
        )
        decision_engine = FakeDecisionEngine(typed_result)
        service = self.build_service(decision_engine)

        result = service.execute(
            engine_user_id="7:-123456789",
            message_text="show me",
            chat_history=[],
        )

        self.assertIs(result.decision_engine_result, typed_result)
        self.assertEqual(result.response_text, "Typed response")
        self.assertEqual(
            result.delivery_decision.current_product_id,
            "product-1",
        )

    def test_execute_consumes_runtime_decision_without_legacy_mapping(self):
        typed_result = DecisionEngineResult(
            runtime_decision=RuntimeDecision(
                response_text="Typed only",
                delivery_type="PAID",
                product_reference="typed-product",
                call_to_action={"send_offer": True},
                publishing_reference={
                    "media_link": "https://fanvue.example/media/typed-product",
                },
                execution_metadata={
                    "delivery_permission_mode": "paid",
                    "delivery_requires_payment": True,
                },
            )
        )
        service = self.build_service(FakeDecisionEngine(typed_result))

        result = service.execute(
            engine_user_id="7:-123456789",
            message_text="show me",
            chat_history=[],
        )

        self.assertEqual(result.response_text, "Typed only")
        self.assertEqual(result.delivery_decision.current_product_id, "typed-product")
        self.assertEqual(result.delivery_decision.delivery_type, "PAID")
        self.assertTrue(result.delivery_decision.requires_payment)
        self.assertEqual(
            result.delivery_decision.paid_media_link,
            "https://fanvue.example/media/typed-product",
        )
        self.assertEqual(
            result.delivery_payload.media_link,
            "https://fanvue.example/media/typed-product",
        )

    def test_load_conversation_state_rebuilds_from_customer_memory(self):
        decision_engine = FakeDecisionEngine(engine_result())
        service = self.build_service(decision_engine)

        state = service.load_conversation_state("7:-123456789")

        self.assertEqual(state.current_experience_id, "experience-1")
        self.assertEqual(state.current_product_id, "memory-product")
        self.assertEqual(state.current_asset_id, "memory-asset")
        self.assertEqual(state.current_delivery_type, "FREE")
        self.assertEqual(state.conversation_mode, "memory-mode")
        self.assertEqual(state.next_recommended_action, "continue_experience")
        self.assertNotIn("token", state.last_delivery)
        self.assertEqual(
            state.metadata["persistence_owner"],
            "MemoryService",
        )

    def test_load_experience_progression_rebuilds_from_existing_state(self):
        decision_engine = FakeDecisionEngine(engine_result())
        service = self.build_service(decision_engine)

        progression = service.load_experience_progression(
            "7:-123456789",
            conversation_state=service.load_conversation_state("7:-123456789"),
        )

        self.assertEqual(progression.current_experience_id, "experience-1")
        self.assertEqual(progression.experience_state, "active")
        self.assertEqual(progression.current_story_position, "customer-scene")
        self.assertEqual(progression.current_asset_position, "2")
        self.assertEqual(progression.progress_percentage, 20)
        self.assertEqual(
            progression.next_recommended_experience_action,
            "continue_experience",
        )
        self.assertNotIn("token", progression.last_progression_event)
        self.assertEqual(
            progression.metadata["workflow_owner"],
            "TelegramCommerceService",
        )

    def test_load_commerce_memory_rebuilds_customer_journey(self):
        service = self.build_service(FakeDecisionEngine(engine_result()))
        conversation = service.load_conversation_state("7:-123456789")
        progression = service.load_experience_progression(
            "7:-123456789",
            conversation_state=conversation,
        )

        memory = service.load_commerce_memory(
            "7:-123456789",
            conversation_state=conversation,
            experience_progression=progression,
        )

        self.assertEqual(memory.purchased_products, ("product-owned",))
        self.assertEqual(memory.current_experience_id, "experience-1")
        self.assertEqual(memory.previous_experiences, ("experience-old",))
        self.assertEqual(memory.current_commerce_journey, "customer")
        self.assertEqual(memory.customer_spending_summary["purchase_count"], 1)
        self.assertEqual(memory.customer_engagement_summary["message_count"], 12)
        self.assertEqual(
            memory.recommended_commerce_action,
            "escalate_commerce_offer",
        )
        self.assertEqual(memory.metadata["memory_owner"], "MemoryService")

    def test_update_commerce_memory_records_free_and_paid_delivery_history(self):
        service = self.build_service(FakeDecisionEngine(engine_result()))
        conversation = service.load_conversation_state("7:-123456789")
        progression = service.load_experience_progression("7:-123456789")
        previous = service.load_commerce_memory(
            "7:-123456789",
            conversation_state=conversation,
            experience_progression=progression,
        )

        free_memory = service.update_commerce_memory(
            previous_memory=previous,
            delivery_decision=TelegramDeliveryDecision(
                offer_authorized=True,
                blocked=False,
                delivery_type="FREE",
                delivery_method="free_asset",
                next_suggested_action="deliver_free_asset",
            ),
            delivery_payload=TelegramDeliveryPayload(
                delivery_type="FREE",
                message_text="Here",
                asset_path="C:/vault/free.jpg",
                delivery_method="free_asset",
                next_suggested_action="deliver_free_asset",
            ),
            conversation_state=conversation,
            experience_progression=progression,
        )
        paid_memory = service.update_commerce_memory(
            previous_memory=free_memory,
            delivery_decision=TelegramDeliveryDecision(
                offer_authorized=True,
                blocked=False,
                delivery_type="PAID",
                delivery_method="paid_media_link",
                next_suggested_action="deliver_paid_media_link",
            ),
            delivery_payload=TelegramDeliveryPayload(
                delivery_type="PAID",
                message_text="Link",
                media_link="https://fanvue.example/media/1",
                delivery_method="paid_media_link",
                next_suggested_action="deliver_paid_media_link",
            ),
            conversation_state=conversation,
            experience_progression=progression,
        )

        self.assertEqual(free_memory.free_assets_delivered, ("C:/vault/free.jpg",))
        self.assertEqual(
            paid_memory.paid_media_links_delivered,
            ("https://fanvue.example/media/1",),
        )
        self.assertEqual(
            paid_memory.last_delivery["delivery_method"],
            "paid_media_link",
        )
        self.assertEqual(
            paid_memory.recommended_commerce_action,
            "deliver_paid_media_link",
        )

    def test_update_conversation_state_tracks_commerce_progress(self):
        decision_engine = FakeDecisionEngine(engine_result())
        service = self.build_service(decision_engine)
        previous = service.load_conversation_state("7:-123456789")
        delivery = service.build_delivery_decision(engine_result())
        progress = service.build_customer_progress(
            engine_user_id="7:-123456789",
            engine_result=engine_result(),
            delivery_decision=delivery,
        )

        state = service.update_conversation_state(
            previous_state=previous,
            engine_result=engine_result(),
            delivery_decision=delivery,
            customer_progress=progress,
        )

        self.assertEqual(state.current_experience_id, "experience-1")
        self.assertEqual(state.current_product_id, "product-1")
        self.assertEqual(state.commerce_state, "paid_media_link_delivery")
        self.assertEqual(state.last_delivery["delivery_type"], "PAID")
        self.assertEqual(state.next_recommended_action, "deliver_paid_media_link")

    def test_paid_delivery_decision_uses_permission_and_media_link_services(self):
        product_recommendation = FakeProductRecommendationService()
        cms_contract = FakeCMSContractService()
        publishing = FakePublishingService()
        service = self.build_service(
            FakeDecisionEngine(engine_result()),
            product_recommendation_service=product_recommendation,
            cms_contract_service=cms_contract,
            publishing_service=publishing,
        )

        decision = service.build_delivery_decision(
            engine_result(
                offer={
                    "offer_type": "premium",
                    "content": {
                        "product_id": "recommended-product",
                        "delivery_type": "PAID",
                        "delivery_permission_mode": "paid",
                        "delivery_requires_payment": True,
                    },
                }
            )
        )

        self.assertEqual(decision.current_product_id, "recommended-product")
        self.assertEqual(decision.delivery_type, "PAID")
        self.assertEqual(decision.delivery_method, "paid_media_link")
        self.assertEqual(decision.paid_media_link, "https://fanvue.example/media/recommended-product")
        self.assertTrue(decision.delivery_permission["allowed"])
        self.assertEqual(decision.delivery_permission["source"], "CMSContractService")
        self.assertEqual(decision.next_suggested_action, "deliver_paid_media_link")
        self.assertEqual(cms_contract.calls[0]["subject_id"], "recommended-product")
        self.assertEqual(publishing.calls, ["recommended-product"])

    def test_recommend_different_product_uses_product_recommendation_service(self):
        product_recommendation = FakeProductRecommendationService()
        service = self.build_service(
            FakeDecisionEngine(engine_result()),
            product_recommendation_service=product_recommendation,
            cms_contract_service=FakeCMSContractService(),
            publishing_service=FakePublishingService(),
        )

        decision = service.build_delivery_decision(
            engine_result(
                delivery_action="recommend_different_product",
                offer={"offer_type": "premium", "content": {}},
            )
        )

        self.assertEqual(product_recommendation.calls, ["premium"])
        self.assertEqual(
            decision.commerce_recommendation["product_id"],
            "recommended-product",
        )
        self.assertEqual(decision.current_product_id, "recommended-product")
        self.assertEqual(
            decision.next_suggested_action,
            "recommend_different_product",
        )

    def test_supported_experience_progression_actions(self):
        service = self.build_service(FakeDecisionEngine(engine_result()))
        previous = TelegramExperienceProgression(
            current_experience_id="experience-1",
            experience_state="active",
            current_story_position="scene-1",
            current_asset_position="asset-1",
            current_product_id="product-1",
            progress_percentage=25,
        )
        conversation_state = service.load_conversation_state("7:-123456789")
        cases = {
            "continue_experience": ("active", "continue_experience", 55),
            "pause_experience": ("paused", "resume_experience", 55),
            "resume_experience": ("active", "continue_experience", 55),
            "complete_experience": ("complete", "switch_experience", 100),
            "switch_experience": ("active", "continue_experience", 55),
            "restart_experience": ("active", "continue_experience", 0),
        }

        for action, expected in cases.items():
            with self.subTest(action=action):
                state, next_action, progress = expected
                progression = service.update_experience_progression(
                    previous_progression=previous,
                    engine_result=engine_result(
                        experience_progression={
                            "action": action,
                            "experience_id": "experience-2",
                            "story_position": "scene-2",
                            "asset_position": "asset-2",
                            "progress_percentage": 55,
                        }
                    ),
                    conversation_state=conversation_state,
                )

                self.assertEqual(progression.experience_state, state)
                self.assertEqual(
                    progression.next_recommended_experience_action,
                    next_action,
                )
                self.assertEqual(progression.progress_percentage, progress)
                self.assertEqual(progression.current_experience_id, "experience-2")
                self.assertEqual(progression.current_story_position, "scene-2")
                self.assertEqual(progression.current_asset_position, "asset-2")
                self.assertEqual(
                    progression.last_progression_event["action"],
                    action,
                )

    def test_free_delivery_is_provider_neutral(self):
        decision_engine = FakeDecisionEngine(
            engine_result(
                offer={
                    "offer_type": "free_asset",
                    "content": {
                        "asset_id": "asset-free",
                        "delivery_type": "FREE",
                        "delivery_permission_mode": "included",
                        "delivery_requires_payment": False,
                    },
                }
            )
        )
        service = self.build_service(decision_engine)

        result = service.execute(
            engine_user_id="7:-123456789",
            message_text="free please",
        )

        self.assertIsNone(result.delivery_decision.offer_link)
        self.assertEqual(result.delivery_decision.delivery_type, "FREE")
        self.assertFalse(result.delivery_decision.requires_payment)
        self.assertEqual(result.customer_progress.commerce_state, "free_delivery")
        self.assertEqual(
            result.conversation_state.next_recommended_action,
            "deliver_free_asset",
        )

    def test_free_delivery_decision_tracks_free_asset(self):
        service = self.build_service(FakeDecisionEngine(engine_result()))

        decision = service.build_delivery_decision(
            engine_result(
                delivery_action="deliver_free_asset",
                offer={
                    "offer_type": "free_asset",
                    "content": {
                        "asset_id": "asset-free",
                        "product_id": "free-product",
                        "delivery_type": "FREE",
                        "delivery_permission_mode": "included",
                        "delivery_requires_payment": False,
                    },
                },
            )
        )

        self.assertEqual(decision.current_product_id, "free-product")
        self.assertEqual(decision.delivery_method, "free_asset")
        self.assertEqual(decision.free_asset_id, "asset-free")
        self.assertEqual(decision.next_suggested_action, "deliver_free_asset")

    def test_free_asset_delivery_payload_resolves_local_vault_path(self):
        asset_service = FakeAssetService()
        service = self.build_service(
            FakeDecisionEngine(engine_result()),
            asset_service=asset_service,
        )
        decision = service.build_delivery_decision(
            engine_result(
                delivery_action="deliver_free_asset",
                offer={
                    "offer_type": "free_asset",
                    "content": {
                        "asset_id": "asset-free",
                        "product_id": "free-product",
                        "delivery_type": "FREE",
                        "delivery_permission_mode": "included",
                        "delivery_requires_payment": False,
                    },
                },
            )
        )

        payload = service.build_telegram_delivery_payload(
            engine_result=engine_result(),
            delivery_decision=decision,
            conversation_state=service.load_conversation_state("7:-123456789"),
            experience_progression=service.load_experience_progression(
                "7:-123456789"
            ),
        )

        self.assertEqual(payload.delivery_method, "free_asset")
        self.assertEqual(payload.asset_path, "C:/vault/asset-free.jpg")
        self.assertEqual(payload.product_reference, "free-product")
        self.assertEqual(payload.next_suggested_action, "deliver_free_asset")

    def test_paid_media_link_delivery_payload_uses_publishing_link(self):
        service = self.build_service(
            FakeDecisionEngine(engine_result()),
            cms_contract_service=FakeCMSContractService(),
            publishing_service=FakePublishingService(),
        )
        decision = service.build_delivery_decision(
            engine_result(
                delivery_action="deliver_paid_media_link",
                product_status="ACTIVE",
                offer={
                    "offer_type": "premium",
                    "content": {
                        "product_id": "paid-product",
                        "delivery_type": "PAID",
                        "delivery_permission_mode": "paid",
                        "delivery_requires_payment": True,
                    },
                },
            )
        )

        payload = service.build_telegram_delivery_payload(
            engine_result=engine_result(product_status="ACTIVE"),
            delivery_decision=decision,
            conversation_state=service.load_conversation_state("7:-123456789"),
            experience_progression=service.load_experience_progression(
                "7:-123456789"
            ),
        )

        self.assertEqual(payload.delivery_method, "paid_media_link")
        self.assertEqual(
            payload.media_link,
            "https://fanvue.example/media/recommended-product",
        )
        self.assertEqual(payload.next_suggested_action, "deliver_paid_media_link")

    def test_text_only_and_delay_delivery_payloads_do_not_attach_media(self):
        service = self.build_service(FakeDecisionEngine(engine_result()))
        conversation = service.load_conversation_state("7:-123456789")
        progression = service.load_experience_progression("7:-123456789")

        text_payload = service.build_telegram_delivery_payload(
            engine_result=engine_result(delivery_action="continue_experience"),
            delivery_decision=service.build_delivery_decision(
                engine_result(delivery_action="continue_experience")
            ),
            conversation_state=conversation,
            experience_progression=progression,
        )
        delay_payload = service.build_telegram_delivery_payload(
            engine_result=engine_result(delivery_action="delay_offer"),
            delivery_decision=service.build_delivery_decision(
                engine_result(delivery_action="delay_offer")
            ),
            conversation_state=conversation,
            experience_progression=progression,
        )

        self.assertEqual(text_payload.delivery_method, "offer")
        self.assertIsNone(text_payload.asset_path)
        self.assertEqual(delay_payload.delivery_method, "none")
        self.assertIsNone(delay_payload.media_link)

    def test_blocked_media_link_and_inactive_product_payloads(self):
        service = self.build_service(FakeDecisionEngine(engine_result()))
        conversation = service.load_conversation_state("7:-123456789")
        progression = service.load_experience_progression("7:-123456789")

        missing_link_payload = service.build_telegram_delivery_payload(
            engine_result=engine_result(delivery_action="deliver_paid_media_link"),
            delivery_decision=TelegramDeliveryDecision(
                offer_authorized=True,
                blocked=False,
                current_product_id="paid-product",
                delivery_type="PAID",
                delivery_method="paid_media_link",
                requires_payment=True,
                next_suggested_action="deliver_paid_media_link",
            ),
            conversation_state=conversation,
            experience_progression=progression,
        )
        inactive_payload = service.build_telegram_delivery_payload(
            engine_result=engine_result(
                delivery_action="deliver_paid_media_link",
                product_status="DRAFT",
            ),
            delivery_decision=TelegramDeliveryDecision(
                offer_authorized=True,
                blocked=False,
                current_product_id="paid-product",
                delivery_type="PAID",
                delivery_method="paid_media_link",
                paid_media_link="https://fanvue.example/media/paid-product",
                requires_payment=True,
                next_suggested_action="deliver_paid_media_link",
            ),
            conversation_state=conversation,
            experience_progression=progression,
        )

        self.assertEqual(missing_link_payload.blocking_reason, "media_link_unavailable")
        self.assertEqual(inactive_payload.blocking_reason, "product_not_active")

    def test_delivery_guard_can_block_payload(self):
        service = self.build_service(
            FakeDecisionEngine(engine_result()),
            content_delivery_guard_service=BlockingGuardService(),
        )
        decision = service.build_delivery_decision(engine_result())
        payload = service.build_telegram_delivery_payload(
            engine_result=engine_result(),
            delivery_decision=decision,
            conversation_state=service.load_conversation_state("7:-123456789"),
            experience_progression=service.load_experience_progression(
                "7:-123456789"
            ),
        )

        self.assertEqual(payload.delivery_method, "blocked")
        self.assertEqual(payload.blocking_reason, "guard_blocked")

    def test_supported_delivery_actions_are_normalized(self):
        service = self.build_service(FakeDecisionEngine(engine_result()))
        actions = (
            "deliver_free_asset",
            "deliver_paid_media_link",
            "continue_experience",
            "delay_offer",
            "skip_delivery",
            "recommend_different_product",
            "escalate_commerce_offer",
        )

        for action in actions:
            with self.subTest(action=action):
                decision = service.build_delivery_decision(
                    engine_result(delivery_action=action)
                )
                self.assertEqual(decision.next_suggested_action, action)

    def test_service_source_does_not_own_products_or_telegram_transport(self):
        source = Path("app/services/telegram_commerce_service.py").read_text()

        self.assertNotIn("ProductRepository", source)
        self.assertNotIn("TelegramInboundAdapter", source)
        self.assertNotIn("TelegramBotApiSender", source)
        self.assertNotIn("TelethonUserTransport", source)

    def test_delivery_decision_model_is_provider_neutral(self):
        decision = TelegramDeliveryDecision(
            offer_authorized=True,
            blocked=False,
            delivery_type="PAID",
            delivery_mode="paid",
            requires_payment=True,
            current_product_id="product-1",
            delivery_method="paid_media_link",
            paid_media_link="https://fanvue.example/media/product-1",
            next_suggested_action="deliver_paid_media_link",
        )

        self.assertEqual(decision.delivery_type, "PAID")
        self.assertEqual(decision.current_product_id, "product-1")
        self.assertFalse(hasattr(decision, "fanvue_media_id"))

    def test_delivery_payload_model_is_provider_neutral(self):
        payload = TelegramDeliveryPayload(
            delivery_type="FREE",
            message_text="Here",
            asset_path="C:/vault/free.jpg",
            product_reference="product-1",
            experience_reference="experience-1",
            next_suggested_action="deliver_free_asset",
            delivery_method="free_asset",
        )

        self.assertEqual(payload.to_dict()["asset_path"], "C:/vault/free.jpg")
        self.assertFalse(hasattr(payload, "send_telegram_media"))

    def test_experience_progression_model_is_provider_neutral(self):
        progression = TelegramExperienceProgression(
            current_experience_id="experience-1",
            experience_state="active",
            current_story_position="scene-1",
            current_asset_position="asset-1",
            current_product_id="product-1",
            progress_percentage=50,
            next_recommended_experience_action="continue_experience",
        )

        self.assertEqual(progression.progress_percentage, 50)
        self.assertFalse(hasattr(progression, "experience_repository"))


if __name__ == "__main__":
    unittest.main()
