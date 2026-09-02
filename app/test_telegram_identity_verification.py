from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.models.conversation_gateway import ConversationGatewayOutput
from app.models.telegram_inbound import TelegramInboundPayload
from app.repositories.telegram_identity_repository import TelegramIdentityConflictError
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_identity_service import TelegramIdentityNotFoundError
from app.services.telegram_identity_verification_service import TelegramIdentityVerificationService
from app.services.telegram_inbound_adapter import TelegramInboundAdapter


NOW = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)


class FakeRepository:
    def __init__(self):
        self.rows = []
        self.proofs = {}
        self.mappings = {}

    def pending(self, *, telegram_user_id, fanvue_account_id):
        return next((row for row in self.rows if row["telegram_user_id"] == telegram_user_id
                     and row["fanvue_account_id"] == fanvue_account_id
                     and row["state"] == "PENDING" and row["expires_at"] > NOW), None)

    def create(self, **values):
        row = {"challenge_id": uuid4(), "state": "PENDING", "created_at": NOW,
               "consumed_at": None, "attempt_count": 0,
               "resulting_identity_mapping_id": None,
               "provider_fanvue_user_uuid": None, **values}
        self.rows.append(row)
        return row

    def complete(self, *, fanvue_account_id, fanvue_user_uuid, token_hash,
                 provider_event_id):
        row = next((item for item in self.rows if item["fanvue_account_id"] == fanvue_account_id
                    and item["token_hash"] == token_hash), None)
        if row is None:
            return {"status": "NO_MATCH"}
        if row["state"] == "VERIFIED":
            return ({"status": "VERIFIED", "mapping": self.mappings[row["telegram_user_id"]],
                     "duplicate": True} if row["provider_fanvue_user_uuid"] == fanvue_user_uuid
                    else {"status": "CONFLICT"})
        if row["expires_at"] <= NOW:
            row["state"] = "EXPIRED"
            return {"status": "EXPIRED"}
        current_tg = self.mappings.get(row["telegram_user_id"])
        current_fv = next((value for value in self.mappings.values()
                           if value.external_fanvue_user_uuid == fanvue_user_uuid), None)
        if current_tg and current_tg.external_fanvue_user_uuid != fanvue_user_uuid:
            raise TelegramIdentityConflictError("Telegram conflict")
        if current_fv and current_fv.telegram_user_id != row["telegram_user_id"]:
            raise TelegramIdentityConflictError("Fanvue conflict")
        mapping = current_tg or SimpleNamespace(
            id=len(self.mappings) + 1, telegram_user_id=row["telegram_user_id"],
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=fanvue_user_uuid,
            verification_status="VERIFIED", is_active=True,
        )
        self.mappings[row["telegram_user_id"]] = mapping
        row.update(state="VERIFIED", consumed_at=NOW,
                   provider_fanvue_user_uuid=fanvue_user_uuid,
                   resulting_identity_mapping_id=mapping.id)
        self.proofs[provider_event_id] = row["challenge_id"]
        return {"status": "VERIFIED", "mapping": mapping, "duplicate": current_tg is not None}


def service(repository=None, *, enabled=True):
    return TelegramIdentityVerificationService(
        repository=repository or FakeRepository(), clock=lambda: NOW,
        enabled=enabled,
        intent_detector=SimpleNamespace(
            has_direct_purchase_intent=lambda message: "buy" in message.lower()
        ),
    )


def test_feature_defaults_off_when_environment_is_absent(monkeypatch):
    monkeypatch.delenv(
        TelegramIdentityVerificationService.FEATURE_FLAG, raising=False
    )
    value = TelegramIdentityVerificationService(repository=FakeRepository())
    assert value.enabled is False
    assert value.should_start("I want to buy that") is False


def test_environment_flag_can_enable_preserved_flow_in_isolation(monkeypatch):
    monkeypatch.setenv(
        TelegramIdentityVerificationService.FEATURE_FLAG, "true"
    )
    repository = FakeRepository()
    value = TelegramIdentityVerificationService(
        repository=repository, clock=lambda: NOW,
        intent_detector=SimpleNamespace(
            has_direct_purchase_intent=lambda message: True
        ),
    )
    assert value.enabled is True
    challenge = start(value)
    assert challenge.verification_code.startswith("AVA-")
    assert len(repository.rows) == 1


def test_disabled_service_cannot_create_or_consume_challenge():
    repository = FakeRepository()
    value = service(repository, enabled=False)
    with pytest.raises(RuntimeError, match="disabled"):
        start(value)
    assert repository.rows == []
    assert value.complete_from_fanvue_message(
        fanvue_account_id=2, fanvue_user_uuid=uuid4(),
        message_text="AVA-222222222222", provider_event_id="evt-disabled",
    ) == {"status": "DISABLED"}
    assert repository.mappings == {}


def start(value, telegram_user_id=101, account=2):
    return value.start(telegram_user_id=telegram_user_id,
                       telegram_chat_id=telegram_user_id,
                       fanvue_account_id=account)


def complete(value, code, fanvue_uuid=None, account=2, event="evt-1"):
    return value.complete_from_fanvue_message(
        fanvue_account_id=account,
        fanvue_user_uuid=fanvue_uuid or uuid4(),
        message_text=code,
        provider_event_id=event,
    )


def test_code_has_sixty_bits_is_hashed_and_persists_across_service_restart():
    repository = FakeRepository()
    challenge = start(service(repository))
    assert challenge.verification_code.startswith("AVA-")
    assert len(challenge.verification_code.removeprefix("AVA-")) == 12
    assert challenge.verification_code not in str(repository.rows)
    restarted = service(repository)
    assert start(restarted).already_pending is True


def test_duplicate_start_keeps_one_pending_challenge_without_disclosing_code_again():
    value = service()
    first, second = start(value), start(value)
    assert first.challenge_id == second.challenge_id
    assert second.verification_code is None
    assert len(value.repository.rows) == 1


def test_correct_signed_fanvue_message_verifies_mapping_and_duplicate_is_idempotent():
    value = service()
    challenge = start(value)
    buyer = uuid4()
    first = complete(value, challenge.verification_code, buyer)
    second = complete(value, challenge.verification_code, buyer, event="evt-1")
    assert first["status"] == second["status"] == "VERIFIED"
    assert second["duplicate"] is True
    assert len(value.repository.mappings) == 1


def test_wrong_token_and_cross_account_token_are_rejected():
    value = service()
    challenge = start(value)
    assert complete(value, "AVA-222222222222")["status"] == "NO_MATCH"
    assert complete(value, challenge.verification_code, account=3)["status"] == "NO_MATCH"
    assert value.repository.mappings == {}


def test_expired_token_cannot_map():
    value = service()
    challenge = start(value)
    value.repository.rows[0]["expires_at"] = NOW - timedelta(seconds=1)
    assert complete(value, challenge.verification_code)["status"] == "EXPIRED"
    assert value.repository.mappings == {}


def test_stolen_consumed_code_cannot_remap_to_another_fanvue_customer():
    value = service()
    challenge = start(value)
    assert complete(value, challenge.verification_code, uuid4())["status"] == "VERIFIED"
    assert complete(value, challenge.verification_code, uuid4(), event="evt-2")["status"] == "CONFLICT"
    assert len(value.repository.mappings) == 1


def test_telegram_and_reverse_fanvue_conflicts_fail_closed():
    repository = FakeRepository()
    buyer_x, buyer_y = uuid4(), uuid4()
    first = start(service(repository), telegram_user_id=101)
    complete(service(repository), first.verification_code, buyer_x)
    repository.rows[0]["state"] = "CANCELLED"
    second = start(service(repository), telegram_user_id=101)
    with pytest.raises(TelegramIdentityConflictError):
        complete(service(repository), second.verification_code, buyer_y)
    third = start(service(repository), telegram_user_id=202)
    with pytest.raises(TelegramIdentityConflictError):
        complete(service(repository), third.verification_code, buyer_x)


def test_username_is_not_an_input_to_verification_or_mapping():
    value = service()
    challenge = start(value)
    result = complete(value, challenge.verification_code)
    assert result["mapping"].telegram_user_id == 101
    assert "username" not in value.repository.rows[0]


class Gateway:
    def execute(self, request):
        return ConversationGatewayOutput(
            correlation_id=request.correlation_id, response_text="normal reply",
            offer_authorized=False, offer_link=None, blocked=False, error_code=None,
            diagnostic_metadata={"customer_sales_decision": "MANUAL_REVIEW",
                                 "customer_sales_reason_code": "IDENTITY_UNRESOLVED"},
        )


def payload(text):
    return TelegramInboundPayload(telegram_user_id=101, telegram_chat_id=101,
                                  message_text=text, message_id=1, chat_history=[])


def test_unknown_user_can_chat_without_being_nagged_on_normal_message():
    identities = SimpleNamespace(
        observe=lambda **kwargs: None,
        resolve_telegram_identity=lambda value: (_ for _ in ()).throw(
            TelegramIdentityNotFoundError("unknown")),
    )
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=Gateway(), telegram_identity_service=identities,
        fanvue_account_id=2, identity_verification_service=service(),
    )
    result = adapter.execute(payload("hello Ava"))
    assert result.response_text == "normal reply"
    assert "identity_verification" not in result.diagnostic_metadata


def test_unknown_user_buying_request_starts_challenge_and_never_gets_offer():
    identities = SimpleNamespace(
        observe=lambda **kwargs: None,
        resolve_telegram_identity=lambda value: (_ for _ in ()).throw(
            TelegramIdentityNotFoundError("unknown")),
    )
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=Gateway(), telegram_identity_service=identities,
        fanvue_account_id=2, identity_verification_service=service(),
    )
    result = adapter.execute(payload("I want to buy that"))
    assert "send me this one-time code" in result.response_text
    assert result.diagnostic_metadata["identity_verification"] == "PENDING"
    assert result.offer_authorized is False
    assert result.offer_link is None


def test_unknown_buying_request_does_not_start_challenge_when_disabled():
    repository = FakeRepository()
    identities = SimpleNamespace(
        observe=lambda **kwargs: None,
        resolve_telegram_identity=lambda value: (_ for _ in ()).throw(
            TelegramIdentityNotFoundError("unknown")),
    )
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=Gateway(), telegram_identity_service=identities,
        fanvue_account_id=2,
        identity_verification_service=service(repository, enabled=False),
    )
    result = adapter.execute(payload("I want to buy that"))
    assert result.response_text == "normal reply"
    assert "AVA-" not in result.response_text
    assert "identity_verification" not in result.diagnostic_metadata
    assert repository.rows == []


def test_non_challenge_fanvue_message_is_ignored_by_verifier():
    value = service()
    result = value.complete_from_fanvue_message(
        fanvue_account_id=2, fanvue_user_uuid=uuid4(),
        message_text="hello Ava", provider_event_id="evt-normal",
    )
    assert result == {"status": "NOT_A_CHALLENGE"}
