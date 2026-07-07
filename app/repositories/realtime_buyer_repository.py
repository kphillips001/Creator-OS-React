from app.database import get_db_connection
from app.services.buyer_tier_service import BuyerTierService


def apply_purchase_to_buyer(
    fanvue_user_id: int,
    purchase_amount: float,
):
    """
    STEP 11.10 + 11.11

    Apply realtime purchase updates
    to buyer intelligence fields.

    Updates:
    - total_spend
    - purchase_count
    - last_purchase_at
    - buyer_tier
    """

    tier_service = BuyerTierService()

    select_sql = """
        SELECT
            total_spend,
            purchase_count
        FROM fanvue_users
        WHERE id = %s;
    """

    update_sql = """
        UPDATE fanvue_users
        SET
            total_spend = %s,
            purchase_count = %s,
            buyer_tier = %s,
            last_purchase_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
        RETURNING
            id,
            total_spend,
            purchase_count,
            buyer_tier,
            last_purchase_at;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(select_sql, (fanvue_user_id,))
            row = cursor.fetchone()

            if not row:
                raise ValueError(
                    f"No fanvue_users record found for id={fanvue_user_id}"
                )

            current_total_spend = float(row["total_spend"] or 0)
            current_purchase_count = int(row["purchase_count"] or 0)

            new_total_spend = current_total_spend + float(purchase_amount)
            new_purchase_count = current_purchase_count + 1

            new_buyer_tier = tier_service.determine_buyer_tier(
                total_spend=new_total_spend,
                purchase_count=new_purchase_count,
            )

            cursor.execute(
                update_sql,
                (
                    new_total_spend,
                    new_purchase_count,
                    new_buyer_tier,
                    fanvue_user_id,
                )
            )

            updated_row = cursor.fetchone()

        conn.commit()

    return updated_row