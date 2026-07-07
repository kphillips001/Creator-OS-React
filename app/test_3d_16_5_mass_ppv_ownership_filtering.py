import inspect

from app.services.mass_ppv_targeting_service import (
    MassPPVTargetingService,
)


def run_test():
    print("\n==============================")
    print(" 3D.16.5 MASS PPV OWNERSHIP FILTERING")
    print("==============================\n")

    source = inspect.getsource(MassPPVTargetingService)

    checks = {
        "ContentOwnershipService imported/used":
            "ContentOwnershipService" in source,

        "ownership service initialized":
            "self.content_ownership_service" in source,

        "content_tag parameter exists":
            "content_tag: str | None = None" in source,

        "ownership check exists":
            "user_already_owns_content" in source,

        "already owns block reason exists":
            "already_owns_content" in source,

        "ownership block log exists":
            "[MASS PPV BLOCK] already owns content" in source,
    }

    for label, passed in checks.items():
        print(f"{label}: {'✅ PASS' if passed else '❌ FAIL'}")
        assert passed, label

    print("\n✅ 3D.16.5 TEST COMPLETE")
    print("Mass PPV targeting ownership filtering is wired.")


if __name__ == "__main__":
    run_test()