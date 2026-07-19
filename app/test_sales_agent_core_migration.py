"""Controlled certification tests for the migrated Sales Agent core.

These tests construct local services only. They do not start a transport, worker,
provider client, or external send path.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.engine.decision_engine import DecisionEngine
from app.main import create_decision_engine
from app.models.asset_provenance import ASSET_PROVENANCE_METADATA_KEY
from app.models.content_recommendation import RecommendationRequest
from app.services.autonomous_commerce_entry_policy import AutonomousCommerceEntryPolicy
from app.services.content_recommendation_service import ContentRecommendationService
from app.services.conversation_gateway import ConversationGateway
from app.services.global_automation_safety_service import GlobalAutomationSafetyService


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_sales_agent_core_imports_and_constructs_from_local_dependencies():
    with patch(
        "app.main.get_gpt_service",
        return_value=SimpleNamespace(generate_response=lambda *_args, **_kwargs: "offline"),
    ):
        engine = create_decision_engine()

    assert isinstance(engine, DecisionEngine)
    assert Path(type(engine).__module__.replace(".", "/") + ".py").as_posix() == "app/engine/decision_engine.py"
    assert ConversationGateway.__module__ == "app.services.conversation_gateway"


def test_core_module_origins_and_source_have_no_legacy_runtime_reference():
    modules = (DecisionEngine, ConversationGateway)
    for value in modules:
        module = __import__(value.__module__, fromlist=[value.__name__])
        module_path = Path(module.__file__).resolve()
        assert module_path.is_relative_to(REPOSITORY_ROOT)

    source_roots = (REPOSITORY_ROOT / "app" / "engine", REPOSITORY_ROOT / "app" / "services")
    forbidden = "c:" + "\\creator-os" + "\\"
    for source_root in source_roots:
        for path in source_root.glob("*.py"):
            assert forbidden not in path.read_text(encoding="utf-8-sig").lower()


def test_global_send_paths_remain_disabled_in_controlled_runtime(tmp_path):
    with (
        patch.object(GlobalAutomationSafetyService, "CONFIG_PATH", tmp_path / "missing.json"),
        patch.dict(
            "os.environ",
            {
                "GLOBAL_AUTOMATION_ENABLED": "false",
                "GLOBAL_SENDS_ENABLED": "false",
                "ENABLE_REALTIME_FANVUE_SEND": "false",
                "ENABLE_MASS_PPV_SENDS": "false",
                "ENABLE_REALTIME_MONETIZATION_REACTIONS": "false",
            },
            clear=False,
        ),
    ):
        safety = GlobalAutomationSafetyService()

    assert safety.can_send_chat()["allowed"] is False
    assert safety.can_send_mass_ppv()["allowed"] is False
    assert safety.can_send_post_purchase_reaction()["allowed"] is False


def test_reference_and_temporary_assets_cannot_enter_autonomous_commerce():
    policy = AutonomousCommerceEntryPolicy()
    unsafe_assets = (
        SimpleNamespace(
            id=91,
            status="approved",
            media_metadata={"reference_library": {"is_reference": True, "canonical": True}},
        ),
        SimpleNamespace(id=92, status="pending_edit", media_metadata={}),
        SimpleNamespace(id=93, status="pending_photoshoot", media_metadata={}),
        SimpleNamespace(id=94, status="removed", media_metadata={}),
    )

    for asset in unsafe_assets:
        decision = policy.can_register_commerce(asset)
        assert decision.allowed is False
        assert (
            "creator_approval_provenance_required" in decision.reasons
            or "asset_not_approved" in decision.reasons
        )


class _RegisteredInventoryOnly:
    def __init__(self, candidates=()):
        self.candidates = tuple(candidates)

    def get_recommendation_candidates(self, **_kwargs):
        return self.candidates

    def eligibility_for_asset(self, asset_id, *, customer_context=None):
        return SimpleNamespace(recommendation_eligible=True, block_reasons=())


def test_unregistered_generation_media_is_not_a_recommendation_source():
    service = ContentRecommendationService(
        chat_commerce_inventory_service=_RegisteredInventoryOnly(),
    )

    result = service.recommend(
        RecommendationRequest(
            creator_profile_id=7,
            customer_context={"generation_image_id": "unregistered-image"},
        )
    )

    assert result.ranked_assets == ()
    assert result.rejected_candidates == ()


def test_creator_approved_asset_still_requires_intelligence_before_commerce():
    asset = SimpleNamespace(
        id=101,
        status="approved",
        media_metadata={
            ASSET_PROVENANCE_METADATA_KEY: {
                "classification": "CREATOR_APPROVAL",
                "source": "asset_registration",
            },
            "creator_approval": {"approved_by": "creator", "approved_at": "2026-07-18T00:00:00Z"},
        },
    )
    decision = AutonomousCommerceEntryPolicy().can_register_commerce(asset)

    assert decision.allowed is False
    assert "content_intelligence_profile_required" in decision.reasons
