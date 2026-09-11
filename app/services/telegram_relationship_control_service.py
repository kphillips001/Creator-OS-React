from app.repositories.telegram_relationship_control_repository import TelegramRelationshipControlRepository


class TelegramRelationshipControlService:
    HOLD_REASON="RELATIONSHIP_HUMAN_OPERATOR_ACTIVE"
    def __init__(self, repository=None): self.repository=repository or TelegramRelationshipControlRepository()
    def get(self, **scope): return self.repository.get(**scope)
    def takeover(self, **scope): return self.repository.transition(mode="HUMAN_OPERATOR",**scope)
    def return_to_ava(self, **scope): return self.repository.transition(mode="AVA_AUTO",**scope)
    def set_content_selling(self, value, **scope):
        return self.repository.set_permissions(content_selling_enabled=value, **scope)
    def set_session_selling(self, value, **scope):
        return self.repository.set_permissions(session_selling_enabled=value, **scope)
    def autonomous_allowed(self, *, creator_profile_id, fanvue_account_id,
                           telegram_user_id, telegram_chat_id=None,
                           captured_version=None):
        control=self.get(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,telegram_chat_id=telegram_chat_id)
        allowed=not control.manual and (captured_version is None or captured_version==control.control_version)
        return allowed,control
    def autonomous_send_guard(self, **scope): return self.repository.autonomous_send_guard(**scope)
