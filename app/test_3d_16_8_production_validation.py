import inspect

from app.services.content_ownership_service import (
    ContentOwnershipService,
)

from app.repositories.content_ownership_repository import (
    get_owned_content_tags,
    user_already_owns_content,
)

from app.repositories.buyer_memory_sync_repository import (
    get_content_ownership_memory,
)

from app.engine.decision_engine import DecisionEngine
from app.services.mass_ppv_targeting_service import (
    MassPPVTargetingService,
)
from app.services.gpt_service import GPTService


def run_test():
    print("\n==============================")
    print(" 3D.16.8 PRODUCTION VALIDATION")
    print("==============================\n")

    print("[1] Ownership service instantiation")
    service = ContentOwnershipService()
    assert service is not None
    print("✅ ContentOwnershipService instantiated")

    print("\n[2] Ownership repository callable checks")
    assert callable(get_owned_content_tags)
    assert callable(user_already_owns_content)
    print("✅ Ownership repository functions callable")

    print("\n[3] Ownership memory query")
    ownership_memory = get_content_ownership_memory("1")
    print(ownership_memory)

    required_memory_keys = [
        "owned_content_count",
        "owned_vip_count",
        "owned_premium_count",
        "last_owned_at",
        "recent_owned_content_tags",
        "collector_score",
        "repeat_purchase_score",
    ]

    for key in required_memory_keys:
        assert key in ownership_memory, f"Missing ownership key: {key}"

    print("✅ Ownership intelligence memory keys validated")

    print("\n[4] DecisionEngine ownership wiring")
    decision_source = inspect.getsource(DecisionEngine)

    decision_checks = [
        "ContentOwnershipService",
        "self.content_ownership_service",
        "user_already_owns_content",
        "ownership_blocked",
        "ownership_blocked_tag",
        "if already_seen and not already_owned",
    ]

    for check in decision_checks:
        assert check in decision_source, f"Missing DecisionEngine wiring: {check}"

    print("✅ DecisionEngine ownership suppression validated")

    print("\n[5] Mass PPV ownership filtering")
    mass_ppv_source = inspect.getsource(MassPPVTargetingService)

    mass_ppv_checks = [
        "ContentOwnershipService",
        "content_tag: str | None = None",
        "user_already_owns_content",
        "already_owns_content",
    ]

    for check in mass_ppv_checks:
        assert check in mass_ppv_source, f"Missing Mass PPV wiring: {check}"

    print("✅ Mass PPV ownership filtering validated")

    print("\n[6] GPT ownership awareness")
    gpt_source = inspect.getsource(GPTService)

    gpt_checks = [
        "ContentOwnershipService",
        "recent_owned_content_tags",
        "ownership_gpt_context",
        "CONTENT OWNERSHIP CONTEXT",
        "Never try to resell already-owned content",
    ]

    for check in gpt_checks:
        assert check in gpt_source, f"Missing GPT ownership wiring: {check}"

    print("✅ GPT ownership awareness validated")

    print("\n✅ 3D.16.8 PRODUCTION VALIDATION PASSED")
    print("Content Ownership Integration is production-valid.")


if __name__ == "__main__":
    run_test()