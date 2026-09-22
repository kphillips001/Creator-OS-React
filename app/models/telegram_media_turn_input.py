"""Typed, non-textual input reconstructed from canonical durable media evidence."""
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TelegramMediaTurnInput:
    media_turn_id: str
    media_operation_id: str
    response_operation_id: str
    telegram_user_id: int
    telegram_chat_id: int
    member_message_ids: tuple[int, ...]
    attachment_ids: tuple[str, ...]
    response_policy: str
    obligations: tuple[str, ...]
    associated_text: str = ""

    @classmethod
    def from_context(cls, context, *, operation_id, user_id, chat_id, message_id):
        authority = context.get('turn_authority') or {}
        for key in ('media_turn_id', 'operation_id'):
            UUID(str(context[key]))
        UUID(str(operation_id))
        ids = tuple(str(UUID(str(x))) for x in context.get('attachment_ids', ()))
        members = tuple(int(x) for x in authority.get('member_message_ids', ()))
        if (not ids or len(ids) != len(context.get('attachment_paths', ()))
                or message_id not in members
                or str(authority.get('response_operation_id')) != str(operation_id)
                or authority.get('telegram_user_id') != user_id
                or authority.get('telegram_chat_id') != chat_id
                or not context.get('response_policy')):
            raise ValueError('MEDIA_TURN_AUTHORITY_MISMATCH')
        return cls(str(context['media_turn_id']), str(context['operation_id']),
                   str(operation_id), user_id, chat_id, members, ids,
                   str(context['response_policy']), tuple(authority.get('obligations', ())),
                   str(authority.get('associated_text') or ''))

    def matches(self, payload):
        return (self.telegram_user_id == payload.telegram_user_id
                and self.telegram_chat_id == payload.telegram_chat_id
                and self.response_operation_id == str(payload.ordinary_reply_operation_id)
                and payload.message_id in self.member_message_ids)
