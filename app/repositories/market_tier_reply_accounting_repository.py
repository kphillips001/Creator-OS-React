"""Read authority for idempotent confirmed ordinary-reply accounting."""
from app.database import get_db_connection


class MarketTierReplyAccountingRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def count_between(self, *, business_day_start, business_day_end, **scope):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT COUNT(*) AS replies_used
                FROM market_tier_confirmed_reply_events
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                  AND resource_classification='ORDINARY_NONCOMMERCIAL'
                  AND confirmed_at>=%s AND confirmed_at<%s""", (
                scope["creator_profile_id"], scope["fanvue_account_id"],
                scope["telegram_user_id"], scope["telegram_chat_id"],
                business_day_start, business_day_end))
            row = cursor.fetchone()
        return int((row or {}).get("replies_used") or 0)
