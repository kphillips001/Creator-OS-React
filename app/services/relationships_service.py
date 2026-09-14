"""Account-scoped read model for the Telegram operator inbox."""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from enum import Enum

from app.repositories.performance_snapshot_repository import PerformanceSnapshotRepository
from app.repositories.relationships_repository import RelationshipsRepository
from app.services.performance_snapshot_service import PerformanceSnapshotService
from app.services.customer_value_attention_service import CustomerValueAttentionService


class RelationshipSort(str, Enum):
    LATEST_ACTIVITY = "LATEST_ACTIVITY"
    LIFETIME_SPEND = "LIFETIME_SPEND"


class RelationshipFilter(str, Enum):
    ALL = "ALL"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    BUYERS = "BUYERS"
    PROSPECTS = "PROSPECTS"
    MANUAL = "MANUAL"
    ACTIVE_SESSION = "ACTIVE_SESSION"
    ACTIVE_INTENT = "ACTIVE_INTENT"
    HIGH_VALUE_PROSPECT = "HIGH_VALUE_PROSPECT"
    IGNORED = "IGNORED"


class RelationshipsService:
    OPERATIONAL_PREDICATE_VERSION = "CHAT_OPERATIONAL_STATUS_V1"
    OVERDUE_GRACE = timedelta(minutes=2)
    def __init__(self, *, people_repository=None, messages_repository=None,
                 value_attention_service=None):
        self.people_repository = people_repository or PerformanceSnapshotRepository()
        self.messages_repository = messages_repository or RelationshipsRepository()
        self.value_attention = value_attention_service or CustomerValueAttentionService()

    def list(self, *, creator_profile_id: int, fanvue_account_id: int,
             search: str = "", sort: RelationshipSort | str = RelationshipSort.LATEST_ACTIVITY,
             filter: RelationshipFilter | str = RelationshipFilter.ALL,
             cursor: str | None = None, limit: int = 50):
        selected_sort = RelationshipSort(str(getattr(sort, "value", sort)).upper())
        selected_filter = RelationshipFilter(str(getattr(filter, "value", filter)).upper())
        people = PerformanceSnapshotService(repository=self.people_repository).people_projection(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
        latest_by_person = self.messages_repository.latest_messages(
            creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
        state_reader = getattr(self.messages_repository, "inbox_state", None)
        inbox_by_person = state_reader(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id) if callable(state_reader) else {}
        rows = []
        for person in people:
            if not person.get("lastChatAt"): continue
            latest = latest_by_person.get(person["telegramUserId"])
            inbox = inbox_by_person.get(person["telegramUserId"], {})
            latest_at = max(value for value in (person["lastChatAt"],
                            latest["occurred_at"] if latest else None) if value is not None)
            inbound_at = inbox.get("last_customer_inbound_at")
            outbound_at = inbox.get("last_visible_outbound_at")
            operational = self._operational_projection(inbox)
            needs_attention = operational["operationalStatus"] == "NEEDS_ATTENTION"
            buyer = bool(person.get("identityStatus") == "MAPPED_VERIFIED" and
                         int(person.get("qualifyingPurchaseCount") or 0) > 0)
            rows.append({**person,"latestActivityAt": latest_at,
                         "latestMessagePreview": (latest.get("content") if latest else None),
                         "latestSpeaker": (latest.get("direction") if latest else None),
                         "controlMode": inbox.get("control_mode") or "AVA_AUTO",
                         "communicationDisposition": inbox.get("communication_disposition") or "ACTIVE",
                         "ignored": inbox.get("communication_disposition") == "IGNORED",
                         "operatorClassification": inbox.get("operator_classification"),
                         "highValueProspect": inbox.get("operator_classification") == "HIGH_VALUE_PROSPECT",
                         "marketTier": inbox.get("market_tier") or "UNCLASSIFIED",
                         "effectiveAttentionPriority": "PRIORITIZED" if inbox.get("operator_classification") == "HIGH_VALUE_PROSPECT" else "AUTOMATIC",
                         "lastCustomerInboundAt": inbound_at,
                         "lastVisibleOutboundAt": outbound_at,
                         "needsAttention": needs_attention,
                         **operational,
                         "isBuyer": buyer})
        term = search.strip().casefold()
        matches_search = lambda row: (not term or term in " ".join(
            str(row.get(key) or "") for key in
            ("displayName", "username", "telegramUserId")).casefold())
        active_rows = [row for row in rows if not row["ignored"] and matches_search(row)]
        ignored_rows = [row for row in rows if row["ignored"] and matches_search(row)]
        counts = {"total": len(active_rows),
                  "needsAttention": sum(bool(r["needsAttention"]) for r in active_rows),
                  "buyers": sum(bool(r["isBuyer"]) for r in active_rows),
                  "prospects": sum(not bool(r["isBuyer"]) for r in active_rows),
                  "manual": sum(r["controlMode"] == "HUMAN_OPERATOR" for r in active_rows)}
        counts["highValueProspects"] = sum(bool(r["highValueProspect"]) for r in active_rows)
        counts["replyScheduled"] = sum(
            r["operationalStatus"] == "REPLY_SCHEDULED" for r in active_rows
        )
        counts["ignored"] = len(ignored_rows)
        predicates = {
            RelationshipFilter.ALL: lambda r: True,
            RelationshipFilter.NEEDS_ATTENTION: lambda r: r["needsAttention"],
            RelationshipFilter.BUYERS: lambda r: r["isBuyer"],
            RelationshipFilter.PROSPECTS: lambda r: not r["isBuyer"],
            RelationshipFilter.MANUAL: lambda r: r["controlMode"] == "HUMAN_OPERATOR",
            RelationshipFilter.ACTIVE_SESSION: lambda r: bool(r.get("activeSalesSession")),
            RelationshipFilter.ACTIVE_INTENT: lambda r: bool(r.get("activePurchaseIntent")),
            RelationshipFilter.HIGH_VALUE_PROSPECT: lambda r: bool(r.get("highValueProspect")),
            RelationshipFilter.IGNORED: lambda r: True,
        }
        rows = ignored_rows if selected_filter is RelationshipFilter.IGNORED else active_rows
        rows = [row for row in rows if predicates[selected_filter](row)]
        if selected_sort is RelationshipSort.LIFETIME_SPEND:
            rows.sort(key=lambda r: (int(r.get("lifetimeVerifiedRevenueMinor") or 0),
                      r["latestActivityAt"],r["personKey"]), reverse=True)
        else:
            rows.sort(key=lambda r: (r["latestActivityAt"],r["personKey"]), reverse=True)
        offset = self._offset(cursor)
        page = rows[offset:offset+max(1,min(limit,100))]
        next_cursor = self._cursor(offset+len(page)) if offset+len(page)<len(rows) else None
        return {"items":page,"nextCursor":next_cursor,"hasMore":next_cursor is not None,
                "sort":selected_sort.value,"filter":selected_filter.value,"summary":counts}

    def acknowledge_attention(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        telegram_user_id: int, occurrence_id: str,
        acknowledged_by: str = "CREATOR_OS_OPERATOR",
    ):
        self._person(creator_profile_id, fanvue_account_id, telegram_user_id)
        inbox = self.messages_repository.inbox_state(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
        ).get(telegram_user_id)
        if not inbox:
            raise LookupError("Relationship not found.")
        projection = self._operational_projection(inbox)
        if (projection["operationalStatus"] != "NEEDS_ATTENTION"
                or projection["attentionOccurrenceId"] != occurrence_id):
            raise ValueError("Attention occurrence is no longer active.")
        acknowledged = self.messages_repository.acknowledge_attention(
            occurrence_id=occurrence_id,
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=int(inbox["telegram_chat_id"]),
            triggering_inbound_message_id=int(inbox["last_inbound_message_id"]),
            causal_operation_id=inbox.get("operation_id"),
            attention_reason=str(projection["operationalStatusReason"]),
            predicate_version=self.OPERATIONAL_PREDICATE_VERSION,
            acknowledged_by=acknowledged_by,
        )
        if acknowledged is None:
            raise ValueError("Attention occurrence does not belong to this relationship.")
        refreshed = dict(inbox)
        refreshed.update({
            "acknowledged_occurrence_id": occurrence_id,
            "acknowledged_at": acknowledged["acknowledged_at"],
            "acknowledged_by": acknowledged["acknowledged_by"],
        })
        return self._operational_projection(refreshed)

    @classmethod
    def _operational_projection(cls, inbox):
        mode = str(inbox.get("control_mode") or "AVA_AUTO")
        inbound = inbox.get("last_customer_inbound_at")
        outbound = inbox.get("last_visible_outbound_at")
        unanswered = bool(inbound and (not outbound or inbound > outbound))
        base = {
            "operationalStatus": "NONE",
            "operationalStatusReason": None,
            "nextAutomaticAttemptAt": None,
            "overdueSince": None,
            "operationState": inbox.get("operation_state"),
            "generationAttempts": int(inbox.get("generation_attempt_count") or 0),
            "sendAttempts": int(inbox.get("send_attempt_count") or 0),
            "hasActiveClaim": False,
            "attentionOccurrenceId": None,
            "attentionAcknowledgedAt": inbox.get("acknowledged_at"),
            "attentionAcknowledgedBy": inbox.get("acknowledged_by"),
        }
        if mode == "HUMAN_OPERATOR":
            if str(inbox.get("communication_disposition") or "ACTIVE") == "IGNORED":
                return {**base, "operationalStatus": "IGNORED",
                        "operationalStatusReason": "Automatic communication disabled for this relationship."}
            return {**base, "operationalStatus": "MANUAL_MODE",
                    "operationalStatusReason": "Operator controls this conversation."}
        if str(inbox.get("communication_disposition") or "ACTIVE") == "IGNORED":
            return {**base, "operationalStatus": "IGNORED",
                    "operationalStatusReason": "Automatic communication disabled for this relationship."}
        if not unanswered:
            return base
        state = str(inbox.get("operation_state") or "")
        error = str(inbox.get("operation_last_error") or "")
        if state == "SUPPRESSED" and error in {
                "MEDIUM_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED",
                "LOW_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED"}:
            policy=dict(dict(inbox.get("delivery_payload") or {}).get(
                "marketResourcePolicy") or {})
            return {**base,
                "operationalStatus": "MEDIUM_MARKET_LIMIT" if error.startswith("MEDIUM") else "LOW_MARKET_LIMIT",
                "operationalStatusReason": error,
                "repliesUsedToday": policy.get("replies_used_today"),
                "dailyReplyBudget": policy.get("daily_reply_budget"),
                "nextResetAt": policy.get("next_reset_at"),
                "effectiveMarketTier": policy.get("market_tier")}
        now = inbox.get("database_now") or datetime.now(timezone.utc)
        lease = inbox.get("lease_expires_at")
        active_claim = bool(inbox.get("claim_owner") and lease and lease > now)
        base["hasActiveClaim"] = active_claim
        if (state == "GENERATING" and not active_claim
                and lease and lease <= now
                and not inbox.get("has_response_payload")
                and int(inbox.get("send_attempt_count") or 0) == 0
                and int(inbox.get("generation_attempt_count") or 0)
                    >= int(inbox.get("max_generation_attempts") or 0)):
            reason = "Generation was interrupted and automatic recovery is exhausted."
            return {**base,"operationalStatus":"NEEDS_ATTENTION",
                    "operationalStatusReason":reason,
                    "attentionOccurrenceId":cls._occurrence_id(inbox,reason)}
        scheduled_reason = error in {
            "availability_deferred", "quality_corrective_retry_scheduled",
        }
        next_attempt = inbox.get("next_retry_at")
        scheduled = bool(
            state == "RETRYABLE" and not inbox.get("has_response_payload")
            and scheduled_reason and next_attempt
            and int(inbox.get("generation_attempt_count") or 0)
                < int(inbox.get("max_generation_attempts") or 0)
            and int(inbox.get("send_attempt_count") or 0) == 0
            and not active_claim
        )
        delivery_retry = bool(
            state == "RETRYABLE" and inbox.get("has_response_payload")
            and next_attempt
            and int(inbox.get("send_attempt_count") or 0)
                < int(inbox.get("max_send_attempts") or 0)
            and not active_claim
        )
        if delivery_retry:
            base["nextAutomaticAttemptAt"] = next_attempt
            reason = "Delivery retry scheduled."
            if next_attempt <= now - cls.OVERDUE_GRACE:
                return {**base, "operationalStatus": "OVERDUE",
                        "operationalStatusReason": reason,
                        "overdueSince": next_attempt + cls.OVERDUE_GRACE}
            return {**base, "operationalStatus": "REPLY_SCHEDULED",
                    "operationalStatusReason": reason}
        if scheduled:
            base["nextAutomaticAttemptAt"] = next_attempt
            reason = (
                "Corrective response scheduled."
                if error == "quality_corrective_retry_scheduled"
                else "Waiting for Ava availability."
            )
            if next_attempt <= now - cls.OVERDUE_GRACE:
                return {**base, "operationalStatus": "OVERDUE",
                        "operationalStatusReason": reason,
                        "overdueSince": next_attempt + cls.OVERDUE_GRACE}
            return {**base, "operationalStatus": "REPLY_SCHEDULED",
                    "operationalStatusReason": reason}
        if state in {"PENDING_GENERATION", "GENERATED", "SENT_CONFIRMED"}:
            return base
        if state in {"GENERATING", "SENDING"} and active_claim:
            return base
        attention_reason = None
        if state == "SEND_UNCERTAIN":
            attention_reason = "Telegram delivery could not be confirmed."
        elif state == "TERMINAL_FAILED":
            attention_reason = "Automatic reply processing exhausted its retry limit."
        elif state == "SUPPRESSED" and (
                error.startswith("quality_corrective_retry_exhausted:")
                or (error.startswith("quality_blocked_before_delivery:") and any(
                    reason in error for reason in cls.CORRECTABLE_REASONS
                ))):
            attention_reason = "A required response could not pass the final quality check."
        elif state == "RETRYABLE" and not next_attempt:
            attention_reason = "Automatic reply work has no scheduled recovery time."
        elif not state:
            attention_reason = "This inbound has no automatic reply operation."
        if not attention_reason:
            return base
        occurrence = cls._occurrence_id(inbox, attention_reason)
        base.update({
            "attentionOccurrenceId": occurrence,
            "operationalStatusReason": attention_reason,
        })
        if inbox.get("acknowledged_occurrence_id") == occurrence:
            return base
        return {**base, "operationalStatus": "NEEDS_ATTENTION"}

    CORRECTABLE_REASONS = (
        "CUSTOMER_QUESTION_UNANSWERED", "TURN_OBLIGATIONS_UNSATISFIED",
    )

    @classmethod
    def _occurrence_id(cls, inbox, reason):
        material = "|".join((
            cls.OPERATIONAL_PREDICATE_VERSION,
            "AVA_TELETHON_PRIVATE",
            str(inbox.get("telegram_chat_id") or ""),
            str(inbox.get("last_inbound_message_id") or ""),
            reason,
            str(inbox.get("operation_id") or ""),
        ))
        return hashlib.sha256(material.encode()).hexdigest()

    def messages(self, *, creator_profile_id: int, fanvue_account_id: int,
                 telegram_user_id: int, cursor: str | None = None, limit: int = 50):
        people = PerformanceSnapshotService(repository=self.people_repository).people_projection(
            creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
        person = next((p for p in people if p["telegramUserId"]==telegram_user_id),None)
        if person is None: raise LookupError("Relationship not found.")
        rows = self.messages_repository.messages(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,telegram_user_id=telegram_user_id)
        end = self._offset(cursor) if cursor else len(rows)
        start = max(0,end-max(1,min(limit,100)))
        items = [self._message(row) for row in rows[start:end]]
        return {"person":person,"items":items,"olderCursor":self._cursor(start) if start else None,
                "hasMoreOlder":start>0}

    def intelligence(self, *, creator_profile_id: int, fanvue_account_id: int,
                     telegram_user_id: int):
        person = self._person(creator_profile_id, fanvue_account_id, telegram_user_id)
        reader = getattr(self.messages_repository, "intelligence", None)
        if not callable(reader):
            raise LookupError("Relationship intelligence is unavailable.")
        source = reader(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            customer_commerce_profile_id=person.get("customerCommerceProfileId"),
            local_fanvue_user_id=person.get("localFanvueUserId"),
        )
        mapped = person.get("identityStatus") == "MAPPED_VERIFIED"
        intents = tuple(source.get("intents") or ())
        presented = tuple(item for item in intents if item.get("presented_at") is not None
                          and item.get("confirmed_delivery") is True)
        purchased = tuple(item for item in presented if self._status(item) == "PURCHASED")
        terminal = {"EXPIRED", "ABANDONED", "SUPERSEDED", "ADMIN_CLOSED"}
        not_purchased = tuple(item for item in presented if self._status(item) in terminal)
        active = next((item for item in intents if self._status(item) in
                       {"CREATED", "PRESENTED", "CLICKED"}), None)
        purchases = tuple(source.get("purchases") or ())
        behavior = {
            "active_purchase_intent": active is not None,
            "active_session": source.get("active_session") is not None,
            "presented_opportunity_count": len(presented),
            "failed_nonconverted_opportunity_count": len(not_purchased),
            "converted_opportunity_count": len(purchased),
            "active_unresolved_opportunity": any(
                self._status(item) in {"PRESENTED", "CLICKED", "UNKNOWN"}
                for item in presented),
        }
        value = self.value_attention.project(
            commerce_memory={
                "schemaVersion": "relationships_intelligence_v1",
                "verifiedPurchaseCount": person.get("qualifyingPurchaseCount") or 0,
                "lifetimeGrossMinor": person.get("lifetimeVerifiedRevenueMinor") or 0,
                "averageOrderValueMinor": (source.get("profile") or {}).get("average_order_value_minor") or 0,
                "largestOrderMinor": (source.get("profile") or {}).get("largest_purchase_minor") or 0,
                "lastPurchaseAt": (source.get("profile") or {}).get("last_purchase_at"),
            } if mapped else {}, behavior=behavior,
            legacy=(source.get("prospect") or {}).get("relationship_state") or {},
        )
        automatic = dict(source.get("latest_value_attention") or {})
        if automatic.get("schemaVersion") != "customer_value_attention_v1":
            automatic = dict(value.to_mapping())
        latest_offer = presented[0] if presented else None
        latest_purchase = purchases[0] if purchases else None
        memory = self._memory_projection(
            (source.get("prospect") or {}).get("preference_state") or {})
        context = self.control_context(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id)
        from app.services.relationship_value_override_service import RelationshipValueOverrideService
        override = RelationshipValueOverrideService().active(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=context["telegram_chat_id"])
        return {
            "person": person,
            "mappingStatus": "VERIFIED" if mapped else "UNMAPPED",
            "customerValue": {
                "buyerStatus": value.buyer_status if mapped else "UNMAPPED_PROSPECT",
                "valueTier": automatic.get("valueTier", value.value_tier),
                "attentionTier": automatic.get("attentionTier", value.attention_tier),
                "lifetimeSpendMinor": value.lifetime_spend_minor if mapped else None,
                "purchaseCount": value.purchase_count if mapped else None,
                "repeatBuyer": value.purchase_count >= 2 if mapped else False,
                "relationshipLifecycle": value.retention_lifecycle if mapped else "PROSPECT",
                "relationshipInvestment": automatic.get("relationshipInvestment", value.relationship_investment),
                "continuationValue": automatic.get("conversationContinuationValue", value.conversation_continuation_value),
                "timeWasterRisk": automatic.get("timeWasterRisk", value.time_waster_risk),
                "retention": automatic.get("retentionPriority", value.retention_priority),
            },
            "operatorClassification": override["classification"] if override else None,
            "effectiveAttentionPriority": "PRIORITIZED" if override else automatic.get("attentionTier", value.attention_tier),
            "behavioralIntelligence": {
                "buyingIntent": "DIRECT" if automatic.get("freshCommercialIntentDetected", value.fresh_commercial_intent_detected) else "NONE",
                "currentSignal": automatic.get("commercialInterestType", value.commercial_interest_type),
                "salesStage": automatic.get("buyerStage", value.buyer_stage),
            },
            "salesPerformance": {
                "offersPresented": len(presented),
                "offersPurchased": len(purchased),
                "offersNotPurchased": len(not_purchased),
                "conversionRate": len(purchased) / len(presented) if presented else None,
                "lastOffer": self._offer(latest_offer),
                "lastPurchase": self._purchase(latest_purchase),
            },
            "commercialState": {
                "activePurchaseIntent": self._offer(active),
                "activeSalesSession": self._session(source.get("active_session")),
                "activeOffer": self._offer(active) if active and active.get("presented_at") else None,
            },
            "purchaseHistory": [self._purchase(item) for item in purchases],
            "relationshipIntelligence": memory,
            "partial": not mapped,
        }

    def control_context(self, *, creator_profile_id, fanvue_account_id, telegram_user_id):
        self._person(creator_profile_id, fanvue_account_id, telegram_user_id)
        result = self.messages_repository.control_context(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id)
        if result is None: raise LookupError("Relationship not found.")
        return result

    def _person(self, creator, account, user_id):
        people = PerformanceSnapshotService(repository=self.people_repository).people_projection(
            creator_profile_id=creator, fanvue_account_id=account)
        person = next((item for item in people if item["telegramUserId"] == user_id), None)
        if person is None or not person.get("lastChatAt"):
            raise LookupError("Relationship not found.")
        return person

    @staticmethod
    def _status(item):
        return str(getattr(item.get("status"), "value", item.get("status") or ""))

    @classmethod
    def _offer(cls, item):
        if not item: return None
        return {"title": item.get("title") or "Private content",
                "type": cls._offering_type(item.get("offering_type"), item.get("session_offering")),
                "priceMinor": item.get("expected_price_minor"),
                "presentedAt": item.get("presented_at"),
                "status": cls._status(item)}

    @classmethod
    def _purchase(cls, item):
        if not item: return None
        return {"title": item.get("title") or "Verified purchase",
                "type": cls._offering_type(item.get("offering_type"), item.get("session_offering")),
                "priceMinor": item.get("gross_minor"),
                "purchasedAt": item.get("payment_timestamp"),
                "ownershipStatus": "OWNED" if item.get("ownership_confirmed") else None}

    @staticmethod
    def _session(item):
        if not item: return None
        return {"state": item.get("state"), "stage": item.get("progression_stage"),
                "type": "Session" if item.get("commercial_foundation_type") == "PHOTOSHOOT" else None}

    @staticmethod
    def _offering_type(value, session=False):
        if session: return "Session"
        value = str(value or "").upper()
        if value == "BUNDLE": return "Bundle"
        if value: return "Single"
        return None

    @staticmethod
    def _memory_projection(state):
        records = state.get("records") if isinstance(state, dict) else None
        current = [item for item in (records or ()) if item.get("status") == "current"]
        result = {"location": None, "timezone": None, "interests": [],
                  "pets": [], "music": [], "preferences": []}
        for item in current:
            category, key, value = item.get("category"), item.get("key"), item.get("value")
            if category == "fact" and key in {"location", "timezone"}: result[key] = value
            elif category in {"interest", "hobby"}: result["interests"].append(value)
            elif category in {"pet", "entity"}: result["pets"].append(value)
            elif category == "preference" and (key == "music" or "music" in str(key or "")):
                result["music"].append(value)
            elif category == "preference": result["preferences"].append(value)
        for key in ("interests", "pets", "music", "preferences"):
            result[key] = list(dict.fromkeys(str(v) for v in result[key] if v not in (None, "")))[:8]
        return result

    @staticmethod
    def _message(row):
        return {"eventKey":str(row["event_key"]),"direction":row["direction"],
                "content":row["content"],"timestamp":row["occurred_at"],
                "telegramMessageId":row.get("telegram_message_id"),
                "messageType":row.get("message_type"),
                "origin":"HUMAN_OPERATOR" if row.get("message_type")=="HUMAN_OPERATOR" else "AI",
                "purchaseIntentId":str(row["purchase_intent_id"]) if row.get("purchase_intent_id") else None}

    @staticmethod
    def _cursor(offset): return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")
    @staticmethod
    def _offset(cursor):
        if not cursor: return 0
        try: return max(0,int(base64.urlsafe_b64decode(cursor+"="*(-len(cursor)%4)).decode()))
        except (ValueError,UnicodeDecodeError): raise ValueError("Invalid cursor.")
