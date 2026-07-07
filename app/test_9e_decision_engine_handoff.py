from app.main import decision_engine


def run_test():
    user_id = "2:4"  # Use a REAL existing user

    print("\n========================================")
    print("9E TEST — DecisionEngine Outreach Handoff")
    print("========================================\n")

    # Step 1 — Set user into outreach-sent state
    decision_engine.memory.update_user_memory(
        user_id,
        {
            "outreach_status": "sent",
            "outreach_response_count": 0,
            "current_route": "outreach",
            "last_route": "outreach",  # IMPORTANT: helps trigger 9E reliably
        },
    )

    # 🔍 Step 2 — VERIFY memory actually saved
    setup_memory = decision_engine.memory.get_user_memory(user_id)

    print("Setup memory check:")
    print("outreach_status:", setup_memory.get("outreach_status"))
    print("outreach_response_count:", setup_memory.get("outreach_response_count"))
    print("current_route:", setup_memory.get("current_route"))
    print("last_route:", setup_memory.get("last_route"))
    print("----------------------------------------")

    # Step 3 — Process inbound message (should trigger handoff)
    result = decision_engine.process_message(
        user_id=user_id,
        message="hey there",
        chat_history=[],
    )

    updated_memory = decision_engine.memory.get_user_memory(user_id)

    print("\nResult response:")
    print(result.get("response"))

    print("\nUpdated outreach fields:")
    print("outreach_status:", updated_memory.get("outreach_status"))
    print("outreach_response_count:", updated_memory.get("outreach_response_count"))
    print("current_route:", updated_memory.get("current_route"))
    print("last_route:", updated_memory.get("last_route"))

    passed = (
        updated_memory.get("outreach_status") == "engaged"
        and updated_memory.get("outreach_response_count") == 1
    )

    print("\nRESULT:", "✅ PASS" if passed else "❌ FAIL")


if __name__ == "__main__":
    run_test()