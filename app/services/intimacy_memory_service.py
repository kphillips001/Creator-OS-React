from app.database import (
    get_db_connection,
)

from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


class IntimacyMemoryService:
    """
    3D.10.14

    Persists long-term intimacy memory.

    Section 6 hardened:
    Intimacy memory sync is scoped by:
    - fanvue_account_id
    - fanvue_user_id
    """

    def __init__(self):
        self.profile_service = (
            IntimacyProfileService()
        )

    def sync_memory(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str,
    ):
        if not fanvue_account_id:
            return {
                "success": False,
                "reason": "missing_fanvue_account_id",
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "reason": "missing_fanvue_user_id",
            }

        profile = (
            self.profile_service.build_profile(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )
        )

        sql = """
            UPDATE user_memory
            SET
                intimacy_tier = %s,
                spender_confidence = %s,
                escalation_priority = %s,
                premium_sexting_allowed = %s,
                explicit_allowed = %s,
                intimacy_memory_synced_at = NOW()
            WHERE fanvue_account_id = %s
              AND fanvue_user_id = %s::text
            RETURNING *;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql,
                    (
                        profile.get("intimacy_tier"),
                        profile.get("spender_confidence"),
                        profile.get("escalation_priority"),
                        profile.get("premium_sexting_allowed"),
                        profile.get("explicit_allowed"),
                        fanvue_account_id,
                        str(fanvue_user_id),
                    ),
                )

                row = cursor.fetchone()
                conn.commit()

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "intimacy_tier": profile.get("intimacy_tier"),
            "memory_synced": row is not None,
            "memory_row": dict(row) if row else None,
        }