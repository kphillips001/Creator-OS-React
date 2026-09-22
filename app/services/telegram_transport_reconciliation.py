"""Read-only, fail-closed assessment of canonical delivery history.

An UNKNOWN result never grants retry authority. Missing history is not negative
delivery proof. No application identity mapping is needed for exact transport
identity evidence.
"""
from datetime import datetime, timedelta, timezone


def _time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("An aware timestamp is required")
    return value.astimezone(timezone.utc)


def assess_telegram_history(*, operation, history):
    unknown = {"outcome": "UNKNOWN", "retry_authorized": False}
    try:
        evidence = operation.get("provider_delivery_evidence") or {}
        route = evidence.get("transport_route") or {}
        if not all(history.get(k) is True for k in (
                "authenticated", "canonical_session", "query_succeeded", "complete")):
            return unknown
        if history.get("truncated") or not route.get("provider_attempt_id"):
            return unknown
        if (str(history.get("sender_id")) != str(route.get("sender_id"))
                or not route.get("sender_id")
                or history.get("sender_scope") != route.get("sender_scope")
                or history.get("peer_id") != route.get("peer_id")):
            return unknown
        start = _time(route["invocation_started_at"])
        end = _time(operation["uncertain_at"])
        if _time(history["query_start"]) > start or _time(history["query_end"]) < end:
            return unknown
        candidates = []
        required = route["required_capabilities"]
        for item in history.get("messages", []):
            if (item.get("outbound") is not True or item.get("peer_id") != route["peer_id"]
                    or str(item.get("sender_id")) != str(route["sender_id"])):
                continue
            if route.get("business_connection_id") and item.get("business_connection_id") != route["business_connection_id"]:
                continue
            # Telegram timestamps have second precision.
            if not start.replace(microsecond=0) <= _time(item["sent_at"]) <= end+timedelta(seconds=1):
                continue
            if item.get("text", "") != operation.get("text", ""):
                continue
            if required.get("photo") and (not operation.get("media_sha256")
                    or item.get("media_sha256") != operation["media_sha256"]):
                continue
            if required.get("url_action") and item.get("url_action") != operation.get("url_action"):
                continue
            identifier = item.get("message_id")
            if isinstance(identifier, bool) or not isinstance(identifier, int) or identifier <= 0:
                continue
            known = evidence.get("telegram_message_id")
            if known is not None and identifier != known:
                continue
            candidates.append(identifier)
        if len(candidates) != 1:
            return unknown
        if evidence.get("telegram_message_id") is None:
            # Text alone cannot distinguish identical concurrent/repeated sends.
            if (history.get("unique_attempt_proven") is not True
                    or history.get("provider_attempt_id") != route["provider_attempt_id"]
                    or history.get("payload_sha256") != route["payload_sha256"]):
                return unknown
        return {"outcome": "DELIVERED", "telegram_message_id": candidates[0],
                "retry_authorized": False}
    except (KeyError, TypeError, ValueError):
        return unknown
