"""Side-effect-free current-turn time and pacing authority for peak engagement."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PeakEngagementConfig:
    enabled: bool = True
    timezone_name: str = "America/Chicago"
    start: time = time(19, 0)
    end: time = time(0, 0)
    active_grace_minutes: int = 20
    availability_multiplier: float = 0.70

    @classmethod
    def from_environment(cls):
        enabled = _truthy(os.getenv("PEAK_ENGAGEMENT_ENABLED", "true"))
        zone = os.getenv("PEAK_ENGAGEMENT_TIMEZONE", "America/Chicago").strip()
        try: ZoneInfo(zone)
        except ZoneInfoNotFoundError as error:
            raise ValueError("PEAK_ENGAGEMENT_TIMEZONE must be an IANA timezone.") from error
        start = cls._parse_time(os.getenv("PEAK_ENGAGEMENT_START", "19:00"), "START")
        end = cls._parse_time(os.getenv("PEAK_ENGAGEMENT_END", "00:00"), "END")
        try:
            grace = int(os.getenv("PEAK_ENGAGEMENT_ACTIVE_GRACE_MINUTES", "20"))
            multiplier = float(os.getenv("PEAK_ENGAGEMENT_AVAILABILITY_MULTIPLIER", "0.70"))
        except ValueError as error:
            raise ValueError("Peak engagement grace and multiplier must be numeric.") from error
        if not 0 <= grace <= 120: raise ValueError("Peak engagement grace must be between 0 and 120 minutes.")
        if not 0 < multiplier <= 1: raise ValueError("Peak engagement multiplier must be in (0, 1].")
        return cls(enabled, zone, start, end, grace, multiplier)

    @staticmethod
    def _parse_time(value, label):
        try: return time.fromisoformat(str(value).strip())
        except ValueError as error:
            raise ValueError(f"PEAK_ENGAGEMENT_{label} must be HH:MM local time.") from error


@dataclass(frozen=True)
class PeakEngagementDecision:
    enabled: bool; active: bool; local_time: datetime; continuation_grace: bool
    pacing_eligible: bool; multiplier: float; investment_adjustment: str | None
    warmup_override_applied: bool; suppressed_by: str | None
    commercial_precedence: str; active_conversation_evidence: Mapping[str, Any]
    config: PeakEngagementConfig

    def diagnostics(self):
        return {"policy":"PEAK_ENGAGEMENT_V1","enabled":self.enabled,"active":self.active,
            "timezone":self.config.timezone_name,"localTime":self.local_time.isoformat(),
            "window":{"start":self.config.start.strftime("%H:%M"),"end":self.config.end.strftime("%H:%M")},
            "continuationGrace":self.continuation_grace,
            "activeConversationEvidence":dict(self.active_conversation_evidence),
            "pacingAdjustment":{"eligible":self.pacing_eligible,"multiplier":self.multiplier},
            "investmentAdjustment":self.investment_adjustment,
            "warmupOverrideApplied":self.warmup_override_applied,
            "suppressedBy":self.suppressed_by,"commercialPrecedence":self.commercial_precedence}


class PeakEngagementPolicy:
    ELIGIBLE_STATES=frozenset({"AVAILABLE","ACTIVE","INTERMITTENT"})
    def __init__(self,config=None): self.config=config or PeakEngagementConfig.from_environment()

    def evaluate(self,*,now=None,availability_state=None,confirmed_exchange_at=None,
                 current_inbound=True,ordinary_work=True,ordinary_treatment="BALANCED",
                 safety_allowed=True,customer_controls_allowed=True,human_takeover=False,
                 ignored=False,chat_enabled=True,fresh=True,burst_survivor=True,
                 send_uncertain=False,commercial_authority=False,active_commercial_session=False,
                 active_purchase_intent=False,active_presentation=False,commercial_cooldown=False,
                 commercial_delivery=False,purchase_acknowledgement=False,verified_buyer=False,
                 reduced_investment=False,low_cost_nurture=False,backoff=False,
                 explicit_disengagement=False,hostility_restraint=False,sleeping=False,
                 sleep_pending_signoff=False):
        instant=now or datetime.now(timezone.utc)
        if instant.tzinfo is None: instant=instant.replace(tzinfo=timezone.utc)
        local=instant.astimezone(ZoneInfo(self.config.timezone_name))
        continuation,evidence=self._continuation(local,confirmed_exchange_at,current_inbound)
        active=bool(self.config.enabled and (self._in_window(local) or continuation))
        commercial=bool(commercial_authority or active_commercial_session or active_purchase_intent
                        or active_presentation or commercial_cooldown or commercial_delivery)
        checks=((not self.config.enabled,"POLICY_DISABLED"),(not active,"OUTSIDE_PEAK_WINDOW"),
            (not current_inbound,"NO_CURRENT_INBOUND_OBLIGATION"),(not safety_allowed,"SAFETY_AUTHORITY"),
            (not customer_controls_allowed or not chat_enabled,"CUSTOMER_CONTROLS"),
            (human_takeover,"HUMAN_TAKEOVER"),(ignored,"RELATIONSHIP_IGNORED"),
            (not fresh,"FRESHNESS"),(not burst_survivor,"BURST_SUPERSESSION"),
            (send_uncertain,"SEND_UNCERTAIN"),(sleeping,"SLEEPING"),
            (sleep_pending_signoff,"SLEEP_PENDING_SIGNOFF"),(commercial,"COMMERCIAL_AUTHORITY"),
            (purchase_acknowledgement,"PURCHASE_ACKNOWLEDGEMENT"),(verified_buyer,"BUYER_AUTHORITY"),
            (reduced_investment,"REDUCED_INVESTMENT"),(low_cost_nurture,"LOW_COST_NURTURE"),
            (backoff,"BACKOFF"),(explicit_disengagement,"EXPLICIT_DISENGAGEMENT"),
            (hostility_restraint,"HOSTILITY_RESTRAINT"),(not ordinary_work,"NON_ORDINARY_WORK"),
            (str(availability_state or "").upper() not in self.ELIGIBLE_STATES,"AVAILABILITY_STATE_INELIGIBLE"))
        suppressed=next((reason for condition,reason in checks if condition),None)
        eligible=suppressed is None
        investment=("ORDINARY_BALANCED_TO_ENGAGED" if eligible and
                    str(ordinary_treatment).upper() in {"STANDARD","BALANCED"} else None)
        return PeakEngagementDecision(self.config.enabled,active,local,continuation,eligible,
            self.config.availability_multiplier,investment,bool(investment),suppressed,
            "CURRENT_COMMERCIAL_AUTHORITY" if commercial else "NO_CURRENT_COMMERCIAL_ACTION",
            evidence,self.config)

    def _in_window(self,local):
        current=local.timetz().replace(tzinfo=None);start,end=self.config.start,self.config.end
        return start<=current<end if start<end else current>=start or current<end

    def _continuation(self,local,confirmed,current_inbound):
        evidence={"currentInbound":bool(current_inbound),"confirmedExchangeAt":None,
                  "withinConfiguredGrace":False,"source":"RECENT_CONFIRMED_ORDINARY_EXCHANGE"}
        if not current_inbound or confirmed is None:return False,evidence
        if confirmed.tzinfo is None:confirmed=confirmed.replace(tzinfo=timezone.utc)
        zone=ZoneInfo(self.config.timezone_name);exchange=confirmed.astimezone(zone)
        evidence["confirmedExchangeAt"]=exchange.isoformat()
        boundary=datetime.combine(local.date(),self.config.end,zone)
        start_date=local.date() if self.config.start<self.config.end else local.date()-timedelta(days=1)
        window_start=datetime.combine(start_date,self.config.start,zone)
        grace=timedelta(minutes=self.config.active_grace_minutes)
        continuation=bool(boundary<=local<boundary+grace and window_start<=exchange<boundary
                          and boundary-grace<=exchange<=local)
        evidence["withinConfiguredGrace"]=continuation
        return continuation,evidence
