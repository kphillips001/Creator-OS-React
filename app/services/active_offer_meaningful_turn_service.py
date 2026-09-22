"""Restart-stable meaningful customer-turn projection for an active offer."""
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.ava_attention_investment_service import AvaAttentionInvestmentService

class ActiveOfferMeaningfulTurnService:
    def __init__(self, *, operations=None, attention=None):
        self.operations=operations or OrdinaryChatReplyRepository()
        self.attention=attention or AvaAttentionInvestmentService()

    def project(self, *, intent, account_scope="AVA_TELETHON_PRIVATE"):
        if (intent is None or getattr(intent,"presented_at",None) is None
                or getattr(intent,"telegram_chat_id",None) is None
                or getattr(intent,"telegram_user_id",None) is None):
            return {"meaningful_turns_since_presentation":0,
                    "window_start":None,"authority":"NO_PRESENTED_OFFER"}
        rows=self.operations.post_presentation_turn_candidates(
            account_scope=account_scope,chat_id=int(intent.telegram_chat_id),
            sender_user_id=int(intent.telegram_user_id),presented_at=intent.presented_at)
        included=[]; excluded=[]
        for row in rows:
            text=str(row.get("inbound_message_text") or "").strip()
            if not text or self.attention._low_information(text):
                excluded.append({"message_id":row["inbound_telegram_message_id"],
                                 "reason":"CANONICAL_LOW_INFORMATION"})
            else:
                included.append(row["inbound_telegram_message_id"])
        return {"meaningful_turns_since_presentation":len(included),
                "window_start":intent.presented_at,"window_end":"CURRENT_PERSISTED_STATE",
                "account_scope":account_scope,"telegram_chat_id":intent.telegram_chat_id,
                "included_message_ids":tuple(included),"excluded":tuple(excluded),
                "authority":"ORDINARY_CHAT_REPLY_OPERATIONS_PLUS_CANONICAL_ATTENTION"}
