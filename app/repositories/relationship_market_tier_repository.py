"""Canonical audited persistence for manual relationship Market Tier."""
from uuid import uuid4

from app.database import get_db_connection
from app.models.relationship_market_tier import (
    RelationshipMarketTier, RelationshipMarketTierRecord,
)


class RelationshipMarketTierRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def active(self, **scope):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM telegram_relationship_market_tiers
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                  AND removed_at IS NULL LIMIT 1""", self._params(scope))
            row = cursor.fetchone()
        return self._model(row) if row else None

    def history(self, **scope):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM telegram_relationship_market_tiers
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                ORDER BY version""", self._params(scope))
            return [self._model(row) for row in cursor.fetchall()]

    def set(self, *, market_tier, changed_by, reason=None, **scope):
        tier = RelationshipMarketTier(market_tier)
        lock = "relationship-market-tier:" + ":".join(str(value) for value in self._params(scope))
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (lock,))
            cursor.execute("""SELECT * FROM telegram_relationship_market_tiers
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                ORDER BY version DESC FOR UPDATE""", self._params(scope))
            rows = cursor.fetchall()
            active = next((row for row in rows if row["removed_at"] is None), None)
            if active and active["market_tier"] == tier.value:
                return self._model(active), False
            identifier = uuid4()
            if active:
                cursor.execute("""UPDATE telegram_relationship_market_tiers SET
                    removed_by=%s,removed_at=NOW(),replaced_by=%s
                    WHERE market_tier_id=%s AND removed_at IS NULL""",
                    (changed_by, identifier, active["market_tier_id"]))
            version = max((int(row["version"]) for row in rows), default=0) + 1
            cursor.execute("""INSERT INTO telegram_relationship_market_tiers(
                market_tier_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id,market_tier,version,
                changed_by,reason) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *""", (identifier, *self._params(scope), tier.value,
                                  version, changed_by, reason))
            return self._model(cursor.fetchone()), True

    def remove(self, *, removed_by, **scope):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE telegram_relationship_market_tiers SET
                removed_by=%s,removed_at=NOW()
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                  AND removed_at IS NULL RETURNING *""",
                (removed_by, *self._params(scope)))
            row = cursor.fetchone()
        return self._model(row) if row else None

    def advance_eligible(self, *, telegram_user_id, telegram_chat_id, available_at,
                         high_value_prospect=False):
        """Move only latest, definitive pre-generation availability work earlier."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE ordinary_chat_reply_operations target SET
                  next_retry_at=%s,updated_at=NOW(),
                  delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)
                    || jsonb_build_object('marketTierScheduleAdvanced',true,
                         'marketTierSchedulingProfile',%s::text)
                WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                  AND telegram_chat_id=%s
                  AND inbound_sender_telegram_user_id=%s
                  AND state='RETRYABLE' AND response_payload IS NULL
                  AND last_error='availability_deferred'
                  AND generation_attempt_count=0 AND send_attempt_count=0
                  AND claim_owner IS NULL AND claimed_at IS NULL
                  AND lease_expires_at IS NULL
                  AND outbound_telegram_message_id IS NULL
                  AND next_retry_at IS NOT NULL AND %s<next_retry_at
                  AND inbound_telegram_message_id=(
                    SELECT MAX(candidate.inbound_telegram_message_id)
                    FROM ordinary_chat_reply_operations candidate
                    WHERE candidate.telegram_account_scope=target.telegram_account_scope
                      AND candidate.telegram_chat_id=target.telegram_chat_id
                      AND candidate.inbound_sender_telegram_user_id=target.inbound_sender_telegram_user_id)
                RETURNING operation_id,next_retry_at""", (
                available_at, "HIGH_HVP" if high_value_prospect else "HIGH",
                telegram_chat_id, telegram_user_id, available_at,
            ))
            row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def _params(scope):
        return tuple(int(scope[key]) for key in (
            "creator_profile_id", "fanvue_account_id",
            "telegram_user_id", "telegram_chat_id"))

    @staticmethod
    def _model(row):
        return RelationshipMarketTierRecord(
            market_tier_id=row["market_tier_id"],
            creator_profile_id=int(row["creator_profile_id"]),
            fanvue_account_id=int(row["fanvue_account_id"]),
            telegram_user_id=int(row["telegram_user_id"]),
            telegram_chat_id=int(row["telegram_chat_id"]),
            market_tier=RelationshipMarketTier(row["market_tier"]),
            version=int(row["version"]),changed_by=row["changed_by"],
            changed_at=row["changed_at"],reason=row.get("reason"),
            removed_by=row.get("removed_by"),removed_at=row.get("removed_at"),
            replaced_by=row.get("replaced_by"))
