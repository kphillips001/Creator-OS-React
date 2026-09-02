"""Final real-PostgreSQL closure coverage for private-chat identity bootstrap."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

import pytest
from types import SimpleNamespace

from app.repositories.private_chat_fingerprint_repository import PrivateChatFingerprintRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.repositories.customer_commerce_memory_repository import CustomerCommerceMemoryRepository
from app.repositories.ownership_intelligence_repository import OwnershipIntelligenceRepository
from app.repositories.telegram_sales_prospect_repository import TelegramSalesProspectRepository
from app.models.ownership_intelligence import OwnershipIdentity
from app.services.customer_commerce_memory_service import CustomerCommerceMemoryService
from app.services.ownership_intelligence_service import OwnershipIntelligenceService
from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService
from app.services.private_chat_unlock_gateway_service import (
    PrivateChatUnlockGatewayService, UnlockUnavailableError,
)
from app.services.runtime_media_link_recovery_service import RuntimeMediaLinkRecoveryService
from app.test_private_chat_settlement_postgres import connection_factory, fixture, settle, state


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@pytest.fixture(autouse=True)
def isolate_synthetic_identity_from_live_boundary(monkeypatch):
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_ALLOWED_FANVUE_HOSTNAMES", "example.invalid")


def _repository():
    return PrivateChatFingerprintRepository(connection_factory=connection_factory)


def _intent(values):
    return PurchaseIntentRepository(connection_factory=connection_factory).get(values["intent_id"])


def _prepare_unopened(values):
    with connection_factory() as c:
        c.execute("DELETE FROM fanvue_runtime_media_links WHERE purchase_intent_id=%s", (values["intent_id"],))
        c.execute("DELETE FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s", (values["intent_id"],))
        c.execute("""UPDATE purchase_intents SET status='PRESENTED',
            presented_at=NOW(),telegram_message_id=900001
            WHERE purchase_intent_id=%s""", (values["intent_id"],))
        c.execute("INSERT INTO commercial_offering_assets(offering_id,asset_id,position) VALUES (%s,%s,1) ON CONFLICT DO NOTHING", (values["offering_id"], values["asset"]))
    return values


class FakeProvider:
    def __init__(self):
        self.lock = Lock()
        self.resources = []
        self.create_calls = 0
        self.delete_calls = 0
        self.fail_create = False
        self.fail_delete = False

    def find_equivalent_media_link(self, media, price):
        with self.lock:
            return [dict(item) for item in self.resources if item["price"] == price and item["media"] == tuple(media)]

    def create_media_link(self, media, price):
        with self.lock:
            self.create_calls += 1
            if self.fail_create:
                raise ConnectionError("synthetic create failure")
            item = {"uuid": str(uuid4()), "url": f"https://example.invalid/{uuid4()}",
                    "media": tuple(media), "price": price}
            self.resources.append(item)
            return dict(item)

    def delete_media_link(self, provider_uuid):
        with self.lock:
            self.delete_calls += 1
            if self.fail_delete:
                raise ConnectionError("synthetic delete failure")
            self.resources = [item for item in self.resources if item["uuid"] != provider_uuid]


def _gateway(values, provider):
    return PrivateChatUnlockGatewayService(
        repository=_repository(),
        intent_repository=PurchaseIntentRepository(connection_factory=connection_factory),
        identities=TelegramIdentityRepository(connection_factory=connection_factory),
        client_factory=lambda _: provider,
        connection_factory=connection_factory,
        token_secret="s" * 32,
    )


def _issue(values, provider):
    gateway = _gateway(values, provider)
    _, url = gateway.issue(_intent(values))
    return gateway, url.rsplit("/", 1)[-1]


def _counts(values):
    with connection_factory() as c:
        return c.execute("""SELECT
            (SELECT count(*) FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s) reservations,
            (SELECT count(*) FROM fanvue_runtime_media_links WHERE purchase_intent_id=%s) runtimes,
            (SELECT count(*) FROM fanvue_runtime_media_link_operations operation JOIN fanvue_runtime_media_links runtime USING(runtime_media_link_id) WHERE runtime.purchase_intent_id=%s AND operation.operation_type='CREATE') creates""",
            (values["intent_id"], values["intent_id"], values["intent_id"])).fetchone()


def test_real_concurrent_fingerprint_allocation_is_unique_and_same_intent_converges():
    first = _prepare_unopened(fixture())
    second = _prepare_unopened(fixture())
    with connection_factory() as c:
        c.execute("UPDATE purchase_intents SET fanvue_account_id=%s WHERE purchase_intent_id=%s", (first["account"], second["intent_id"]))
    intents = (_intent(first), _intent(second))
    repo = _repository()
    def allocate(item):
        return repo.reserve_price(intent=item, canonical_prices={1499}, candidate_prices=(1498, 1497, 1496))
    with ThreadPoolExecutor(max_workers=2) as pool:
        allocated = list(pool.map(allocate, intents))
    assert {item.exact_price_minor for item in allocated} == {1498, 1497}
    with ThreadPoolExecutor(max_workers=2) as pool:
        repeated = list(pool.map(lambda _: allocate(intents[0]), range(2)))
    assert repeated[0].fingerprint_reservation_id == repeated[1].fingerprint_reservation_id
    with connection_factory() as c:
        rows = c.execute("SELECT exact_price_minor,count(*) n FROM fanvue_fingerprint_reservations WHERE fanvue_account_id=%s AND currency='USD' GROUP BY exact_price_minor", (first["account"],)).fetchall()
    assert all(row["n"] == 1 for row in rows)


def test_real_concurrent_unlock_converges_on_one_authoritative_resource(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    values = _prepare_unopened(fixture())
    provider = FakeProvider()
    gateway, token = _issue(values, provider)
    with ThreadPoolExecutor(max_workers=2) as pool:
        urls = list(pool.map(lambda _: gateway.resolve_alias(token), range(2)))
    assert urls[0] == urls[1]
    assert provider.create_calls == 1
    assert _counts(values) == {"reservations": 1, "runtimes": 1, "creates": 1}
    with connection_factory() as c:
        intent = c.execute(
            "SELECT status,configured_base_price_minor,actual_charged_price_minor "
            "FROM purchase_intents WHERE purchase_intent_id=%s",
            (values["intent_id"],),
        ).fetchone()
        target = c.execute(
            "SELECT exact_price_minor FROM fanvue_fingerprint_reservations "
            "WHERE purchase_intent_id=%s", (values["intent_id"],),
        ).fetchone()["exact_price_minor"]
    assert intent["status"] == "CLICKED"
    assert intent["configured_base_price_minor"] == 1499
    assert target != intent["configured_base_price_minor"]
    assert intent["actual_charged_price_minor"] is None
    assert gateway.resolve_alias(token) == urls[0]


def test_create_failure_retry_retains_fingerprint_and_intent(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    values = _prepare_unopened(fixture()); provider = FakeProvider(); provider.fail_create = True
    gateway, token = _issue(values, provider)
    with pytest.raises(UnlockUnavailableError):
        gateway.resolve_alias(token)
    with connection_factory() as c:
        before = c.execute("SELECT fingerprint_reservation_id,exact_price_minor FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()
        operation = c.execute("""SELECT operation.state,operation.last_error
            FROM fanvue_runtime_media_link_operations operation
            JOIN fanvue_runtime_media_links runtime USING(runtime_media_link_id)
            WHERE runtime.purchase_intent_id=%s AND operation.operation_type='CREATE'""",
            (values["intent_id"],)).fetchone()
    assert operation["state"] == "UNCERTAIN" and operation["last_error"] == "ConnectionError"
    provider.fail_create = False
    assert gateway.resolve_alias(token).startswith("https://example.invalid/")
    with connection_factory() as c:
        after = c.execute("SELECT fingerprint_reservation_id,exact_price_minor FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()
    assert before == after and _counts(values)["reservations"] == 1


def test_provider_success_local_interruption_reconciles_without_second_create(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    values = _prepare_unopened(fixture()); provider = FakeProvider()
    gateway, token = _issue(values, provider)
    original_activate = gateway.repository.activate
    gateway.repository.activate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("synthetic local interruption"))
    with pytest.raises(UnlockUnavailableError):
        gateway.resolve_alias(token)
    assert provider.create_calls == 1 and len(provider.resources) == 1
    gateway.repository.activate = original_activate
    with connection_factory() as c:
        c.execute("UPDATE fanvue_runtime_media_link_operations SET next_attempt_at=NOW() WHERE state='UNCERTAIN'")
    result = RuntimeMediaLinkRecoveryService(repository=gateway.repository, client_factory=lambda _: provider).run_once()
    assert result[0][1] == "SUCCEEDED" and provider.create_calls == 1
    assert gateway.resolve_alias(token) == provider.resources[0]["url"]


def test_crash_before_redirect_reuses_confirmed_runtime(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    values = _prepare_unopened(fixture()); provider = FakeProvider(); gateway, token = _issue(values, provider)
    first = gateway.resolve_alias(token)
    restarted, _ = _issue(values, provider)
    assert restarted.resolve_alias(token) == first and provider.create_calls == 1


def test_delete_failure_retries_without_releasing_price(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    values = _prepare_unopened(fixture()); provider = FakeProvider(); gateway, token = _issue(values, provider)
    gateway.resolve_alias(token)
    runtime = gateway.repository.get_live_link(values["intent_id"], now=datetime.now(timezone.utc))
    gateway.repository.request_delete(runtime.runtime_media_link_id)
    provider.fail_delete = True
    recovery = RuntimeMediaLinkRecoveryService(repository=gateway.repository, client_factory=lambda _: provider)
    assert recovery.run_once()[0][1] == "FAILED"
    with connection_factory() as c:
        assert c.execute("SELECT state FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()["state"] == "ACTIVE"
        c.execute("UPDATE fanvue_runtime_media_link_operations SET next_attempt_at=NOW() WHERE operation_type='DELETE'")
    provider.fail_delete = False
    assert recovery.run_once()[0][1] == "SUCCEEDED"
    with connection_factory() as c:
        assert c.execute("SELECT state FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()["state"] == "ACTIVE"


def test_orphan_reconciles_only_with_exact_provider_match(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    values = _prepare_unopened(fixture()); provider = FakeProvider(); gateway, token = _issue(values, provider)
    provider.fail_create = True
    with pytest.raises(UnlockUnavailableError): gateway.resolve_alias(token)
    with connection_factory() as c:
        reservation = c.execute("SELECT exact_price_minor FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()
        c.execute("UPDATE fanvue_runtime_media_link_operations SET next_attempt_at=NOW() WHERE state='UNCERTAIN'")
    provider.fail_create = False
    provider.resources.append({"uuid": str(uuid4()), "url": "https://example.invalid/orphan", "media": ("synthetic-media",), "price": reservation["exact_price_minor"]})
    recovery = RuntimeMediaLinkRecoveryService(repository=gateway.repository, client_factory=lambda _: provider)
    assert recovery.run_once()[0][1] == "SUCCEEDED"
    assert gateway.resolve_alias(token) == "https://example.invalid/orphan"


def test_ambiguous_orphan_stays_operator_recovery_only_and_cannot_map(monkeypatch):
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    values = _prepare_unopened(fixture()); provider = FakeProvider(); gateway, token = _issue(values, provider)
    provider.fail_create = True
    with pytest.raises(UnlockUnavailableError): gateway.resolve_alias(token)
    with connection_factory() as c:
        price = c.execute("SELECT exact_price_minor FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()["exact_price_minor"]
        c.execute("UPDATE fanvue_runtime_media_link_operations SET next_attempt_at=NOW() WHERE state='UNCERTAIN'")
    provider.fail_create = False
    provider.resources.extend([
        {"uuid": str(uuid4()), "url": "https://example.invalid/orphan-a", "media": ("synthetic-media",), "price": price},
        {"uuid": str(uuid4()), "url": "https://example.invalid/orphan-b", "media": ("synthetic-media",), "price": price},
    ])
    recovery = RuntimeMediaLinkRecoveryService(repository=gateway.repository, client_factory=lambda _: provider)
    assert recovery.run_once()[0][1] == "FAILED"
    with connection_factory() as c:
        runtime = c.execute("SELECT state,provider_media_link_uuid FROM fanvue_runtime_media_links WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()
        mappings = c.execute("SELECT count(*) n FROM telegram_identity_map WHERE telegram_user_id=%s", (values["telegram"],)).fetchone()["n"]
    assert runtime == {"state": "UNCERTAIN", "provider_media_link_uuid": None}
    assert mappings == 0 and _repository().match_purchase(
        fanvue_account_id=values["account"], currency="USD", gross_minor=price,
    ) == []


def test_uncertain_runtime_purchase_fails_closed():
    values = fixture(session=True, offering_type="PHOTOSET")
    with connection_factory() as c:
        c.execute("UPDATE fanvue_runtime_media_links SET state='UNCERTAIN' WHERE runtime_media_link_id=%s", (values["runtime_id"],))
    assert settle(values) is None
    result = state(values)
    assert result["mappings"] == 0 and result["sessions"] == 0
    assert result["intent"]["status"] == "CREATED" and result["reservation"] == "ACTIVE"


def _mapped_identity(values):
    mapping = TelegramIdentityRepository(connection_factory=connection_factory).get_verified_by_telegram_user_id(values["telegram"])
    assert mapping is not None
    return OwnershipIdentity(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        external_fanvue_user_uuid=values["buyer_uuid"], telegram_user_id=values["telegram"],
        legacy_fanvue_user_id=str(values["user"]),
    )


def _memory(identity, profile=None):
    ownership = OwnershipIntelligenceService(
        repository=OwnershipIntelligenceRepository(connection_factory=connection_factory)
    )
    return CustomerCommerceMemoryService(
        repository=CustomerCommerceMemoryRepository(connection_factory=connection_factory),
        ownership_service=ownership,
    ).build(identity=identity, customer_profile=profile)


def _provider_profile(values, *, gross=1497, transaction="tx-1"):
    profile_id = uuid4(); now = datetime.now(timezone.utc)
    with connection_factory() as c:
        c.execute("""INSERT INTO customer_commerce_profiles(
            customer_commerce_profile_id,creator_profile_id,fanvue_account_id,
            external_fanvue_user_uuid,first_seen_at,last_seen_at,first_purchase_at,
            last_purchase_at,lifetime_gross_minor,lifetime_net_minor,purchase_count,
            average_order_value_minor,largest_purchase_minor,profile_state)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,'FIRST_PURCHASE')""",
            (profile_id, values["creator"], values["account"], values["buyer_uuid"],
             now, now, now, now, gross, gross - 200, gross, gross))
        c.execute("""INSERT INTO customer_commerce_transactions(
            customer_commerce_transaction_id,customer_commerce_profile_id,fanvue_account_id,
            transaction_order_id,gross_minor,net_minor,payment_status,purchase_source,payment_timestamp)
            VALUES (%s,%s,%s,%s,%s,%s,'paid','media_link',%s)""",
            (uuid4(), profile_id, values["account"], transaction, gross, gross - 200, now))
        return c.execute("SELECT * FROM customer_commerce_profiles WHERE customer_commerce_profile_id=%s", (profile_id,)).fetchone()


def test_post_settlement_commerce_memory_graduates_without_losing_prospect_state():
    values = fixture(session=True, offering_type="PHOTOSET")
    profile = _provider_profile(values)
    prospect_service = UnmappedTelegramProspectService(
        repository=TelegramSalesProspectRepository(connection_factory=connection_factory)
    )
    before = prospect_service.context(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
    )
    assert before.profile.external_fanvue_user_uuid is None
    assert before.memory.purchase_events == () and before.memory.owned_asset_ids == ()
    settle(values)
    memory = _memory(_mapped_identity(values), SimpleNamespace(**profile))
    assert any(event.source_type == "PURCHASE_INTENT" for event in memory.purchase_events)
    assert values["asset"] in memory.owned_asset_ids
    assert memory.lifetime_gross_minor == 1497 and memory.purchase_count >= 1
    with connection_factory() as c:
        prospect = c.execute("SELECT relationship_state,preference_state,graduated_mapping_id FROM telegram_sales_prospects WHERE telegram_sales_prospect_id=%s", (values["prospect_id"],)).fetchone()
        session_count = c.execute("SELECT count(*) n FROM sales_sessions WHERE fanvue_user_id=%s", (values["user"],)).fetchone()["n"]
    assert prospect["relationship_state"] == {"stage": "warm"}
    assert prospect["preference_state"] == {"theme": "portrait"}
    assert prospect["graduated_mapping_id"] is not None and session_count == 1


def test_historical_vault_hydrates_only_after_real_fingerprint_mapping():
    values = fixture(); historical_asset = values["asset"]
    with connection_factory() as c:
        c.execute("""INSERT INTO content_usage_log(content_item_id,fanvue_account_id,
            fanvue_user_id,usage_type,purchased_at,content_tag,fanvue_media_uuid,purchase_amount)
            VALUES (%s,%s,%s,'content_unlocked',NOW()-INTERVAL '30 days','vault','historical-media',9.99)""",
            (historical_asset, values["account"], str(values["user"])))
    unmapped = OwnershipIdentity(creator_profile_id=values["creator"], fanvue_account_id=values["account"], telegram_user_id=values["telegram"])
    before = _memory(unmapped)
    assert before.purchase_events == () and before.owned_asset_ids == ()
    settle(values)
    after = _memory(_mapped_identity(values))
    assert any(event.source_type == "VAULT_UNLOCK" for event in after.purchase_events)
    assert historical_asset in after.owned_asset_ids
    assert values["offering_id"] in after.owned_offering_ids


def test_unmapped_vault_purchase_remains_fanvue_only_after_read_paths():
    values = fixture()
    with connection_factory() as c:
        c.execute("""INSERT INTO content_usage_log(content_item_id,fanvue_account_id,
            fanvue_user_id,usage_type,purchased_at,content_tag,fanvue_media_uuid,purchase_amount)
            VALUES (%s,%s,%s,'content_unlocked',NOW(),'vault','unmapped-media',9.99)""",
            (values["asset"], values["account"], str(values["user"])))
    fanvue_only = OwnershipIdentity(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        external_fanvue_user_uuid=values["buyer_uuid"], legacy_fanvue_user_id=str(values["user"]),
    )
    memory = _memory(fanvue_only)
    assert values["asset"] in memory.owned_asset_ids
    with connection_factory() as c:
        assert c.execute("SELECT count(*) n FROM telegram_identity_map WHERE fanvue_account_id=%s AND external_fanvue_user_uuid=%s", (values["account"], values["buyer_uuid"])).fetchone()["n"] == 0
        assert c.execute("SELECT count(*) n FROM purchase_intents WHERE external_fanvue_user_uuid=%s", (values["buyer_uuid"],)).fetchone()["n"] == 0
        prospect = c.execute("SELECT graduated_mapping_id FROM telegram_sales_prospects WHERE telegram_sales_prospect_id=%s", (values["prospect_id"],)).fetchone()
    assert prospect["graduated_mapping_id"] is None
