from app.config import settings
from app.logger import get_logger
from app.services.memory_service import MemoryService
from app.services.intent_service import IntentService
from app.services.offer_service import OfferService
from app.services.content_service import ContentService
from app.services.gpt_service import GPTService
from app.services.user_value_service import UserValueService
from app.services.post_offer_service import PostOfferService  # ✅ NEW
from app.services.timing_engine import TimingEngine
from app.services.ppv_targeting_service import PPVTargetingService
from app.services.ppv_broadcast_service import PPVBroadcastService
from app.services.outreach_runner import OutreachRunner
from app.engine.mode_engine import ModeEngine
from app.engine.decision_engine import DecisionEngine
from app.repositories.memory_repository import reset_exhausted_outreach_user
from app.repositories.fanvue_account_repository import get_or_create_account
from app.repositories.user_repository import (
    get_or_create_user_with_memory,
    get_outreach_candidate_rows,
)
from app.repositories.memory_repository import (
    reset_exhausted_outreach_user,
    mark_outreach_response,
    force_reset_outreach_state,
)
from app.repositories.chat_message_repository import (
    get_or_create_chat_thread,
    save_chat_message,
    get_recent_messages_for_gpt,
)
from app.repositories.ppv_broadcast_repository import (
    log_broadcast_send,
    get_recent_broadcasts_for_user,
)

logger = get_logger()

memory_service = MemoryService()
intent_service = IntentService()
user_value_service = UserValueService()
offer_service = OfferService()
content_service = ContentService()
post_offer_service = PostOfferService()
timing_engine = TimingEngine()
ppv_targeting_service = PPVTargetingService()
ppv_broadcast_service = PPVBroadcastService()
outreach_runner = OutreachRunner()

print("OPENAI KEY PREFIX:", settings.OPENAI_API_KEY[:12])
gpt_service = GPTService(settings.OPENAI_API_KEY)
mode_engine = ModeEngine()

decision_engine = DecisionEngine(
    memory_service,
    intent_service,
    user_value_service,
    mode_engine,
    offer_service,
    content_service,
    post_offer_service,  # ✅ NEW (IMPORTANT)
    timing_engine,
    gpt_service,
    settings,
    logger,
)


def start_app():
    logger.info("Fanvue Chatbot is starting...")
    logger.info(f"Default persona: {settings.DEFAULT_PERSONA}")

    fanvue_username = "ava.blackthorne"
    simulated_fanvue_user_uuid = "11111111-1111-1111-1111-111111111111"

    account = get_or_create_account(
        username=fanvue_username,
        display_name="Ava Blackthorne",
    )

    context = get_or_create_user_with_memory(
        fanvue_account_id=account["id"],
        fanvue_user_uuid=simulated_fanvue_user_uuid,
        username="test_user",
        display_name="Test User",
        relationship_status="follower",
        is_subscriber=False,
        is_follower=True,
        source="cli_test",
    )

    db_user = context["user"]
    engine_user_id = f"{account['id']}:{db_user['id']}"

    thread = get_or_create_chat_thread(
        fanvue_account_id=account["id"],
        fanvue_user_id=db_user["id"],
    )

    print("\nFanvue Chatbot Simulator")
    print("Type 'exit' to quit.")
    print("Type '/reset' to clear this test user's memory.")
    print("Type '/memory' to view this test user's stored memory.\n")
    print(f"Connected account: {account['username']} (account_id={account['id']})")
    print(f"Simulated fan UUID: {simulated_fanvue_user_uuid}")
    print(f"Engine user key: {engine_user_id}")
    print(f"Chat thread id: {thread['id']}\n")

    while True:
        user_message = input("You: ").strip()

        if user_message.lower() == "exit":
            print("Goodbye")
            break

        if user_message.lower() == "/reset":
            memory_service.clear_user_memory(engine_user_id)
            print("Test user memory cleared\n")
            continue

        if user_message.lower() == "/memory":
            user_memory = memory_service.get_user_memory(engine_user_id)
            print("\n----- USER MEMORY -----")
            if not user_memory:
                print("No memory found.")
            else:
                for key, value in user_memory.items():
                    print(f"{key}: {value}")
            print("------------------------\n")
            continue

        if not user_message:
            continue

        # Track outreach responses before normal message processing
        current_memory = memory_service.get_user_memory(engine_user_id)
        if current_memory and (current_memory.get("outreach_status") or "").lower() == "sent":
            mark_outreach_response(
                fanvue_account_id=account["id"],
                fanvue_user_id=db_user["id"],
            )
            print("[DEBUG] Outreach response tracked.")

        # Save inbound message
        save_chat_message(
            fanvue_account_id=account["id"],
            thread_id=thread["id"],
            fanvue_user_id=db_user["id"],
            direction="inbound",
            sender_type="user",
            text=user_message,
        )

        # Fetch recent chat history for GPT
        chat_history = get_recent_messages_for_gpt(
            fanvue_account_id=account["id"],
            thread_id=thread["id"],
            limit=4,
        )
        result = decision_engine.process_message(
            engine_user_id,
            user_message,
            chat_history=chat_history,
        )

        if result is None:
            print("Bot: Error - process_message returned None\n")
            continue

        # Save bot response
        save_chat_message(
            fanvue_account_id=account["id"],
            thread_id=thread["id"],
            fanvue_user_id=db_user["id"],
            direction="outbound",
            sender_type="bot",
            text=result["response"],
        )

        print(f"Bot: {result['response']}\n")

        route_result = result.get("route", {}) or {}
        route_name = route_result.get("route", "unknown")
        route_confidence = route_result.get("confidence", 0.0)
        route_signals = route_result.get("signals", [])
        route_reason = route_result.get("reason", "")

        print("----- DEBUG SUMMARY -----")
        print(f"Route: {route_name}")
        print(f"Route Confidence: {route_confidence}")
        print(f"Route Signals: {route_signals}")
        print(f"Route Reason: {route_reason}")
        print(f"Tier: {result['intent']['tier']}")
        print(f"Score: {result['intent']['score']}")
        print(f"Msg Score: {result['intent']['message_score']}")
        print(f"Beh Score: {result['intent']['behavior_score']}")
        print(f"Signals: {result['intent']['signals']}")
        print(f"Mode: {result['mode']}")
        print(f"Offer: {result['offer']['offer_type']}")
        print(f"Send Offer: {result['send_offer']}")
        print(f"Send Nudge: {result.get('send_nudge', False)}")
        print(f"Nudge Type: {result.get('nudge_type')}")
        print("-------------------------\n")


# ==============================
# PPV BROADCAST TEST (TEMP)
# ==============================

def test_ppv_log():
    print("\n--- TESTING PPV BROADCAST LOG ---")

    log_broadcast_send(
        fanvue_account_id=1,
        fanvue_user_id=123,
        content_tag="TEST_PPv_001",
        campaign_type="test"
    )

    results = get_recent_broadcasts_for_user(123)

    print("Recent broadcasts:", results)
    print("--- END TEST ---\n")


def test_ppv_targets():
    print("\n--- TESTING PPV TARGETING ---")

    targets = ppv_targeting_service.get_basic_targets(
        fanvue_account_id=1,
        content_tag="TEST_PPv_001",
        cooldown_hours=24,
        include_followers=True,
        include_subscribers=True,
        limit=20,
    )

    print(f"Target count: {len(targets)}")

    for target in targets:
        print(target)

    print("--- END TARGET TEST ---\n")


def test_ppv_broadcast_real_run():
    print("\n--- TESTING PPV BROADCAST REAL RUN ---")

    results = ppv_broadcast_service.run_basic_broadcast(
        fanvue_account_id=1,
        content_tag="BROADCAST_TEST_004",  # NEW TAG
        campaign_type="test_broadcast",
        cooldown_hours=24,
        include_followers=True,
        include_subscribers=True,
        limit=20,
        dry_run=False,  # IMPORTANT
    )

    print("Broadcast Results:")
    print(results)
    print("--- END BROADCAST REAL RUN TEST ---\n")


# ==============================
# OUTREACH ENGINE TEST (TEMP)
# ==============================

def test_outreach_candidates():
    print("\n--- TESTING OUTREACH ENGINE ---")

    results = outreach_runner.run_outreach_cycle(
        fanvue_account_id=2,
        limit=20,
        dry_run=False,  # ✅ LIVE MODE FOR THIS TEST
    )

    print(f"Fanvue Account ID: {results['fanvue_account_id']}")
    print(f"Dry Run: {results['dry_run']}")
    print(f"Candidate Count: {results['candidate_count']}")
    print(f"Eligible Count: {results['eligible_count']}")
    print(f"Ineligible Count: {results['ineligible_count']}")
    print(f"Processed Count: {results['processed_count']}")

    print("\n--- PROCESSED USERS ---")
    for user in results["processed"]:
        username = user.get("username", "unknown")
        preview = user.get("outreach_preview", {})
        reason = preview.get("reason", "No reason available.")
        recommended_status = preview.get("recommended_status", "unknown")
        suggested_opener = user.get("suggested_opener", None)
        memory_updated = user.get("memory_updated", False)
        log_created = user.get("log_created", False)

        print(
            f"username={username} | eligible=True | "
            f"status={recommended_status} | memory_updated={memory_updated} | "
            f"log_created={log_created} | reason={reason}"
        )

        if suggested_opener:
            print(f"  opener: {suggested_opener}")

    print("\n--- SKIPPED USERS ---")
    for user in results["skipped"]:
        username = user.get("username", "unknown")
        preview = user.get("outreach_preview", {})
        reason = preview.get("reason", "No reason available.")
        recommended_status = preview.get("recommended_status", "unknown")

        print(
            f"username={username} | eligible=False | "
            f"status={recommended_status} | reason={reason}"
        )

    print("--- END OUTREACH TEST ---\n")


def test_force_reset_outreach():
    print("\n--- FORCE RESET OUTREACH STATE ---")

    result = force_reset_outreach_state(
        fanvue_account_id=2,
        fanvue_user_id=4,
    )

    if result:
        print("Outreach state reset successfully.")
        print(
            f"user_id={result['fanvue_user_id']} | "
            f"status={result['outreach_status']} | "
            f"attempts={result['outreach_attempts']} | "
            f"last_outreach_at={result['last_outreach_at']}"
        )
    else:
        print("User not found.")

    print("--- END FORCE RESET ---\n")


# test_force_reset_outreach()
# test_outreach_candidates()
# test_force_reset_outreach()