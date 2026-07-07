class BuyerClassificationService:
    """
    15G-EXT Buyer Classification Service.

    Converts normalized Fanvue spend / purchase data into a clean buyer tier.

    This service does NOT fetch API data.
    It only classifies normalized buyer metrics.

    Section 6 hardened:
    Recent-offer checks are scoped by:
    - fanvue_account_id
    - fanvue_user_id
    """

    def classify_buyer(
        self,
        total_spend: float = 0,
        purchase_count: int = 0,
        is_top_spender: bool = False,
    ) -> dict:
        total_spend = float(total_spend or 0)
        purchase_count = int(purchase_count or 0)

        avg_spend = 0
        if purchase_count > 0:
            avg_spend = round(total_spend / purchase_count, 2)

        if is_top_spender or total_spend >= 500:
            classification = "WHALE"
            user_value_tier = "whale"
            is_whale = True

        elif total_spend >= 150:
            classification = "HIGH_VALUE"
            user_value_tier = "high"
            is_whale = False

        elif purchase_count >= 2 or total_spend >= 25:
            classification = "ACTIVE_BUYER"
            user_value_tier = "medium"
            is_whale = False

        elif total_spend > 0:
            classification = "LOW_SPENDER"
            user_value_tier = "low"
            is_whale = False

        else:
            classification = "NON_BUYER"
            user_value_tier = "cold"
            is_whale = False

        return {
            "buyer_classification": classification,
            "user_value_tier": user_value_tier,
            "is_whale": is_whale,
            "is_spender": total_spend > 0,
            "is_top_spender": bool(is_top_spender),
            "total_spend": total_spend,
            "purchase_count": purchase_count,
            "avg_spend_per_purchase": avg_spend,
        }

    def _has_recent_offer(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> bool:
        if not fanvue_account_id or not fanvue_user_id:
            return False

        from app.database import get_db_connection

        sql = """
            SELECT 1
            FROM content_usage_log
            WHERE fanvue_account_id = %s
              AND fanvue_user_id = %s
              AND usage_type = 'ppv_sent'
              AND created_at >= NOW() - INTERVAL '24 HOURS'
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        fanvue_account_id,
                        str(fanvue_user_id),
                    ),
                )
                return cur.fetchone() is not None