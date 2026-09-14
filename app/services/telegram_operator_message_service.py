from uuid import NAMESPACE_URL,uuid5
from app.repositories.chat_message_repository import save_chat_message
from app.repositories.telegram_operator_message_repository import TelegramOperatorMessageRepository
from app.services.telegram_business_commercial_transport import TelegramBusinessCommercialTransport
from app.services.telegram_relationship_control_service import TelegramRelationshipControlService


class TelegramOperatorMessageError(RuntimeError):
    def __init__(self, message, *, status_code=409, operation=None):
        super().__init__(message);self.status_code=status_code;self.operation=operation


class TelegramOperatorMessageService:
    def __init__(self, *, repository=None, controls=None, transport=None,
                 conversation_message_saver=save_chat_message):
        self.repository=repository or TelegramOperatorMessageRepository()
        self.controls=controls or TelegramRelationshipControlService()
        self.transport=transport or TelegramBusinessCommercialTransport()
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
        claimed=self.repository.claim(operation["operation_id"],expected_version=control.control_version)
        if claimed is None: raise TelegramOperatorMessageError("Manual Mode changed before send.",operation=operation)
        try:
            sent=self.transport.send_text(chat_id=context["telegram_chat_id"],message_text=message,
                button_label=None,button_url=None)
            message_id=getattr(sent,"id",sent)
            if not isinstance(message_id,int) or isinstance(message_id,bool):
                raise ConnectionError("Telegram acceptance lacked a provider message ID.")
        except (TimeoutError,ConnectionError,OSError) as error:
            current=self.repository.ambiguous(claimed["operation_id"],error)
            raise TelegramOperatorMessageError("Telegram delivery outcome is uncertain.",operation=current) from error
        except Exception as error:
            current=self.repository.failed(claimed["operation_id"],error)
            raise TelegramOperatorMessageError("Telegram message was not sent.",operation=current) from error
        confirmed=self.repository.confirmed(claimed["operation_id"],message_id)
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
