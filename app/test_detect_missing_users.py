from app.database import get_db_connection
from app.services.fanvue_relationship_sync_service import FanvueRelationshipSyncService
from app.services.fanvue_oauth_service import FanvueOAuthService


def get_all_db_user_uuids(fanvue_account_id: int) -> set[str]:
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT fanvue_user_uuid
            FROM fanvue_users
            WHERE fanvue_account_id = %s
            """,
            (fanvue_account_id,),
        )

        rows = cur.fetchall()
        return {str(row["fanvue_user_uuid"]) for row in rows}


def run_test():
    print("\n=== 14N-4A MISSING USER DETECTION TEST ===\n")

    fanvue_account_id = 1

    oauth = FanvueOAuthService()
    token = oauth.get_valid_access_token()

    service = FanvueRelationshipSyncService(token)

    # STEP 1: Current API snapshot
    relationship_map = service.build_relationship_map()
    current_uuids = set(relationship_map.keys())

    print(f"[CURRENT USERS] {len(current_uuids)}")

    # STEP 2: DB snapshot
    db_uuids = get_all_db_user_uuids(fanvue_account_id)
    print(f"[DB USERS] {len(db_uuids)}")

    # STEP 3: Detect missing
    missing_users = db_uuids - current_uuids

    print(f"\n[MISSING USERS DETECTED] count={len(missing_users)}")

    # Show sample
    sample = list(missing_users)[:10]
    print("\nSample missing UUIDs:")
    for uuid in sample:
        print(uuid)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()