from datetime import datetime

from app.services.fanvue_oauth_service import FanvueOAuthService
from app.services.fanvue_relationship_sync_service import FanvueRelationshipSyncService
from app.repositories.fanvue_user_repository import (
    upsert_fanvue_user,
    get_all_fanvue_user_uuids,
)
from app.database import get_db_connection


class FanvueRelationshipSyncOrchestrator:
    def __init__(self, fanvue_account_id: int):
        self.fanvue_account_id = fanvue_account_id

    def mark_missing_users(self, missing_uuids: set[str]):
        if not missing_uuids:
            print("[FANVUE MISSING USERS] none")
            return 0

        now = datetime.utcnow()

        with get_db_connection() as conn:
            cur = conn.cursor()

            for uuid in missing_uuids:
                print(f"[FANVUE USER MISSING] uuid={uuid}")

                cur.execute(
                    """
                    UPDATE fanvue_users
                    SET
                        is_follower = FALSE,
                        is_subscriber = FALSE,
                        relationship_status = 'missing',
                        follower_lost_at = COALESCE(follower_lost_at, %s),
                        missing_since_at = COALESCE(missing_since_at, %s)
                    WHERE fanvue_account_id = %s
                    AND fanvue_user_uuid = %s
                    """,
                    (now, now, self.fanvue_account_id, uuid),
                )

            conn.commit()
            cur.close()

        return len(missing_uuids)

    def sync_current_relationships(self):
        print("\n[FANVUE RELATIONSHIP SYNC START]")

        oauth = FanvueOAuthService()
        access_token = oauth.get_valid_access_token()

        service = FanvueRelationshipSyncService(access_token=access_token)
        relationship_map = service.build_relationship_map()

        print(f"[FANVUE RELATIONSHIP USERS FOUND] total={len(relationship_map)}")

        saved_count = 0

        for user in relationship_map.values():
            user["fanvue_account_id"] = self.fanvue_account_id

            upsert_fanvue_user(user)
            saved_count += 1

        current_uuids = set(relationship_map.keys())
        db_uuids = get_all_fanvue_user_uuids(self.fanvue_account_id)

        missing_uuids = db_uuids - current_uuids

        print(f"[FANVUE MISSING USERS DETECTED] count={len(missing_uuids)}")

        missing_count = self.mark_missing_users(missing_uuids)

        print(
            f"[FANVUE RELATIONSHIP SYNC COMPLETE] "
            f"saved={saved_count} missing={missing_count}"
        )

        return {
            "found": len(relationship_map),
            "saved": saved_count,
            "missing": missing_count,
        }