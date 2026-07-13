import sys
import types
import unittest
from types import SimpleNamespace
from uuid import uuid4

fake_psycopg = types.ModuleType("psycopg")
fake_psycopg_types = types.ModuleType("psycopg.types")
fake_psycopg_json = types.ModuleType("psycopg.types.json")
fake_psycopg_rows = types.ModuleType("psycopg.rows")
fake_psycopg.connect = lambda *args, **kwargs: None
fake_psycopg_json.Json = lambda value: value
fake_psycopg_json.Jsonb = lambda value: value
fake_psycopg_rows.dict_row = object()
sys.modules.setdefault("psycopg", fake_psycopg)
sys.modules.setdefault("psycopg.types", fake_psycopg_types)
sys.modules.setdefault("psycopg.types.json", fake_psycopg_json)
sys.modules.setdefault("psycopg.rows", fake_psycopg_rows)

from app.engine.decision_engine import DecisionEngine
from app.models.chat_commerce_registration import ChatInventoryCandidate
from app.models.content_recommendation import RecommendationRequest
from app.services.content_recommendation_service import ContentRecommendationService


def candidate(asset_id, *, product_ids=(), experience_ids=()):
    return ChatInventoryCandidate(
        asset_id=asset_id,
        chat_registration_id=uuid4(),
        creator_profile_id=7,
        media_link=f"https://fanvue.example/media/{asset_id}",
        provider_media_id=f"media-{asset_id}",
        product_ids=tuple(product_ids),
        experience_ids=tuple(experience_ids),
    )


class FakeChatInventory:
    def __init__(self, candidates=(), suppressed=()):
        self.candidates = tuple(candidates)
        self.suppressed = {int(value) for value in suppressed}

    def get_recommendation_candidates(self, **kwargs):
        return self.candidates

    def eligibility_for_asset(self, asset_id, *, customer_context=None):
        asset_id = int(asset_id)
        blocked = asset_id in self.suppressed
        return SimpleNamespace(
            recommendation_eligible=not blocked,
            block_reasons=("not_chat_ready",) if blocked else (),
        )


class FakeContentIntelligence:
    def __init__(self, profiles):
        self.profiles = profiles

    def get_asset_intelligence(self, asset_id):
        return self.profiles.get(int(asset_id))


def profile(*, themes=(), keywords=(), confidence=0.9):
    return SimpleNamespace(
        confidence=confidence,
        themes=tuple(themes),
        tags=tuple(themes),
        keywords=tuple(keywords),
        mood=None,
        setting=None,
        activity=None,
        outfit=None,
        objects=(),
        environment=None,
        activities=(),
        clothing=None,
        classification="photo",
        technical_quality={"has_runtime_media": True},
    )


class ContentRecommendationServiceTests(unittest.TestCase):
    def make_service(self, candidates, profiles, suppressed=()):
        return ContentRecommendationService(
            chat_commerce_inventory_service=FakeChatInventory(
                candidates,
                suppressed=suppressed,
            ),
            content_intelligence_service=FakeContentIntelligence(profiles),
        )

    def test_ranking_returns_highest_scored_chat_ready_asset_first(self):
        service = self.make_service(
            (candidate(101), candidate(202)),
            {
                101: profile(themes=("beach",), confidence=0.4),
                202: profile(themes=("gym",), confidence=0.95),
            },
        )

        result = service.recommend(
            RecommendationRequest(
                creator_profile_id=7,
                customer_context={"preferred_content_theme": "gym"},
                limit=2,
            )
        )

        self.assertEqual(result.ranked_assets[0].asset_id, 202)
        self.assertGreater(result.ranked_assets[0].score.total, result.ranked_assets[1].score.total)
        self.assertFalse(result.ranked_assets[0].suppressed)

    def test_customer_fit_changes_ranking(self):
        service = self.make_service(
            (candidate(101), candidate(202)),
            {
                101: profile(themes=("beach",), keywords=("ocean",)),
                202: profile(themes=("gym",), keywords=("workout",)),
            },
        )

        result = service.recommend(
            RecommendationRequest(
                customer_context={"interests": ("workout",)},
                conversation_context={"message_text": "I want workout photos"},
                limit=2,
            )
        )

        self.assertEqual(result.ranked_assets[0].asset_id, 202)
        self.assertIn("Customer fit increased ranking.", result.customer_rationale)

    def test_business_learning_changes_ranking(self):
        service = self.make_service(
            (candidate(101), candidate(202)),
            {
                101: profile(themes=("beach",)),
                202: profile(themes=("gym",)),
            },
        )

        result = service.recommend(
            RecommendationRequest(
                business_context={"asset_scores": {"101": 25, "202": 0}},
                limit=2,
            )
        )

        self.assertEqual(result.ranked_assets[0].asset_id, 101)
        self.assertIn("Business evidence increased ranking.", result.business_rationale)

    def test_suppression_keeps_candidate_out_of_ranked_assets(self):
        service = self.make_service(
            (candidate(101), candidate(202)),
            {
                101: profile(themes=("beach",), confidence=1.0),
                202: profile(themes=("gym",), confidence=0.5),
            },
            suppressed=(101,),
        )

        result = service.recommend(RecommendationRequest(limit=2))

        self.assertEqual(tuple(item.asset_id for item in result.ranked_assets), (202,))
        self.assertEqual(result.rejected_candidates[0].asset_id, 101)
        self.assertIn("not_chat_ready", result.rejected_candidates[0].suppression_reasons)

    def test_ownership_suppresses_candidate(self):
        service = self.make_service(
            (candidate(101),),
            {101: profile(themes=("vip",))},
        )

        result = service.recommend(
            RecommendationRequest(
                customer_context={"owned_content_tags": ("chat_asset_101",)}
            )
        )

        self.assertEqual(result.ranked_assets, ())
        self.assertEqual(result.rejected_candidates[0].asset_id, 101)
        self.assertIn(
            "customer_already_owns_asset",
            result.rejected_candidates[0].suppression_reasons,
        )

    def test_non_chat_ready_assets_never_rank(self):
        service = self.make_service(
            (candidate(101),),
            {101: profile(themes=("vip",))},
            suppressed=(101,),
        )

        result = service.recommend(RecommendationRequest())

        self.assertEqual(result.ranked_assets, ())
        self.assertEqual(result.rejected_candidates[0].asset_id, 101)

    def test_decision_engine_consumes_ranked_result(self):
        class Logger:
            def info(self, message):
                pass

        class Settings:
            DEFAULT_PERSONA = "ava"

        class ProductRecommendations:
            last_offer_candidate_contract = None

            def __init__(self):
                self.called = False

            def get_content(self, offer_type, persona, working_memory):
                self.called = True
                return {"source": "product_recommendation_service"}

        engine = object.__new__(DecisionEngine)
        engine.logger = Logger()
        engine.settings = Settings()
        engine.cms_contract_service = SimpleNamespace(
            build_customer_progress=lambda *args, **kwargs: {"customer": "progress"}
        )
        engine.product_recommendation_service = ProductRecommendations()
        engine.chat_commerce_inventory_service = None
        engine.chat_commerce_delivery_service = SimpleNamespace(
            prepare_delivery=lambda request: SimpleNamespace(
                success=True,
                failure_reason=None,
                to_context=lambda: {
                    "delivery_id": "delivery-202",
                    "success": True,
                    "validation": {"failures": []},
                    "payload": {
                        "delivery_id": "delivery-202",
                        "asset_id": 202,
                        "product_id": "product-202",
                        "experience_id": None,
                        "media_link": "https://fanvue.example/media/202",
                        "provider_media_id": "media-202",
                        "recommendation_id": "rec-202",
                        "fulfillment_id": "fulfillment-202",
                        "delivery_type": "PAID",
                        "delivery_method": "paid_media_link",
                        "delivery_ready": True,
                    },
                },
            )
        )
        engine.content_recommendation_service = self.make_service(
            (candidate(101), candidate(202)),
            {
                101: profile(themes=("beach",)),
                202: profile(themes=("gym",)),
            },
        )

        payload = engine._select_cms_content(
            "vip_offer",
            {"creator_profile_id": 7, "preferred_content_theme": "gym"},
        )

        self.assertEqual(payload["source"], "content_recommendation_engine")
        self.assertEqual(payload["asset_id"], 202)
        self.assertTrue(payload["delivery_prepared"])
        self.assertEqual(payload["chat_delivery_payload"]["delivery_id"], "delivery-202")
        self.assertFalse(engine.product_recommendation_service.called)

    def test_decision_engine_preserves_product_fallback(self):
        class Logger:
            def info(self, message):
                pass

        class Settings:
            DEFAULT_PERSONA = "ava"

        class EmptyRecommendation:
            def recommend(self, request):
                return SimpleNamespace(top_candidate=None)

        class ProductRecommendations:
            last_offer_candidate_contract = None

            def get_content(self, offer_type, persona, working_memory):
                return {"source": "product_recommendation_service"}

        engine = object.__new__(DecisionEngine)
        engine.logger = Logger()
        engine.settings = Settings()
        engine.cms_contract_service = SimpleNamespace(
            build_customer_progress=lambda *args, **kwargs: {"customer": "progress"}
        )
        engine.product_recommendation_service = ProductRecommendations()
        engine.chat_commerce_inventory_service = None
        engine.content_recommendation_service = EmptyRecommendation()

        payload = engine._select_cms_content("vip_offer", {"creator_profile_id": 7})

        self.assertEqual(payload["source"], "product_recommendation_service")


if __name__ == "__main__":
    unittest.main()
