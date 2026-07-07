from app.services.realtime_buyer_state_service import RealtimeBuyerStateService
from app.database import get_db_connection


def seed_pending_ppv(fanvue_user_id: int, content_item_id: int):
    """
    Inserts a PPV sent record WITHOUT a purchase
    → this should trigger pending_ppv = True
    """
    print("\n[SEED] Creating pending PPV...")

    sql = """
        INSERT INTO content_usage_log (
            fanvue_user_id,
            content_item_id,
            usage_type,
            created_at
        )
        VALUES (%s, %s, 'ppv_sent', NOW());
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (fanvue_user_id, content_item_id))

    print("[SEED COMPLETE]")


def clear_test_data(fanvue_user_id: int):
    """
    Clears test data so runs are clean
    """
    print("\n[CLEANUP] Clearing old test data...")

    sql = """
        DELETE FROM content_usage_log
        WHERE fanvue_user_id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (fanvue_user_id,))

    print("[CLEANUP COMPLETE]")


def run_test():
    print("\n==============================")
    print(" REALTIME BUYER STATE TEST")
    print("==============================\n")

    service = RealtimeBuyerStateService()

    fanvue_user_id = 123
    content_item_id = 65

    # 1️⃣ Clean slate
    clear_test_data(fanvue_user_id)

    # 2️⃣ Seed pending PPV (sent but NOT purchased)
    seed_pending_ppv(fanvue_user_id, content_item_id)

    # 3️⃣ Get state
    state = service.get_buyer_state(fanvue_user_id)

    # 4️⃣ Check eligibility (UPDATED)
    result = service.is_eligible_for_mass_ppv(fanvue_user_id)

    print("\n--- STATE ---")
    for k, v in state.items():
        print(f"{k}: {v}")

    print("\n--- RESULT ---")
    print(result)

    print("\n--- EXPECTED ---")
    print("pending_ppv = True")
    print("allowed = False")
    print("block_reason = 'pending_ppv'")


if __name__ == "__main__":
    run_test()