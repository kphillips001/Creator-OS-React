from datetime import datetime, timezone, timedelta

from app.database import get_db_connection


class MassPPVSuppressionSignalService:
    """
    3D.14 — Mass PPV Suppression Integration

    Builds realtime Mass PPV suppression signals from:
    - buyer_intelligence
    - user_memory
    - realtime monetization memory

    Purpose:
    Protect active spenders from cheap Mass PPV broadcasts.

    Section 6 hardened:
    Suppression signals are scoped by:
    - fanvue_account_id
    - fanvue_user_id
    """

    PROTECTED_BUYER_TIERS = {
        "ACTIVE_BUYER",
        "HIGH_VALUE",
        "WHALE",
    }

    PREMIUM_RUNTIME_MODES = {
        "premium_gate",
        "premium",
        "exclusive",
    }

    PREMIUM_RUNTIME_BLOCK_MODES = {
        "premium_gate",
        "premium",
        "exclusive",
        "close_mode",
    }

    HIGH_CONFIDENCE_VALUES = {
        "high",
        "very_high",
        "premium",
    }

    PREMIUM_ONLY_BUYER_TIERS = {
        "ACTIVE_BUYER",
        "HIGH_VALUE",
        "WHALE",
    }

    PREMIUM_ONLY_VALUE_TIERS = {
        "HIGH_VALUE",
        "WHALE",
    }

    ACTIVE_POST_PURCHASE_FIELDS = [
        "thank_you_flow_active",
        "tip_reward_flow_active",
        "subscriber_welcome_flow_active",
        "premium_followup_active",
        "delayed_followup_active",
        "reaction_pipeline_active",
    ]

    PURCHASE_SUPPRESSION_HOURS = 48
    TIP_SUPPRESSION_HOURS = 24

    def get_suppression_signals(
        self,
        fanvue_account_id: int,
        fanvue_user_id,
    ):
        if not fanvue_account_id:
            return self._empty_profile(
                fanvue_account_id=None,
                fanvue_user_id=fanvue_user_id,
                suppressed=True,
                reason="missing_fanvue_account_id",
            )

        if not fanvue_user_id:
            return self._empty_profile(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=None,
                suppressed=True,
                reason="missing_fanvue_user_id",
            )

        buyer = self._get_buyer_intelligence(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        memory = self._get_user_memory(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        reasons = []

        buyer_tier = self._normalize_upper(
            self._first_value(
                buyer,
                memory,
                "buyer_tier",
            )
        )

        user_value_tier = self._normalize_upper(
            self._first_value(
                memory,
                buyer,
                "user_value_tier",
            )
        )

        runtime_mode = self._safe_lower(
            self._first_value(
                memory,
                buyer,
                "runtime_mode",
            )
        )

        spender_confidence = self._safe_lower(
            self._first_value(
                memory,
                buyer,
                "spender_confidence",
            )
        )

        recent_purchase_active = (
            self._is_recent_purchase_active(
                memory,
                buyer,
            )
        )

        recent_tip_active = (
            self._is_recent_tip_active(
                memory,
                buyer,
            )
        )

        premium_sexting_allowed = self._truthy(
            self._first_value(
                memory,
                buyer,
                "premium_sexting_allowed",
            )
        )

        premium_intimacy_eligible = premium_sexting_allowed

        is_whale = self._truthy(
            self._first_value(
                memory,
                buyer,
                "is_whale",
            )
        )

        is_top_spender = self._truthy(
            self._first_value(
                memory,
                buyer,
                "is_top_spender",
            )
        )

        active_post_purchase_flows = (
            self._get_active_post_purchase_flows(
                memory,
                buyer,
            )
        )

        if recent_purchase_active:
            reasons.append("recent_purchase")

        if recent_tip_active:
            reasons.append("recent_tip")

        if premium_intimacy_eligible:
            reasons.append("premium_intimacy_eligible")

        if premium_sexting_allowed:
            reasons.append("premium_sexting_allowed")

        if runtime_mode in self.PREMIUM_RUNTIME_BLOCK_MODES:
            reasons.append(
                f"premium_runtime_mode:{runtime_mode}"
            )

        if spender_confidence in self.HIGH_CONFIDENCE_VALUES:
            reasons.append(
                f"high_spender_confidence:{spender_confidence}"
            )

        if buyer_tier in self.PROTECTED_BUYER_TIERS:
            reasons.append(
                f"protected_buyer_tier:{buyer_tier}"
            )

        if buyer_tier in self.PREMIUM_ONLY_BUYER_TIERS:
            reasons.append(
                f"premium_only_buyer_tier:{buyer_tier}"
            )

        if user_value_tier in self.PROTECTED_BUYER_TIERS:
            reasons.append(
                f"protected_value_tier:{user_value_tier}"
            )

        if user_value_tier in self.PREMIUM_ONLY_VALUE_TIERS:
            reasons.append(
                f"premium_only_value_tier:{user_value_tier}"
            )

        if is_whale:
            reasons.append("whale")

        if is_top_spender:
            reasons.append("top_spender")

        for flow in active_post_purchase_flows:
            reasons.append(
                f"active_post_purchase_flow:{flow}"
            )

        reasons = self._dedupe_list(reasons)

        suppressed = len(reasons) > 0

        premium_only_treatment = (
            buyer_tier in self.PREMIUM_ONLY_BUYER_TIERS
            or user_value_tier in self.PREMIUM_ONLY_VALUE_TIERS
            or is_whale
            or is_top_spender
            or premium_intimacy_eligible
        )

        return {
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "suppressed": suppressed,
            "primary_reason": reasons[0] if reasons else None,
            "reasons": reasons,
            "premium_only_treatment": premium_only_treatment,
            "signals": {
                "buyer_tier": buyer_tier,
                "user_value_tier": user_value_tier,
                "runtime_mode": runtime_mode,
                "recent_purchase_active": recent_purchase_active,
                "recent_tip_active": recent_tip_active,
                "premium_intimacy_eligible": premium_intimacy_eligible,
                "premium_sexting_allowed": premium_sexting_allowed,
                "spender_confidence": spender_confidence,
                "is_whale": is_whale,
                "is_top_spender": is_top_spender,
                "active_post_purchase_flows": active_post_purchase_flows,
            },
        }

    def _get_buyer_intelligence(
        self,
        fanvue_account_id: int,
        fanvue_user_id,
    ):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM buyer_intelligence
                    WHERE fanvue_account_id = %s
                      AND fanvue_user_id = %s
                    LIMIT 1
                    """,
                    (
                        fanvue_account_id,
                        str(fanvue_user_id),
                    ),
                )

                row = cur.fetchone()

        if not row:
            return {}

        return dict(row)

    def _get_user_memory(
        self,
        fanvue_account_id: int,
        fanvue_user_id,
    ):
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM user_memory
                    WHERE fanvue_account_id = %s
                      AND fanvue_user_id = %s
                    LIMIT 1
                    """,
                    (
                        fanvue_account_id,
                        str(fanvue_user_id),
                    ),
                )

                row = cur.fetchone()

        if not row:
            return {}

        return dict(row)

    def _get_active_post_purchase_flows(
        self,
        memory,
        buyer,
    ):
        active = []

        for field in self.ACTIVE_POST_PURCHASE_FIELDS:
            value = self._first_value(
                memory,
                buyer,
                field,
            )

            if self._truthy(value):
                active.append(field)

        return active

    def _is_recent_purchase_active(self, memory, buyer):
        last_purchase_at = self._first_value(
            memory,
            buyer,
            "last_purchase_at",
        )

        if not last_purchase_at:
            return False

        parsed = self._safe_parse_datetime(last_purchase_at)

        if not parsed:
            return False

        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(hours=self.PURCHASE_SUPPRESSION_HOURS)
        )

        return parsed >= cutoff

    def _is_recent_tip_active(self, memory, buyer):
        last_tip_at = self._first_value(
            memory,
            buyer,
            "last_tip_at",
        )

        if not last_tip_at:
            return False

        parsed = self._safe_parse_datetime(last_tip_at)

        if not parsed:
            return False

        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(hours=self.TIP_SUPPRESSION_HOURS)
        )

        return parsed >= cutoff

    def _safe_parse_datetime(self, value):
        if not value:
            return None

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)

            return value

        try:
            parsed = datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed

        except Exception:
            return None

    def _first_value(self, primary, secondary, key):
        value = primary.get(key)

        if value is not None:
            return value

        return secondary.get(key)

    def _truthy(self, value):
        return value in [
            True,
            "true",
            "True",
            "TRUE",
            1,
            "1",
            "yes",
            "YES",
        ]

    def _safe_lower(self, value):
        if not value:
            return None

        return str(value).lower()

    def _normalize_upper(self, value):
        if not value:
            return None

        return str(value).upper()

    def _dedupe_list(self, items):
        deduped = []

        for item in items:
            if item not in deduped:
                deduped.append(item)

        return deduped

    def _empty_profile(
        self,
        fanvue_account_id,
        fanvue_user_id,
        suppressed,
        reason,
    ):
        return {
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "suppressed": suppressed,
            "primary_reason": reason,
            "reasons": [reason],
            "premium_only_treatment": False,
            "signals": {},
        }