import logging

from app.database import get_db_connection


logger = logging.getLogger(__name__)


def upsert_buyer_purchase_stats(
    fanvue_account_id: int,
    fanvue_user_id: str,
    purchase_amount: float,
):
    """
    3D.4B

    Updates realtime buyer intelligence stats
    after purchases/unlocks.
    """

    sql = """
        INSERT INTO buyer_intelligence (
            fanvue_account_id,
            fanvue_user_id,
            total_spend,
            purchase_count,
            last_purchase_at,
            created_at,
            updated_at
        )
        VALUES (
            %s,
            %s,
            %s,
            1,
            NOW(),
            NOW(),
            NOW()
        )

        ON CONFLICT (
            fanvue_account_id,
            fanvue_user_id
        )

        DO UPDATE SET

            total_spend = (
                buyer_intelligence.total_spend
                + EXCLUDED.total_spend
            ),

            purchase_count = (
                buyer_intelligence.purchase_count
                + 1
            ),

            last_purchase_at = NOW(),

            updated_at = NOW()

        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    fanvue_account_id,
                    fanvue_user_id,
                    purchase_amount,
                ),
            )

            row = cursor.fetchone()

            conn.commit()

            return row


def refresh_buyer_tier(
    fanvue_account_id: int,
    fanvue_user_id: str,
):
    """
    3D.4B

    Calculates:
    - buyer_tier
    - is_spender
    - is_top_spender
    - is_whale
    """

    sql = """
        SELECT *
        FROM buyer_intelligence
        WHERE fanvue_account_id = %s
        AND fanvue_user_id = %s
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    fanvue_account_id,
                    fanvue_user_id,
                ),
            )

            row = cursor.fetchone()

            if not row:
                return None

            total_spend = float(
                row["total_spend"] or 0
            )

            purchase_count = int(
                row["purchase_count"] or 0
            )

            buyer_tier = "NON_BUYER"

            #
            # TIER CALCULATION
            #

            if total_spend >= 1000:
                buyer_tier = "WHALE"

            elif total_spend >= 300:
                buyer_tier = "HIGH_VALUE"

            elif (
                total_spend >= 75
                or purchase_count >= 5
            ):
                buyer_tier = "ACTIVE_BUYER"

            elif total_spend > 0:
                buyer_tier = "LOW_SPENDER"

            is_spender = total_spend > 0
            is_top_spender = total_spend >= 300
            is_whale = total_spend >= 1000

            update_sql = """
                UPDATE buyer_intelligence
                SET
                    buyer_tier = %s,
                    is_spender = %s,
                    is_top_spender = %s,
                    is_whale = %s,
                    updated_at = NOW()
                WHERE fanvue_account_id = %s
                AND fanvue_user_id = %s
                RETURNING *;
            """

            cursor.execute(
                update_sql,
                (
                    buyer_tier,
                    is_spender,
                    is_top_spender,
                    is_whale,
                    fanvue_account_id,
                    fanvue_user_id,
                ),
            )

            updated = cursor.fetchone()

            conn.commit()

            return updated


def upsert_buyer_tip_stats(
    fanvue_account_id: int,
    fanvue_user_id: str,
    tip_amount: float,
):
    """
    3D.6

    Updates realtime buyer intelligence stats
    after tips.
    """

    sql = """
        INSERT INTO buyer_intelligence (
            fanvue_account_id,
            fanvue_user_id,
            total_tip_amount,
            tip_count,
            last_tip_at,
            created_at,
            updated_at
        )
        VALUES (
            %s,
            %s,
            %s,
            1,
            NOW(),
            NOW(),
            NOW()
        )

        ON CONFLICT (
            fanvue_account_id,
            fanvue_user_id
        )

        DO UPDATE SET
            total_tip_amount = (
                buyer_intelligence.total_tip_amount
                + EXCLUDED.total_tip_amount
            ),

            tip_count = (
                buyer_intelligence.tip_count
                + 1
            ),

            last_tip_at = NOW(),
            updated_at = NOW()

        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    fanvue_account_id,
                    fanvue_user_id,
                    tip_amount,
                ),
            )

            row = cursor.fetchone()
            conn.commit()

            return row


def activate_subscription(
    fanvue_account_id: int,
    fanvue_user_id: str,
):
    """
    3D.7

    Activates subscriber state.
    """

    sql = """
        UPDATE buyer_intelligence
        SET
            is_subscriber = TRUE,
            subscription_status = 'ACTIVE',
            subscribed_at = NOW(),
            last_subscription_event_at = NOW(),
            updated_at = NOW()
        WHERE fanvue_account_id = %s
        AND fanvue_user_id = %s
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    fanvue_account_id,
                    fanvue_user_id,
                ),
            )

            row = cursor.fetchone()

            conn.commit()

            return row


def cancel_subscription(
    fanvue_account_id: int,
    fanvue_user_id: str,
):
    """
    3D.7

    Cancels subscriber state.
    """

    sql = """
        UPDATE buyer_intelligence
        SET
            is_subscriber = FALSE,
            subscription_status = 'CANCELLED',
            cancelled_at = NOW(),
            last_subscription_event_at = NOW(),
            updated_at = NOW()
        WHERE fanvue_account_id = %s
        AND fanvue_user_id = %s
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    fanvue_account_id,
                    fanvue_user_id,
                ),
            )

            row = cursor.fetchone()

            conn.commit()

            return row


def get_buyer_intelligence_by_user_id(
    fanvue_account_id: int,
    fanvue_user_id: str,
):
    """
    3D.9

    Fetches buyer intelligence for spend intelligence logic.
    """

    logger.info(
        "[IDENTITY FLOW] layer=BuyerIntelligenceRepository "
        "fanvue_account_id=%r fanvue_account_id_type=%s "
        "fanvue_user_id=%r fanvue_user_id_type=%s",
        fanvue_account_id,
        type(fanvue_account_id).__name__,
        fanvue_user_id,
        type(fanvue_user_id).__name__,
    )

    sql = """
        SELECT *
        FROM buyer_intelligence
        WHERE fanvue_account_id = %s
        AND fanvue_user_id = %s
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    fanvue_account_id,
                    fanvue_user_id,
                ),
            )

            return cursor.fetchone()
