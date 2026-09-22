"""Fail-closed authority for authenticated Telegram negative-history evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.repositories.operator_delivery_resolution_repository import (
    OperatorDeliveryResolutionRepository,
)


class TelegramNegativeHistoryAttestationService:
    METHOD = "AUTHENTICATED_TELEGRAM_HISTORY_NEGATIVE_ATTESTATION"
    VERSION = "1"
    MIN_BEFORE = timedelta(minutes=15)
    MIN_AFTER = timedelta(minutes=30)

    def __init__(self, *, repository=None, now=None):
        self.repository = repository or OperatorDeliveryResolutionRepository()
        self.now = now or (lambda: datetime.now(timezone.utc))

    def evaluate(self, *, operation: dict, fingerprint: dict, readback: dict) -> dict:
        reasons = []
        sending_at = self._time(operation.get("sending_at"))
        uncertain_at = self._time(operation.get("uncertain_at"))
        query_start = self._time(readback.get("query_start"))
        query_end = self._time(readback.get("query_end"))
        executed_at = self._time(readback.get("executed_at"))
        messages = list(readback.get("messages") or ())
        expected_peer = int(operation.get("telegram_chat_id") or 0)

        if operation.get("state") != "SEND_UNCERTAIN": reasons.append("OPERATION_NOT_SEND_UNCERTAIN")
        if operation.get("outbound_telegram_message_id") is not None: reasons.append("OUTBOUND_ID_ALREADY_EXISTS")
        if operation.get("sent_confirmed_at") is not None: reasons.append("DELIVERY_ALREADY_CONFIRMED")
        if self._positive_provider_evidence(operation): reasons.append("POSITIVE_PROVIDER_EVIDENCE_CONFLICT")
        if readback.get("authenticated") is not True: reasons.append("READBACK_NOT_AUTHENTICATED")
        if readback.get("canonical_session") is not True: reasons.append("NON_CANONICAL_SESSION")
        if int(readback.get("peer_id") or 0) != expected_peer: reasons.append("PEER_MISMATCH")
        if readback.get("query_succeeded") is not True: reasons.append("QUERY_FAILED")
        if readback.get("complete") is not True: reasons.append("WINDOW_INCOMPLETE")
        if readback.get("truncated") is True: reasons.append("WINDOW_TRUNCATED")
        if readback.get("authorization_error") is True: reasons.append("AUTHORIZATION_ERROR")
        if not all((sending_at, uncertain_at, query_start, query_end, executed_at)):
            reasons.append("TIMESTAMPS_INCOMPLETE")
        elif query_start > sending_at-self.MIN_BEFORE:
            reasons.append("INSUFFICIENT_PRE_SEND_WINDOW")
        elif query_end < uncertain_at+self.MIN_AFTER:
            reasons.append("INSUFFICIENT_POST_SEND_WINDOW")
        if not readback.get("lower_boundary_reached"):
            reasons.append("LOWER_BOUNDARY_NOT_PROVEN")
        if not readback.get("upper_boundary_reached"):
            reasons.append("UPPER_BOUNDARY_NOT_PROVEN")
        anchors = {int(value) for value in (fingerprint.get("anchor_message_ids") or ())}
        observed = {int(item["id"]) for item in messages if item.get("id") is not None}
        if anchors and not anchors.issubset(observed): reasons.append("CHRONOLOGY_ANCHOR_MISSING")

        matches = [item for item in messages if (
            query_start and query_end and self._time(item.get("date"))
            and query_start <= self._time(item.get("date")) <= query_end
            and self._matches(item, fingerprint)
        )]
        classification = "STILL_UNCERTAIN"
        if matches and not reasons:
            classification = "CONFIRMED_DELIVERED"
        elif not reasons:
            classification = "CONFIRMED_NOT_DELIVERED"
        return {
            "classification": classification,
            "eligible": classification == "CONFIRMED_NOT_DELIVERED",
            "reasons": reasons,
            "matchingCandidates": matches,
            "evidence": {
                "attestationMethod": self.METHOD, "attestationVersion": self.VERSION,
                "operationId": str(operation.get("operation_id")), "peerId": expected_peer,
                "sendingAt": sending_at, "uncertainAt": uncertain_at,
                "queryStart": query_start, "queryEnd": query_end,
                "queryExecutedAt": executed_at, "complete": readback.get("complete") is True,
                "truncated": readback.get("truncated") is True,
                "messagesInspected": len(messages),
                "earliestObserved": min((self._time(x.get("date")) for x in messages
                                         if x.get("date") is not None), default=None),
                "latestObserved": max((self._time(x.get("date")) for x in messages
                                       if x.get("date") is not None), default=None),
                "authenticationProvenance": str(readback.get("authentication_provenance") or ""),
                "sessionCredentialPersisted": False,
                "anchorMessageIds": sorted(anchors), "matchingCandidateCount": len(matches),
                "fingerprint": self._safe_fingerprint(fingerprint),
                "classification": classification, "failureReasons": reasons,
            },
        }

    def attest_not_delivered(self, *, operation: dict, fingerprint: dict,
                             readback: dict, creator_profile_id: int,
                             fanvue_account_id: int, relationship_key: str,
                             purchase_intent_id: UUID | None, resolved_by: str):
        result = self.evaluate(operation=operation, fingerprint=fingerprint, readback=readback)
        if not result["eligible"]:
            return {**result, "resolution": None, "idempotent": False}
        resolution, idempotent = self.repository.resolve(
            operation_id=UUID(str(operation["operation_id"])),
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            relationship_key=relationship_key,
            telegram_user_id=int(operation["inbound_sender_telegram_user_id"]),
            telegram_chat_id=int(operation["telegram_chat_id"]),
            purchase_intent_id=purchase_intent_id, outcome="NOT_DELIVERED",
            presentation_mode=str(fingerprint.get("presentation_mode") or "UNKNOWN"),
            provider_acceptance_evidence=False, provider_readback_evidence=True,
            resolved_by=resolved_by, evidence=result["evidence"],
        )
        return {**result, "resolution": resolution, "idempotent": idempotent}

    @staticmethod
    def _positive_provider_evidence(operation):
        payload = dict(operation.get("delivery_payload") or {})
        provider = dict(payload.get("provider_delivery_evidence") or {})
        return bool(provider.get("telegram_message_id") or provider.get("accepted") is True)

    @staticmethod
    def _matches(message, fingerprint):
        if message.get("out") is not True:
            return False
        expected = " ".join(str(fingerprint.get("text") or "").split())
        actual = " ".join(str(message.get("text") or "").split())
        media_expected = bool(fingerprint.get("media_expected"))
        media_present = bool(message.get("media_type") or message.get("photo_id"))
        if expected and actual == expected and (not media_expected or media_present):
            return True
        button_url = str(fingerprint.get("button_url") or "")
        return bool(button_url and media_present and any(
            str(item.get("url") or "") == button_url for item in (message.get("buttons") or ())
        ))

    @staticmethod
    def _safe_fingerprint(value):
        return {key: value.get(key) for key in (
            "text", "media_expected", "asset_sha256", "offering_id",
            "publication_id", "purchase_intent_id", "button_url",
            "anchor_message_ids", "presentation_mode",
        )}

    @staticmethod
    def _time(value):
        if value is None: return None
        if isinstance(value, str): value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None: value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
