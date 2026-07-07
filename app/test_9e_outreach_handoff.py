from app.services.outreach_service import OutreachService


def run_test():
    service = OutreachService()

    user_memory = {
        "fanvue_user_id": 501,
        "username": "handoff_test_user",
        "outreach_status": "sent",
        "outreach_response_count": 1,
        "current_route": "outreach",
        "last_route": "none",
    }

    print("\n========================================")
    print("9E TEST — Outreach → Monetization Handoff")
    print("========================================\n")

    updates = service.handle_outreach_response(user_memory)

    expected = {
        "outreach_status": "engaged",
        "outreach_response_count": 2,
        "last_outreach_response_at": "NOW()",
        "current_route": "chat",
        "last_route": "outreach",
    }

    passed = updates == expected

    print("Updates:")
    print(updates)
    print("\nExpected:")
    print(expected)
    print("\nRESULT:", "✅ PASS" if passed else "❌ FAIL")


if __name__ == "__main__":
    run_test()