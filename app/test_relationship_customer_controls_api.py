from app.api import relationships as api


class Controls:
    def __init__(self): self.calls=[]
    def read(self, **scope):
        return {"configured":{"avaChatEnabled":True,
                "contentSellingEnabled":False,"sessionSellingEnabled":False},
                "effective":{"chatAllowed":False,
                "chatReason":"GLOBAL_AVA_BOT_DISABLED"}}
    def set_chat(self, value, **scope): self.calls.append(("chat",value,scope)); return {"state":self.read()}
    def set_content(self, value, **scope): self.calls.append(("content",value,scope)); return {"state":self.read()}
    def set_session(self, value, **scope): self.calls.append(("session",value,scope)); return {"state":self.read()}


def test_customer_control_api_returns_configured_and_effective_state(monkeypatch):
    service=Controls()
    context={"telegram_chat_id":4,"telegram_identity_mapping_id":5,
             "local_fanvue_user_id":6}
    monkeypatch.setattr(api,"_relationship_scope",lambda _key:(1,2,3,context))
    monkeypatch.setattr(api,"_customer_permissions_service",lambda:service)
    read=api.relationship_automation_controls("telegram:1:2:3")
    assert read["configured"]["avaChatEnabled"] is True
    assert read["effective"]["chatAllowed"] is False
    body=api.CustomerPermissionChange(value=True,reason="operator choice")
    api.patch_relationship_content_selling("telegram:1:2:3",body)
    api.patch_relationship_session_selling("telegram:1:2:3",body)
    assert [call[0] for call in service.calls]==["content","session"]
    assert all(call[2]["telegram_user_id"]==3 for call in service.calls)
