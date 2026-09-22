"""Derived repeated-sexual-escalation commercial policy; no persistence."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


class SexualSalesOpportunityService:
    """Derive opportunity/cooldown state from confirmed PurchaseIntent history."""

    COMPLIMENT = re.compile(
        r"\b(?:you(?:'re| are| look| have)?\s+(?:such\s+|so\s+)?(?:sexy|hot|gorgeous|beautiful)(?:\s+curves)?|"
        r"love your (?:body|look|outfit)|what a (?:body|babe))\b", re.I,
    )
    ESCALATION = re.compile(
        r"\b(?:horny|naked|nude|take (?:it|your clothes) off|touch (?:you|your)|"
        r"kiss (?:you|your)|lick (?:you|your)|fuck|cock|dick|puss(?:y)?|clit|nipple|cum|orgasm|hard[ -]?on|"
        r"finger(?:ing|s)?|suck(?:ing)?|thrust(?:ing)?|what would you do to me|"
        r"in bed|turn(?:ed|ing)? (?:me|you) on)\b", re.I,
    )

    TERMINAL_MISS = frozenset({
        "EXPIRED", "ABANDONED", "SUPERSEDED", "ADMIN_CLOSED",
    })

    def __init__(self, *, intents, cooldown: timedelta,
                 max_opportunities: int = 3,
                 episode_separation: timedelta = timedelta(hours=6)):
        self.intents = intents
        self.cooldown = cooldown
        self.maximum = max(1, int(max_opportunities))
        self.episode_separation = episode_separation

    def classify(self, message: str, *, tone=None, commercial=False,
                 customer_heat_signal=None) -> str:
        text = str(message or "").strip()
        if commercial:
            return "CURRENT_COMMERCIAL_INTEREST"
        heat = dict(customer_heat_signal or {})
        if heat.get("warmupOverrideEligible") is True:
            if heat.get("type") in {
                "CURRENT_COMMERCIAL_INTEREST", "INTIMATE_CONTENT_REQUEST",
                "INTIMATE_CONTENT_INTEREST",
            }:
                return "CURRENT_COMMERCIAL_INTEREST"
            return "SEXUAL_ESCALATION"
        if self.ESCALATION.search(text):
            return "SEXUAL_ESCALATION"
        if self.COMPLIMENT.search(text):
            return "SEXUAL_ATTRACTIVE_COMPLIMENT"
        if dict(tone or {}).get("sexualOrProvocative") is True:
            return "SEXUAL_ATTRACTIVE_COMPLIMENT"
        return "NONE"

    def project(self, *, creator_profile_id: int, fanvue_account_id: int,
                telegram_user_id: int, latest_message: str, now: datetime,
                tone=None, commercial_signal=False,
                ordinary_topic_after_last_offer=False,
                customer_heat_signal=None) -> dict:
        now = self._aware(now)
        reader = getattr(self.intents, "list_confirmed_presentations_for_buyer", None)
        rows = tuple(reader(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )) if callable(reader) else ()
        signal = self.classify(
            latest_message, tone=tone, commercial=commercial_signal,
            customer_heat_signal=customer_heat_signal,
        )
        purchased = next((row for row in rows if self._status(row) == "PURCHASED"), None)
        misses = tuple(row for row in rows if self._status(row) in self.TERMINAL_MISS)
        last = rows[0] if rows else None
        last_at = self._aware(getattr(last, "presented_at", None)) if last else None
        used_total = len(misses)
        exhausted_at = self._aware(getattr(misses[0], "presented_at", None)) \
            if used_total >= self.maximum else None
        cooldown_until = exhausted_at + self.cooldown if exhausted_at else None
        cooldown_active = bool(cooldown_until and now < cooldown_until)
        post_cooldown = bool(exhausted_at and not cooldown_active)
        active_unresolved = any(self._status(row) in {
            "PRESENTED", "CLICKED", "UNKNOWN"
        } for row in rows)
        active_row = next((row for row in rows if self._status(row) in {
            "PRESENTED", "CLICKED", "UNKNOWN"
        }), None)
        separated = bool(
            last_at is None or ordinary_topic_after_last_offer
            or now - last_at >= self.episode_separation
        )
        new_episode = bool(signal == "SEXUAL_ESCALATION" and separated
                           and not active_unresolved)
        effective_used = min(used_total, self.maximum)
        # Decay grants one renewed chance, rather than resetting history to zero.
        opportunity_number = self.maximum if post_cooldown else effective_used + 1
        eligible = bool(
            signal == "SEXUAL_ESCALATION" and new_episode and not cooldown_active
            and purchased is None
            and (used_total < self.maximum or post_cooldown)
        )
        reason = (
            "CURRENT_COMMERCIAL_SIGNAL_OVERRIDE" if signal == "CURRENT_COMMERCIAL_INTEREST" else
            "BUYER_LIFECYCLE_AUTHORITATIVE" if purchased is not None else
            "SEXUAL_SALES_COOLDOWN_ACTIVE" if cooldown_active else
            "ACTIVE_OR_UNSETTLED_PRESENTATION" if active_unresolved else
            "SAME_SEXUAL_SALES_EPISODE" if signal == "SEXUAL_ESCALATION" and not separated else
            "SEXUAL_COMPLIMENT_ONLY" if signal == "SEXUAL_ATTRACTIVE_COMPLIMENT" else
            "NEW_SEXUAL_SALES_EPISODE" if eligible else "NO_SEXUAL_ESCALATION"
        )
        episode_id = (
            f"sexual:{telegram_user_id}:{int(now.timestamp() // max(1, int(self.episode_separation.total_seconds())))}"
            if new_episode else None
        )
        return {
            "sexualSignalClass": signal,
            "sexualSalesEpisodeId": episode_id,
            "sexualSalesOpportunityEligible": eligible,
            "sexualSalesOpportunitiesUsed": effective_used,
            "sexualSalesOpportunityNumber": opportunity_number if eligible else None,
            "sexualSalesCooldownActive": cooldown_active,
            "sexualSalesCooldownUntil": cooldown_until.isoformat() if cooldown_until else None,
            "sexualSalesEligibilityReason": reason,
            "sexualSalesSuppressionReason": None if eligible else reason,
            "commercialSignalOverride": signal == "CURRENT_COMMERCIAL_INTEREST",
            "confirmedPresentationCount": len(rows),
            "unsuccessfulPresentationCount": used_total,
            "activeUnresolvedPresentation": active_unresolved,
            "activePresentationBridge": bool(
                active_unresolved
                and signal in {"NONE", "SEXUAL_ATTRACTIVE_COMPLIMENT", "SEXUAL_ESCALATION"}
                and purchased is None
            ),
            "activePresentationId": (
                str(getattr(active_row, "purchase_intent_id", "")) or None
                if active_row is not None else None
            ),
            "activePresentationState": self._status(active_row) if active_row else None,
            "activePresentationBridgeReason": (
                "KEEP_RELATIONSHIP_ALIVE_WHILE_EXISTING_PRESENTATION_REMAINS_AVAILABLE"
                if active_unresolved and purchased is None else None
            ),
            "lastSexualOfferAt": last_at.isoformat() if last_at else None,
            "lastSexualOfferOutcome": self._status(last) if last else None,
            "postCooldownRenewal": post_cooldown,
            "derivedFrom": "PURCHASE_INTENT_CONFIRMED_PRESENTATIONS",
            "customerHeatSignal": dict(customer_heat_signal or {}),
        }

    @staticmethod
    def _status(row):
        value = getattr(row, "status", None)
        return str(getattr(value, "value", value) or "").upper()

    @staticmethod
    def _aware(value):
        if value is None:
            return None
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
