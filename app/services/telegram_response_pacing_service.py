"""Canonical humanized delay policy for Ava private Telegram replies."""
from __future__ import annotations

import asyncio
import os
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class TelegramResponsePacingDecision:
    mode: str
    policy: str
    calculated_delay_ms: int
    applied_delay_ms: int
    reason: str
    bypass_reason: str | None = None
    controlled_identity: bool = False

    def diagnostics(self):
        return {
            "mode": self.mode, "policy": self.policy,
            "canonicalSource": "TelegramResponsePacingService",
            "calculatedDelayMs": self.calculated_delay_ms,
            "calculatedDelaySeconds": round(self.calculated_delay_ms / 1000, 3),
            "appliedDelayMs": self.applied_delay_ms,
            "applied": self.applied_delay_ms > 0,
            "bypassed": self.applied_delay_ms == 0,
            "bypassReason": self.bypass_reason,
            "controlledIdentity": self.controlled_identity,
            "restoreMarker": (
                "SESSION_5_PACING_BYPASS_ACTIVE"
                if self.bypass_reason == "SESSION_5_ADVERSARIAL_CERTIFICATION"
                else None
            ),
            "certificationExitRequired": (
                self.bypass_reason == "SESSION_5_ADVERSARIAL_CERTIFICATION"
            ),
            "typingBehavior": "BOUNDED_PRE_SEND_DELAY",
            "wouldHaveWaitedSeconds": round(self.calculated_delay_ms / 1000, 3),
            "reason": self.reason,
        }


class TelegramResponsePacingService:
    """One calculation for production waits and controlled shadow evaluation."""

    POLICY = "AVA_PRIVATE_CHAT_HUMANIZED_V1"

    def __init__(self, *, variance=None, sleeper=asyncio.sleep):
        self._variance = variance or (lambda: random.uniform(0.86, 1.14))
        self._sleeper = sleeper

    def calculate(self, *, inbound_text: str, reply_text: str,
                  commercial: bool = False, acknowledgement: bool = False,
                  shadow: bool = False,
                  telegram_user_id: int | None = None) -> TelegramResponsePacingDecision:
        inbound_words = len((inbound_text or "").split())
        reply_words = len((reply_text or "").split())
        complexity = min(2400, max(0, inbound_words - 5) * 85)
        composition = min(5200, reply_words * 145)
        base = 900 if reply_words <= 6 else 1450
        reason = "short casual reaction" if reply_words <= 6 else "reply length and conversational complexity"
        if commercial:
            base, composition = 750, min(composition, 2500)
            reason = "commerce close kept responsive"
        if acknowledgement:
            base, composition = 850, min(composition, 2100)
            reason = "purchase acknowledgement kept responsive"
        delay = int(max(650, min(9000, (base + complexity + composition) * float(self._variance()))))
        configured = str(os.getenv("CONTROLLED_AUTONOMY_TELEGRAM_USER_ID") or "").strip()
        controlled = bool(configured and str(telegram_user_id or "") == configured)
        session_five = (
            str(os.getenv("SESSION_5_PACING_BYPASS_ENABLED", "false")).strip().lower()
            in {"1", "true", "yes", "on"}
        )
        bypass_reason = None
        mode = "APPLIED"
        applied = delay
        if shadow:
            mode, applied, bypass_reason = "SHADOW", 0, "SHADOW_MODE"
        elif controlled and session_five:
            mode, applied, bypass_reason = (
                "SESSION_5_TEST_BYPASS", 0,
                "SESSION_5_ADVERSARIAL_CERTIFICATION",
            )
        return TelegramResponsePacingDecision(
            mode=mode, policy=self.POLICY, calculated_delay_ms=delay,
            applied_delay_ms=applied, reason=reason,
            bypass_reason=bypass_reason, controlled_identity=controlled,
        )

    async def wait(self, decision: TelegramResponsePacingDecision) -> None:
        if decision.applied_delay_ms > 0:
            await self._sleeper(decision.applied_delay_ms / 1000)
