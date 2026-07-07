from app.database import get_db_connection
from app.services.realtime_buyer_state_service import RealtimeBuyerStateService


TEST_FANVUE_USER_ID = 123
TEST_CONTENT_ITEM_ID = 65


def get_test_user_uuid():
    sql = """
        SELECT fanvue_user_uuid
        FROM fanvue_users
        WHERE id = %s
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (TEST_FANVUE_USER_ID,))
            row = cur.fetchone()

    if not row:
        return None

    return row.get("fanvue_user_uuid")


def clear_test_data():
    print("\n[CLEANUP] Clearing test data...")

    user_uuid = get_test_user_uuid()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM content_usage_log
                WHERE fanvue_user_id = %s;
                """,
                (TEST_FANVUE_USER_ID,),
            )

            cur.execute(
                """
                DELETE FROM user_memory
                WHERE fanvue_user_id = %s;
                """,
                (TEST_FANVUE_USER_ID,),
            )

            if user_uuid:
                cur.execute(
                    """
                    DELETE FROM fanvue_chat_messages
                    WHERE sender_uuid = %s::text
                    OR fanvue_user_uuid = %s::text;
                    """,
                    (user_uuid, user_uuid),
                )

    print("[CLEANUP COMPLETE]")


def seed_usage(usage_type: str):
    print(f"\n[SEED] Creating {usage_type}...")

    sql = """
        INSERT INTO content_usage_log (
            fanvue_user_id,
            content_item_id,
            usage_type,
            created_at
        )
        VALUES (%s, %s, %s, NOW());
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    TEST_FANVUE_USER_ID,
                    TEST_CONTENT_ITEM_ID,
                    usage_type,
                ),
            )

    print("[SEED COMPLETE]")


def seed_active_chat():
    print("\n[SEED] Creating active chat message...")

    user_uuid = get_test_user_uuid()

    if not user_uuid:
        raise AssertionError(
            "Cannot seed active chat: test user has no fanvue_user_uuid"
        )

    sql = """
        INSERT INTO fanvue_chat_messages (
            fanvue_account_id,
            fanvue_user_uuid,
            fanvue_message_uuid,
            sender_uuid,
            message_text,
            sent_at,
            is_inbound,
            raw_payload
        )
        VALUES (
            1,
            %s::text,
            gen_random_uuid()::text,
            %s::text,
            'test active chat message',
            NOW(),
            true,
            '{}'::jsonb
        );
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (user_uuid, user_uuid))

    print("[SEED COMPLETE]")


def seed_close_ready_memory():
    print("\n[SEED] Creating close-ready user_memory row...")

    sql = """
        INSERT INTO user_memory (
            fanvue_user_id,
            fanvue_account_id,
            intent_score,
            heat_score,
            conversation_mode,
            buyer_tier,
            user_value_tier,
            is_whale,
            is_top_spender,
            buyer_classification
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    TEST_FANVUE_USER_ID,
                    1,  # ✅ REQUIRED FIX (fanvue_account_id)
                    0.9,  # intent_score
                    0.9,  # heat_score
                    "close",  # conversation_mode
                    "high",  # buyer_tier
                    "high",  # user_value_tier
                    False,
                    False,
                    "high_value",
                ),
            )

    print("[SEED COMPLETE]")


def assert_result(label: str, result: dict, expected_allowed: bool, expected_reason: str | None):
    print(f"\n--- {label} ---")
    print(result)

    actual_allowed = result.get("allowed")
    actual_reason = result.get("block_reason")

    if actual_allowed != expected_allowed:
        raise AssertionError(
            f"{label} failed: expected allowed={expected_allowed}, got {actual_allowed}"
        )

    if actual_reason != expected_reason:
        raise AssertionError(
            f"{label} failed: expected block_reason={expected_reason}, got {actual_reason}"
        )

    print(f"✅ PASS: {label}")


def assert_reason_in_list(label: str, result: dict, expected_reason: str):
    block_reasons = result.get("block_reasons", [])

    if expected_reason not in block_reasons:
        raise AssertionError(
            f"{label} failed: expected {expected_reason} in block_reasons, got {block_reasons}"
        )


def run_test():
    print("\n========================================")
    print(" REALTIME BUYER STATE BLOCK TESTS")
    print("========================================\n")

    service = RealtimeBuyerStateService()

    # 1. Clean user should be allowed
    clear_test_data()
    result = service.is_eligible_for_mass_ppv(TEST_FANVUE_USER_ID)
    assert_result(
        label="clean user should be allowed",
        result=result,
        expected_allowed=True,
        expected_reason=None,
    )

    # 2. Recent offer should be blocked
    clear_test_data()
    seed_usage("ppv_sent")
    result = service.is_eligible_for_mass_ppv(TEST_FANVUE_USER_ID)
    assert_reason_in_list("recent offer should be blocked", result, "recent_offer")
    assert_result(
        label="recent offer should be blocked",
        result=result,
        expected_allowed=False,
        expected_reason="pending_ppv",
    )

    # 3. Pending PPV should be blocked
    clear_test_data()
    seed_usage("ppv_sent")
    result = service.is_eligible_for_mass_ppv(TEST_FANVUE_USER_ID)
    assert_reason_in_list("pending PPV should be blocked", result, "pending_ppv")
    assert_result(
        label="pending PPV should be blocked",
        result=result,
        expected_allowed=False,
        expected_reason="pending_ppv",
    )

    # 4. Recent purchase should be blocked
    clear_test_data()
    seed_usage("ppv_purchased")
    result = service.is_eligible_for_mass_ppv(TEST_FANVUE_USER_ID)
    assert_result(
        label="recent purchase should be blocked",
        result=result,
        expected_allowed=False,
        expected_reason="recent_purchase",
    )

    # 5. Active chat should be blocked
    clear_test_data()
    seed_active_chat()
    result = service.is_eligible_for_mass_ppv(TEST_FANVUE_USER_ID)
    assert_result(
        label="active chat should be blocked",
        result=result,
        expected_allowed=False,
        expected_reason="active_chat",
    )

    # 6. Close-ready user should be blocked
    clear_test_data()
    seed_close_ready_memory()
    result = service.is_eligible_for_mass_ppv(TEST_FANVUE_USER_ID)
    assert_result(
        label="close-ready user should be blocked",
        result=result,
        expected_allowed=False,
        expected_reason="close_ready",
    )

    clear_test_data()

    print("\n✅ STEP 5.10 PHASE 2 COMPLETE")
    print("All realtime buyer state block tests passed.")


if __name__ == "__main__":
    run_test()