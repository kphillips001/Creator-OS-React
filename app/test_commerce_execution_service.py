import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.commerce_execution import (
    CommerceExecutionRequest,
    RuntimeExecutionPayload,
    RuntimeExecutionAction,
)
from app.services.commerce_execution_service import CommerceExecutionService


class FakeRuntimeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, payload, *, context=None):
        self.calls.append({"payload": payload, "context": dict(context or {})})
        return SimpleNamespace(
            status="success",
            executed=True,
            metadata={"execution_state": "delegated_to_fake_runtime"},
        )


class FailingRuntimeExecutor:
    def execute(self, payload, *, context=None):
        return SimpleNamespace(
            status="failed",
            executed=False,
            metadata={
                "execution_state": "failed_runtime_execution",
                "error_type": "provider_timeout",
            },
        )


class CommerceExecutionServiceTests(unittest.TestCase):
    def test_execute_delegates_payload_to_runtime_boundary(self):
        executor = FakeRuntimeExecutor()
        request = CommerceExecutionRequest(
            execution_decision={"action": "deliver_text"},
            execution_payload={"message_text": "hello"},
            provider="telegram",
            delivery_type="PAID",
            product_strategy_context=SimpleNamespace(),
            commerce_strategy_context=SimpleNamespace(),
            publishing_outputs={"media_link": "https://example.test/media"},
            runtime_context={"correlation_id": "turn-1"},
        )

        result = CommerceExecutionService().execute(
            request,
            runtime_executor=executor,
        )

        self.assertEqual(result.status, "success")
        self.assertTrue(result.executed)
        self.assertEqual(result.execution_state, "delegated_to_fake_runtime")
        self.assertEqual(
            executor.calls,
            [
                {
                    "payload": result.runtime_intent,
                    "context": {"correlation_id": "turn-1"},
                }
            ],
        )
        self.assertEqual(result.metadata["owner"], "CommerceExecutionService")
        self.assertTrue(result.metadata["delegated_to_runtime"])
        self.assertFalse(result.metadata["generates_runtime_decisions"])
        self.assertFalse(result.metadata["calls_provider_apis_directly"])
        self.assertFalse(result.metadata["modifies_publishing"])
        self.assertFalse(result.metadata["creates_products"])
        self.assertFalse(result.metadata["creates_product_drafts"])
        self.assertTrue(result.recommendations)
        self.assertEqual(
            result.execution_plan.execution_type,
            "execute_paid_product",
        )
        self.assertEqual(
            result.execution_plan.business_intent,
            "Execute PAID Product",
        )
        self.assertFalse(result.execution_plan.metadata["telegram_action"])
        self.assertEqual(
            result.runtime_intent.actions,
            (
                RuntimeExecutionAction.DELIVER_MEDIA_LINK,
                RuntimeExecutionAction.PRESENT_CALL_TO_ACTION,
                RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            ),
        )
        self.assertFalse(result.runtime_intent.metadata["telegram_specific"])
        self.assertIsInstance(result.runtime_intent.payload, RuntimeExecutionPayload)
        self.assertEqual(result.runtime_intent.payload.message_text, "hello")
        self.assertEqual(result.runtime_result.status, "success")
        self.assertTrue(result.runtime_result.executed)

    def test_prepare_runtime_intent_builds_typed_payload_from_plan(self):
        result = CommerceExecutionService().execute(
            CommerceExecutionRequest(
                delivery_type="PAID",
                product_reference="product-typed",
                provider="telegram",
            )
        )

        self.assertIsInstance(result.runtime_intent.payload, RuntimeExecutionPayload)
        self.assertEqual(
            result.runtime_intent.payload.execution_type,
            "execute_paid_product",
        )
        self.assertEqual(
            result.runtime_intent.payload.product_reference,
            "product-typed",
        )

    def test_execute_defers_without_runtime_executor(self):
        result = CommerceExecutionService().execute(
            {
                "execution_decision": {"action": "deliver_later"},
                "execution_payload": {"message_text": "later"},
                "provider": "telegram",
            }
        )

        self.assertEqual(result.status, "deferred")
        self.assertFalse(result.executed)
        self.assertEqual(
            result.execution_state,
            "deferred_until_runtime_executor_available",
        )
        self.assertFalse(result.metadata["delegated_to_runtime"])
        self.assertEqual(result.runtime_result.status, "deferred")
        self.assertFalse(result.runtime_result.executed)

    def test_free_execution_plan_is_provider_neutral(self):
        result = CommerceExecutionService().execute(
            CommerceExecutionRequest(
                execution_decision={"delivery_type": "FREE"},
                execution_payload={"delivery_type": "FREE"},
                provider="telegram",
            )
        )

        self.assertEqual(result.execution_plan.execution_type, "execute_free_product")
        self.assertEqual(result.execution_plan.business_intent, "Execute FREE Product")
        self.assertFalse(result.execution_plan.requires_media_link)
        self.assertIn(
            "prepare_business_delivery_context",
            result.execution_plan.provider_neutral_steps,
        )
        self.assertFalse(result.execution_plan.metadata["telegram_action"])
        self.assertEqual(
            result.runtime_intent.actions,
            (
                RuntimeExecutionAction.DELIVER_MEDIA,
                RuntimeExecutionAction.CONTINUE_CONVERSATION,
            ),
        )

    def test_paid_execution_plan_requires_publishing_output(self):
        result = CommerceExecutionService().execute(
            CommerceExecutionRequest(
                delivery_type="PAID",
                provider="telegram",
                publishing_outputs={"media_link": "https://example.test/product"},
            )
        )

        self.assertEqual(result.execution_plan.execution_type, "execute_paid_product")
        self.assertEqual(result.execution_plan.business_intent, "Execute PAID Product")
        self.assertTrue(result.execution_plan.requires_media_link)
        self.assertIn(
            "require_publishing_output",
            result.execution_plan.provider_neutral_steps,
        )
        self.assertFalse(result.metadata["modifies_publishing"])
        self.assertEqual(
            result.runtime_intent.actions,
            (
                RuntimeExecutionAction.DELIVER_MEDIA_LINK,
                RuntimeExecutionAction.PRESENT_CALL_TO_ACTION,
                RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            ),
        )

    def test_bundle_execution_plan_is_business_intent_only(self):
        result = CommerceExecutionService().execute(
            {
                "delivery_type": "PAID",
                "product_type": "bundle",
                "product_reference": "product-bundle-1",
            }
        )

        self.assertEqual(
            result.execution_plan.execution_type,
            "execute_bundle_product",
        )
        self.assertEqual(
            result.execution_plan.business_intent,
            "Execute Bundle Product",
        )
        self.assertIn(
            "prepare_bundle_delivery_context",
            result.execution_plan.provider_neutral_steps,
        )
        self.assertEqual(
            result.execution_plan.metadata["product_reference"],
            "product-bundle-1",
        )
        self.assertIn(
            RuntimeExecutionAction.DELIVER_BUNDLE,
            result.runtime_intent.actions,
        )

    def test_album_execution_plan_supports_photo_and_video_sets(self):
        for product_type in ("PHOTO_SET", "VIDEO_SET"):
            with self.subTest(product_type=product_type):
                result = CommerceExecutionService().execute(
                    {
                        "delivery_type": "PAID",
                        "product_type": product_type,
                    }
                )

                self.assertEqual(
                    result.execution_plan.execution_type,
                    "execute_album_product",
                )
                self.assertEqual(
                    result.execution_plan.business_intent,
                    "Execute Album Product",
                )
                self.assertIn(
                    "prepare_album_delivery_context",
                    result.execution_plan.provider_neutral_steps,
                )
                self.assertIn(
                    RuntimeExecutionAction.DELIVER_ALBUM,
                    result.runtime_intent.actions,
                )

    def test_story_execution_plan_is_distinct_from_album_execution(self):
        result = CommerceExecutionService().execute(
            {
                "delivery_type": "PAID",
                "product_type": "STORY",
            }
        )

        self.assertEqual(result.execution_plan.execution_type, "execute_story_product")
        self.assertEqual(result.execution_plan.business_intent, "Execute Story Product")
        self.assertIn(
            "prepare_story_delivery_context",
            result.execution_plan.provider_neutral_steps,
        )
        self.assertFalse(result.execution_plan.metadata["runtime_specific"])
        self.assertIn(
            RuntimeExecutionAction.DELIVER_STORY_STEP,
            result.runtime_intent.actions,
        )
        self.assertIn(
            RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            result.runtime_intent.actions,
        )

    def test_prepare_runtime_intent_supports_call_to_action_and_follow_up(self):
        result = CommerceExecutionService().execute(
            {
                "delivery_type": "PAID",
                "product_type": "SINGLE_IMAGE",
                "provider": "telegram",
            }
        )

        self.assertIn(
            RuntimeExecutionAction.PRESENT_CALL_TO_ACTION,
            result.runtime_intent.actions,
        )
        self.assertIn(
            RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            result.runtime_intent.actions,
        )
        self.assertFalse(result.runtime_intent.metadata["runtime_specific"])
        self.assertFalse(result.runtime_intent.metadata["calls_provider_apis_directly"])

    def test_generic_runtime_intent_continues_conversation(self):
        result = CommerceExecutionService().execute(
            {
                "execution_decision": {"action": "continue"},
                "provider": "telegram",
            }
        )

        self.assertEqual(
            result.runtime_intent.actions,
            (
                RuntimeExecutionAction.CONTINUE_CONVERSATION,
                RuntimeExecutionAction.FOLLOW_UP_REQUIRED,
            ),
        )

    def test_execution_review_surfaces_plan_intent_result_and_diagnostics(self):
        service = CommerceExecutionService()
        result = service.execute(
            CommerceExecutionRequest(
                execution_decision={"action": "deliver_paid"},
                execution_payload={"message_text": "link"},
                provider="telegram",
                delivery_type="PAID",
                runtime_context={"correlation_id": "turn-review"},
            ),
            runtime_executor=FakeRuntimeExecutor(),
        )

        review = service.build_execution_review(
            result,
            reviewed_at="2026-07-04T00:00:00+00:00",
        )

        self.assertEqual(review.status, "success")
        self.assertTrue(review.executed)
        self.assertEqual(review.provider, "telegram")
        self.assertEqual(review.execution_type, "execute_paid_product")
        self.assertEqual(review.business_intent, "Execute PAID Product")
        self.assertEqual(review.runtime_executor, "FakeRuntimeExecutor")
        self.assertEqual(review.reviewed_at, "2026-07-04T00:00:00+00:00")
        self.assertEqual(review.plan["execution_type"], "execute_paid_product")
        self.assertEqual(
            review.runtime_intent["actions"],
            (
                "DELIVER_MEDIA_LINK",
                "PRESENT_CALL_TO_ACTION",
                "FOLLOW_UP_REQUIRED",
            ),
        )
        self.assertEqual(review.runtime_result["status"], "success")
        self.assertEqual(
            review.runtime_result["provider_metadata"]["execution_state"],
            "delegated_to_fake_runtime",
        )
        self.assertEqual(
            review.diagnostics["execution_owner"],
            "CommerceExecutionService",
        )
        self.assertEqual(review.diagnostics["review_owner"], "Execution Review")
        self.assertTrue(review.compatibility["read_only"])
        self.assertFalse(review.compatibility["calls_telegram"])
        self.assertFalse(review.compatibility["calls_publishing"])
        self.assertFalse(review.compatibility["modifies_decision_engine"])
        self.assertEqual(review.errors, ())

    def test_execution_review_surfaces_runtime_errors(self):
        service = CommerceExecutionService()
        result = service.execute(
            {
                "delivery_type": "PAID",
                "provider": "telegram",
            },
            runtime_executor=FailingRuntimeExecutor(),
        )

        review = service.build_execution_review(result)

        self.assertEqual(review.status, "failed")
        self.assertFalse(review.executed)
        self.assertIn("execution_status:failed", review.errors)
        self.assertIn("error_type:provider_timeout", review.errors)
        self.assertEqual(
            review.runtime_result["execution_state"],
            "failed_runtime_execution",
        )

    def test_execution_review_summary_is_workspace_ready(self):
        service = CommerceExecutionService()
        executed = service.execute(
            {
                "delivery_type": "FREE",
                "provider": "telegram",
            },
            runtime_executor=FakeRuntimeExecutor(),
        )
        deferred = service.execute(
            {
                "delivery_type": "PAID",
                "provider": "telegram",
            }
        )

        summary = service.build_execution_review_summary(
            [executed, deferred],
            reviewed_at="2026-07-04T00:00:00+00:00",
        )

        self.assertEqual(summary.total_executions, 2)
        self.assertEqual(summary.executed_count, 1)
        self.assertEqual(summary.deferred_count, 1)
        self.assertEqual(summary.failed_count, 0)
        self.assertEqual(summary.providers, ("telegram",))
        self.assertIn("DELIVER_MEDIA", summary.runtime_actions)
        self.assertIn("DELIVER_MEDIA_LINK", summary.runtime_actions)
        self.assertEqual(len(summary.items), 2)
        self.assertTrue(all(item.compatibility["read_only"] for item in summary.items))

    def test_service_imports_do_not_cross_ownership_boundaries(self):
        path = Path("app/services/commerce_execution_service.py")
        tree = ast.parse(path.read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        forbidden_fragments = (
            "telegram",
            "decision_engine",
            "publishing",
            "product_catalog",
            "ai_product_drafting",
            "product_strategy_service",
            "commerce_strategy_service",
            "product_repository",
        )
        for module in imports:
            with self.subTest(module=module):
                self.assertFalse(
                    any(fragment in module for fragment in forbidden_fragments)
                )


if __name__ == "__main__":
    unittest.main()
