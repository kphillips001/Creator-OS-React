import inspect

from app.engine.decision_engine import DecisionEngine


def run_test():
    print("\n==============================")
    print(" 3D.16.4 OWNERSHIP SUPPRESSION")
    print("==============================\n")

    source = inspect.getsource(DecisionEngine)

    checks = {
        "ContentOwnershipService imported/used":
            "ContentOwnershipService" in source,

        "ownership service initialized":
            "self.content_ownership_service = ContentOwnershipService()" in source,

        "ownership check exists":
            "user_already_owns_content" in source,

        "ownership block flag exists":
            "ownership_blocked" in source,

        "ownership blocked tag exists":
            "ownership_blocked_tag" in source,

        "ownership-safe duplicate check":
            "if already_seen and not already_owned" in source,
    }

    for label, passed in checks.items():
        print(f"{label}: {'✅ PASS' if passed else '❌ FAIL'}")
        assert passed, label

    print("\n✅ 3D.16.4 TEST COMPLETE")
    print("DecisionEngine ownership suppression wiring is present.")


if __name__ == "__main__":
    run_test()