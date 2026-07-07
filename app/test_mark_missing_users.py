from datetime import datetime

from app.database import get_db_connection
from app.services.fanvue_relationship_sync_service import FanvueRelationshipSyncService
from app.services.fanvue_oauth_service import FanvueOAuthService


def get_all_db_user_rows(fanvue_account_id: int):
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT fanvue_user_uuid, is_follower, is_subscriber
            FROM fanvue_users
            WHERE fanvue_account_id = %s
            """,
            (fanvue_account_id,),
        )

        return cur.fetchall()


def mark_missing_users(fanvue_account_id: int, missing_uuids: set[str]):
    if not missing_uuids:
        print("[NO MISSING USERS]")
        return

    with get_db_connection() as conn:
        cur = conn.cursor()

        now = datetime.utcnow()

        for uuid in missing_uuids:
            print(f"[MARK MISSING] uuid={uuid}")

            cur.execute(
                """
                UPDATE fanvue_users
                SET
                    is_follower = FALSE,
                    follower_lost_at = %s
                WHERE fanvue_account_id = %s
                AND fanvue_user_uuid = %s
                """,
                (now, fanvue_account_id, uuid),
            )

        conn.commit()

    print(f"[MISSING USERS UPDATED] count={len(missing_uuids)}")


def run_test():
    print("\n=== 14N-4B MARK MISSING USERS TEST ===\n")

    fanvue_account_id = 1

    oauth = FanvueOAuthService()
    token = oauth.get_valid_access_token()

    service = FanvueRelationshipSyncService(token)

    # current snapshot
    relationship_map = service.build_relationship_map()
    current_uuids = set(relationship_map.keys())

    # db snapshot
    db_rows = get_all_db_user_rows(fanvue_account_id)
    db_uuids = {str(row["fanvue_user_uuid"]) for row in db_rows}

    # detect missing
    missing = db_uuids - current_uuids

    print(f"[MISSING DETECTED] count={len(missing)}")

    # update DB
    mark_missing_users(fanvue_account_id, missing)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()