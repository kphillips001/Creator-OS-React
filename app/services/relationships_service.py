"""Account-scoped read model for the Telegram operator inbox."""

import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from enum import Enum

from app.repositories.performance_snapshot_repository import PerformanceSnapshotRepository
from app.repositories.relationships_repository import RelationshipsRepository
from app.services.performance_snapshot_service import PerformanceSnapshotService
from app.services.customer_value_attention_service import CustomerValueAttentionService
from app.services.ppv_escalation_projection_service import PPVEscalationProjectionService
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
from app.services.contextual_customer_tone_service import ContextualCustomerToneService
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService


class RelationshipSort(str, Enum):
    LATEST_ACTIVITY = "LATEST_ACTIVITY"
    LIFETIME_SPEND = "LIFETIME_SPEND"
    COUNTRY_TIER_HIGH_TO_LOW = "COUNTRY_TIER_HIGH_TO_LOW"
    COUNTRY_TIER_LOW_TO_HIGH = "COUNTRY_TIER_LOW_TO_HIGH"


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
    OPERATIONAL_PREDICATE_VERSION = "CHAT_OPERATIONAL_STATUS_V3"
    OVERDUE_GRACE = timedelta(minutes=2)
    def __init__(self, *, people_repository=None, messages_repository=None,
                 value_attention_service=None, active_sales_service=None,
                 ppv_escalation_service=None, sales_brain_config=None):
        self.people_repository = people_repository or PerformanceSnapshotRepository()
        self.messages_repository = messages_repository or RelationshipsRepository()
        self.value_attention = value_attention_service or CustomerValueAttentionService()
        self.active_sales = active_sales_service
        self.ppv_escalation = ppv_escalation_service or PPVEscalationProjectionService()
        self.sales_brain_config = sales_brain_config or CustomerSalesBrainConfig.from_environment()

    def list(self, *, creator_profile_id: int, fanvue_account_id: int,
             search: str = "", sort: RelationshipSort | str = RelationshipSort.LATEST_ACTIVITY,
             filter: RelationshipFilter | str = RelationshipFilter.ALL,
             country_tiers: list[str] | tuple[str, ...] | None = None,
             cursor: str | None = None, limit: int = 50):
        selected_sort = RelationshipSort(str(getattr(sort, "value", sort)).upper())
        selected_filter = RelationshipFilter(str(getattr(filter, "value", filter)).upper())
        selected_tiers = {str(value).upper() for value in (country_tiers or [])}
        allowed_tiers = {"HIGH", "MEDIUM", "LOW", "UNCLASSIFIED"}
        if not selected_tiers.issubset(allowed_tiers):
            raise ValueError("Country Tier must be HIGH, MEDIUM, LOW, or UNCLASSIFIED.")
        people = PerformanceSnapshotService(repository=self.people_repository).people_projection(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
        latest_by_person = self.messages_repository.latest_messages(
            creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
        state_reader = getattr(self.messages_repository, "inbox_state", None)
        inbox_by_person = state_reader(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id) if callable(state_reader) else {}
        attention_reader = getattr(
            self.messages_repository, "commercial_attention_by_person", None
        )
        attention_by_person = attention_reader(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
        ) if callable(attention_reader) else {}
        rows = []
        from app.services.active_sales_opportunity_service import ActiveSalesOpportunityService
        active_sales = self.active_sales or ActiveSalesOpportunityService()
        for person in people:
            if not person.get("lastChatAt"): continue
            latest = latest_by_person.get(person["telegramUserId"])
            inbox = inbox_by_person.get(person["telegramUserId"], {})
            commercial_attention = attention_by_person.get(
                person["telegramUserId"], {}
            )
            latest_at = max(value for value in (person["lastChatAt"],
                            latest["occurred_at"] if latest else None) if value is not None)
            inbound_at = inbox.get("last_customer_inbound_at")
            outbound_at = inbox.get("last_visible_outbound_at")
            operational = self._operational_projection(inbox)
            opportunity = active_sales.project(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=person["telegramUserId"],
                telegram_chat_id=int(inbox.get("telegram_chat_id") or person["telegramUserId"]),
            )
            if (opportunity["active"] and operational["operationalStatus"] in
                    {"MEDIUM_MARKET_LIMIT", "LOW_MARKET_LIMIT"}):
                operational = {
                    **operational,
                    "operationalStatus": "REPLY_SCHEDULED",
                    "operationalStatusReason": "ACTIVE_SALES_OPPORTUNITY_REQUIRES_REEVALUATION",
                    "activeSalesOpportunity": opportunity,
                }
            self._record_projection(creator_profile_id,fanvue_account_id,person['telegramUserId'],inbox,operational)
            needs_attention = operational["operationalStatus"] == "NEEDS_ATTENTION"
            buyer = bool(person.get("identityStatus") == "MAPPED_VERIFIED" and
                         int(person.get("qualifyingPurchaseCount") or 0) > 0)
            failed_presentations = int(
                commercial_attention.get("failed_presentation_count") or 0
            )
            verified_purchases = max(
                int(commercial_attention.get("verified_purchase_count") or 0),
                int(person.get("qualifyingPurchaseCount") or 0),
            )
            time_waster = bool(
                not buyer and verified_purchases == 0
                and failed_presentations
                    >= self.sales_brain_config.time_waster_min_failed_presentations
            )
            rows.append({**person,"latestActivityAt": latest_at,
                         "latestMessagePreview": (latest.get("content") if latest else None),
                         "latestSpeaker": (latest.get("direction") if latest else None),
                         "controlMode": inbox.get("control_mode") or "AVA_AUTO",
                         "communicationDisposition": inbox.get("communication_disposition") or "ACTIVE",
                         "ignored": inbox.get("communication_disposition") == "IGNORED",
                         "operatorClassification": inbox.get("operator_classification"),
                         "highValueProspect": inbox.get("operator_classification") == "HIGH_VALUE_PROSPECT",
                          "marketTier": inbox.get("market_tier") or "UNCLASSIFIED",
                          "timeWaster": time_waster,
                          "failedPresentationCount": failed_presentations,
                          "verifiedPurchaseCount": verified_purchases,
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
            r["operationalStatus"] in {"REPLY_SCHEDULED", "REPLY_READY"}
            for r in active_rows
        )
        counts["operationalCategories"]={category:sum(
            r.get('operationalCategory')==category and (r.get('operatorAlertActive') or category in {'RECOVERY_PENDING','NO_REPLY_REQUIRED'})
            for r in rows) for category in ('HUMAN_ATTENTION_REQUIRED','SYSTEM_INCIDENT','DELIVERY_UNCERTAIN','RECOVERY_PENDING','NO_REPLY_REQUIRED')}
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
        if selected_tiers:
            rows = [row for row in rows if row["marketTier"] in selected_tiers]
        if selected_sort in {RelationshipSort.COUNTRY_TIER_HIGH_TO_LOW,
                             RelationshipSort.COUNTRY_TIER_LOW_TO_HIGH}:
            order = ({"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNCLASSIFIED": 3}
                     if selected_sort is RelationshipSort.COUNTRY_TIER_HIGH_TO_LOW else
                     {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "UNCLASSIFIED": 3})
            rows.sort(key=lambda r: (r["latestActivityAt"], r["personKey"]), reverse=True)
            rows.sort(key=lambda r: order[r["marketTier"]])
        elif selected_sort is RelationshipSort.LIFETIME_SPEND:
            rows.sort(key=lambda r: (int(r.get("lifetimeVerifiedRevenueMinor") or 0),
                      r["latestActivityAt"],r["personKey"]), reverse=True)
        else:
            rows.sort(key=lambda r: (r["latestActivityAt"],r["personKey"]), reverse=True)
        offset = self._offset(cursor)
        page = rows[offset:offset+max(1,min(limit,100))]
        next_cursor = self._cursor(offset+len(page)) if offset+len(page)<len(rows) else None
        return {"items":page,"nextCursor":next_cursor,"hasMore":next_cursor is not None,
                "sort":selected_sort.value,"filter":selected_filter.value,
                "countryTiers":sorted(selected_tiers),"summary":counts}

    def _record_projection(self, creator_profile_id, fanvue_account_id, telegram_user_id, inbox, projection):
        record=getattr(self.messages_repository,'record_projection_transition',None)
        if callable(record):
            record(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,telegram_chat_id=inbox.get('telegram_chat_id') or telegram_user_id,
                projection=projection)

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
        if (projection["operationalStatus"] not in {"NEEDS_ATTENTION", "SYSTEM_INCIDENT", "DELIVERY_UNCERTAIN"}
                or projection["attentionOccurrenceId"] != occurrence_id):
            raise ValueError("Attention occurrence is no longer active.")
        uncertainty = projection["operationalStatus"] == "DELIVERY_UNCERTAIN"
        acknowledged = self.messages_repository.acknowledge_attention(
            occurrence_id=occurrence_id,
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=int(inbox["telegram_chat_id"]),
            triggering_inbound_message_id=int(inbox["last_inbound_message_id"]),
            causal_operation_id=None if uncertainty else inbox.get("operation_id"),
            attention_reason=str(projection["attentionReasonIdentity"]),
            predicate_version="DELIVERY_UNCERTAIN_ACK_V1" if uncertainty else self.OPERATIONAL_PREDICATE_VERSION,
            acknowledged_by=acknowledged_by,
        )
        if acknowledged is None:
            raise ValueError("Attention occurrence does not belong to this relationship.")
        refreshed = dict(inbox)
        if uncertainty:
            refreshed["uncertainty_acknowledgements"] = [*(inbox.get("uncertainty_acknowledgements") or []), acknowledged]
        refreshed.update({
            "acknowledgement_id": acknowledged.get("acknowledgement_id"),
            "acknowledged_occurrence_id": occurrence_id,
            "acknowledged_at": acknowledged["acknowledged_at"],
            "acknowledged_by": acknowledged["acknowledged_by"],
        })
        if uncertainty:
            for key in ("acknowledgement_id","acknowledged_occurrence_id","acknowledged_at","acknowledged_by"):
                refreshed[key]=inbox.get(key)
        result=self._operational_projection(refreshed)
        self._record_projection(creator_profile_id,fanvue_account_id,telegram_user_id,refreshed,result)
        return result

    @classmethod
    def _operational_projection(cls, inbox):
        from app.services.conversation_operational_projection import project
        return project(inbox,legacy=cls._legacy_operational_projection,occurrence_id=cls._occurrence_id)

    @classmethod
    def _legacy_operational_projection(cls, inbox):
        mode = str(inbox.get("control_mode") or "AVA_AUTO")
        inbound = inbox.get("last_customer_inbound_at")
        outbound = inbox.get("last_visible_outbound_at")
        unanswered = bool(inbound and (not outbound or inbound > outbound))
        base = {
            "operationalStatus": "NONE",
            "operationalStatusReason": None,
            "nextAutomaticAttemptAt": None,
            "pendingReplyPreview": None,
            "overdueSince": None,
            "operationState": inbox.get("operation_state"),
            "operationId": str(inbox["operation_id"]) if inbox.get("operation_id") else None,
            "inboundMessageId": inbox.get("operation_inbound_message_id"),
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
        retry_at = inbox.get("next_retry_at")
        scheduled_delivery_at = inbox.get("scheduled_delivery_at")
        next_attempt = (
            scheduled_delivery_at
            if scheduled_delivery_at and (
                not inbox.get("has_response_payload")
                or error == "prepared_for_scheduled_delivery"
            )
            else retry_at
        )
        active_claim = bool(inbox.get("claim_owner") and lease and lease > now)
        attention_investment = dict(
            dict(inbox.get("delivery_payload") or {}).get("attentionInvestment") or {}
        )
        authoritative_no_obligation = (
            attention_investment.get("meaningfulObligation") is False
        )
        associated_meaningful_obligation = (
            inbox.get("operation_has_meaningful_obligation") is True
        )
        base["hasActiveClaim"] = active_claim
        stranded_generated = bool(
            state == "GENERATED"
            and inbox.get("has_response_payload")
            and not inbox.get("sending_at")
            and not inbox.get("outbound_telegram_message_id")
            and not inbox.get("sent_confirmed_at")
            and int(inbox.get("send_attempt_count") or 0) == 0
            and not next_attempt
            and not active_claim
            and inbox.get("operation_updated_at")
            and inbox["operation_updated_at"] <= now - timedelta(seconds=30)
        )
        if stranded_generated:
            reason = "Generated response was not delivered and requires recovery."
            return {**base, "operationalStatus": "NEEDS_ATTENTION",
                    "operationalStatusReason": reason,
                    "attentionOccurrenceId": cls._occurrence_id(inbox, reason)}
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
        from app.services.ordinary_reply_retry_policy import OrdinaryReplyRetryPolicy
        retry = OrdinaryReplyRetryPolicy.evaluate(
            state=state, reason=error, next_retry_at=next_attempt,
            generation_attempts=inbox.get("generation_attempt_count"),
            max_generation_attempts=inbox.get("max_generation_attempts"),
            send_attempts=inbox.get("send_attempt_count"),
            has_response_payload=inbox.get("has_response_payload"),
            outbound_telegram_message_id=inbox.get("outbound_telegram_message_id"),
            sent_confirmed_at=inbox.get("sent_confirmed_at"),
            has_active_claim=active_claim,
        )
        delivery_retry = bool(
            state == "RETRYABLE" and inbox.get("has_response_payload")
            and str(inbox.get("pending_reply_preview") or "").strip()
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
            return {**base, "operationalStatus": "REPLY_READY",
                    "operationalStatusReason": reason,
                    "pendingReplyPreview": inbox["pending_reply_preview"]}
        if retry.scheduler_eligible:
            base["nextAutomaticAttemptAt"] = next_attempt
            reason = (
                "Corrective response scheduled."
                if retry.category == "QUALITY_CORRECTIVE"
                else "Waiting for Ava readiness."
                if retry.category == "GLOBAL_READINESS"
                else "Generation retry scheduled."
                if retry.category in {
                    "DECISION_ENGINE_EXCEPTION", "EMPTY_GENERATION",
                    "GENERATION_FAILURE",
                }
                else "Waiting for Ava availability."
            )
            generation_failure = retry.category in {
                "DECISION_ENGINE_EXCEPTION", "EMPTY_GENERATION",
                "GENERATION_FAILURE",
            }
            overdue = bool(
                retry.due(now) if generation_failure
                else next_attempt <= now - cls.OVERDUE_GRACE
            )
            if overdue:
                return {**base, "operationalStatus": "OVERDUE",
                        "operationalStatusReason": reason,
                        "overdueSince": (next_attempt if generation_failure
                                         else next_attempt + cls.OVERDUE_GRACE)}
            return {**base, "operationalStatus": "REPLY_SCHEDULED",
                    "operationalStatusReason": reason}
        if state == "RETRYABLE" and not inbox.get("has_response_payload"):
            reason = (
                "Automatic generation retry budget is exhausted."
                if retry.exhausted else
                "Automatic reply work has no actionable retry path."
            )
            return {**base, "operationalStatus": "NEEDS_ATTENTION",
                    "operationalStatusReason": reason,
                    "attentionOccurrenceId": cls._occurrence_id(inbox, reason)}
        if state in {"PENDING_GENERATION", "GENERATED", "SENT_CONFIRMED"}:
            return base
        if (state == "SEND_UNCERTAIN"
                and inbox.get("delivery_resolution_outcome") == "DELIVERED"
                and inbox.get("delivery_resolution_provenance") == "OPERATOR_ATTESTED"):
            return base
        if state in {"GENERATING", "SENDING"} and active_claim:
            return base
        attention_reason = None
        if state == "SEND_UNCERTAIN":
            attention_reason = "Telegram delivery could not be confirmed."
        elif (state == "TERMINAL_FAILED" and not (
                error.startswith("EMPTY_GENERATION:")
                and (authoritative_no_obligation
                     or inbox.get("has_unresolved_meaningful_obligation") is False))):
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
        elif (state in {"SUPPRESSED", "TERMINAL_FAILED"}
              and not inbox.get("has_active_response_operation")
              and associated_meaningful_obligation
              and not authoritative_no_obligation):
            attention_reason = (
                "Customer conversation is unanswered and no automatic response "
                "operation remains actionable."
            )
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
                 telegram_user_id: int, cursor: str | None = None, limit: int = 50,
                 include_person: bool = True):
        page_size=max(1,min(limit,100))
        exists=getattr(self.messages_repository,"relationship_exists",None)
        if callable(exists) and not exists(creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,telegram_user_id=telegram_user_id):
            raise LookupError("Relationship not found.")
        person=None
        if include_person or not callable(exists):
            people = PerformanceSnapshotService(repository=self.people_repository).people_projection(
                creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
            person = next((p for p in people if p["telegramUserId"]==telegram_user_id),None)
            if person is None: raise LookupError("Relationship not found.")
        if callable(exists):
            boundary=self._message_cursor(cursor) if cursor else None
            rows = self.messages_repository.messages(
                creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
                before_occurred_at=boundary[0] if boundary else None,
                before_event_key=boundary[1] if boundary else None,limit=page_size+1)
            has_more=len(rows)>page_size
            rows=rows[-page_size:]
            older=self._message_cursor_for(rows[0]) if has_more and rows else None
        else:
            rows = self.messages_repository.messages(creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,telegram_user_id=telegram_user_id)
            end = self._offset(cursor) if cursor else len(rows)
            start = max(0,end-page_size)
            rows,has_more,older=rows[start:end],start>0,self._cursor(start) if start else None
        result={"items":[self._message(row) for row in rows],"olderCursor":older,
                "hasMoreOlder":has_more}
        if include_person: result["person"]=person
        return result

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
        failed_presentation_count = len({
            str(item.get("id") or item.get("purchase_intent_id"))
            for item in not_purchased
            if item.get("id") is not None or item.get("purchase_intent_id") is not None
        })
        verified_purchase_count = int(person.get("qualifyingPurchaseCount") or 0)
        time_waster = (
            mapped
            and verified_purchase_count == 0
            and failed_presentation_count
            >= self.sales_brain_config.time_waster_min_failed_presentations
        )
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
        diagnostics = dict(source.get("latest_sales_diagnostics") or {})
        diagnostic_source = dict(source.get("latest_sales_diagnostic_source") or {})
        transcript_rows = self.messages_repository.messages(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        diagnostic_message_id = diagnostic_source.get("inbound_telegram_message_id")
        current_index = next((index for index in range(len(transcript_rows) - 1, -1, -1)
            if transcript_rows[index].get("direction") == "CUSTOMER"
            and transcript_rows[index].get("telegram_message_id") == diagnostic_message_id), None)
        if current_index is not None:
            current = transcript_rows[current_index]
            recent = tuple({
                "role": "customer" if item.get("direction") == "CUSTOMER" else "assistant",
                "content": item.get("content") or "",
            } for item in transcript_rows[max(0, current_index - 12):current_index])
            tone = ContextualCustomerToneService().classify(
                message=str(current.get("content") or ""), recent_transcript=recent,
            )
            counts = dict((diagnostics.get("customer_value_attention") or {}).get(
                "behaviorEvidenceCounts") or {})
            permission = CustomerEffectivePermissionsService().read(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=context["telegram_chat_id"],
            )
            hot_context = {
                **counts,
                "contextual_customer_tone": tone,
                "sales_progression": diagnostics.get("sales_progression") or {},
                "relationship_control_mode": (permission.get("configured") or {}).get(
                    "relationshipMode", "AVA_AUTO"),
                "communication_disposition": (permission.get("communication") or {}).get(
                    "disposition", "ACTIVE"),
                "relationship_ignored": (permission.get("communication") or {}).get(
                    "ignored") is True,
                "effective_content_selling_allowed": (permission.get("effective") or {}).get(
                    "contentSellingAllowed") is True,
                "purchase_cooldown_active": bool(
                    ((diagnostics.get("commerce_decision") or {}).get("active_buying_window") or {})
                    .get("evidence", {}).get("purchaseCooldownActive")
                ),
            }
            evaluator = object.__new__(CustomerSalesBrainService)
            evaluator.config = self.sales_brain_config
            hot = evaluator._proactive_hot_opportunity_assessment(
                hot_context,
                active_purchase_intent=context.get("active_purchase_intent") is True,
                active_sales_session=context.get("active_sales_session") is True,
            )
            diagnostics["contextual_customer_tone"] = tone
            diagnostics["proactiveHotOpportunity"] = hot
            diagnostics["salesBrainProjectionSource"] = {
                "authority": "CURRENT_CANONICAL_TRANSCRIPT_AND_DURABLE_DIAGNOSTIC_EVIDENCE",
                "inboundTelegramMessageId": diagnostic_message_id,
                "inboundReceivedAt": diagnostic_source.get("inbound_received_at"),
                "operationId": diagnostic_source.get("operation_id"),
            }
        reentry = dict(diagnostics.get("commercial_reentry") or {})
        reentry_value = dict(diagnostics.get("customer_value_attention") or {})
        commercial_reentry = (
            reentry.get("active") is True and reentry.get("authorized") is True
        ) or (
            reentry_value.get("relationshipRewarmingActive") is True
            and reentry_value.get("historicalCommercialInterest") is True
            and reentry_value.get("relationshipRewarmingCommercialReentryAllowed") is True
        )
        ppv_escalation = self.ppv_escalation.project(
            mapped=mapped,
            verified_purchase_count=(person.get("qualifyingPurchaseCount") if mapped else None),
            intents=intents,
            latest_diagnostics=diagnostics,
            messages_since_last_offer=source.get("messages_since_last_offer"),
            follow_through=source.get("follow_through"),
            commercial_reentry=commercial_reentry,
            sexual_receptiveness_threshold=(
                self.sales_brain_config.sexual_receptiveness_min_engagements),
        )
        return {
            "person": person,
            "mappingStatus": "VERIFIED" if mapped else "UNMAPPED",
            "customerValue": {
                "buyerStatus": value.buyer_status if mapped else "UNMAPPED_PROSPECT",
                "valueTier": (
                    automatic.get("valueTier", value.value_tier) if mapped else None
                ),
                "attentionTier": (
                    automatic.get("attentionTier", value.attention_tier) if mapped else None
                ),
                "lifetimeSpendMinor": value.lifetime_spend_minor if mapped else None,
                "purchaseCount": value.purchase_count if mapped else None,
                "repeatBuyer": value.purchase_count >= 2 if mapped else False,
                "relationshipLifecycle": value.retention_lifecycle if mapped else "PROSPECT",
                "relationshipInvestment": automatic.get("relationshipInvestment", value.relationship_investment),
                "continuationValue": automatic.get("conversationContinuationValue", value.conversation_continuation_value),
                "timeWasterRisk": automatic.get("timeWasterRisk", value.time_waster_risk),
                "timeWaster": time_waster,
                "failedPresentationCount": failed_presentation_count,
                "verifiedPurchaseCount": verified_purchase_count,
                "timeWasterThreshold": self.sales_brain_config.time_waster_min_failed_presentations,
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
            "ppvEscalation": ppv_escalation,
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

    @staticmethod
    def _message_cursor_for(row):
        value=json.dumps([row["occurred_at"].isoformat(),str(row["event_key"])],
                         separators=(",",":"))
        return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")

    @staticmethod
    def _message_cursor(cursor):
        try:
            value=json.loads(base64.urlsafe_b64decode(
                cursor+"="*(-len(cursor)%4)).decode())
            if not isinstance(value,list) or len(value)!=2: raise ValueError
            occurred=datetime.fromisoformat(str(value[0]))
            if occurred.tzinfo is None: raise ValueError
            event_key=str(value[1])
            if not event_key: raise ValueError
            return occurred,event_key
        except (ValueError,TypeError,UnicodeDecodeError,json.JSONDecodeError):
            raise ValueError("Invalid cursor.")
