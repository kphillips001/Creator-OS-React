"""Read-only projection for the single configured controlled Telegram test identity."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

from app.database import get_db_connection
from app.services.controlled_autonomy_test_service import ControlledAutonomyTestService
from app.services.controlled_test_reset_service import ControlledTestResetService
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.schema_manager_service import SchemaManagerService


class LiveControlledTestUnavailable(ValueError):
    pass


def _iso(value):
    return value.isoformat() if value is not None else None


def _mask(value: int | str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:2] + "*" * max(4, len(text) - 4) + text[-2:]


def _get(source: dict[str, Any], *path, default=None):
    value: Any = source
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


class LiveControlledTestObserverService:
    """Never invokes the conversation engine, selector, transport, or providers."""

    def __init__(self, *, connection_factory=get_db_connection, boundary=None):
        self.connection_factory = connection_factory
        self.boundary = boundary or ControlledAutonomyTestService()

    def snapshot(self) -> dict[str, Any]:
        user_id, chat_id = self._identity()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            observation = self._one(cursor, """SELECT * FROM telegram_identity_observations
                WHERE telegram_user_id=%s""", (user_id,))
            mapping = self._one(cursor, """SELECT * FROM telegram_identity_map
                WHERE telegram_user_id=%s AND is_active=TRUE ORDER BY id LIMIT 1""", (user_id,))
            prospect = self._one(cursor, """SELECT * FROM telegram_sales_prospects
                WHERE telegram_user_id=%s AND telegram_chat_id=%s ORDER BY last_observed_at DESC LIMIT 1""",
                (user_id, chat_id))
            operations = self._all(cursor, """SELECT * FROM ordinary_chat_reply_operations
                WHERE inbound_sender_telegram_user_id=%s AND telegram_chat_id=%s
                ORDER BY created_at,inbound_telegram_message_id""", (user_id, chat_id))
            intents = self._all(cursor, """SELECT * FROM purchase_intents
                WHERE telegram_user_id=%s OR telegram_chat_id=%s ORDER BY created_at""", (user_id, chat_id))
            sessions = self._all(cursor, """SELECT s.* FROM sales_sessions s
                LEFT JOIN telegram_identity_map m ON m.id=s.telegram_identity_mapping_id
                WHERE m.telegram_user_id=%s ORDER BY s.created_at""", (user_id,))
            provisional_sessions = self._all(cursor, """SELECT * FROM telegram_provisional_sales_sessions
                WHERE telegram_user_id=%s AND telegram_chat_id=%s ORDER BY created_at""", (user_id, chat_id))
            fingerprints = self._all(cursor, """SELECT * FROM fanvue_fingerprint_reservations
                WHERE telegram_user_id=%s ORDER BY created_at""", (user_id,))
            intent_ids = [item["purchase_intent_id"] for item in intents]
            runtime_links = []
            if intent_ids:
                runtime_links = self._all(cursor, """SELECT * FROM fanvue_runtime_media_links
                    WHERE purchase_intent_id=ANY(%s) ORDER BY created_at""", (intent_ids,))
            offering = self._one(cursor, """SELECT * FROM commercial_offerings
                WHERE title LIKE 'CONTROLLED SMOKE TEST%%' AND price_minor=300
                ORDER BY created_at DESC LIMIT 1""", ())
            publication = None
            if offering:
                publication = self._one(cursor, """SELECT * FROM commercial_publications
                    WHERE commercial_offering_id=%s ORDER BY created_at DESC LIMIT 1""",
                    (offering["offering_id"],))
            workers = self._all(cursor, """SELECT DISTINCT ON (worker_name,worker_type)
                worker_name,worker_type,status,last_heartbeat_at,metadata
                FROM worker_heartbeats WHERE worker_name IN ('Telegram','Commerce Reconciliation')
                ORDER BY worker_name,worker_type,last_heartbeat_at DESC""", ())
            memory = None
            if mapping:
                memory = self._one(cursor, """SELECT * FROM user_memory
                    WHERE fanvue_account_id=%s AND fanvue_user_id=%s ORDER BY id LIMIT 1""",
                    (mapping["fanvue_account_id"], str(mapping["local_fanvue_user_id"])))
        turns = [self._turn(row, intents, mapping, sessions, index + 1)
                 for index, row in enumerate(operations)]
        latest = turns[-1] if turns else None
        return {
            "mode": "LIVE_CONTROLLED_TEST",
            "badges": ["LIVE CONTROLLED TEST", "External Sends: Controlled"],
            "configured": True,
            "customer": {
                "label": "Controlled Telegram Test Customer",
                "telegramNumericId": _mask(user_id), "chatId": _mask(chat_id),
                "mappingState": "MAPPED" if mapping else "UNMAPPED",
                "fanvueUuid": _mask(mapping.get("external_fanvue_user_uuid")) if mapping else None,
                "prospectState": "OBSERVED" if prospect else "NOT OBSERVED",
                "relationshipState": (prospect or {}).get("relationship_state") or {},
                "buyerTier": _get(latest or {}, "decision", "buyerTier", default="Not evaluated"),
                "inboundCount": len(operations),
                "purchaseIntentState": intents[-1]["status"] if intents else "NONE",
                "sessionState": sessions[-1]["state"] if sessions else "NONE",
                "lastObservedAt": _iso((observation or {}).get("last_observed_at")),
            },
            "conversation": self._conversation(turns),
            "turns": turns,
            "currentState": self._current(latest, mapping, intents, sessions),
            "memory": self._memory(memory, prospect),
            "timeContext": self._time(latest, prospect),
            "pacing": self._pacing(operations[-1] if operations else None),
            "sleep": self._sleep(operations),
            "ordinaryReplyOperations": [self._operation(item) for item in operations],
            "identityDiagnostics": self._identity_diagnostics(
                user_id, chat_id, observation, mapping, prospect,
            ),
            "commerceState": self._commerce_state(
                latest, intents, fingerprints, runtime_links, mapping, sessions,
            ),
            "recommendationDecision": _get(
                latest or {}, "decision", "rawDiagnostics", "recommendation_diagnostics",
                default={"state": "Not evaluated"},
            ),
            "fingerprintDiagnostics": {
                "bootstrapEnabled": self._flag("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED"),
                "controlledRestriction": True,
                "reservations": [self._safe_row(item) for item in fingerprints],
                "runtimeMediaLinks": [self._safe_row(item) for item in runtime_links],
                "state": "No fingerprint reservation exists" if not fingerprints else "AVAILABLE",
            },
            "sessionDiagnostics": {
                "provisionalSessions": [self._safe_row(item) for item in provisional_sessions],
                "canonicalSessions": [self._safe_row(item) for item in sessions],
                "state": "No Session exists" if not provisional_sessions and not sessions else "AVAILABLE",
            },
            "purchaseAcknowledgement": self._acknowledgement(intents),
            "controlledTestOffering": self._offering(offering, publication),
            "runtimeSafety": self._runtime_safety(workers),
            "resetDryRun": self.reset_dry_run(),
            "pollIntervalSeconds": 3,
            "readOnly": True,
        }

    def reset_dry_run(self) -> dict[str, Any]:
        self._identity()
        return ControlledTestResetService(
            connection_factory=self.connection_factory, boundary=self.boundary,
        ).preview()

    def _identity(self):
        configured = self.boundary.configured_identity()
        if configured is None:
            raise LiveControlledTestUnavailable("No controlled Telegram test customer configured")
        return configured

    @staticmethod
    def _one(cursor, query, params):
        cursor.execute(query, params); row = cursor.fetchone()
        return dict(row) if row else None

    @staticmethod
    def _all(cursor, query, params):
        cursor.execute(query, params); return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _count(cursor, query, params):
        cursor.execute(query, params); return int(cursor.fetchone()["n"])

    def _turn(self, row, intents, mapping, sessions, number):
        payload = dict(row.get("response_payload") or {})
        diagnostic = dict(payload.get("diagnostic_metadata") or {})
        delivery = dict(payload.get("delivery_payload") or {})
        delivery_metadata = dict(delivery.get("metadata") or {})
        unlock_button = dict(
            delivery_metadata.get("private_chat_unlock_button") or {}
        )
        unlock_url = str(unlock_button.get("url") or "").strip()
        if unlock_url:
            from app.services.customer_facing_commerce_url_service import (
                validate_customer_facing_commerce_url,
            )
            destination = validate_customer_facing_commerce_url(unlock_url)
            diagnostic.update({
                "customer_facing_destination_valid": destination.valid,
                "customer_facing_destination_failure_reason": destination.failure_reason,
                "customer_facing_destination_origin": destination.origin,
                "destination_scope": destination.scope,
                "commercial_presentation_complete": bool(
                    diagnostic.get("commercial_presentation_complete")
                    and destination.valid
                ),
                "commercial_presentation_failure_reason": (
                    None if destination.valid else destination.failure_reason
                ),
            })
        route = dict(diagnostic.get("route") or {})
        classifier = dict(route.get("classifier_result") or {})
        commerce = dict(diagnostic.get("commerce_decision") or {})
        result_correlation = payload.get("correlation_id")
        intent = next((item for item in intents if (
            str(item.get("conversation_id") or "") == str(result_correlation or "")
            or (
                int(dict(item.get("created_metadata") or {}).get(
                    "inbound_message_id"
                ) or -1) == int(row.get("inbound_telegram_message_id") or -2)
                and int(item.get("telegram_user_id") or -1)
                == int(row.get("inbound_sender_telegram_user_id") or -2)
            )
        )), None)
        return {
            "turn": number, "operationId": str(row["operation_id"]),
            "customerMessage": row.get("inbound_message_text") or "Unavailable — predates durable inbound capture",
            "customerMessagePersisted": row.get("inbound_message_text") is not None,
            "reply": row.get("response_text"),
            "inboundProviderMessageId": row.get("inbound_telegram_message_id"),
            "outboundProviderMessageId": row.get("outbound_telegram_message_id"),
            "receivedAt": _iso(row.get("inbound_received_at") or row.get("created_at")), "generatedAt": _iso(row.get("generated_at")),
            "confirmedAt": _iso(row.get("sent_confirmed_at")), "replyOperationState": row.get("state"),
            "classification": "commercial" if payload.get("delivery_requires_payment") else "ordinary",
            "decision": {
                "intent": _get(diagnostic, "intent", "tier", default=classifier.get("intent_level", "Not evaluated")),
                "commercialIntent": classifier.get("monetization_intent", "Not evaluated"),
                "commercialObjection": diagnostic.get("commercial_objection") or "Not evaluated",
                "nextBestOffer": diagnostic.get("next_best_offer") or "Not evaluated",
                "commercialSummary": diagnostic.get("commercial_summary") or {
                    "status": "Not evaluated"
                },
                "relationship": diagnostic.get("relationship_route") or "Not evaluated",
                "relationshipStage": diagnostic.get("customer_buyer_stage") or "Not evaluated",
                "buyerTier": diagnostic.get("buyer_tier") or "Not evaluated",
                "salesBrainDecision": commerce.get("decision") or "Not evaluated",
                "salesBrainReason": commerce.get("reason_code") or diagnostic.get("no_offering_reason") or "Not evaluated",
                "sell": bool(diagnostic.get("offer_authorized")),
                "commercePolicy": commerce.get("commerce_execution_policy") or "Not evaluated",
                "commerceMode": diagnostic.get("commerce_mode") or "Not evaluated",
                "promptMode": diagnostic.get("commerce_prompt_mode") or "Not evaluated",
                "authorization": diagnostic.get("offer_authorized", "Not evaluated"),
                "recommendationDecision": diagnostic.get("no_offering_reason") or "Not evaluated",
                "selectionSource": diagnostic.get("selection_source") or "Not evaluated",
                "eligibilitySource": diagnostic.get("eligibility_source") or "Not evaluated",
                "memorySource": diagnostic.get("memory_source") or "Not evaluated",
                "conversationalMemory": diagnostic.get("conversational_memory") or {
                    "retrievalAttempted": False,
                    "separateFromCommerceMemory": True,
                },
                "recommendationSource": _get(diagnostic, "recommendation_diagnostics", "recommendationEngineVersion", default="Not evaluated"),
                "requestedMediaType": diagnostic.get("requested_media_type") or "Not evaluated",
                "requestedThemes": diagnostic.get("requested_themes") or [],
                "offeringCandidate": _get(
                    diagnostic, "offering_copy_diagnostics",
                    "offeringInternalTitle", default="Not evaluated",
                ),
                "offeringSelected": diagnostic.get("offering_selected", False),
                "offeringId": diagnostic.get("offering_id"), "offeringType": diagnostic.get("offering_type"),
                "configuredPriceMinor": diagnostic.get("price_minor"), "fulfillable": diagnostic.get("fulfillable", False),
                "noOfferingReason": diagnostic.get("no_offering_reason") or "Not evaluated",
                "purchaseIntentCreated": intent is not None,
                "purchaseIntentId": str(intent["purchase_intent_id"]) if intent else None,
                "purchaseIntentReused": diagnostic.get("purchase_intent_reused"),
                "commercialPayloadComposed": diagnostic.get(
                    "commercial_payload_composed",
                    bool(payload.get("delivery_requires_payment")),
                ),
                "finalCustomerFacingOfferText": diagnostic.get(
                    "final_customer_facing_offer_text"
                ) or row.get("response_text"),
                "linkAttachmentMode": diagnostic.get(
                    "commercial_link_attachment_mode"
                ),
                "outboundDispatchAttempted": (
                    row.get("send_attempt_count", 0) > 0
                    or bool(diagnostic.get("outbound_dispatch_attempted"))
                ),
                "outboundDispatchPath": diagnostic.get(
                    "outbound_dispatch_path"
                ),
                "outboundDispatchError": row.get("last_error"),
                "outboundRetryEligible": (
                    row.get("state") in {"GENERATED", "RETRYABLE"}
                    and row.get("outbound_telegram_message_id") is None
                ),
                "outboundIdempotencyKey": diagnostic.get(
                    "outbound_dispatch_idempotency_key"
                ) or row.get("correlation_id"),
                "deliveryType": payload.get("delivery_type") or "Not evaluated",
                "resultType": "commercial" if payload.get("delivery_requires_payment") else "ordinary",
                "fingerprintState": "NONE" if intent is None else intent.get("identity_bootstrap_mode") or "NONE",
                "mappingState": "MAPPED" if mapping else "UNMAPPED",
                "sessionState": sessions[-1]["state"] if sessions else "NONE",
                "rawDiagnostics": diagnostic,
            },
        }

    @staticmethod
    def _conversation(turns):
        messages = []
        for turn in turns:
            messages.append({"role": "user", "content": turn["customerMessage"], "timestamp": turn["receivedAt"],
                "providerMessageId": turn["inboundProviderMessageId"], "classification": "inbound"})
            if turn.get("reply"):
                messages.append({"role": "assistant", "content": turn["reply"], "timestamp": turn["confirmedAt"],
                    "providerMessageId": turn["outboundProviderMessageId"], "classification": turn["classification"],
                    "replyOperationState": turn["replyOperationState"]})
        return messages

    @staticmethod
    def _current(latest, mapping, intents, sessions):
        d = (latest or {}).get("decision") or {}
        return {"relationship": d.get("relationship", "Not evaluated"),
            "engagement": d.get("intent", "Not evaluated"), "salesBrainStage": d.get("salesBrainDecision", "Not evaluated"),
            "commercialIntent": d.get("commercialIntent", "Not evaluated"), "offerReadiness": d.get("authorization", "Not evaluated"),
            "backoffCooldown": "Not evaluated", "activePurchaseIntent": intents[-1]["status"] if intents else "NONE",
            "mappingState": "MAPPED" if mapping else "UNMAPPED", "sessionState": sessions[-1]["state"] if sessions else "NONE",
            "ownedContentAwareness": "AVAILABLE" if mapping else "UNAVAILABLE — customer unmapped",
            "lastDecisionReason": d.get("salesBrainReason", "Not evaluated")}

    @staticmethod
    def _memory(memory, prospect):
        prospect_state = dict((prospect or {}).get("preference_state") or {})
        records = list(prospect_state.get("records") or [])
        current = [item for item in records if item.get("status") == "current"]
        if prospect and (current or prospect_state):
            by_category = lambda name: [item for item in current if item.get("category") == name]
            return {"available": bool(current), "source": "telegram_sales_prospects.preference_state",
                "identitySource": "TELEGRAM_NUMERIC_PROSPECT",
                "stableFacts": by_category("fact"), "preferences": by_category("preference"),
                "entities": by_category("entity"), "routines": by_category("routine"),
                "events": by_category("event"),
                "location": prospect_state.get("location"), "timezone": prospect_state.get("timezone"),
                "retrieval": prospect_state.get("lastRetrieval") or {},
                "lastWrite": prospect_state.get("lastExtraction") or {},
                "supersededCount": sum(item.get("status") == "superseded" for item in records),
                "relationshipFacts": (prospect or {}).get("relationship_state") or {},
                "lastUpdated": _iso((prospect or {}).get("last_observed_at")),
                "commerceMemorySeparate": True}
        if memory:
            return {"available": True, "source": "user_memory", "facts": memory.get("notes") or {},
                "preferences": {"theme": memory.get("preferred_content_theme"), "tags": memory.get("favorite_content_tags") or []},
                "lastUpdated": _iso(memory.get("updated_at")), "commerceMemorySeparate": True}
        return {"available": False, "source": "NONE", "stableFacts": [], "preferences": [],
            "entities": [], "routines": [], "events": [], "relationshipFacts": {},
            "lastUpdated": _iso((prospect or {}).get("last_observed_at")), "commerceMemorySeparate": True}

    @staticmethod
    def _time(latest, prospect=None):
        diagnostic = _get(latest or {}, "decision", "rawDiagnostics", default={})
        context = diagnostic.get("time_context") if isinstance(diagnostic, dict) else None
        memory = dict((prospect or {}).get("preference_state") or {})
        return {"runtimeUtcNow": datetime.now(timezone.utc).isoformat(),
            "avaTimezone": _get(context or {}, "avaTimezone", default="NOT PROVIDED"),
            "avaLocalTime": _get(context or {}, "avaLocalTime", default="NOT PROVIDED"),
            "avaDayOfWeek": _get(context or {}, "avaDayOfWeek", default="NOT PROVIDED"),
            "avaDaypart": _get(context or {}, "avaDaypart", default="NOT PROVIDED"),
            "customerTimezone": _get(context or {}, "customerTimezone", default="NOT PROVIDED"),
            "customerLocalTime": _get(context or {}, "customerLocalTime", default="NOT PROVIDED"),
            "customerDayOfWeek": _get(context or {}, "customerDayOfWeek", default="NOT PROVIDED"),
            "customerDaypart": _get(context or {}, "customerDaypart", default="NOT PROVIDED"),
            "currentPersistedCustomerTimezone": memory.get("timezone"),
            "source": "latest persisted generation decision"}

    @staticmethod
    def _pacing(row):
        if not row:
            return {"status": "No human pacing applied"}
        start, generated, confirmed = row.get("created_at"), row.get("generated_at"), row.get("sent_confirmed_at")
        canonical = _get(dict(row.get("response_payload") or {}),
            "diagnostic_metadata", "response_pacing", default={})
        return {"inboundReceived": _iso(start), "generationStarted": "NOT PERSISTED", "generationCompleted": _iso(generated),
            "deliveryStarted": _iso(row.get("sending_at")) or "NOT PERSISTED", "telegramConfirmed": _iso(confirmed),
            "totalResponseLatencyMs": round((confirmed-start).total_seconds()*1000) if start and confirmed else None,
            "canonicalPacing": canonical or "NOT PROVIDED",
            "canonicalSource": canonical.get("canonicalSource", "NOT PROVIDED") if isinstance(canonical, dict) else "NOT PROVIDED",
            "mode": canonical.get("mode", "NOT PROVIDED") if isinstance(canonical, dict) else "NOT PROVIDED",
            "configuredHumanDelay": canonical.get("calculatedDelayMs", "NOT PROVIDED") if isinstance(canonical, dict) else "NOT PROVIDED",
            "actualAppliedDelay": canonical.get("appliedDelayMs", "NOT PROVIDED") if isinstance(canonical, dict) else "NOT PROVIDED",
            "bypassed": canonical.get("bypassed", "NOT PROVIDED") if isinstance(canonical, dict) else "NOT PROVIDED",
            "bypassReason": canonical.get("bypassReason") if isinstance(canonical, dict) else None,
            "typingBehavior": canonical.get("typingBehavior", "NOT PROVIDED") if isinstance(canonical, dict) else "NOT PROVIDED",
            "status": ("Shadow pacing calculated; no wait applied" if isinstance(canonical, dict)
                       and canonical.get("mode") == "SHADOW" else
                       "Human pacing applied" if isinstance(canonical, dict)
                       and canonical.get("appliedDelayMs", 0) > 0 else
                       "Pacing calculated but bypassed" if canonical else
                       "No human pacing applied")}

    @staticmethod
    def _sleep(operations):
        latest = operations[-1] if operations else None
        payload = dict((latest or {}).get("response_payload") or {})
        diagnostics = dict(payload.get("diagnostic_metadata") or {})
        context = dict(diagnostics.get("sleep_context") or {})
        deferred = [row for row in operations if str(row.get("last_error") or "").startswith("sleep_deferred:")]
        if not context and deferred:
            marker = str(deferred[-1].get("last_error") or "").split(":", 1)[-1]
            return {"state": "ASLEEP", "cycleId": marker,
                "canonicalTimezone": "America/New_York",
                "deferredInboundCount": len(deferred),
                "responseDeferredDueToSleep": True,
                "source": "ordinary_chat_reply_operations"}
        if not context:
            return {"state": "NOT EVALUATED", "canonicalTimezone": "America/New_York",
                "deferredInboundCount": 0, "responseDeferredDueToSleep": False}
        context["deferredInboundCount"] = len(deferred)
        context["signoffDelivered"] = bool(
            context.get("signoffRequired")
            and (latest or {}).get("state") == "SENT_CONFIRMED"
        )
        context["signoffPending"] = bool(
            context.get("signoffRequired") and not context["signoffDelivered"]
        )
        context["source"] = "ordinary_chat_reply_operations.response_payload"
        return context

    @staticmethod
    def _operation(row):
        return {"operationId": str(row["operation_id"]),
            "telegramAccountScope": row.get("telegram_account_scope"),
            "telegramChatId": _mask(row.get("telegram_chat_id")),
            "inboundTelegramMessageId": row.get("inbound_telegram_message_id"),
            "inboundSenderTelegramUserId": _mask(row.get("inbound_sender_telegram_user_id")),
            "inboundMessageText": row.get("inbound_message_text") or "Unavailable — predates durable inbound capture",
            "inboundReceivedAt": _iso(row.get("inbound_received_at")),
            "conversationThreadId": row.get("conversation_thread_id"),
            "correlationId": row.get("correlation_id"), "state": row.get("state"),
            "responseContentSha256": row.get("response_content_sha256"),
            "outboundTelegramMessageId": row.get("outbound_telegram_message_id"),
            "generationAttemptCount": row.get("generation_attempt_count"),
            "sendAttemptCount": row.get("send_attempt_count"),
            "maxGenerationAttempts": row.get("max_generation_attempts"),
            "maxSendAttempts": row.get("max_send_attempts"),
            "nextRetryAt": _iso(row.get("next_retry_at")), "lastError": row.get("last_error"),
            "generatedAt": _iso(row.get("generated_at")), "sendingAt": _iso(row.get("sending_at")),
            "sentConfirmedAt": _iso(row.get("sent_confirmed_at")), "uncertainAt": _iso(row.get("uncertain_at")),
            "failedAt": _iso(row.get("failed_at")), "createdAt": _iso(row.get("created_at")),
            "updatedAt": _iso(row.get("updated_at"))}

    @staticmethod
    def _identity_diagnostics(user_id, chat_id, observation, mapping, prospect):
        return {"telegramNumericId": _mask(user_id), "telegramChatId": _mask(chat_id),
            "observationExists": observation is not None,
            "firstObservedAt": _iso((observation or {}).get("first_observed_at")),
            "lastObservedAt": _iso((observation or {}).get("last_observed_at")),
            "prospectExists": prospect is not None,
            "prospectId": str((prospect or {}).get("telegram_sales_prospect_id")) if prospect else None,
            "graduatedAt": _iso((prospect or {}).get("graduated_at")),
            "mappingState": "MAPPED" if mapping else "UNMAPPED",
            "mappingId": (mapping or {}).get("id"),
            "mappingVerificationStatus": (mapping or {}).get("verification_status"),
            "mappingVerificationMethod": (mapping or {}).get("verification_method"),
            "fanvueUuid": _mask((mapping or {}).get("external_fanvue_user_uuid"))}

    @classmethod
    def _commerce_state(cls, latest, intents, fingerprints, runtime_links, mapping, sessions):
        decision = (latest or {}).get("decision") or {}
        return {"sell": decision.get("sell", False),
            "offerAuthorized": decision.get("authorization", False),
            "offeringSelected": decision.get("offeringSelected", False),
            "offeringId": decision.get("offeringId"), "offeringType": decision.get("offeringType"),
            "configuredPriceMinor": decision.get("configuredPriceMinor"),
            "purchaseIntents": [cls._safe_row(item) for item in intents],
            "fingerprintReservations": [cls._safe_row(item) for item in fingerprints],
            "runtimeMediaLinks": [cls._safe_row(item) for item in runtime_links],
            "mappingState": "MAPPED" if mapping else "UNMAPPED",
            "sessions": [cls._safe_row(item) for item in sessions],
            "ownershipAwareness": "AVAILABLE" if mapping else "UNAVAILABLE — customer unmapped",
            "fulfillable": decision.get("fulfillable", False),
            "deliveryType": decision.get("deliveryType", "Not evaluated")}

    @classmethod
    def _acknowledgement(cls, intents):
        rows = [{"purchaseIntentId": str(item["purchase_intent_id"]),
            "state": item.get("status"), "eligible": item.get("purchase_acknowledged_at") is None,
            "correlation": item.get("correlation_id"),
            "providerMessageId": item.get("telegram_message_id"),
            "acknowledgedAt": _iso(item.get("purchase_acknowledged_at"))}
            for item in intents]
        return {"state": "NONE" if not rows else "AVAILABLE", "items": rows}

    @classmethod
    def _offering(cls, offering, publication):
        if not offering:
            return {"state": "NOT FOUND"}
        metadata = dict((publication or {}).get("publication_metadata") or {})
        media = dict(metadata.get("media_link") or {})
        return {"offeringId": str(offering["offering_id"]), "title": offering.get("title"),
            "type": offering.get("offering_type"), "channel": offering.get("primary_sales_channel"),
            "status": offering.get("status"), "basePriceMinor": offering.get("price_minor"),
            "currency": offering.get("currency"), "assetId": offering.get("hero_asset_id"),
            "publicationId": str(publication["publication_id"]) if publication else None,
            "publicationState": (publication or {}).get("status"),
            "canonicalMediaLinkUuid": media.get("uuid") or (publication or {}).get("external_product_id"),
            "canonicalMediaLinkState": (publication or {}).get("provider_resource_status"),
            "clicks": media.get("clicks"), "unlocks": media.get("unlocks"),
            "earnings": media.get("earnings"),
            "fulfillmentReady": offering.get("status") == "READY" and (publication or {}).get("status") == "LIVE"}

    def _runtime_safety(self, workers):
        manager = SchemaManagerService(connection_factory=self.connection_factory)
        certification = manager.certify()
        applied = manager.applied_migrations()
        files = {item.name: item.checksum for item in manager.load_forward_migrations()}
        mismatches = sorted(name for name, checksum in applied.items()
                            if name in files and files[name] != checksum)
        global_safety = GlobalAutomationSafetyService().check_global_safety()
        safe_workers = []
        for item in workers:
            metadata = dict(item.get("metadata") or {})
            metadata.pop("last_inbound_chat_id", None)
            safe_workers.append({"workerName": item.get("worker_name"),
                "workerType": item.get("worker_type"), "status": item.get("status"),
                "lastHeartbeatAt": _iso(item.get("last_heartbeat_at")), "metadata": metadata})
        return {"workers": safe_workers, "globalAutonomy": global_safety,
            "controlledAutonomyEnabled": self._flag("CONTROLLED_AUTONOMY_TEST_ENABLED"),
            "controlledIdentityRestriction": self.boundary.audit_metadata(),
            "fingerprintBootstrapEnabled": self._flag("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED"),
            "fanvueDmChallengeEnabled": self._flag("TELEGRAM_FANVUE_DM_IDENTITY_VERIFICATION_ENABLED"),
            "runtimeMode": "OFFLINE" if global_safety.get("blocked") else "ONLINE",
            "externalSends": "Controlled",
            "schema": {"status": certification.status,
                "missingMigrations": list(certification.missing_migrations),
                "drift": list(certification.drift), "checksumMismatches": mismatches}}

    @staticmethod
    def _flag(name):
        return str(os.getenv(name) or "").strip().lower() in {"1","true","yes","on","enabled"}

    @staticmethod
    def _safe_row(row):
        result = {}
        for key, value in dict(row).items():
            if key in {"delivery_url", "provider_url"}:
                result[key] = value
            elif hasattr(value, "isoformat"):
                result[key] = value.isoformat()
            elif key in {"external_fanvue_user_uuid"}:
                result[key] = _mask(value)
            else:
                result[key] = str(value) if key.endswith("_id") and value is not None else value
        return result
