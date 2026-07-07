from app.database import get_db_connection


def reset_user_chat(
    fanvue_account_id: int,
    fanvue_user_uuid: str,
):
    """
    Reset a test chat user back to a fresh-user state.

    Section 6 hardened:
    Reset is scoped by:
    - fanvue_account_id
    - fanvue_user_uuid
    - internal fanvue_user_id

    Clears only data for the selected creator account:
    - fanvue_chat_messages by fanvue_account_id + fanvue_user_uuid
    - user_memory by fanvue_account_id + internal fanvue_user_id
    - content_usage_log by fanvue_account_id + internal fanvue_user_id

    NOTE:
    This does NOT delete the fanvue_users row itself.
    That allows get_or_create_user_with_memory() to reuse the same user safely.
    """

    if not fanvue_account_id:
        return {
            "success": False,
            "reason": "missing_fanvue_account_id",
        }

    if not fanvue_user_uuid:
        return {
            "success": False,
            "reason": "missing_fanvue_user_uuid",
        }

    fanvue_user_uuid = str(fanvue_user_uuid)

    print(
        f"[RESET CHAT] account_id={fanvue_account_id} "
        f"user_uuid={fanvue_user_uuid}"
    )

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            # --------------------------------------------------
            # 1. Find internal DB user id from account + Fanvue UUID
            # --------------------------------------------------
            cursor.execute(
                """
                SELECT id
                FROM fanvue_users
                WHERE fanvue_account_id = %s
                  AND fanvue_user_uuid = %s
                LIMIT 1
                """,
                (
                    fanvue_account_id,
                    fanvue_user_uuid,
                ),
            )

            row = cursor.fetchone()
            fanvue_user_id = row["id"] if row else None

            print(f"[RESET CHAT] internal_user_id={fanvue_user_id}")

            # --------------------------------------------------
            # 2. Delete chat messages by account + Fanvue UUID
            # --------------------------------------------------
            cursor.execute(
                """
                DELETE FROM fanvue_chat_messages
                WHERE fanvue_account_id = %s
                  AND fanvue_user_uuid = %s
                """,
                (
                    fanvue_account_id,
                    fanvue_user_uuid,
                ),
            )

            chat_deleted = cursor.rowcount

            # --------------------------------------------------
            # 3. Delete memory + content usage by account + internal user id
            # --------------------------------------------------
            memory_deleted = 0
            usage_deleted = 0

            if fanvue_user_id:
                cursor.execute(
                    """
                    DELETE FROM user_memory
                    WHERE fanvue_account_id = %s
                      AND fanvue_user_id = %s::text
                    """,
                    (
                        fanvue_account_id,
                        str(fanvue_user_id),
                    ),
                )
                memory_deleted = cursor.rowcount

                cursor.execute(
                    """
                    DELETE FROM content_usage_log
                    WHERE fanvue_account_id = %s
                      AND fanvue_user_id = %s
                    """,
                    (
                        fanvue_account_id,
                        str(fanvue_user_id),
                    ),
                )
                usage_deleted = cursor.rowcount

        conn.commit()

    print(f"[RESET CHAT] chat_deleted={chat_deleted}")
    print(f"[RESET CHAT] memory_deleted={memory_deleted}")
    print(f"[RESET CHAT] usage_deleted={usage_deleted}")
    print("[RESET CHAT] COMPLETE")

    return {
        "success": True,
        "fanvue_account_id": fanvue_account_id,
        "fanvue_user_uuid": fanvue_user_uuid,
        "fanvue_user_id": fanvue_user_id,
        "chat_deleted": chat_deleted,
        "memory_deleted": memory_deleted,
        "usage_deleted": usage_deleted,
    }