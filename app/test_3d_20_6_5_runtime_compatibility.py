import runpy


def run_test():
    print("\n=== 3D.20.6.5 RUNTIME COMPATIBILITY VALIDATION ===\n")

    print("\n--- 1. Dependency DecisionEngine Injection ---")
    runpy.run_module(
        "app.test_3d_20_6_2_decision_engine_dependency_injection",
        run_name="__main__",
    )

    print("\n--- 2. Whale Burnout Compatibility ---")
    runpy.run_module(
        "app.test_3d_20_5_whale_burnout_prevention",
        run_name="__main__",
    )

    print("\n--- 3. Premium Continuity Compatibility ---")
    runpy.run_module(
        "app.test_3d_20_4_premium_conversation_continuity",
        run_name="__main__",
    )

    print("\n--- 4. Emotional Presence Compatibility ---")
    runpy.run_module(
        "app.test_3d_20_3_emotional_presence_refinement",
        run_name="__main__",
    )

    print("\n=== 3D.20.6.5 RUNTIME COMPATIBILITY COMPLETE ===\n")


if __name__ == "__main__":
    run_test()