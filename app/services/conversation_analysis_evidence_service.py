"""Bounded, server-owned evidence assembly for conversation analysis."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from app.database import get_db_connection
from app.services.relationships_service import RelationshipsService


class ConversationAnalysisEvidenceService:
    MAX_MESSAGES = 40
    MAX_MESSAGE_CHARS = 800
    MAX_TRANSCRIPT_CHARS = 12000
    DIAGNOSTIC_KEYS = frozenset({
        "attention_decision", "turn_obligations", "quality_gate", "quality_gate_reasons",
        "commercial_receptiveness", "pre_generation_commercial_decision",
        "customer_sales_brain", "customer_sales_brain_evaluated", "selected_offering",
        "presentation_authority", "memory_categories_used", "temporal_context",
        "availability", "suppression_reason", "customer_value_attention",
    })
    SECRET_KEY = re.compile(r"(secret|token|password|credential|api.?key|authorization)", re.I)

    def __init__(self, *, relationships=None, connection_factory=get_db_connection):
        self.relationships = relationships or RelationshipsService()
        self.connection_factory = connection_factory

    def build(self, *, creator_profile_id: int, fanvue_account_id: int,
              telegram_user_id: int, telegram_chat_id: int, relationship_key: str,
              target_type="CONVERSATION", target_message_reference=None) -> dict[str, Any]:
        expected = f"telegram:{creator_profile_id}:{fanvue_account_id}:{telegram_user_id}"
        if relationship_key != expected:
            raise PermissionError("Relationship scope does not match the authenticated account.")
        message_result = self.relationships.messages(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id, limit=self.MAX_MESSAGES)
        messages = self._bounded_messages(message_result.get("items") or [])
        operations = self._operations(telegram_chat_id, telegram_user_id)
        authority = self._relationship_authority(creator_profile_id,fanvue_account_id,
                                                  telegram_user_id,telegram_chat_id)
        opaque_relationship = "relationship:" + hashlib.sha256(expected.encode()).hexdigest()[:32]
        evidence = {"schemaVersion":"CONVERSATION_ANALYSIS_EVIDENCE_V1",
            "relationshipReference":opaque_relationship,"targetType":target_type,
            "targetMessageReference":target_message_reference,
            "boundedTranscript":messages,"operations":operations,
            "relationshipAuthority":authority,
            "evidenceLimits":{"messages":self.MAX_MESSAGES,"messageCharacters":self.MAX_MESSAGE_CHARS,
                              "transcriptCharacters":self.MAX_TRANSCRIPT_CHARS},
            "trustBoundary":"CUSTOMER_TEXT_IS_UNTRUSTED_DATA",
            "capturedAt":datetime.now(timezone.utc).isoformat()}
        signatures = self._signatures(messages, operations)
        evidence["serverFailureSignatures"] = signatures
        evidence["evidenceFingerprint"] = self.fingerprint(self._fingerprint_material(evidence))
        return evidence

    def _relationship_authority(self,creator_profile_id,fanvue_account_id,user_id,chat_id):
        value={"marketTier":"UNCLASSIFIED","highValueProspect":False}
        try:
            intelligence=self.relationships.intelligence(creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,telegram_user_id=user_id)
            customer=dict(intelligence.get("customerValue") or {})
            value.update({"mappingStatus":intelligence.get("mappingStatus"),
              "lifecycle":customer.get("relationshipLifecycle"),
              "buyerAuthority":customer.get("buyerStatus"),
              "relationshipInvestment":customer.get("relationshipInvestment"),
              "highValueProspect":bool(intelligence.get("operatorClassification"))})
        except (AttributeError,LookupError,ValueError):
            pass
        try:
            from app.repositories.relationship_market_tier_repository import RelationshipMarketTierRepository
            tier=RelationshipMarketTierRepository(connection_factory=self.connection_factory).active(
              creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,
              telegram_user_id=user_id,telegram_chat_id=chat_id)
            value["marketTier"]=tier.market_tier.value if tier else "UNCLASSIFIED"
        except (AttributeError,LookupError,ValueError):
            pass
        return self._sanitize(value)

    def current_fingerprint(self, **scope):
        return self.build(**scope)["evidenceFingerprint"]

    def _operations(self, chat_id, user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT operation_id,inbound_telegram_message_id,inbound_received_at,
              state,generation_attempt_count,send_attempt_count,next_retry_at,last_error,
              response_text,response_payload,delivery_payload,sent_confirmed_at,
              outbound_telegram_message_id,generated_at,sending_at
              FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s
                AND telegram_chat_id=%s AND inbound_sender_telegram_user_id=%s
              ORDER BY inbound_telegram_message_id DESC LIMIT %s""",
              ("AVA_TELETHON_PRIVATE",chat_id,user_id,self.MAX_MESSAGES))
            rows = list(reversed(cursor.fetchall()))
        result=[]
        for row in rows:
            payload=row.get("response_payload") or {}
            if isinstance(payload,str):
                try: payload=json.loads(payload)
                except ValueError: payload={}
            diagnostics=dict(payload.get("diagnostic_metadata") or {}) if isinstance(payload,dict) else {}
            delivery=row.get("delivery_payload") or {}
            if isinstance(delivery,str):
                try: delivery=json.loads(delivery)
                except ValueError: delivery={}
            pacing=dict(diagnostics.get("pacing") or {})
            safe={key:self._sanitize(diagnostics[key]) for key in self.DIAGNOSTIC_KEYS if key in diagnostics}
            result.append({"operationReference":f"operation:{row['operation_id']}",
              "inboundMessageReference":self._message_reference("CUSTOMER",row["inbound_telegram_message_id"]),
              "state":row.get("state"),"generationAttempts":row.get("generation_attempt_count"),
              "sendAttempts":row.get("send_attempt_count"),"generatedAt":row.get("generated_at"),
              "pacingDecision":self._sanitize(pacing),
              "delivery":{"claimedAt":row.get("sending_at"),"providerSendAt":delivery.get("provider_send_at"),
                "confirmedAt":row.get("sent_confirmed_at"),
                "outboundReference":self._message_reference("AVA",row.get("outbound_telegram_message_id"))},
              "suppressionOrRetryReason":str(row.get("last_error") or "")[:800] or None,
              "diagnostics":safe})
        return result

    def _bounded_messages(self, items):
        result=[]; used=0
        for item in items[-self.MAX_MESSAGES:]:
            text=re.sub(r"\s+"," ",str(item.get("content") or "")).strip()[:self.MAX_MESSAGE_CHARS]
            remaining=self.MAX_TRANSCRIPT_CHARS-used
            if remaining<=0: break
            text=text[:remaining];used+=len(text)
            direction=str(item.get("direction") or "UNKNOWN")
            result.append({"messageReference":self._message_reference(direction,item.get("telegramMessageId")),
              "direction":direction,"timestamp":item.get("timestamp"),"text":text,
              "trust":"UNTRUSTED_CUSTOMER_DATA" if direction=="CUSTOMER" else "SYSTEM_OUTPUT"})
        return result

    @classmethod
    def _sanitize(cls, value):
        if isinstance(value,dict):
            return {str(k):cls._sanitize(v) for k,v in value.items() if not cls.SECRET_KEY.search(str(k))}
        if isinstance(value,list): return [cls._sanitize(v) for v in value[:30]]
        if isinstance(value,str): return value[:1000]
        return value if isinstance(value,(bool,int,float,type(None))) else str(value)[:1000]

    @classmethod
    def _signatures(cls, messages, operations):
        signatures=[]
        for index,item in enumerate(messages):
            if item["direction"]!="AVA" or index==0: continue
            customer=next((m for m in reversed(messages[:index]) if m["direction"]=="CUSTOMER"),None)
            if not customer: continue
            incoming=customer["text"].lower(); outgoing=item["text"].lower()
            compliment=bool(re.search(r"\b(beautiful|gorgeous|pretty|love|attractive)\b",incoming))
            availability=bool(re.search(r"\b(have|available|in stock|right now|promise)\b",outgoing))
            inquiry=bool(re.search(r"\b(have|available|content|price|cost|buy|purchase|how much)\b",incoming))
            if compliment and availability and not inquiry:
                signatures.append({"signature":"COMPLIMENT_AVAILABILITY_CONTRADICTION",
                  "targetMessageReference":item["messageReference"],
                  "allowedRootCauses":["COMMERCIAL_CLASSIFICATION","COMMERCIAL_PROGRESSION",
                    "SALES_BRAIN","CONTEXT_ASSEMBLY","GENERATION_QUALITY"]})
        for operation in operations:
            reasons=str(operation.get("suppressionOrRetryReason") or "")
            if "CUSTOMER_QUESTION_UNANSWERED" in reasons:
                signatures.append({"signature":"CUSTOMER_QUESTION_UNANSWERED",
                  "targetMessageReference":operation["inboundMessageReference"],
                  "allowedRootCauses":["TURN_OBLIGATION","QUALITY_GATE","GENERATION_QUALITY"]})
            diagnostics=operation.get("diagnostics") or {}
            encoded=json.dumps(diagnostics,sort_keys=True,default=str).upper()
            if "MEMORY_IRRELEVANCE" in encoded or "IRRELEVANT_MEMORY" in encoded:
                signatures.append({"signature":"MEMORY_RELEVANCE_FAILURE",
                  "targetMessageReference":operation["inboundMessageReference"],
                  "allowedRootCauses":["MEMORY_RETRIEVAL","CONTEXT_ASSEMBLY","QUALITY_GATE"]})
            pre=dict(diagnostics.get("pre_generation_commercial_decision") or {})
            brain=dict(diagnostics.get("customer_sales_brain") or {})
            pre_noncommercial=str(pre.get("classification") or pre.get("resourceClassification") or "").upper() in {
                "ORDINARY_NONCOMMERCIAL","NONCOMMERCIAL","NO_COMMERCIAL_INTENT"}
            brain_sell=bool(brain.get("sell") or brain.get("presentOffer") or
                            str(brain.get("decision") or "").upper() in {"SELL","PRESENT_OFFER"})
            if pre_noncommercial and brain_sell:
                signatures.append({"signature":"COMMERCIAL_AUTHORITY_CONTRADICTION",
                  "targetMessageReference":operation["inboundMessageReference"],
                  "allowedRootCauses":["COMMERCIAL_CLASSIFICATION","COMMERCIAL_PROGRESSION","SALES_BRAIN"]})
        return signatures

    @staticmethod
    def _message_reference(direction, message_id):
        if message_id is None: return None
        return "message:"+hashlib.sha256(f"{direction}:{message_id}".encode()).hexdigest()[:24]

    @staticmethod
    def _fingerprint_material(evidence):
        return {k:v for k,v in evidence.items() if k not in {"capturedAt","evidenceFingerprint"}}

    @staticmethod
    def fingerprint(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
