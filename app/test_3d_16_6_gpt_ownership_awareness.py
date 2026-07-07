import inspect

from app.services.gpt_service import GPTService


def run_test():
    print("\n==============================")
    print(" 3D.16.6 GPT OWNERSHIP AWARENESS")
    print("==============================\n")

    source = inspect.getsource(GPTService)

    checks = {
        "ContentOwnershipService imported/used":
            "ContentOwnershipService" in source,

        "ownership service initialized":
            "self.content_ownership_service" in source,

        "recent owned tags supported":
            "recent_owned_content_tags" in source,

        "ownership GPT context exists":
            "ownership_gpt_context" in source,

        "ownership section injected":
            "CONTENT OWNERSHIP CONTEXT" in source,

        "resell prevention rule exists":
            "Never try to resell already-owned content" in source,
    }

    for label, passed in checks.items():
        print(f"{label}: {'✅ PASS' if passed else '❌ FAIL'}")
        assert passed, label

    print("\n✅ 3D.16.6 TEST COMPLETE")
    print("GPT ownership-awareness layer is wired.")


if __name__ == "__main__":
    run_test()