"""Canonical schema + disposable PostgreSQL; fake provider, injected clock."""

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest
from test_evergreen_checkout import database
from app.repositories.private_chat_fingerprint_repository import token_digest
from app.services.canonical_evergreen_unlock import resolve_alias
from app.services.private_chat_unlock_gateway_service import (
    PrivateChatUnlockGatewayService,
)
from app.models.evergreen_checkout import CheckoutUnavailable

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "20260921_151_evergreen_offer_authority.sql"


@pytest.fixture(scope="module")
def canonical_db(database):
    schema = (ROOT.parent / "fixture-schema.sql").read_text()
    schema = "\n".join(
        line for line in schema.splitlines() if not line.startswith("\\")
    )
    with database() as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
        c.execute(schema)
        c.execute((ROOT / "migrations/forward" / MIGRATION).read_text())
        c.execute((ROOT / "migrations/forward/20260921_152_manual_offer_delivery_anchor.sql").read_text())
    return database


class Provider:
    def __init__(self):
        self.resources = []
        self.calls = 0
        self.timeout = False
        self.visible = True
        self.after = None

    def find_equivalent_media_link(self, media, price):
        return self.resources.copy() if self.visible else []

    def create_media_link(self, media, price):
        self.calls += 1
        link = {
            "uuid": str(uuid4()),
            "url": "https://www.fanvue.com/media-link/test",
            "price": price,
            "mediaUuids": list(media),
        }
        self.resources.append(link)
        if self.after:
            self.after()
        if self.timeout:
            raise TimeoutError("synthetic accepted; response lost")
        return link


@pytest.fixture
def offer(canonical_db):
    db = canonical_db
    now = datetime.now(timezone.utc)
    root = uuid4()
    grant = uuid4()
    product = uuid4()
    publication = uuid4()
    reservation = uuid4()
    with db() as c:
        c.execute(
            "TRUNCATE creator_profiles,fanvue_accounts,content_items,evergreen_checkout_lineage,evergreen_checkout_resolution_events CASCADE"
        )
        c.execute(
            "INSERT INTO fanvue_accounts(id,account_name) VALUES(901,'synthetic')"
        )
        c.execute(
            "INSERT INTO creator_profiles(id,fanvue_account_id,persona_name,display_name,age,gender,location) VALUES(901,'901','Test','Test',25,'test','test')"
        )
        c.execute(
            "INSERT INTO content_items(id,file_path,classification,creator_profile_id,fanvue_account_id,is_test) VALUES(901,'synthetic.png','neutral',901,901,TRUE)"
        )
        c.execute(
            "INSERT INTO commercial_offerings(offering_id,creator_profile_id,offering_type,title,hero_asset_id,primary_sales_channel,status,price_minor) VALUES(%s,901,'SINGLE_IMAGE','Neutral test',901,'AI_CHAT','READY',999)",
            (product,),
        )
        c.execute(
            "INSERT INTO commercial_offering_assets(offering_id,asset_id,position) VALUES(%s,901,1)",
            (product,),
        )
        c.execute(
            "INSERT INTO commercial_publications(publication_id,commercial_offering_id,provider,status,external_product_id,publication_metadata) VALUES(%s,%s,'FANVUE','LIVE','product',%s::jsonb)",
            (
                publication,
                product,
                json.dumps(
                    {
                        "media_link": {
                            "media_uuids": ["media-test"],
                            "url": "https://www.fanvue.com/media-link/test",
                        }
                    }
                ),
            ),
        )
        c.execute(
            "INSERT INTO runtime_control_records(creator_profile_id,mode,status) VALUES('901','LIVE','LIVE') ON CONFLICT(creator_profile_id) DO UPDATE SET mode='LIVE'"
        )
        c.execute(
            """INSERT INTO purchase_intents(purchase_intent_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,
            commercial_offering_id,commercial_publication_id,provider,provider_resource_id,delivery_url,correlation_id,
            expected_price_minor,expected_currency,configured_base_price_minor,identity_bootstrap_mode,expires_at,status,
            created_metadata,presented_at) VALUES(%s,901,901,99001,99001,%s,%s,'FANVUE','product','https://www.fanvue.com/media-link/test',%s,
            999,'USD',999,'PRIVATE_CHAT_FINGERPRINT',%s,'PRESENTED','{"presentation_origin":"HUMAN_OPERATOR_PRESENTED"}',%s)""",
            (root, product, publication, uuid4(), now + timedelta(hours=24), now),
        )
        c.execute(
            """INSERT INTO telegram_unlock_grants(unlock_grant_id,token_hash,purchase_intent_id,telegram_user_id,telegram_chat_id,
            commercial_offering_id,commercial_publication_id,fanvue_account_id,currency,public_alias_hash,public_alias_generation)
            VALUES(%s,%s,%s,99001,99001,%s,%s,901,'USD',%s,0)""",
            (
                grant,
                token_digest("legacy"),
                root,
                product,
                publication,
                token_digest("A" * 22),
            ),
        )
        c.execute(
            """INSERT INTO fanvue_fingerprint_reservations(fingerprint_reservation_id,fanvue_account_id,currency,exact_price_minor,
            configured_base_price_minor,purchase_intent_id,telegram_user_id) VALUES(%s,901,'USD',1001,999,%s,99001)""",
            (reservation, root),
        )
    clock = SimpleNamespace(now=now)
    provider = Provider()
    gateway = PrivateChatUnlockGatewayService(
        connection_factory=db,
        client_factory=lambda _: provider,
        clock=lambda: clock.now,
    )
    return SimpleNamespace(
        db=db,
        clock=clock,
        provider=provider,
        gateway=gateway,
        root=root,
        grant=grant,
        product=product,
        publication=publication,
        reservation=reservation,
        alias="A" * 22,
    )


@pytest.mark.parametrize("hours", [24, 72])
@pytest.mark.parametrize("price", [997, 1001])
def test_same_alias_price_multiple_generations(offer, hours, price):
    o = offer
    with o.db() as c:
        c.execute(
            "UPDATE purchase_intents SET expires_at=%s,created_metadata=%s::jsonb WHERE purchase_intent_id=%s",
            (
                o.clock.now + timedelta(hours=hours),
                json.dumps(
                    {"presentation_origin": "HUMAN_OPERATOR_PRESENTED"}
                    if hours == 24
                    else {}
                ),
                o.root,
            ),
        )
        c.execute(
            "UPDATE fanvue_fingerprint_reservations SET exact_price_minor=%s", (price,)
        )
    assert resolve_alias(o.gateway, o.alias).startswith("https://www.fanvue.com/")
    for generation in (1, 2):
        o.clock.now += timedelta(hours=hours + 1)
        assert resolve_alias(o.gateway, o.alias).startswith("https://www.fanvue.com/")
        with o.db() as c:
            rows = c.execute(
                "SELECT * FROM evergreen_checkout_lineage ORDER BY generation"
            ).fetchall()
            assert len(rows) == generation
            assert all(
                r["predecessor_price_minor"] == r["successor_price_minor"] == price
                for r in rows
            )
            assert (
                c.execute(
                    "SELECT count(*) n FROM fanvue_fingerprint_reservations"
                ).fetchone()["n"]
                == 1
            )
    assert o.provider.calls == 1


def test_concurrent_clicks(offer):
    o = offer
    o.clock.now += timedelta(hours=25)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: resolve_alias(o.gateway, o.alias), range(2)))
    assert results[0] == results[1] and o.provider.calls == 1
    with o.db() as c:
        assert (
            c.execute("SELECT count(*) n FROM evergreen_checkout_lineage").fetchone()[
                "n"
            ]
            == 1
        )


def test_ambiguous_creation_never_recreated(offer):
    o = offer
    o.provider.timeout = True
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    o.provider.visible = False
    for _ in range(2):
        with pytest.raises(CheckoutUnavailable):
            resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1
    o.provider.visible = True
    assert resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE telegram_unlock_grants SET state='REVOKED'",
        "UPDATE commercial_publications SET status='ARCHIVED'",
        "UPDATE commercial_offerings SET price_minor=1299",
        "UPDATE runtime_control_records SET mode='OFFLINE'",
        "UPDATE purchase_intents SET telegram_chat_id=99002",
    ],
)
def test_authority_invalidations(offer, mutation):
    o = offer
    resolve_alias(o.gateway, o.alias)
    with o.db() as c:
        c.execute(mutation)
    o.clock.now += timedelta(hours=25)
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1


@pytest.mark.parametrize(
    "timing", ["before_expiry", "after_successor", "late_predecessor"]
)
def test_fingerprint_settlement_and_immutable_predecessor(offer, timing):
    from app.services.private_chat_purchase_settlement_service import (
        PrivateChatPurchaseSettlementService,
    )

    o = offer
    resolve_alias(o.gateway, o.alias)
    buyer = uuid4()
    with o.db() as c:
        c.execute(
            "INSERT INTO telegram_identity_observations(telegram_user_id,telegram_chat_id,private_chat_id) VALUES(99001,99001,99001) ON CONFLICT DO NOTHING"
        )
        c.execute(
            "INSERT INTO fanvue_users(id,fanvue_user_uuid,fanvue_account_id) VALUES(901,%s,901)",
            (buyer,),
        )
    if timing == "after_successor":
        o.clock.now += timedelta(hours=25)
        resolve_alias(o.gateway, o.alias)
    elif timing == "late_predecessor":
        with o.db() as c:
            c.execute(
                "UPDATE purchase_intents SET status='EXPIRED' WHERE purchase_intent_id=%s",
                (o.root,),
            )
    with o.db() as c:
        before = c.execute(
            "SELECT md5(to_jsonb(i)::text) digest FROM purchase_intents i WHERE purchase_intent_id=%s",
            (o.root,),
        ).fetchone()["digest"]
    settlement = PrivateChatPurchaseSettlementService(o.db)
    # Session continuation is covered by its existing suite; this fixture has no Session.
    settlement._reconcile_sales_session = lambda *a, **k: None
    settlement._graduate_session = lambda *a, **k: None
    args = dict(
        fanvue_account_id=901,
        currency="USD",
        gross_minor=1001,
        source="medialink",
        buyer_uuid=buyer,
        local_fanvue_user_id=901,
        transaction_id="synthetic-payment",
        payment_id="payment",
        event_id="event",
        purchased_at=o.clock.now,
    )
    first = settlement.settle(**args)
    second = settlement.settle(**args)
    assert (
        first["intent"]["purchase_intent_id"] == second["intent"]["purchase_intent_id"]
    )
    with o.db() as c:
        assert (
            c.execute(
                "SELECT count(*) n FROM purchase_intents WHERE status='PURCHASED'"
            ).fetchone()["n"]
            == 1
        )
        assert (
            c.execute(
                "SELECT count(*) n FROM telegram_identity_map WHERE telegram_user_id=99001"
            ).fetchone()["n"]
            == 1
        )
        if timing != "before_expiry":
            assert (
                c.execute(
                    "SELECT md5(to_jsonb(i)::text) digest FROM purchase_intents i WHERE purchase_intent_id=%s",
                    (o.root,),
                ).fetchone()["digest"]
                == before
            )
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1


def test_schema_governance_constraints_and_rollback(canonical_db):
    import hashlib
    from app.services.schema_manager_service import SchemaManagerService

    with canonical_db() as c:
        c.execute(
            "TRUNCATE creator_profiles,fanvue_accounts,content_items,evergreen_checkout_lineage,evergreen_checkout_resolution_events CASCADE"
        )
        for p in (ROOT / "migrations/forward").glob("*.sql"):
            c.execute(
                "INSERT INTO schema_migrations(migration_name,checksum) VALUES(%s,%s) ON CONFLICT(migration_name) DO UPDATE SET checksum=EXCLUDED.checksum",
                (
                    p.name,
                    hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest(),
                ),
            )
    manager = SchemaManagerService(connection_factory=canonical_db)
    report = manager.certify()
    assert report.status == "PASS", report.drift
    with canonical_db() as c:
        c.execute((ROOT / "migrations/rollback" / MIGRATION).read_text())
        c.execute("DELETE FROM schema_migrations WHERE migration_name=%s", (MIGRATION,))
    report = manager.reconcile_one(MIGRATION)
    assert report.status == "PASS", report.drift
    with canonical_db() as c:
        c.execute(
            "ALTER TABLE evergreen_checkout_lineage DROP CONSTRAINT evergreen_price_immutable"
        )
    assert manager.certify().status != "PASS"
    with canonical_db() as c:
        c.execute(
            "ALTER TABLE evergreen_checkout_lineage ADD CONSTRAINT evergreen_price_immutable CHECK(predecessor_price_minor=successor_price_minor)"
        )


def test_unknown_expired_generation_reconciles_without_duplicate(offer):
    o = offer
    o.clock.now += timedelta(hours=25)
    o.provider.timeout = True
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    o.clock.now += timedelta(hours=25)
    o.provider.visible = False
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1
    o.provider.visible = True
    assert resolve_alias(o.gateway, o.alias)
    with o.db() as c:
        assert (
            c.execute("SELECT count(*) n FROM evergreen_checkout_lineage").fetchone()[
                "n"
            ]
            == 2
        )
    assert o.provider.calls == 1


@pytest.mark.parametrize(
    "point", ["before_invocation", "after_acceptance", "persistence"]
)
def test_provider_crash_or_persistence_loss_is_quarantined(offer, point, monkeypatch):
    from contextlib import contextmanager

    o = offer

    class Crash(BaseException):
        pass

    if point == "before_invocation":

        def crash(*_):
            raise Crash()

        o.provider.create_media_link = crash
    elif point == "after_acceptance":
        o.provider.after = lambda: (_ for _ in ()).throw(Crash())
    else:
        original = o.gateway.connection_factory

        class Connection:
            def __init__(self, c):
                self.c = c

            def execute(self, sql, *a, **k):
                if (
                    "INSERT INTO evergreen_provider_operations" in sql
                    and "provider_evidence" in sql
                ):
                    raise RuntimeError("synthetic persistence loss")
                return self.c.execute(sql, *a, **k)

            def __getattr__(self, name):
                return getattr(self.c, name)

        @contextmanager
        def fail():
            with original() as c:
                yield Connection(c)

        o.gateway.connection_factory = fail
    with pytest.raises((Crash, CheckoutUnavailable)):
        resolve_alias(o.gateway, o.alias)
    o.gateway.connection_factory = o.db
    o.provider.visible = False
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == (0 if point == "before_invocation" else 1)
    if point != "before_invocation":
        o.provider.visible = True
        assert resolve_alias(o.gateway, o.alias)
        assert o.provider.calls == 1


def test_revocation_during_provider_work_prevents_redirect(offer):
    o = offer

    def revoke():
        with o.db() as c:
            c.execute("UPDATE telegram_unlock_grants SET state='REVOKED'")

    o.provider.after = revoke
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    with o.db() as c:
        assert (
            c.execute("SELECT use_count FROM telegram_unlock_grants").fetchone()[
                "use_count"
            ]
            == 0
        )
    assert o.provider.calls == 1


def test_immutable_family_predecessor_and_fingerprint_constraints(offer):
    import psycopg

    o = offer
    o.clock.now += timedelta(hours=25)
    resolve_alias(o.gateway, o.alias)
    for sql in (
        "UPDATE evergreen_offer_authorities SET final_price_minor=1003",
        "DELETE FROM evergreen_provider_operations",
        "UPDATE purchase_intents SET expected_price_minor=1003 WHERE status='EXPIRED'",
        "UPDATE fanvue_fingerprint_reservations SET exact_price_minor=1003",
        "UPDATE evergreen_checkout_lineage SET successor_price_minor=1003",
    ):
        with pytest.raises(psycopg.Error):
            with o.db() as c:
                c.execute(sql)


def test_conflicting_offer_not_adopted(offer):
    o = offer
    resolve_alias(o.gateway, o.alias)
    with o.db() as c:
        c.execute(
            "UPDATE purchase_intents SET status='EXPIRED' WHERE purchase_intent_id=%s",
            (o.root,),
        )
        row = c.execute(
            "SELECT * FROM purchase_intents WHERE purchase_intent_id=%s", (o.root,)
        ).fetchone()
        from app.repositories.purchase_intent_repository import PurchaseIntentRepository

        with c.cursor() as cur:
            PurchaseIntentRepository()._insert(
                cur,
                dict(
                    row,
                    purchase_intent_id=uuid4(),
                    correlation_id=uuid4(),
                    expires_at=o.clock.now + timedelta(days=4),
                ),
            )
    o.clock.now += timedelta(hours=25)
    with pytest.raises(CheckoutUnavailable, match="unavailable"):
        resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1


@pytest.mark.parametrize("hours", [24, 72])
@pytest.mark.parametrize("payment_resource", ["product", "product-renewed"])
def test_mapped_customer_successor_and_atomic_settlement(
    offer, hours, payment_resource
):
    from app.repositories.purchase_intent_repository import PurchaseIntentRepository

    o = offer
    buyer = uuid4()
    with o.db() as c:
        c.execute("DELETE FROM fanvue_fingerprint_reservations")
        c.execute(
            "INSERT INTO fanvue_users(id,fanvue_user_uuid,fanvue_account_id) VALUES(901,%s,901)",
            (buyer,),
        )
        c.execute(
            "INSERT INTO telegram_identity_map(id,telegram_user_id,telegram_chat_id,fanvue_account_id,local_fanvue_user_id,external_fanvue_user_uuid,verification_status) VALUES(901,99001,99001,901,901,%s,'VERIFIED')",
            (buyer,),
        )
        c.execute(
            "UPDATE purchase_intents SET telegram_identity_mapping_id=901,external_fanvue_user_uuid=%s,identity_bootstrap_mode='NONE',expires_at=%s,created_metadata=%s::jsonb",
            (
                buyer,
                o.clock.now + timedelta(hours=hours),
                json.dumps(
                    {"presentation_origin": "HUMAN_OPERATOR_PRESENTED"}
                    if hours == 24
                    else {}
                ),
            ),
        )
    o.provider.resources = [
        {
            "uuid": "product",
            "url": "https://www.fanvue.com/media-link/test",
            "price": 999,
            "mediaUuids": ["media-test"],
        }
    ]
    assert resolve_alias(o.gateway, o.alias)
    o.clock.now += timedelta(hours=hours + 1)
    # The canonical publisher has reconciled a replacement resource for the
    # same publication/media/price. Preserve both acknowledgements for late pay.
    renewed = "https://www.fanvue.com/media-link/renewed"
    with o.db() as c:
        c.execute(
            "UPDATE commercial_publications SET external_product_id='product-renewed',publication_metadata=%s::jsonb",
            (
                json.dumps(
                    {"media_link": {"media_uuids": ["media-test"], "url": renewed}}
                ),
            ),
        )
    o.provider.resources = [
        {
            "uuid": "product-renewed",
            "url": renewed,
            "price": 999,
            "mediaUuids": ["media-test"],
        }
    ]
    assert resolve_alias(o.gateway, o.alias) == renewed
    repo = PurchaseIntentRepository(o.db)
    args = dict(
        at=o.clock.now,
        transaction_id="mapped-payment",
        payment_id="payment",
        event_id="event",
    )
    from app.services.commerce_signal_service import CommerceSignalService

    service = CommerceSignalService(
        repository=SimpleNamespace(),
        identity_repository=SimpleNamespace(),
        customer_service=SimpleNamespace(),
        purchase_intent_service=SimpleNamespace(),
        purchase_intent_repository=repo,
        photoshoot_lifecycle_service=SimpleNamespace(
            synchronize_attributed_purchase=lambda **_: None
        ),
        telegram_delivery_service=SimpleNamespace(recover_accepted=lambda **_: []),
        fingerprint_attribution_service=SimpleNamespace(),
    )
    values = dict(
        creator_profile_id=901,
        fanvue_account_id=901,
        buyer_uuid=buyer,
        amount_minor=999,
        payment_timestamp=o.clock.now,
        transaction_id="mapped-payment",
        payment_id="payment",
        event_id="event",
        customer_commerce_profile_id=uuid4(),
        media_link_purchase=True,
        provider_resource_id=payment_resource,
        transaction_currency="USD",
    )
    a = service._attribute(**values)
    b = service._attribute(**values)
    assert a["state"] == b["state"] == "ATTRIBUTED"
    assert (
        a["purchaseIntentId"] == b["purchaseIntentId"]
        and a["purchaseIntentId"] != o.root
    )
    assert o.provider.calls == 0
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)


def test_database_connection_loss_releases_family_lock_without_duplicate(offer):
    o = offer
    o.clock.now += timedelta(hours=25)

    def disconnect():
        with o.db() as c:
            # This cluster exists only for this test module. Release the session
            # lock exactly as a lost DB connection would, during provider work.
            rows = c.execute(
                "SELECT DISTINCT pid FROM pg_locks WHERE locktype='advisory' AND pid<>pg_backend_pid()"
            ).fetchall()
            assert rows
            for row in rows:
                c.execute("SELECT pg_terminate_backend(%s)", (row["pid"],))

    o.provider.after = disconnect
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    o.provider.after = None
    assert resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1
    with o.db() as c:
        assert (
            c.execute("SELECT count(*) n FROM evergreen_checkout_lineage").fetchone()[
                "n"
            ]
            == 1
        )


def test_database_restart_after_provider_acceptance(offer):
    o = offer
    o.clock.now += timedelta(hours=25)
    o.provider.after = o.db.restart
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    o.provider.after = None
    assert resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1


def test_purchase_during_refresh_prevents_redirect(offer, monkeypatch):
    from app.services.canonical_evergreen_unlock import CanonicalUnlockRuntime
    from app.services.private_chat_purchase_settlement_service import (
        PrivateChatPurchaseSettlementService,
    )

    o = offer
    buyer = uuid4()
    with o.db() as c:
        c.execute(
            "INSERT INTO telegram_identity_observations(telegram_user_id,telegram_chat_id,private_chat_id) VALUES(99001,99001,99001) ON CONFLICT DO NOTHING"
        )
        c.execute(
            "INSERT INTO fanvue_users(id,fanvue_user_uuid,fanvue_account_id) VALUES(901,%s,901)",
            (buyer,),
        )
    original = CanonicalUnlockRuntime.reconcile

    def settle_during_refresh(self, transaction, **kwargs):
        destination = original(self, transaction, **kwargs)
        settlement = PrivateChatPurchaseSettlementService(o.db)
        result = settlement.settle(
            fanvue_account_id=901,
            currency="USD",
            gross_minor=1001,
            source="medialink",
            buyer_uuid=buyer,
            local_fanvue_user_id=901,
            transaction_id="race-payment",
            payment_id="payment",
            event_id="event",
            purchased_at=o.clock.now,
        )
        assert result["intent"]["status"] == "PURCHASED"
        return destination

    monkeypatch.setattr(CanonicalUnlockRuntime, "reconcile", settle_during_refresh)
    o.clock.now += timedelta(hours=25)
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    with o.db() as c:
        assert (
            c.execute(
                "SELECT count(*) n FROM purchase_intents WHERE status='PURCHASED'"
            ).fetchone()["n"]
            == 1
        )
        assert (
            c.execute("SELECT use_count FROM telegram_unlock_grants").fetchone()[
                "use_count"
            ]
            == 0
        )
    assert o.provider.calls == 1


def test_real_gateway_issuance_freezes_price_and_reuses_alias(offer, monkeypatch):
    from app.repositories.purchase_intent_repository import PurchaseIntentRepository

    o = offer
    monkeypatch.setenv("EVERGREEN_UNLOCK_ENABLED", "true")
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    monkeypatch.setenv("CREATOR_OS_PUBLIC_API_URL", "https://unlock.example.test")
    o.gateway.token_secret = "synthetic-test-secret" * 3
    with o.db() as c:
        c.execute("DELETE FROM telegram_unlock_grants")
    intent = PurchaseIntentRepository(o.db).get(o.root)
    intent, price = o.gateway.reserve_offer_price(intent)
    assert price == 1001
    grant, url = o.gateway.issue(intent)
    assert o.gateway.issue(intent)[1] == url
    assert o.provider.calls == 0
    o.clock.now += timedelta(hours=25)
    assert o.gateway.resolve_alias(url.rsplit("/", 1)[1])
    with o.db() as c:
        f = c.execute("SELECT * FROM evergreen_offer_authorities").fetchone()
        assert (
            f["final_price_minor"] == 1001
            and f["unlock_grant_id"] == grant.unlock_grant_id
        )
        assert (
            c.execute("SELECT count(*) n FROM telegram_unlock_grants").fetchone()["n"]
            == 1
        )


def test_currency_change_fails_closed(offer):
    o = offer
    resolve_alias(o.gateway, o.alias)
    with o.db() as c:
        c.execute(
            "UPDATE purchase_intents SET expected_currency='EUR' WHERE purchase_intent_id=%s",
            (o.root,),
        )
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1


def test_real_http_preview_and_expired_checkout_use_canonical_gateway(
    offer, monkeypatch
):
    import re
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import private_chat_unlock as api

    o = offer
    o.clock.now += timedelta(hours=25)
    monkeypatch.setenv("EVERGREEN_UNLOCK_ENABLED", "true")
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    monkeypatch.setenv("CREATOR_OS_UNLOCK_TOKEN_SECRET", "synthetic-secret" * 4)
    monkeypatch.setenv("CREATOR_OS_PUBLIC_API_URL", "https://unlock.example.test")
    monkeypatch.setattr(api, "PrivateChatUnlockGatewayService", lambda: o.gateway)
    app = FastAPI()
    app.include_router(api.public_alias_router)
    with TestClient(app, base_url="https://unlock.example.test") as browser:
        page = browser.get("/u/" + o.alias, headers={"User-Agent": "TelegramBot"})
        assert page.status_code == 204
        with o.db() as c:
            assert (
                c.execute("SELECT use_count FROM telegram_unlock_grants").fetchone()[
                    "use_count"
                ]
                == 0
            )
            assert (
                c.execute(
                    "SELECT count(*) n FROM evergreen_checkout_lineage"
                ).fetchone()["n"]
                == 0
            )
            assert (
                c.execute(
                    "SELECT count(*) n FROM evergreen_provider_operations"
                ).fetchone()["n"]
                == 0
            )
        assert o.provider.calls == 0
        result = browser.get(
            "/u/" + o.alias,
            headers={"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document", "Sec-Fetch-User": "?1"},
            follow_redirects=False,
        )
        assert result.status_code == 302
        assert result.headers["location"].startswith("https://www.fanvue.com/")
        assert o.provider.calls == 1
        with o.db() as c:
            assert (
                c.execute("SELECT use_count FROM telegram_unlock_grants").fetchone()[
                    "use_count"
                ]
                == 1
            )
            assert (
                c.execute(
                    "SELECT count(*) n FROM evergreen_checkout_lineage"
                ).fetchone()["n"]
                == 1
            )
            assert c.execute(
                "SELECT state,attempt_count FROM evergreen_provider_operations"
            ).fetchone() == {"state": "READY", "attempt_count": 1}


@pytest.mark.parametrize(
    "field,value", [("price", 1003), ("mediaUuids", ["wrong-media"]), ("price", None)]
)
def test_provider_acknowledgement_cannot_change_price_or_product(offer, field, value):
    o = offer

    def corrupt():
        o.provider.resources[0][field] = value

    o.provider.after = corrupt
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1
    with o.db() as c:
        assert (
            c.execute("SELECT state FROM evergreen_provider_operations").fetchone()[
                "state"
            ]
            == "UNKNOWN"
        )
        assert (
            c.execute("SELECT count(*) n FROM fanvue_runtime_media_links").fetchone()[
                "n"
            ]
            == 0
        )
    o.provider.visible = False
    with pytest.raises(CheckoutUnavailable):
        resolve_alias(o.gateway, o.alias)
    assert o.provider.calls == 1


@pytest.mark.parametrize("hours", [24,72])
def test_concurrent_one_click_http_gets_preserve_family_and_provider(offer, monkeypatch, hours):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import private_chat_unlock as api
    o=offer
    with o.db() as c:
        c.execute("UPDATE purchase_intents SET expires_at=%s WHERE purchase_intent_id=%s", (o.clock.now+timedelta(hours=hours),o.root))
    o.clock.now += timedelta(hours=hours+1)
    monkeypatch.setenv("EVERGREEN_UNLOCK_ENABLED","true")
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED","true")
    monkeypatch.setattr(api,"PrivateChatUnlockGatewayService",lambda:o.gateway)
    app=FastAPI();app.include_router(api.public_alias_router)
    with TestClient(app) as browser:
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies=list(pool.map(lambda _:browser.get("/u/"+o.alias,headers={"Sec-Fetch-Mode":"navigate","Sec-Fetch-Dest":"document"},follow_redirects=False),range(4)))
    assert all(r.status_code==302 for r in replies)
    assert len({r.headers["location"] for r in replies})==1
    assert o.provider.calls==1
    with o.db() as c:
        assert c.execute("SELECT count(*) n FROM evergreen_checkout_lineage").fetchone()["n"]==1
        assert c.execute("SELECT count(*) n FROM evergreen_provider_operations").fetchone()["n"]==1
        assert c.execute("SELECT count(*) n FROM fanvue_fingerprint_reservations").fetchone()["n"]==1
