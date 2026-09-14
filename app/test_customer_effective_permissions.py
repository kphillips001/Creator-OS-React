from dataclasses import replace

import pytest

from app.models.telegram_relationship_control import (
    TelegramRelationshipControl, TelegramRelationshipMode,
)
from app.services.customer_effective_permissions_service import (
    CustomerEffectivePermissionsService,
)


class Relationships:
    def __init__(self, *, mode=TelegramRelationshipMode.AVA_AUTO,
                 content=False, session=False):
        self.control = TelegramRelationshipControl(
            None, 1, 2, 3, 3, mode, 0,
            content_selling_enabled=content,
            session_selling_enabled=session)
    def get(self, **_): return self.control
    def takeover(self, **_):
        self.control = replace(self.control, mode=TelegramRelationshipMode.HUMAN_OPERATOR,
                               control_version=self.control.control_version+1)
        return self.control
    def return_to_ava(self, **_):
        self.control = replace(self.control, mode=TelegramRelationshipMode.AVA_AUTO,
                               control_version=self.control.control_version+1)
        return self.control
    def set_content_selling(self, value, **_):
        if value != self.control.content_selling_enabled:
            self.control = replace(self.control, content_selling_enabled=value,
                                   control_version=self.control.control_version+1)
        return self.control
    def set_session_selling(self, value, **_):
        if value != self.control.session_selling_enabled:
            self.control = replace(self.control, session_selling_enabled=value,
                                   control_version=self.control.control_version+1)
        return self.control


class Ava:
    def __init__(self, desired="ON", effective="ON"):
        self.state = {"desired": desired, "effective": effective}
    def read(self, **_): return {"avaBot": self.state}


class Global:
    def __init__(self, content=True, session=True):
        self.content, self.session = content, session
    def read(self): return {"contentSellingEnabled": self.content,
                            "sessionSellingEnabled": self.session}


def service(relationships, *, ava=None, global_permissions=None):
    return CustomerEffectivePermissionsService(
        relationship_controls=relationships, ava_bot_controls=ava or Ava(),
        global_selling_permissions=global_permissions or Global())


def scope():
    return dict(creator_profile_id=1, fanvue_account_id=2,
                telegram_user_id=3, telegram_chat_id=3)


def test_new_customer_control_defaults_all_customer_permissions_on():
    control = TelegramRelationshipControl(
        None, 1, 2, 3, 3, TelegramRelationshipMode.AVA_AUTO, 0,
    )
    assert control.mode is TelegramRelationshipMode.AVA_AUTO
    assert control.content_selling_enabled is True
    assert control.session_selling_enabled is True


def test_global_off_cannot_be_overridden_by_customer_on():
    relationships = Relationships(content=True, session=True)
    state = service(relationships, ava=Ava("OFF", "OFF"),
                    global_permissions=Global(False, False)).read(**scope())
    assert state["configured"]["avaChatEnabled"] is True
    assert state["effective"]["chatAllowed"] is False
    assert state["effective"]["chatReason"] == "GLOBAL_AVA_BOT_DISABLED"
    assert state["effective"]["contentSellingReason"] == "GLOBAL_CONTENT_SELLING_DISABLED"
    assert state["effective"]["sessionSellingReason"] == "GLOBAL_SESSION_SELLING_DISABLED"


def test_customer_restrictions_narrow_globally_enabled_permissions():
    state = service(Relationships()).read(**scope())
    assert state["effective"]["chatAllowed"] is True
    assert state["effective"]["contentSellingAllowed"] is False
    assert state["effective"]["contentSellingReason"] == "CUSTOMER_CONTENT_SELLING_DISABLED"
    assert state["effective"]["sessionSellingReason"] == "CUSTOMER_SESSION_SELLING_DISABLED"


@pytest.mark.parametrize("mode,content,session,expected", [
    (TelegramRelationshipMode.HUMAN_OPERATOR, True, True, (False, False, False)),
    (TelegramRelationshipMode.AVA_AUTO, False, False, (True, False, False)),
    (TelegramRelationshipMode.AVA_AUTO, True, False, (True, True, False)),
    (TelegramRelationshipMode.AVA_AUTO, False, True, (True, False, True)),
    (TelegramRelationshipMode.AVA_AUTO, True, True, (True, True, True)),
])
def test_customer_effective_permission_matrix(mode, content, session, expected):
    state = service(Relationships(
        mode=mode, content=content, session=session,
    )).read(**scope())
    assert (
        state["effective"]["chatAllowed"],
        state["effective"]["contentSellingAllowed"],
        state["effective"]["sessionSellingAllowed"],
    ) == expected


def test_mutations_are_independent_and_identical_patch_is_idempotent():
    relationships = Relationships()
    controls = service(relationships)
    first = controls.set_content(True, changed_by="OPERATOR", **scope())
    second = controls.set_content(True, changed_by="OPERATOR", **scope())
    assert first["state"]["configured"]["contentSellingEnabled"] is True
    assert second["changed"] is False
    assert relationships.control.control_version == 1
    controls.set_chat(False, changed_by="OPERATOR", **scope())
    assert relationships.control.mode is TelegramRelationshipMode.HUMAN_OPERATOR
    assert relationships.control.content_selling_enabled is True


def test_one_customer_control_does_not_change_another():
    first, second = Relationships(), Relationships(content=True)
    service(first).set_session(True, changed_by="OPERATOR", **scope())
    assert first.control.session_selling_enabled is True
    assert second.control.session_selling_enabled is False


def test_restrictions_survive_service_restart_username_change_and_mapping():
    repository_backed = Relationships(content=False, session=False)
    first_process = service(repository_backed)
    first_process.set_chat(False, changed_by="OPERATOR", **scope())
    # Username is intentionally not part of the authority key. Mapping enriches
    # the same Telegram-owned row rather than replacing it.
    repository_backed.control = replace(
        repository_backed.control, telegram_identity_mapping_id=44,
        local_fanvue_user_id=55)
    restarted = service(repository_backed)
    state = restarted.read(**scope())
    assert state["configured"] == {
        "avaChatEnabled": False,
        "contentSellingEnabled": False,
        "sessionSellingEnabled": False,
        "relationshipMode": "HUMAN_OPERATOR",
        "controlVersion": 1,
    }
    assert state["identity"]["telegramIdentityMappingId"] == 44
    assert state["identity"]["localFanvueUserId"] == 55
