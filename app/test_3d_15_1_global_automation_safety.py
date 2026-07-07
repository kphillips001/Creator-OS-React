import os

from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)


def set_env(values):
    for key, value in values.items():
        os.environ[key] = value


def run_test():
    print("\n==============================")
    print("3D.15.1 GLOBAL AUTOMATION SAFETY TEST")
    print("==============================\n")

    service = GlobalAutomationSafetyService()

    # CASE 1 — Master OFF blocks everything
    set_env({
        "GLOBAL_AUTOMATION_ENABLED": "false",
        "GLOBAL_SENDS_ENABLED": "true",
        "CHAT_AUTOMATION_ENABLED": "true",
        "ENABLE_REALTIME_FANVUE_SEND": "true",
    })

    result = service.can_send_chat()
    print("Master OFF result:", result)

    assert result["allowed"] is False
    assert result["reason"] == "global_automation_disabled"

    # CASE 2 — Sends OFF blocks everything
    set_env({
        "GLOBAL_AUTOMATION_ENABLED": "true",
        "GLOBAL_SENDS_ENABLED": "false",
        "CHAT_AUTOMATION_ENABLED": "true",
        "ENABLE_REALTIME_FANVUE_SEND": "true",
    })

    result = service.can_send_chat()
    print("Sends OFF result:", result)

    assert result["allowed"] is False
    assert result["reason"] == "global_sends_disabled"

    # CASE 3 — Master ON, chat OFF blocks chat only
    set_env({
        "GLOBAL_AUTOMATION_ENABLED": "true",
        "GLOBAL_SENDS_ENABLED": "true",
        "MANUAL_PAUSE_ENABLED": "false",
        "CHAT_AUTOMATION_ENABLED": "false",
        "ENABLE_REALTIME_FANVUE_SEND": "true",
    })

    result = service.can_send_chat()
    print("Chat OFF result:", result)

    assert result["allowed"] is False
    assert result["reason"] == "chat_automation_disabled"

    # CASE 4 — Master ON, chat ON allows chat
    set_env({
        "GLOBAL_AUTOMATION_ENABLED": "true",
        "GLOBAL_SENDS_ENABLED": "true",
        "MANUAL_PAUSE_ENABLED": "false",
        "CHAT_AUTOMATION_ENABLED": "true",
        "ENABLE_REALTIME_FANVUE_SEND": "true",
    })

    result = service.can_send_chat()
    print("Chat ON result:", result)

    assert result["allowed"] is True

    # CASE 5 — Post-purchase can be independently enabled
    set_env({
        "GLOBAL_AUTOMATION_ENABLED": "true",
        "GLOBAL_SENDS_ENABLED": "true",
        "MANUAL_PAUSE_ENABLED": "false",
        "POST_PURCHASE_REACTIONS_ENABLED": "true",
        "ENABLE_REALTIME_MONETIZATION_REACTIONS": "true",
        "ENABLE_POST_PURCHASE_AUTOMATION": "true",
    })

    result = service.can_send_post_purchase_reaction()
    print("Post-purchase ON result:", result)

    assert result["allowed"] is True

    print("\n✅ 3D.15.1 PASSED")


if __name__ == "__main__":
    run_test()