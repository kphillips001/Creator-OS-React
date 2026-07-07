from datetime import datetime, timezone

from app.repositories.memory_repository import (
    create_user_memory_row,
    update_memory_fields,
)


class RealtimeBuyerSessionRefreshService:
    """
    SECTION 2 REALTIME ENRICHMENT

    Refreshes buyer-session activity from
    realtime Fanvue webhook events.

    IMPORTANT:
    Real Fanvue webhooks send UUIDs.
    Internal memory tables use local bigint IDs.

    This service maps:
    Fanvue UUID -> local fanvue_users.id / fanvue_account_id
    before updating memory.
    """

    def get_local_user_ids(
        self,
        webhook_fanvue_user_uuid: str,
        webhook_fanvue_account_uuid: str | None = None,
    ):
        from app.database import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        fanvue_account_id
                    FROM fanvue_users
                    WHERE fanvue_user_uuid = %s
                    LIMIT 1;
                    """,
                    (
                        str(webhook_fanvue_user_uuid),
                    ),
                )

                user_row = cur.fetchone()

                if not user_row:
                    return None

                return {
                    "success": True,
                    "fanvue_user_id": user_row["id"],
                    "fanvue_account_id": user_row["fanvue_account_id"],
                    "local_fanvue_user_id": user_row["id"],
                    "local_fanvue_account_id": user_row["fanvue_account_id"],
                }

    def refresh_from_message(
        self,
        fanvue_user_id,
        fanvue_account_id,
        message_text: str,
    ):
        realtime_timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        print("\n[REALTIME BUYER SESSION REFRESH]")
        print(
            f"webhook_fanvue_user_uuid={fanvue_user_id}"
        )
        print(
            f"webhook_fanvue_account_id={fanvue_account_id}"
        )

        local_ids = self.get_local_user_ids(
            webhook_fanvue_user_uuid=str(
                fanvue_user_id
            ),
            webhook_fanvue_account_uuid=str(
                fanvue_account_id
            ),
        )

        if not local_ids:
            print("[BUYER SESSION REFRESH SKIPPED]")
            print(
                "No matching local fanvue_users row found."
            )

            return {
                "success": False,
                "skipped": True,
                "reason": "local_user_not_found",
                "fanvue_user_uuid": str(
                    fanvue_user_id
                ),
                "fanvue_account_id": fanvue_account_id,
            }

        local_fanvue_user_id = local_ids[
            "local_fanvue_user_id"
        ]

        local_fanvue_account_id = local_ids[
            "local_fanvue_account_id"
        ]

        print(
            f"local_fanvue_user_id={local_fanvue_user_id}"
        )

        print(
            f"local_fanvue_account_id={local_fanvue_account_id}"
        )

        create_user_memory_row(
            fanvue_account_id=local_fanvue_account_id,
            fanvue_user_id=local_fanvue_user_id,
        )

        memory_update_result = update_memory_fields(
            fanvue_account_id=local_fanvue_account_id,
            fanvue_user_id=local_fanvue_user_id,
            data={
                "last_user_message": message_text,
                "last_active_at": realtime_timestamp,
                "last_inbound_at": realtime_timestamp,
                "buyer_session_active": True,
                "buyer_session_last_message_at": realtime_timestamp,
                "buyer_session_last_action_at": realtime_timestamp,
                "buyer_session_last_action": "message_received_webhook",
            },
        )

        print("[BUYER SESSION REFRESHED]")

        return {
            "success": True,
            "fanvue_user_id": local_fanvue_user_id,
            "fanvue_account_id": local_fanvue_account_id,
            "fanvue_user_uuid": str(
                fanvue_user_id
            ),
            "fanvue_account_id_input": (
                fanvue_account_id
            ),
            "realtime_timestamp": realtime_timestamp,
            "memory_updated": (
                memory_update_result is not None
            ),
        }