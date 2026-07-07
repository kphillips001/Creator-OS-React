from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)


class RealtimeBuyerStateService:
    """
    Step 5.1 — Mass PPV safety gate.

    3D.14.6 — RealtimeBuyerStateService Integration

    Determines whether a user is safe to receive Mass PPV.

    Protects users based on:
    - recent offers
    - recent purchases
    - active chat
    - pending PPV
    - buyer sessions
    - close-ready state
    - realtime monetization suppression signals

    Section 6 hardened:
    All buyer-state checks are scoped by:
    - fanvue_account_id
    - fanvue_user_id
    """

    def __init__(self):
        self.mass_ppv_suppression_service = (
            MassPPVSuppressionSignalService()
        )

    def _as_text_id(self, fanvue_user_id) -> str:
        return str(fanvue_user_id)

    def _has_recent_offer(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> bool:
        fanvue_user_id = self._as_text_id(fanvue_user_id)

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
                        fanvue_user_id,
                    ),
                )
                row = cur.fetchone()

        has_recent_offer = row is not None
        print(f"[REALTIME CHECK] recent_offer={has_recent_offer}")

        return has_recent_offer

    def _has_recent_purchase(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> bool:
        fanvue_user_id = self._as_text_id(fanvue_user_id)

        from app.database import get_db_connection

        sql = """
            SELECT 1
            FROM content_usage_log
            WHERE fanvue_account_id = %s
              AND fanvue_user_id = %s
              AND usage_type = 'ppv_purchased'
              AND created_at >= NOW() - INTERVAL '24 HOURS'
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        fanvue_account_id,
                        fanvue_user_id,
                    ),
                )
                row = cur.fetchone()

        has_recent_purchase = row is not None
        print(f"[REALTIME CHECK] recent_purchase={has_recent_purchase}")

        return has_recent_purchase

    def _is_actively_chatting(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> bool:
        from app.database import get_db_connection

        sql = """
            SELECT 1
            FROM fanvue_chat_messages m
            JOIN fanvue_users u
                ON u.fanvue_user_uuid::text = m.fanvue_user_uuid::text
               AND u.fanvue_account_id = m.fanvue_account_id
            WHERE u.fanvue_account_id = %s
              AND u.id = %s
              AND m.sender_uuid::text = m.fanvue_user_uuid::text
              AND m.created_at >= NOW() - INTERVAL '15 MINUTES'
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        fanvue_account_id,
                        fanvue_user_id,
                    ),
                )
                row = cur.fetchone()

        is_active = row is not None
        print(f"[REALTIME CHECK] is_actively_chatting={is_active}")

        return is_active

    def _get_buyer_level(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> str:
        from app.database import get_db_connection

        sql = """
            SELECT
                relationship_status,
                is_subscriber,
                last_purchase_at
            FROM fanvue_users
            WHERE fanvue_account_id = %s
              AND id = %s
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        fanvue_account_id,
                        fanvue_user_id,
                    ),
                )
                row = cur.fetchone()

        if not row:
            print("[REALTIME CHECK] buyer_level=LOW (default: no fanvue_users row)")
            return "LOW"

        relationship_status = (row.get("relationship_status") or "").lower()
        is_subscriber = bool(row.get("is_subscriber"))
        last_purchase_at = row.get("last_purchase_at")

        if last_purchase_at:
            level = "MID"
        elif is_subscriber or relationship_status == "subscriber":
            level = "MID"
        else:
            level = "LOW"

        print(f"[REALTIME CHECK] buyer_level={level}")

        return level

    def _has_active_session(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> bool:
        fanvue_user_id = self._as_text_id(fanvue_user_id)

        from app.database import get_db_connection

        sql = """
            SELECT
                buyer_session_active,
                buyer_session_step,
                buyer_session_cooldown_until,
                buyer_session_ended_at
            FROM user_memory
            WHERE fanvue_account_id = %s
              AND fanvue_user_id = %s
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        fanvue_account_id,
                        fanvue_user_id,
                    ),
                )
                row = cur.fetchone()

        if not row:
            print("[REALTIME CHECK] has_active_session=False (no user_memory row)")
            return False

        buyer_session_active = bool(row.get("buyer_session_active"))
        buyer_session_step = str(row.get("buyer_session_step") or "").lower()
        buyer_session_cooldown_until = row.get("buyer_session_cooldown_until")
        buyer_session_ended_at = row.get("buyer_session_ended_at")

        active_steps = {
            "bridge",
            "build_tension",
            "controlled_ppv",
            "offer",
            "close",
            "close_mode",
        }

        if buyer_session_active:
            print("[REALTIME CHECK] has_active_session=True (buyer_session_active)")
            return True

        if buyer_session_step in active_steps and not buyer_session_ended_at:
            print(
                f"[REALTIME CHECK] has_active_session=True "
                f"(buyer_session_step={buyer_session_step})"
            )
            return True

        if buyer_session_cooldown_until and not buyer_session_ended_at:
            print("[REALTIME CHECK] has_active_session=True (buyer_session_cooldown)")
            return True

        print("[REALTIME CHECK] has_active_session=False")
        return False

    def _is_close_ready(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> bool:
        fanvue_user_id = self._as_text_id(fanvue_user_id)

        from app.database import get_db_connection

        sql = """
            SELECT
                intent_score,
                heat_score,
                conversation_mode,
                buyer_tier,
                user_value_tier,
                is_whale,
                is_top_spender,
                buyer_classification
            FROM user_memory
            WHERE fanvue_account_id = %s
              AND fanvue_user_id = %s
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        fanvue_account_id,
                        fanvue_user_id,
                    ),
                )
                row = cur.fetchone()

        if not row:
            print("[REALTIME CHECK] is_close_ready=False (no user_memory row)")
            return False

        intent_score = row.get("intent_score") or 0
        heat_score = row.get("heat_score") or 0
        conversation_mode = (row.get("conversation_mode") or "").lower()
        buyer_tier = (row.get("buyer_tier") or "").lower()
        user_value_tier = (row.get("user_value_tier") or "").lower()
        buyer_classification = (row.get("buyer_classification") or "").lower()
        is_whale = bool(row.get("is_whale"))
        is_top_spender = bool(row.get("is_top_spender"))

        is_high_intent = intent_score >= 0.75
        is_hot = heat_score >= 0.75

        is_close_mode = conversation_mode in {
            "offer",
            "close",
            "close_mode",
            "conversion",
        }

        is_high_value = (
            buyer_tier in {"high", "whale", "high_value", "active_buyer"}
            or user_value_tier in {"high", "whale", "high_value"}
            or buyer_classification in {"high_value", "whale"}
        )

        is_spender = is_whale or is_top_spender

        is_ready = any(
            [
                is_high_intent,
                is_hot,
                is_close_mode,
                is_high_value,
                is_spender,
            ]
        )

        print(
            f"[REALTIME CHECK] is_close_ready={is_ready} | "
            f"intent={intent_score}, heat={heat_score}, mode={conversation_mode}, "
            f"tier={buyer_tier}, value={user_value_tier}, whale={is_whale}"
        )

        return is_ready

    def _get_mass_ppv_suppression_profile(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> dict:
        profile = (
            self.mass_ppv_suppression_service
            .get_suppression_signals(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )
        )

        print("[REALTIME CHECK] mass_ppv_suppression_profile=")
        print(profile)

        return profile

    def _has_pending_ppv_offer(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> dict:
        fanvue_user_id = self._as_text_id(fanvue_user_id)

        from app.database import get_db_connection
        from datetime import datetime

        sql = """
            SELECT sent.created_at
            FROM content_usage_log sent
            WHERE sent.fanvue_account_id = %s
              AND sent.fanvue_user_id = %s
              AND sent.usage_type = 'ppv_sent'
              AND sent.created_at >= NOW() - INTERVAL '48 HOURS'
              AND NOT EXISTS (
                  SELECT 1
                  FROM content_usage_log purchased
                  WHERE purchased.fanvue_account_id = sent.fanvue_account_id
                    AND purchased.fanvue_user_id = sent.fanvue_user_id
                    AND purchased.content_item_id = sent.content_item_id
                    AND purchased.usage_type = 'ppv_purchased'
                    AND purchased.created_at >= sent.created_at
              )
            ORDER BY sent.created_at DESC
            LIMIT 1
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        fanvue_account_id,
                        fanvue_user_id,
                    ),
                )
                row = cur.fetchone()

        if not row:
            print("[REALTIME CHECK] pending_ppv=False")
            return {
                "has_pending": False,
                "sent_at": None,
                "hours_since_sent": None,
            }

        sent_at = row["created_at"]

        if sent_at.tzinfo is not None:
            now = datetime.now(sent_at.tzinfo)
        else:
            now = datetime.now()

        hours_since = (now - sent_at).total_seconds() / 3600

        print(
            f"[REALTIME CHECK] pending_ppv=True "
            f"(sent {round(hours_since, 2)}h ago)"
        )

        return {
            "has_pending": True,
            "sent_at": sent_at,
            "hours_since_sent": hours_since,
        }

    def get_buyer_state(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ) -> dict:
        print("[REALTIME BUYER STATE]")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"fanvue_user_id={fanvue_user_id}")

        if not fanvue_account_id:
            return {
                "error": "missing_fanvue_account_id",
                "buyer_level": "LOW",
                "has_active_session": False,
                "recent_offer": False,
                "recent_purchase": False,
                "pending_ppv": False,
                "pending_ppv_data": {
                    "has_pending": False,
                    "sent_at": None,
                    "hours_since_sent": None,
                },
                "is_close_ready": False,
                "is_actively_chatting": False,
                "mass_ppv_suppressed": True,
                "mass_ppv_suppression_profile": {
                    "suppressed": True,
                    "reasons": ["missing_fanvue_account_id"],
                },
            }

        if not fanvue_user_id:
            return {
                "error": "missing_fanvue_user_id",
                "buyer_level": "LOW",
                "has_active_session": False,
                "recent_offer": False,
                "recent_purchase": False,
                "pending_ppv": False,
                "pending_ppv_data": {
                    "has_pending": False,
                    "sent_at": None,
                    "hours_since_sent": None,
                },
                "is_close_ready": False,
                "is_actively_chatting": False,
                "mass_ppv_suppressed": True,
                "mass_ppv_suppression_profile": {
                    "suppressed": True,
                    "reasons": ["missing_fanvue_user_id"],
                },
            }

        pending_ppv_data = self._has_pending_ppv_offer(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        suppression_profile = self._get_mass_ppv_suppression_profile(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        return {
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "buyer_level": self._get_buyer_level(
                fanvue_account_id,
                fanvue_user_id,
            ),
            "has_active_session": self._has_active_session(
                fanvue_account_id,
                fanvue_user_id,
            ),
            "recent_offer": self._has_recent_offer(
                fanvue_account_id,
                fanvue_user_id,
            ),
            "recent_purchase": self._has_recent_purchase(
                fanvue_account_id,
                fanvue_user_id,
            ),
            "pending_ppv": pending_ppv_data["has_pending"],
            "pending_ppv_data": pending_ppv_data,
            "is_close_ready": self._is_close_ready(
                fanvue_account_id,
                fanvue_user_id,
            ),
            "is_actively_chatting": self._is_actively_chatting(
                fanvue_account_id,
                fanvue_user_id,
            ),
            "mass_ppv_suppressed": suppression_profile.get(
                "suppressed",
                False,
            ),
            "mass_ppv_suppression_profile": suppression_profile,
        }

    def is_eligible_for_mass_ppv(
        self,
        fanvue_account_id: int | dict,
        fanvue_user_id: int | None = None,
    ) -> dict:
        """
        Step 5.9 — Final Eligibility Decision

        3D.14.6:
        Adds Mass PPV suppression profile into live eligibility.

        3E + Section 6 hardening:
        Supports either:
        - prebuilt buyer state dict
        - fanvue_account_id + fanvue_user_id
        """

        if isinstance(fanvue_account_id, dict):
            print("[CHECK MASS PPV ELIGIBILITY]")
            print("[MASS PPV ELIGIBILITY] Existing buyer state received")
            state = fanvue_account_id
        else:
            print("[CHECK MASS PPV ELIGIBILITY]")
            state = self.get_buyer_state(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )

        block_reasons = []

        suppression_profile = state.get(
            "mass_ppv_suppression_profile",
            {},
        )

        if state.get("pending_ppv"):
            block_reasons.append("pending_ppv")

        if state.get("recent_offer"):
            block_reasons.append("recent_offer")

        if state.get("recent_purchase"):
            block_reasons.append("recent_purchase")

        if state.get("has_active_session"):
            block_reasons.append("active_session")

        if state.get("is_close_ready"):
            block_reasons.append("close_ready")

        if state.get("is_actively_chatting"):
            block_reasons.append("active_chat")

        if state.get("buyer_level") in ["HIGH", "WHALE"]:
            block_reasons.append("high_value_user")

        if suppression_profile.get("suppressed"):
            block_reasons.append("mass_ppv_suppressed")

            for reason in suppression_profile.get("reasons", []):
                if reason not in block_reasons:
                    block_reasons.append(reason)

        allowed = len(block_reasons) == 0
        primary_reason = block_reasons[0] if block_reasons else None

        result = {
            "allowed": allowed,
            "blocked": not allowed,
            "block_reason": primary_reason,
            "block_reasons": block_reasons,
            "suppression_profile": suppression_profile,
            "state": state,
        }

        print("\n[FINAL ELIGIBILITY RESULT]")
        print(result)

        return result