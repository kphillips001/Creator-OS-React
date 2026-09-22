from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository


class OrdinaryReplyCancellationError(RuntimeError):
    pass


class OrdinaryReplyCancellationService:
    ACCOUNT_SCOPE = "AVA_TELETHON_PRIVATE"

    def __init__(self, repository=None):
        self.repository = repository or OrdinaryChatReplyRepository()

    def cancel(self, *, operation_id, telegram_chat_id, telegram_user_id,
               inbound_message_id, cancelled_by="CREATOR_OS_OPERATOR"):
        outcome, operation = self.repository.cancel_operator_reply(
            operation_id=operation_id,
            account_scope=self.ACCOUNT_SCOPE,
            chat_id=int(telegram_chat_id),
            sender_user_id=int(telegram_user_id),
            inbound_message_id=int(inbound_message_id),
            cancelled_by=cancelled_by,
        )
        if outcome == "AUTHORITY_MISMATCH":
            raise OrdinaryReplyCancellationError(
                "Reply operation no longer belongs to this conversation.")
        if outcome == "DELIVERY_OR_LIFECYCLE_WON":
            raise OrdinaryReplyCancellationError(
                "Reply cancellation was refused because delivery or another lifecycle transition already started.")
        return operation, outcome == "CANCELLED"
