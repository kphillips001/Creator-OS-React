import time
from uuid import NAMESPACE_URL,uuid5
from app.repositories.chat_message_repository import save_chat_message
from app.repositories.telegram_operator_message_repository import TelegramOperatorMessageRepository
from app.services.telegram_business_commercial_transport import TelegramBusinessCommercialTransport
from app.services.telegram_relationship_control_service import TelegramRelationshipControlService
from app.services.telegram_manual_transport_resolver import (
    ManualTelegramRouteUnavailable,
    ManualTelegramRuntimeUnavailable,
    StaticBusinessManualTransportResolver,
    TelegramManualTransportResolver,
)


class TelegramOperatorMessageError(RuntimeError):
    def __init__(self, message, *, status_code=409, operation=None,
                 code="MANUAL_TELEGRAM_SEND_FAILED",
                 delivery_certainty="DEFINITELY_NOT_SENT"):
        super().__init__(message);self.status_code=status_code;self.operation=operation
        self.code=code;self.delivery_certainty=delivery_certainty


class TelegramPrivateManualDispatchClient:
    """Wait for the singleton Telegram runtime to execute one durable private send."""
    def __init__(self, repository, *, timeout_seconds=20, poll_seconds=.1, sleep=time.sleep):
        self.repository=repository;self.timeout_seconds=timeout_seconds
        self.poll_seconds=poll_seconds;self.sleep=sleep

    def dispatch(self, operation):
        deadline=time.monotonic()+self.timeout_seconds
        current=operation
        while time.monotonic()<deadline:
            current=self.repository.get(operation["operation_id"]) or current
            if current["state"] in {"CONFIRMED","FAILED","AMBIGUOUS"}: return current
            self.sleep(self.poll_seconds)
        raise ConnectionError("Private Telegram delivery confirmation timed out.")


class TelegramOperatorMessageService:
    def __init__(self, *, repository=None, controls=None, transport=None,
                 resolver=None, private_dispatcher=None,
                 conversation_message_saver=save_chat_message):
        self.repository=repository or TelegramOperatorMessageRepository()
        self.controls=controls or TelegramRelationshipControlService()
        self.transport=transport or TelegramBusinessCommercialTransport()
        self.resolver=resolver or (StaticBusinessManualTransportResolver()
            if transport is not None else TelegramManualTransportResolver())
        self.private_dispatcher=private_dispatcher or TelegramPrivateManualDispatchClient(
            self.repository)
        self.save_message=conversation_message_saver

    def send(self, *, context, text, idempotency_key, expected_control_version, changed_by):
        message=str(text or "").strip()
        if not message: raise TelegramOperatorMessageError("Message text is required.",status_code=422)
        if len(message)>4096: raise TelegramOperatorMessageError("Message is too long.",status_code=422)
        control=self.controls.get(creator_profile_id=context["creator_profile_id"],
            fanvue_account_id=context["fanvue_account_id"],telegram_user_id=context["telegram_user_id"],
            telegram_chat_id=context["telegram_chat_id"])
        if getattr(control,"ignored",False):
            raise TelegramOperatorMessageError(
                "Unignore this relationship before sending a manual message.")
        if not control.manual: raise TelegramOperatorMessageError("Manual Mode is not active.")
        if control.control_version!=int(expected_control_version):
            raise TelegramOperatorMessageError("Relationship control version is stale.")
        durable_scope={key:context.get(key) for key in (
            "creator_profile_id","fanvue_account_id","telegram_user_id","telegram_chat_id",
            "telegram_identity_mapping_id","local_fanvue_user_id","conversation_thread_id")}
        operation=self.repository.reserve(**durable_scope,idempotency_key=str(idempotency_key),
            message_text=message,relationship_control_version=control.control_version,changed_by=changed_by)
        if operation["state"]=="CONFIRMED": return operation
        if operation["state"] in {"SENDING","AMBIGUOUS"}:
            raise TelegramOperatorMessageError("Message delivery requires reconciliation.",operation=operation)
        try: route=self.resolver.resolve(context)
        except ManualTelegramRuntimeUnavailable as error:
            raise TelegramOperatorMessageError(
                "Couldn't send — the private Telegram runtime is not ready. The message was definitely not sent.",
                operation=operation,code=error.code) from error
        except ManualTelegramRouteUnavailable as error:
            claimed=self.repository.claim(operation["operation_id"],
                expected_version=control.control_version,route="NO_ROUTE")
            current=self.repository.failed(operation["operation_id"],error) if claimed else operation
            raise TelegramOperatorMessageError(
                "Couldn't send — this customer isn't reachable through an authorized Telegram route. The message was definitely not sent.",
                operation=current,code=error.code) from error
        claimed=self.repository.claim(operation["operation_id"],
            expected_version=control.control_version,route=route.kind)
        if claimed is None: raise TelegramOperatorMessageError("Manual Mode changed before send.",operation=operation)
        if route.kind == TelegramManualTransportResolver.PRIVATE:
            try: current=self.private_dispatcher.dispatch(claimed)
            except (TimeoutError,ConnectionError,OSError) as error:
                raise TelegramOperatorMessageError(
                    "Delivery status is uncertain — don't retry yet.",operation=claimed,
                    code="MANUAL_TELEGRAM_DELIVERY_UNCERTAIN",
                    delivery_certainty="DELIVERY_UNCERTAIN") from error
            if current["state"] == "CONFIRMED":
                self.controls.repository.touch_manual_activity(control)
                return current
            if current["state"] == "AMBIGUOUS":
                raise TelegramOperatorMessageError(
                    "Delivery status is uncertain — don't retry yet.",operation=current,
                    code="MANUAL_TELEGRAM_DELIVERY_UNCERTAIN",
                    delivery_certainty="DELIVERY_UNCERTAIN")
            raise TelegramOperatorMessageError(
                "Couldn't send — Telegram rejected the private message. The message was definitely not sent.",
                operation=current,code="MANUAL_TELEGRAM_PROVIDER_REJECTED")
        from app.services.telegram_transport_boundary import RoutedTelegramSender, ManualInvocationRecorder
        recorder = ManualInvocationRecorder(self.repository, claimed)
        sender = RoutedTelegramSender(self.transport, context={
            "record_transport_evidence": recorder, "operation_id": str(claimed["operation_id"]),
            "provider_attempt_id": recorder.owner}, metadata={})
        try:
            transport_values={"chat_id":context["telegram_chat_id"],"message_text":message,
                "button_label":None,"button_url":None}
            if route.business_connection_id is not None:
                transport_values["expected_business_connection_id"]=route.business_connection_id
            sent=sender.send_text(**transport_values)
            message_id=getattr(sent,"id",sent)
            if not isinstance(message_id,int) or isinstance(message_id,bool):
                raise ConnectionError("Telegram acceptance lacked a provider message ID.")
        except (TimeoutError,ConnectionError,OSError) as error:
            current=self.repository.ambiguous(claimed["operation_id"],error,owner=recorder.final_owner)
            raise TelegramOperatorMessageError(
                "Delivery status is uncertain — don't retry yet.",operation=current,
                code="MANUAL_TELEGRAM_DELIVERY_UNCERTAIN",
                delivery_certainty="DELIVERY_UNCERTAIN") from error
        except Exception as error:
            current=self.repository.failed(claimed["operation_id"],error,owner=recorder.final_owner)
            raise TelegramOperatorMessageError(
                "Couldn't send — Telegram rejected the message. The message was definitely not sent.",
                operation=current,code=getattr(error,"code","MANUAL_TELEGRAM_PROVIDER_REJECTED")) from error
        confirmed=self.repository.confirmed(claimed["operation_id"],message_id,owner=recorder.final_owner)
        if confirmed is None:
            raise TelegramOperatorMessageError("Confirmation owner changed; do not resend.",
                operation=claimed, delivery_certainty="DELIVERY_UNCERTAIN")
        if context.get("conversation_thread_id") and context.get("local_fanvue_user_id"):
            self.save_message(fanvue_account_id=context["fanvue_account_id"],
                thread_id=context["conversation_thread_id"],fanvue_user_id=context["local_fanvue_user_id"],
                direction="outbound",sender_type="bot",text=message,
                fanvue_message_uuid=uuid5(NAMESPACE_URL,f"telegram:{context['telegram_chat_id']}:outbound:{message_id}"),
                raw_payload={"provider":"TELEGRAM","channel":"PRIVATE_CHAT",
                    "telegram_chat_id":context["telegram_chat_id"],"telegram_message_id":message_id,
                    "origin":"HUMAN_OPERATOR","operator_message_operation_id":str(claimed["operation_id"])})
        self.controls.repository.touch_manual_activity(control)
        return confirmed
