from app.database import get_db_connection


OWNERSHIP_USAGE_TYPES = [
    "ppv_purchased",
    "content_unlocked",
    "content_owned",
    "purchase",
    "unlock",
    "owned",
]


def get_content_ownership_memory(
    fanvue_account_id: int,
    fanvue_user_id: str,
):
    """
    3D.16.7

    Builds lightweight ownership intelligence from content_usage_log.
    Account-safe ownership memory.
    """

    sql = """
        SELECT
            COUNT(DISTINCT content_tag) AS owned_content_count,

            COUNT(DISTINCT content_tag) FILTER (
                WHERE LOWER(content_tag) LIKE '%%vip%%'
            ) AS owned_vip_count,

            COUNT(DISTINCT content_tag) FILTER (
                WHERE LOWER(content_tag) LIKE '%%premium%%'
            ) AS owned_premium_count,

            MAX(created_at) AS last_owned_at,

            (
                ARRAY_AGG(DISTINCT content_tag)
                FILTER (WHERE content_tag IS NOT NULL)
            )[1:10] AS recent_owned_content_tags

        FROM content_usage_log
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s
          AND usage_type = ANY(%s);
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    fanvue_account_id,
                    str(fanvue_user_id),
                    OWNERSHIP_USAGE_TYPES,
                ),
            )
            row = cursor.fetchone()

    if not row:
        return {
            "owned_content_count": 0,
            "owned_vip_count": 0,
            "owned_premium_count": 0,
            "last_owned_at": None,
            "recent_owned_content_tags": [],
            "collector_score": 0,
            "repeat_purchase_score": 0,
        }

    row = dict(row)

    owned_content_count = int(row.get("owned_content_count") or 0)
    owned_vip_count = int(row.get("owned_vip_count") or 0)
    owned_premium_count = int(row.get("owned_premium_count") or 0)

    collector_score = min(owned_content_count * 10, 100)

    repeat_purchase_score = min(
        (owned_vip_count * 8) + (owned_premium_count * 15),
        100,
    )

    return {
        "owned_content_count": owned_content_count,
        "owned_vip_count": owned_vip_count,
        "owned_premium_count": owned_premium_count,
        "last_owned_at": row.get("last_owned_at"),
        "recent_owned_content_tags": row.get("recent_owned_content_tags") or [],
        "collector_score": collector_score,
        "repeat_purchase_score": repeat_purchase_score,
    }


def sync_buyer_intelligence_to_user_memory(
    fanvue_account_id: int,
    fanvue_user_id: str,
):
    """
    3D.8 + 3D.16.7

    Copies realtime monetization intelligence from buyer_intelligence
    into user_memory so DecisionEngine/GPT context can access it.

    Section 6 hardened:
    Sync is scoped by fanvue_account_id + fanvue_user_id.
    """

    sql = """
        UPDATE user_memory um
        SET
            last_purchase_at = bi.last_purchase_at,
            last_tip_at = bi.last_tip_at,
            purchase_count = bi.purchase_count,
            total_spend = bi.total_spend,
            total_tip_amount = bi.total_tip_amount,
            buyer_tier = bi.buyer_tier,
            user_value_tier = CASE
                WHEN bi.is_whale = TRUE THEN 'WHALE'
                WHEN bi.is_top_spender = TRUE THEN 'HIGH_VALUE'
                WHEN bi.buyer_tier = 'ACTIVE_BUYER' THEN 'ACTIVE_BUYER'
                WHEN bi.is_spender = TRUE THEN 'LOW_SPENDER'
                ELSE 'LOW'
            END,
            is_spender = bi.is_spender,
            is_top_spender = bi.is_top_spender,
            is_whale = bi.is_whale,
            recent_purchase_active = (
                bi.last_purchase_at IS NOT NULL
                AND bi.last_purchase_at >= NOW() - INTERVAL '48 hours'
            ),
            recent_tip_active = (
                bi.last_tip_at IS NOT NULL
                AND bi.last_tip_at >= NOW() - INTERVAL '48 hours'
            ),
            is_subscriber = bi.is_subscriber,
            subscription_status = bi.subscription_status,
            last_monetization_sync_at = NOW()
        FROM buyer_intelligence bi
        WHERE um.fanvue_account_id = bi.fanvue_account_id
          AND um.fanvue_user_id = bi.fanvue_user_id
          AND bi.fanvue_account_id = %s
          AND bi.fanvue_user_id = %s
        RETURNING um.*;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    fanvue_account_id,
                    str(fanvue_user_id),
                ),
            )

            row = cursor.fetchone()
            conn.commit()

    if not row:
        return None

    row = dict(row)

    ownership_memory = get_content_ownership_memory(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
    )

    row.update(ownership_memory)

    return row