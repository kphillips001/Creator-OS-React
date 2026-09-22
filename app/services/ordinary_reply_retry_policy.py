"""Canonical retry semantics shared by ordinary-reply scheduling and projection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OrdinaryReplyRetryDecision:
    category: str | None
    scheduler_eligible: bool
    exhausted: bool
    actionable_at: datetime | None

    def due(self, now: datetime) -> bool:
        return bool(self.scheduler_eligible and self.actionable_at
                    and self.actionable_at <= now and not self.exhausted)


class OrdinaryReplyRetryPolicy:
    """Fail-closed taxonomy for definitively-unsent generation retries."""

    EXACT_REASONS = {
        "availability_deferred": "AVAILABILITY",
        "quality_corrective_retry_scheduled": "QUALITY_CORRECTIVE",
        "global_delivery_readiness_deferred": "GLOBAL_READINESS",
        "historical_survivor_reconciliation_scheduled": "SURVIVOR_RECONCILIATION",
    }
    PREFIX_REASONS = {
        "DECISION_ENGINE_EXCEPTION:": "DECISION_ENGINE_EXCEPTION",
        "EMPTY_GENERATION:": "EMPTY_GENERATION",
        "GENERATION_FAILURE:": "GENERATION_FAILURE",
    }

    @classmethod
    def category(cls, reason: str | None) -> str | None:
        value = str(reason or "")
        if value in cls.EXACT_REASONS:
            return cls.EXACT_REASONS[value]
        return next((category for prefix, category in cls.PREFIX_REASONS.items()
                     if value.startswith(prefix)), None)

    @classmethod
    def evaluate(cls, *, state, reason, next_retry_at, generation_attempts,
                 max_generation_attempts, send_attempts, has_response_payload,
                 outbound_telegram_message_id=None, sent_confirmed_at=None,
                 has_active_claim=False) -> OrdinaryReplyRetryDecision:
        category = cls.category(reason)
        exhausted = int(generation_attempts or 0) >= int(max_generation_attempts or 0)
        safe_shape = bool(
            str(getattr(state, "value", state) or "") == "RETRYABLE"
            and category is not None
            and not has_response_payload
            and int(send_attempts or 0) == 0
            and outbound_telegram_message_id is None
            and sent_confirmed_at is None
            and not has_active_claim
        )
        return OrdinaryReplyRetryDecision(
            category=category,
            scheduler_eligible=bool(safe_shape and next_retry_at and not exhausted),
            exhausted=exhausted,
            actionable_at=next_retry_at,
        )

    @classmethod
    def sql_reason_predicate(cls, column: str) -> str:
        exact = ",".join("'%s'" % value.replace("'", "''")
                         for value in cls.EXACT_REASONS)
        prefixes = " OR ".join(
            f"{column} LIKE '{prefix.replace(chr(39), chr(39)*2)}%%'"
            for prefix in cls.PREFIX_REASONS)
        return f"({column} IN ({exact}) OR {prefixes})"
