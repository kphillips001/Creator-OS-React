from app.services.automated_reaction_type_router_service import (
    AutomatedReactionTypeRouterService,
)

from app.services.automated_reaction_target_safety_service import (
    AutomatedReactionTargetSafetyService,
)

from app.services.automated_reaction_duplicate_protection_service import (
    AutomatedReactionDuplicateProtectionService,
)

from app.services.automated_reaction_cooldown_service import (
    AutomatedReactionCooldownService,
)

from app.services.automated_reaction_buyer_session_safety_service import (
    AutomatedReactionBuyerSessionSafetyService,
)

from app.services.automated_reaction_outbound_service import (
    AutomatedReactionOutboundService,
)


def main():
    print("\n=== 3D.18.13 STRESS + EDGE CASE TESTS ===\n")

    router = AutomatedReactionTypeRouterService()
    target_safety = AutomatedReactionTargetSafetyService()
    duplicate_guard = AutomatedReactionDuplicateProtectionService()
    cooldown = AutomatedReactionCooldownService()
    session_safety = AutomatedReactionBuyerSessionSafetyService()
    outbound = AutomatedReactionOutboundService()

    unsupported_event = router.resolve_reaction_type(
        monetization_event={
            "event_type": "unsupported_event",
        }
    )

    print("unsupported event")
    print(unsupported_event)
    assert unsupported_event["blocked"] is True
    print("PASS\n")

    missing_target = target_safety.validate_target_safety(
        monetization_event={
            "event_type": "purchase_received",
            "fanvue_user_id": "fanvue_user_abc",
            "fanvue_account_id": "fanvue_account_abc",
        }
    )

    print("missing local user mapping")
    print(missing_target)
    assert missing_target["blocked"] is True
    assert missing_target["reason"] == "missing_local_user_mapping"
    print("PASS\n")

    missing_thread = target_safety.validate_target_safety(
        monetization_event={
            "event_type": "purchase_received",
            "local_user_id": 123,
            "fanvue_user_id": "fanvue_user_abc",
            "fanvue_account_id": "fanvue_account_abc",
        }
    )

    print("missing thread")
    print(missing_thread)
    assert missing_thread["blocked"] is True
    assert missing_thread["reason"] == "missing_reaction_thread_context"
    print("PASS\n")

    duplicate_event = duplicate_guard.validate_duplicate_reaction(
        monetization_event={
            "external_event_id": "dup_event_123",
            "fanvue_user_id": "fanvue_user_abc",
        },
        reaction_type="purchase_thank_you",
        reaction_history=[
            {
                "event_id": "dup_event_123",
                "fanvue_user_id": "fanvue_user_abc",
                "reaction_type": "purchase_thank_you",
            }
        ],
    )

    print("duplicate event")
    print(duplicate_event)
    assert duplicate_event["blocked"] is True
    assert duplicate_event["reason"] == "duplicate_event_reaction"
    print("PASS\n")

    recent_outbound = cooldown.validate_cooldown(
        reaction_type="purchase_thank_you",
        outbound_history=[
            {
                "sent_at": __import__("datetime")
                .datetime.utcnow()
                .isoformat()
            }
        ],
    )

    print("recent outbound")
    print(recent_outbound)
    assert recent_outbound["blocked"] is True
    assert recent_outbound["reason"] == "recent_outbound_activity"
    print("PASS\n")

    blocked_session = session_safety.validate_buyer_session_safety(
        reaction_type="premium_followup",
        runtime_state={
            "buyer_session_active": True,
            "buyer_session_step": "close",
            "close_mode": True,
        },
    )

    print("blocked buyer session")
    print(blocked_session)
    assert blocked_session["blocked"] is True
    assert blocked_session["reason"] == "close_mode_reaction_blocked"
    print("PASS\n")

    blocked_execution = outbound.execute_reaction(
        message_payload={
            "reaction_type": "purchase_thank_you",
            "message_text": "Aww thank you babe 💕",
        },
        execution_mode_result={
            "execution_mode": "blocked",
        },
    )

    print("blocked execution")
    print(blocked_execution)
    assert blocked_execution["blocked"] is True
    assert blocked_execution["live_send_performed"] is False
    print("PASS\n")

    dry_run_execution = outbound.execute_reaction(
        message_payload={
            "reaction_type": "purchase_thank_you",
            "message_text": "Aww thank you babe 💕",
        },
        execution_mode_result={
            "execution_mode": "dry_run",
        },
    )

    print("dry-run execution")
    print(dry_run_execution)
    assert dry_run_execution["success"] is True
    assert dry_run_execution["dry_run"] is True
    assert dry_run_execution["live_send_performed"] is False
    print("PASS\n")

    print("✅ 3D.18.13 Stress + Edge Case Tests passed")


if __name__ == "__main__":
    main()