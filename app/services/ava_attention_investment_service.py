"""Bounded operational attention per response window, never customer intelligence."""
from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum

class AvaAttentionInvestment(str,Enum):
    NORMAL="NORMAL"; LOWER_PRIORITY="LOWER_PRIORITY"; MINIMAL_NURTURE="MINIMAL_NURTURE"

@dataclass(frozen=True)
class AvaAttentionDecision:
    investment:AvaAttentionInvestment; priority:int; outcome:str; reasons:tuple[str,...]
    meaningful_obligation:bool; commercial_referent:bool
    def diagnostics(self):
        return {"policy":"AVA_ATTENTION_INVESTMENT_V1","investment":self.investment.value,
            "priority":self.priority,"outcome":self.outcome,"reasons":list(self.reasons),
            "meaningfulObligation":self.meaningful_obligation,"commercialReferent":self.commercial_referent,
            "permanentCustomerLabel":False}

class AvaAttentionInvestmentService:
    QUESTION=re.compile(r"\?|\b(?:who|what|when|where|why|how|can|could|would|do|are|is)\b",re.I)
    COMMERCIAL=re.compile(r"\b(?:buy|price|purchase|unlock|offer|content|photo|video|set)\b",re.I)
    SUMMON=re.compile(r"\b(?:hello|are you there|where are you|where did you go|gone quiet|you.ve gone quiet)\b",re.I)
    AFFECTION=re.compile(r"\b(?:love you|babe|miss you)\b",re.I)
    EMOJI_ONLY=re.compile(r"^[\W_]+$",re.UNICODE)
    @classmethod
    def _low_information(cls,text):
        clean=str(text or "").strip()
        return bool(clean and (cls.EMOJI_ONLY.fullmatch(clean) or cls.SUMMON.search(clean)
            or cls.AFFECTION.search(clean) or len(clean.split())<=2))
    def evaluate(self,messages,*,verified_buyer=False,repeat_buyer=False,high_value_buyer=False):
        texts=[str(item).strip() for item in messages if str(item or "").strip()]
        obligation=any(self.QUESTION.search(item) and not self.SUMMON.search(item) for item in texts)
        commercial=any(self.COMMERCIAL.search(item) for item in texts)
        low_count=sum(self._low_information(item) for item in texts)
        meaningful=any(not self._low_information(item) for item in texts)
        reasons=[]
        if verified_buyer:reasons.append("VERIFIED_BUYER_RETENTION")
        if repeat_buyer or high_value_buyer:reasons.append("ELEVATED_RETENTION_VALUE")
        if obligation:reasons.append("MEANINGFUL_DIRECT_QUESTION")
        if commercial:reasons.append("COMMERCIAL_REFERENT")
        if low_count>=5 and not meaningful:reasons.append("SUSTAINED_LOW_INFORMATION")
        if verified_buyer or meaningful or obligation or commercial:investment=AvaAttentionInvestment.NORMAL
        elif low_count>=6:investment=AvaAttentionInvestment.MINIMAL_NURTURE
        elif low_count>=3:investment=AvaAttentionInvestment.LOWER_PRIORITY
        else:investment=AvaAttentionInvestment.NORMAL
        no_response=investment is AvaAttentionInvestment.MINIMAL_NURTURE and not obligation and not commercial and not verified_buyer
        priority=(40 if high_value_buyer else 30 if repeat_buyer else 20 if verified_buyer else 0)
        priority+=15 if obligation else 10 if commercial else 5 if meaningful else 0
        return AvaAttentionDecision(investment,priority,"NO_RESPONSE_REQUIRED" if no_response else "RESPOND",
            tuple(reasons),obligation,commercial)
