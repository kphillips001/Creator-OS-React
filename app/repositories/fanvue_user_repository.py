from app.database import get_db_connection


def upsert_fanvue_user(user: dict):
    if not user.get("fanvue_user_uuid"):
        print("[UPSERT SKIPPED] Missing UUID")
        return

    print(
        f"[UPSERT] uuid={user['fanvue_user_uuid']} "
        f"username={user.get('username')} "
        f"follower={user.get('is_follower')} "
        f"subscriber={user.get('is_subscriber')}"
    )

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO fanvue_users (
                    fanvue_account_id,
                    fanvue_user_uuid,
                    username,
                    display_name,
                    relationship_status,
                    is_follower,
                    is_subscriber
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (fanvue_account_id, fanvue_user_uuid)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    display_name = EXCLUDED.display_name,
                    relationship_status = EXCLUDED.relationship_status,
                    is_follower = EXCLUDED.is_follower,
                    is_subscriber = EXCLUDED.is_subscriber
                """,
                (
                    user["fanvue_account_id"],
                    user["fanvue_user_uuid"],
                    user.get("username"),
                    user.get("display_name"),
                    user.get("relationship_status"),
                    user.get("is_follower"),
                    user.get("is_subscriber"),
                ),
            )

        conn.commit()

    print(f"[UPSERT COMPLETE] uuid={user['fanvue_user_uuid']}")

def get_all_fanvue_user_uuids(fanvue_account_id: int) -> set:
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
        cur.close()

    return {str(row["fanvue_user_uuid"]) for row in rows}

def get_relationship_stats(fanvue_account_id: int):
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                COUNT(*) AS total_users,
                COUNT(*) FILTER (WHERE is_follower = TRUE) AS followers,
                COUNT(*) FILTER (WHERE is_subscriber = TRUE) AS subscribers,
                COUNT(*) FILTER (WHERE relationship_status = 'missing') AS missing
            FROM fanvue_users
            WHERE fanvue_account_id = %s
            """,
            (fanvue_account_id,),
        )

        row = cur.fetchone()
        cur.close()

    return row