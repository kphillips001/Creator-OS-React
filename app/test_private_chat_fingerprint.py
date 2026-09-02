from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.fingerprint_price_allocator import (
    FingerprintPoolExhaustedError,
    FingerprintPricePolicy,
)
from app.services.private_chat_unlock_gateway_service import (
    PrivateChatUnlockGatewayService,
    UnlockUnavailableError,
    fingerprint_bootstrap_enabled,
)
from app.services.runtime_media_link_recovery_service import RuntimeMediaLinkRecoveryService


@pytest.fixture(autouse=True)
def _isolate_controlled_launch_boundary(monkeypatch):
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "false")


def test_nearest_first_prices_alternate_down_then_up():
    policy = FingerprintPricePolicy()
    assert list(policy.candidates(1499))[:6] == [1498, 1500, 1497, 1501, 1496, 1502]


def test_feature_defaults_off(monkeypatch):
    monkeypatch.delenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", raising=False)
    assert fingerprint_bootstrap_enabled() is False


def test_launch_fairness_bands_and_five_percent_cap():
    policy = FingerprintPricePolicy()
    assert policy.maximum_delta(500) == 25
    assert policy.maximum_delta(1499) == 50
    assert policy.maximum_delta(3000) == 100
    assert policy.maximum_delta(300) == 15


def test_allocator_excludes_canonical_and_historical_prices():
    policy = FingerprintPricePolicy()
    assert policy.select(1499, excluded_prices={1498, 1500}) == 1497


def test_allocator_fails_closed_when_pool_is_exhausted():
    policy = FingerprintPricePolicy()
    with pytest.raises(FingerprintPoolExhaustedError):
        policy.select(300, excluded_prices=set(policy.candidates(300)))


def _intent():
    return SimpleNamespace(
        purchase_intent_id=uuid4(), telegram_user_id=123, telegram_chat_id=123,
        commercial_offering_id=uuid4(), commercial_publication_id=uuid4(),
        fanvue_account_id=7, expected_currency="USD", expected_price_minor=1499,
        creator_profile_id=2,
    )


class Grants:
    def __init__(self): self.grant = None
    def get_grant_for_intent(self, _): return self.grant
    def create_grant(self, *, grant_id, token, intent, audit_metadata):
        if self.grant is None:
            self.grant = SimpleNamespace(
                unlock_grant_id=grant_id, purchase_intent_id=intent.purchase_intent_id,
                public_alias_hash=None, public_alias_generation=None,
            )
        return self.grant
    def assign_public_alias(self, *, grant_id, alias_hash, generation):
        self.grant.public_alias_hash = alias_hash
        self.grant.public_alias_generation = generation
        return self.grant


def test_gateway_token_is_durable_256_bit_mac_and_button_is_exact(monkeypatch):
    repository = Grants()
    service = PrivateChatUnlockGatewayService(
        repository=repository, token_secret="s" * 32,
    )
    monkeypatch.setenv("CREATOR_OS_PUBLIC_API_URL", "https://creator.example")
    intent = _intent()
    first_grant, first_url = service.issue(intent)
    second_grant, second_url = service.issue(intent)
    assert first_grant.unlock_grant_id == second_grant.unlock_grant_id
    assert first_url == second_url
    assert first_url.startswith("https://creator.example/u/")
    assert len(first_url.rsplit("/", 1)[-1]) == 22
    assert service.BUTTON_LABEL == "🔓 Unlock"


def test_gateway_rejects_missing_public_origin_before_creating_grant(monkeypatch):
    repository = Grants()
    service = PrivateChatUnlockGatewayService(
        repository=repository, token_secret="s" * 32,
    )
    monkeypatch.delenv("CREATOR_OS_PUBLIC_API_URL", raising=False)
    with pytest.raises(UnlockUnavailableError, match="PUBLIC_COMMERCE_ORIGIN_UNAVAILABLE"):
        service.issue(_intent())
    assert repository.grant is None


def test_existing_grant_is_reused_when_only_public_origin_changes(monkeypatch):
    repository = Grants()
    service = PrivateChatUnlockGatewayService(
        repository=repository, token_secret="s" * 32,
    )
    intent = _intent()
    monkeypatch.setenv("CREATOR_OS_PUBLIC_API_URL", "https://one.creator.example")
    first_grant, first_url = service.issue(intent)
    monkeypatch.setenv("CREATOR_OS_PUBLIC_API_URL", "https://two.creator.example")
    second_grant, second_url = service.issue(intent)
    assert first_grant.unlock_grant_id == second_grant.unlock_grant_id
    assert first_url.rsplit("/", 1)[-1] == second_url.rsplit("/", 1)[-1]
    assert first_url != second_url


class ResolveRepository:
    def __init__(self, grant, link=None): self.grant, self.link = grant, link
    def resolve_grant(self, _): return self.grant
    def get_live_link(self, *_args, **_kwargs): return self.link


def test_mapped_customer_redirects_to_canonical_without_fingerprint(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    intent = _intent()
    grant = SimpleNamespace(
        telegram_user_id=intent.telegram_user_id,
        telegram_chat_id=intent.telegram_chat_id,
        commercial_offering_id=intent.commercial_offering_id,
        commercial_publication_id=intent.commercial_publication_id,
        fanvue_account_id=intent.fanvue_account_id,
        currency=intent.expected_currency,
        purchase_intent_id=intent.purchase_intent_id,
        last_used_at=datetime.now(timezone.utc),
    )
    service = PrivateChatUnlockGatewayService(
        repository=ResolveRepository(grant),
        intent_repository=SimpleNamespace(get=lambda _: intent),
        identities=SimpleNamespace(
            get_verified_by_telegram_user_id=lambda _: object()
        ), token_secret="s" * 32,
        purchase_intent_lifecycle=SimpleNamespace(record_click=lambda *_args, **_kwargs: intent),
    )
    monkeypatch.setattr(service, "_eligible_publication", lambda _: {
        "delivery_url": "https://www.fanvue.com/canonical", "media_uuids": ("m",),
    })
    assert service.resolve("x" * 64) == "https://www.fanvue.com/canonical"


def test_migration_091_contains_session_and_concurrency_guards():
    from pathlib import Path
    forward = Path("migrations/forward/20260825_091_private_chat_fingerprint_bootstrap.sql").read_text()
    rollback = Path("migrations/rollback/20260825_091_private_chat_fingerprint_bootstrap.sql").read_text()
    for fragment in (
        "telegram_sales_prospects", "telegram_provisional_sales_sessions",
        "configured_base_price_minor", "actual_fingerprint_price_minor",
        "first_purchase_intent_id UUID NULL UNIQUE",
        "fanvue_fingerprint_reservations", "telegram_unlock_grants",
    ):
        assert fragment in forward
    assert "DROP TABLE IF EXISTS public.telegram_provisional_sales_sessions" in rollback


def test_recovery_reconciles_exactly_one_provider_create_match():
    runtime_id, operation_id = uuid4(), uuid4()
    class Repository:
        def __init__(self): self.activated = None; self.finished = []
        def claim_due_operations(self, **_):
            return [{"operation_id": operation_id, "runtime_media_link_id": runtime_id,
                     "operation_type": "CREATE"}]
        def operation_runtime(self, _):
            return {"runtime_media_link_id": runtime_id, "fanvue_account_id": 7,
                    "exact_price_minor": 1498,
                    "publication_metadata": {"media_link": {"media_uuids": ["m1"]}}}
        def activate(self, runtime_id, **values): self.activated = (runtime_id, values)
        def finish_operation(self, operation_id, **values): self.finished.append((operation_id, values))
    repository = Repository()
    client = SimpleNamespace(find_equivalent_media_link=lambda media, price: [
        {"uuid": "provider-1", "url": "https://fanvue.example/runtime"}])
    result = RuntimeMediaLinkRecoveryService(
        repository=repository, client_factory=lambda _: client).run_once()
    assert result == ((operation_id, "SUCCEEDED"),)
    assert repository.activated[1]["provider_uuid"] == "provider-1"
    assert repository.finished[-1][1]["succeeded"] is True
