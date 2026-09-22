"""One explicitly authorized operator campaign on the shared delivery lifecycle.

No HTTP endpoint, customer selection, LLM, retry, or independent Telegram client.
Sequence numbers occupy a dedicated audit scope; they are not Telegram inbound IDs.
"""
import asyncio
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5, uuid4

from app.models.telegram_transport_contract import TelegramRequirements
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.telegram_transport_boundary import RoutedTelegramSender


PEER = 7857064998
SCOPE = "OPERATOR_TRANSPORT_CERTIFICATION_20260920"
TEXT = "Creator-OS transport test"
CAPTION = "Creator-OS media transport test"
ROOT = Path(__file__).resolve().parents[2]
IMAGE = ROOT / ".tmp" / "telegram-neutral-certification.png"


def neutral_image_bytes():
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (640, 360), "white")
    ImageDraw.Draw(image).text((180, 170), "Creator-OS Transport Test", fill="black")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def operation_id(kind):
    if kind not in {"text", "media"}:
        raise ValueError("Only the authorized text and media tests exist")
    return uuid5(NAMESPACE_URL, f"{SCOPE}:{PEER}:{kind}")


class TelegramTransportCertificationService:
    def __init__(self, repository=None):
        self.repository = repository or OrdinaryChatReplyRepository()

    def enqueue(self, kind):
        identifier = operation_id(kind)
        prior = self.repository.get(identifier)
        if prior is not None:
            return prior  # Never re-arm a test, including failed/uncertain tests.
        if kind == "media":
            text = self.repository.get(operation_id("text"))
            if text is None or text.state.value != "SENT_CONFIRMED":
                raise ValueError("Text must be SENT_CONFIRMED before media is prepared")
            IMAGE.parent.mkdir(parents=True, exist_ok=True)
            IMAGE.write_bytes(neutral_image_bytes())
        message = TEXT if kind == "text" else CAPTION
        audit = {"operator_transport_certification": {
            "campaign": SCOPE, "recipient": PEER, "kind": kind,
            "source": "EXPLICIT_OPERATOR_TEST_AUTHORIZATION",
            "sequence_is_not_telegram_inbound": True,
        }}
        with self.repository.connection_factory() as connection:
            connection.execute("""INSERT INTO ordinary_chat_reply_operations(
                operation_id,telegram_account_scope,telegram_chat_id,
                inbound_telegram_message_id,inbound_sender_telegram_user_id,
                correlation_id,inbound_message_text,state,response_text,
                response_content_sha256,response_payload,delivery_payload,
                generated_at,max_send_attempts,max_generation_attempts)
                VALUES(%s,%s,%s,%s,%s,%s,%s,'GENERATED',%s,%s,%s::jsonb,%s::jsonb,
                       NOW(),1,1) ON CONFLICT DO NOTHING""",
                (identifier,SCOPE,PEER,1 if kind == "text" else 2,PEER,
                 f"{SCOPE}:{kind}","OPERATOR TEST — not an inbound message",
                 message,sha256(message.encode()).hexdigest(),json.dumps(audit),
                 json.dumps(audit)))
        return self.repository.get(identifier)

    def _validate(self, operation, kind):
        if (operation.operation_id != operation_id(kind)
                or operation.telegram_account_scope != SCOPE
                or operation.telegram_chat_id != PEER
                or operation.inbound_sender_telegram_user_id != PEER
                or operation.response_text != (TEXT if kind == "text" else CAPTION)
                or operation.send_attempt_count != 0):
            raise ValueError("Certification scope/content/attempt mismatch")
        if kind == "media":
            text = self.repository.get(operation_id("text"))
            if text is None or text.state.value != "SENT_CONFIRMED":
                raise ValueError("Text is not confirmed")
            if not IMAGE.is_file() or IMAGE.read_bytes() != neutral_image_bytes():
                raise ValueError("Only the exact neutral fixture is authorized")

    async def poll(self, transport):
        # Fixed IDs, never discover arbitrary customer work or retry an attempt.
        for kind in ("text", "media"):
            operation = await asyncio.to_thread(self.repository.get, operation_id(kind))
            if operation is None:
                return
            if operation.state.value == "SENT_CONFIRMED":
                continue
            if operation.state.value != "GENERATED":
                return
            owner = f"operator-certification:{uuid4()}"
            try:
                await asyncio.to_thread(self._validate, operation, kind)
                values = {"chat_id": PEER, "message_text": operation.response_text}
                if kind == "media":
                    values["asset_path"] = str(IMAGE)
                requirements = TelegramRequirements.from_send(
                    message_text=operation.response_text,
                    asset_path=values.get("asset_path"), sender_scope="AVA_TELETHON_PRIVATE")
                # Preflight inside the actual authorized singleton, before claim.
                await transport.prepare_delivery(chat_id=PEER, requirements=requirements)
            except Exception as error:
                await asyncio.to_thread(self.repository.fail_generated_before_send,
                    operation.operation_id, reason="CERTIFICATION_PREFLIGHT:" + type(error).__name__)
                # max_send_attempts=1 is not enough before an attempt; explicitly
                # leave this scope outside all normal automatic retry discovery.
                return
            claimed = await asyncio.to_thread(self.repository.claim_send,
                operation.operation_id, owner=owner)
            if claimed is None:
                return
            def record(evidence):
                return self.repository.record_provider_evidence(
                    operation.operation_id, owner=owner, evidence=evidence)
            sender = RoutedTelegramSender(transport, context={
                "operation_id": str(operation.operation_id),
                "provider_attempt_id": owner,
                "required_sender_scope": "AVA_TELETHON_PRIVATE",
                "record_transport_evidence": record}, metadata={})
            try:
                result = await (sender.send_text(**values) if kind == "text"
                                else sender.send_asset(**values))
                message_id = getattr(result, "id", result)
                if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
                    raise RuntimeError("Missing provider message ID")
                confirmed = await asyncio.to_thread(self.repository.confirm_sent,
                    operation.operation_id, owner=owner, telegram_message_id=message_id)
                if confirmed is None:
                    raise RuntimeError("Confirmation persistence failed")
            except Exception as error:
                await asyncio.to_thread(self.repository.fail_send,
                    operation.operation_id, owner=owner,
                    reason="CERTIFICATION_STOP:" + type(error).__name__, ambiguous=True)
                return
            # One operation per scheduler cycle; media requires a separate CLI command.
            return
