"""One customer-conversation preflight/invocation/receipt boundary.

Operator alerts and channel publishing are separate domains: they must retain
operator/channel recipient authorities and must never supply customer-conversation
operation IDs or be used as fallback routes here. Experimental bot/commerce
compatibility adapters are non-delivering without a canonical lifecycle owner.
No failover after invocation.
"""
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone
import inspect
from pathlib import Path
from hashlib import sha256
from uuid import uuid4

from app.models.telegram_transport_contract import (
    DeliveryCertainty, TelegramPreflightError, TelegramRequirements, route_evidence,
)

_acknowledger = ContextVar("telegram_acknowledger", default=None)


class TelegramInvocationUnknown(ConnectionError):
    certainty = DeliveryCertainty.UNKNOWN


class TelegramAcknowledgementPersistenceError(ConnectionError):
    certainty = DeliveryCertainty.ACCEPTED

    def __init__(self, evidence):
        super().__init__("Provider accepted; acknowledgement persistence failed.")
        self.provider_evidence = dict(evidence)


def capture_acknowledgement(message_id, **evidence):
    if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
        return
    value = {"telegram_message_id": message_id, "accepted": True, "certainty": "ACCEPTED", **evidence}
    callback = _acknowledger.get()
    if callback is not None:
        try:
            if callback(value) is None:
                raise RuntimeError("Acknowledgement owner no longer holds the operation.")
        except Exception as error:
            raise TelegramAcknowledgementPersistenceError(value) from error


@contextmanager
def acknowledgement_scope(callback):
    token = _acknowledger.set(callback)
    try:
        yield
    finally:
        _acknowledger.reset(token)


class RoutedTelegramSender:
    def __init__(self, sender, *, context, metadata):
        self.sender = sender
        self.context = context or {}
        self.metadata = metadata
        self._invoked = False

    def __getattr__(self, name):
        return getattr(self.sender, name)

    def _requirements(self, values):
        validator = getattr(self.sender, "validate_delivery", None)
        if callable(validator):
            validator(values)
        return TelegramRequirements.from_send(
            **{k: v for k, v in values.items() if k in {
                "message_text", "asset_path", "button_label", "button_url", "disable_link_preview", "caption_entities"}},
            sender_scope=self.context.get("required_sender_scope"))

    def _begin(self, reachability, requirements, values):
        if self._invoked:
            raise TelegramInvocationUnknown("This delivery boundary already began an invocation.")
        if reachability.peer_id != values["chat_id"]:
            raise TelegramPreflightError("Reachability evidence does not match the requested peer.")
        record = self.context.get("record_transport_evidence")
        if not callable(record):
            raise TelegramPreflightError("Durable operation recorder is required before Telegram invocation.")
        payload = dict(values)
        media = values.get("asset_path")
        if media and Path(media).is_file():
            digest = sha256()
            with Path(media).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b""):
                    digest.update(chunk)
            payload["source_media_sha256"] = digest.hexdigest()
        decision = route_evidence(reachability, requirements,
            operation_id=self.context.get("operation_id") or self.context.get("correlation_id"),
            attempt_id=self.context.get("provider_attempt_id") or uuid4(), payload=payload)
        if "source_media_sha256" in payload:
            decision["source_media_sha256"] = payload["source_media_sha256"]
        if values.get("caption_entities") is not None:
            decision["rendered_action"] = {"semantic": "UNLOCK", "rendering": "CAPTION_TEXT_URL",
                "caption": values["message_text"], "entities": values["caption_entities"]}
        decision["invocation_started_at"] = datetime.now(timezone.utc).isoformat()
        if record({"transport_route": decision, "certainty": "UNKNOWN"}) is None:
            raise TelegramInvocationUnknown("Invocation ownership is unavailable; do not resend.")
        self._invoked = True
        self.metadata["transport_route"] = decision
        return record

    def _call(self, name, values):
        method = getattr(self.sender, name)
        prepare = getattr(self.sender, "prepare_delivery", None)
        if not callable(prepare):
            # Injected adapters must implement the contract to enter real send paths.
            raise TelegramPreflightError("Sender has no Telegram capability/reachability contract.")
        requirements = self._requirements(values)
        if inspect.iscoroutinefunction(method) or inspect.iscoroutinefunction(prepare):
            async def execute():
                peer = prepare(chat_id=values["chat_id"], requirements=requirements)
                if inspect.isawaitable(peer):
                    peer = await peer
                if peer.business_connection_id:
                    values["expected_business_connection_id"] = peer.business_connection_id
                record = self._begin(peer, requirements, values)
                with acknowledgement_scope(record):
                    try:
                        result = method(**values)
                        result = await result if inspect.isawaitable(result) else result
                        capture_acknowledgement(getattr(result, "id", result))
                        return result
                    except Exception as error:
                        if getattr(error, "certainty", None) is not None:
                            raise
                        raise TelegramInvocationUnknown("Telegram invocation outcome is unknown.") from error
            return execute()
        peer = prepare(chat_id=values["chat_id"], requirements=requirements)
        if peer.business_connection_id:
            values["expected_business_connection_id"] = peer.business_connection_id
        record = self._begin(peer, requirements, values)
        with acknowledgement_scope(record):
            try:
                result = method(**values)
                capture_acknowledgement(getattr(result, "id", result))
                return result
            except Exception as error:
                if getattr(error, "certainty", None) is not None:
                    raise
                raise TelegramInvocationUnknown("Telegram invocation outcome is unknown.") from error

    def send_text(self, **values):
        return self._call("send_text", values)

    def send_asset(self, **values):
        return self._call("send_asset", values)


class ManualInvocationRecorder:
    """CAS the queued operation before invocation; all later writes use that owner."""
    def __init__(self, repository, operation):
        self.repository = repository
        self.operation_id = operation["operation_id"]
        self.owner = str(uuid4())
        self.begun = False

    def __call__(self, evidence):
        if self.begun and "transport_route" in evidence:
            return None
        if not self.begun:
            result = self.repository.begin_invocation(self.operation_id,
                owner=self.owner, evidence=evidence)
            self.begun = result is not None
            return result
        return self.repository.record_transport_evidence(self.operation_id,
            owner=self.owner, evidence=evidence)

    @property
    def final_owner(self):
        return self.owner if self.begun else None
