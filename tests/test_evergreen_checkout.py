"""Real PostgreSQL certification with synthetic ordinary-commerce authorities.

Starts a disposable local cluster. Never reads a production connection URL or
calls any external provider. Requires PostgreSQL binaries in PG_TEST_BIN/PATH.
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.models.evergreen_checkout import (
    CheckoutBinding, CheckoutEligibility, CheckoutGrant, CheckoutPrice,
    CheckoutTransaction, CheckoutUnavailable,
)
from app.repositories.evergreen_checkout_repository import EvergreenCheckoutRepository
from app.services.evergreen_checkout_service import EvergreenCheckoutService
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import verify_isolated_test_connection

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "20260920_146_evergreen_checkout_lineage.sql"
NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)
BINDING = CheckoutBinding("test-shop", "test-customer", "test-subject", "test-web")


@pytest.fixture(scope="module")
def database():
    default = Path(r"C:\Program Files\PostgreSQL\17\bin")
    binaries = Path(os.environ.get("PG_TEST_BIN", str(default)))
    initdb = shutil.which("initdb") or str(binaries / ("initdb.exe" if os.name == "nt" else "initdb"))
    pgctl = shutil.which("pg_ctl") or str(binaries / ("pg_ctl.exe" if os.name == "nt" else "pg_ctl"))
    if not Path(initdb).is_file() or not Path(pgctl).is_file():
        pytest.skip("Local PostgreSQL binaries required; set PG_TEST_BIN")
    with tempfile.TemporaryDirectory(prefix="evergreen_checkout_test_") as directory:
        data = Path(directory) / "pgdata"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        def run(*args):
            # PostgreSQL children inherit handles on Windows. DEVNULL avoids
            # both pipe hangs and log-file handles held beyond server shutdown.
            return subprocess.run(args, check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=45,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        run(initdb, "-D", str(data), "-A", "trust", "-U", "checkout_test", "--encoding=UTF8", "--no-locale")
        run(pgctl, "-D", str(data), "-l", str(Path(directory) / "postgres.log"),
            "-o", f"-h 127.0.0.1 -p {port}", "-w", "start")
        try:
            admin = f"host=127.0.0.1 port={port} user=checkout_test dbname=postgres"
            with connect(admin, autocommit=True) as connection:
                connection.execute("CREATE DATABASE evergreen_checkout_test")
            url = f"host=127.0.0.1 port={port} user=checkout_test dbname=evergreen_checkout_test"
            @contextmanager
            def factory():
                with connect(url, row_factory=dict_row) as connection:
                    verify_isolated_test_connection(connection, url, None)
                    connection.commit()
                    yield connection
            factory.url = url
            def restart():
                run(pgctl, "-D", str(data), "-m", "fast", "-w", "stop")
                run(pgctl, "-D", str(data), "-l", str(Path(directory) / "postgres.log"),
                    "-o", f"-h 127.0.0.1 -p {port}", "-w", "start")
            factory.restart = restart
            with factory() as connection:
                connection.execute((ROOT / "migrations/forward" / MIGRATION).read_text())
                connection.execute("""CREATE TABLE public.checkout_test_transactions (
                    transaction_id UUID PRIMARY KEY, status TEXT NOT NULL,
                    expires_at TIMESTAMPTZ NOT NULL, price_minor BIGINT NOT NULL,
                    currency TEXT NOT NULL, offer_id TEXT NOT NULL,
                    revoked BOOLEAN NOT NULL DEFAULT FALSE)""")
            yield factory
        finally:
            run(pgctl, "-D", str(data), "-m", "fast", "-w", "stop")


class Authority:
    """Synthetic canonical store, sharing the service's actual SQL transaction."""
    def __init__(self, original):
        self.grant = CheckoutGrant(uuid4(), original, BINDING)
        self.alias = "synthetic-checkout-alias"
        self.eligibility = CheckoutEligibility(**{
            **{field: True for field in asdict(CheckoutEligibility()) if field != "configured_price"},
            "configured_price": CheckoutPrice(999, "USD"),
        })
        self.transaction_binding = BINDING
        self.crash_create = False

    def authenticate(self, alias, binding, *, connection):
        if alias != self.alias:
            raise CheckoutUnavailable("ALIAS_INVALID")
        return self.grant

    def lock_scope(self, grant, *, connection):
        connection.execute("SELECT pg_advisory_xact_lock(412374::bigint)")

    def load(self, transaction_id, *, connection):
        row = connection.execute("SELECT * FROM checkout_test_transactions WHERE transaction_id=%s FOR UPDATE",
                                 (transaction_id,)).fetchone()
        if row is None:
            return None
        return CheckoutTransaction(row["transaction_id"], self.transaction_binding, row["offer_id"],
            row["status"], row["expires_at"], CheckoutPrice(row["price_minor"], row["currency"]), row["revoked"])

    def validate(self, grant, transaction, *, connection):
        return self.eligibility

    def expire(self, transaction, *, now, connection):
        connection.execute("UPDATE checkout_test_transactions SET status='EXPIRED' WHERE transaction_id=%s",
                           (transaction.transaction_id,))
        return self.load(transaction.transaction_id, connection=connection)

    def create_successor(self, predecessor, *, transaction_id, price, expires_at, idempotency_key, connection):
        assert transaction_id == idempotency_key
        connection.execute("""INSERT INTO checkout_test_transactions
            (transaction_id,status,expires_at,price_minor,currency,offer_id)
            VALUES (%s,'CREATED',%s,%s,%s,%s)""",
            (transaction_id, expires_at, price.minor, price.currency, predecessor.offer_id))
        if self.crash_create:
            raise RuntimeError("synthetic failure after INSERT, before lineage commit")
        return self.load(transaction_id, connection=connection)

    def validate_destination(self, destination, transaction):
        return destination == f"https://checkout.example.test/{transaction.transaction_id}"


class Runtime:
    def __init__(self):
        self.operations = {}
        self.calls = []
        self.lock = Lock()
        self.fail = False
        self.after = None

    def reconcile(self, transaction, *, operation_key):
        with self.lock:
            self.calls.append(operation_key)
            destination = self.operations.setdefault(operation_key,
                f"https://checkout.example.test/{transaction.transaction_id}")
            if self.fail:
                raise RuntimeError("provider result lost after idempotent creation")
            if self.after:
                self.after()
            return destination


@pytest.fixture
def scenario(database):
    original = uuid4()
    with database() as connection:
        connection.execute("TRUNCATE evergreen_checkout_lineage, evergreen_checkout_resolution_events, checkout_test_transactions")
        connection.execute("""INSERT INTO checkout_test_transactions
            (transaction_id,status,expires_at,price_minor,currency,offer_id)
            VALUES (%s,'EXPIRED',%s,999,'USD','ordinary-digital-template')""", (original, NOW - timedelta(hours=1)))
    authority = Authority(original)
    runtime = Runtime()
    repository = EvergreenCheckoutRepository(connection_factory=database)
    service = EvergreenCheckoutService(namespace="ordinary-test-checkout", authority=authority,
        runtime=runtime, repository=repository, clock=lambda: NOW)
    return service, authority, runtime, database


def resolve(scenario):
    service, authority, *_ = scenario
    return service.resolve(authority.alias, binding=BINDING)


def test_active_transaction_resolves_without_refresh(scenario):
    service, authority, runtime, factory = scenario
    with factory() as connection:
        connection.execute("UPDATE checkout_test_transactions SET status='CREATED',expires_at=%s", (NOW + timedelta(days=1),))
    result = resolve(scenario)
    assert result.generation == 0
    assert result.effective_transaction_id == authority.grant.original_transaction_id
    with factory() as connection:
        assert connection.execute("SELECT count(*) AS n FROM evergreen_checkout_lineage").fetchone()["n"] == 0


def test_expired_successor_stable_alias_prices_and_audit(scenario):
    service, authority, runtime, factory = scenario
    with factory() as connection:
        before = authority.load(authority.grant.original_transaction_id, connection=connection)
    first = resolve(scenario)
    second = resolve(scenario)
    assert first == second
    assert first.original_transaction_id == before.transaction_id
    assert first.effective_transaction_id != before.transaction_id
    with factory() as connection:
        assert authority.load(before.transaction_id, connection=connection) == before
        row = connection.execute("SELECT * FROM evergreen_checkout_lineage").fetchone()
        assert row["predecessor_id"] == before.transaction_id
        assert row["successor_id"] == first.effective_transaction_id
        assert (row["predecessor_price_minor"], row["successor_price_minor"]) == (999, 999)
        assert row["refresh_reason"] == "TRANSACTION_EXPIRED"
        assert row["refreshed_at"] == NOW
        assert row["eligibility_result"] == "ELIGIBLE"
        assert row["runtime_state"] == "READY"
        events = connection.execute("SELECT * FROM evergreen_checkout_resolution_events").fetchall()
        assert len(events) == 2
        assert all(row["effective_transaction_id"] == first.effective_transaction_id for row in events)
    assert len(runtime.operations) == 1


def test_due_active_transitions_once_and_successor_later_expires(scenario):
    service, authority, runtime, factory = scenario
    with factory() as connection:
        connection.execute("UPDATE checkout_test_transactions SET status='CLICKED'")
    first = resolve(scenario)
    service.clock = lambda: NOW + timedelta(days=4)
    second = resolve(scenario)
    assert second.generation == 2
    assert second.effective_transaction_id != first.effective_transaction_id
    with factory() as connection:
        original = authority.load(first.original_transaction_id, connection=connection)
        previous = authority.load(first.effective_transaction_id, connection=connection)
        assert original.status == previous.status == "EXPIRED"
        rows = connection.execute("SELECT * FROM evergreen_checkout_lineage ORDER BY generation").fetchall()
        assert rows[1]["predecessor_id"] == rows[0]["successor_id"]


def test_ten_simultaneous_clicks_converge(scenario):
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(lambda _: resolve(scenario), range(10)))
    assert len({result.effective_transaction_id for result in results}) == 1
    assert len(scenario[2].operations) == 1
    with scenario[3]() as connection:
        assert connection.execute("SELECT count(*) AS n FROM checkout_test_transactions").fetchone()["n"] == 2
        assert connection.execute("SELECT count(*) AS n FROM evergreen_checkout_lineage").fetchone()["n"] == 1


def test_crash_before_commit_rolls_back_transaction_and_lineage(scenario):
    service, authority, runtime, factory = scenario
    authority.crash_create = True
    with pytest.raises(CheckoutUnavailable, match="This checkout link is unavailable") as caught:
        resolve(scenario)
    assert caught.value.reason_code == "CHECKOUT_INTERNAL_FAILURE"
    with factory() as connection:
        assert connection.execute("SELECT count(*) AS n FROM checkout_test_transactions").fetchone()["n"] == 1
        assert connection.execute("SELECT count(*) AS n FROM evergreen_checkout_lineage").fetchone()["n"] == 0
    authority.crash_create = False
    assert resolve(scenario).generation == 1


def test_crash_after_commit_runtime_failure_restarts_with_same_generation_and_key(scenario):
    service, authority, runtime, factory = scenario
    runtime.fail = True
    with pytest.raises(CheckoutUnavailable) as caught:
        resolve(scenario)
    assert caught.value.reason_code == "RUNTIME_RECONCILIATION_FAILED"
    with factory() as connection:
        saved = connection.execute("SELECT * FROM evergreen_checkout_lineage").fetchone()
        assert saved["runtime_state"] == "FAILED"
    runtime.fail = False
    restarted = EvergreenCheckoutService(namespace=service.namespace, authority=authority,
        runtime=runtime, repository=EvergreenCheckoutRepository(connection_factory=factory), clock=lambda: NOW)
    result = restarted.resolve(authority.alias, binding=BINDING)
    assert result.effective_transaction_id == saved["successor_id"]
    assert runtime.calls[0] == runtime.calls[1]
    assert len(runtime.operations) == 1


@pytest.mark.parametrize("field,reason", [
    ("identity_valid", "IDENTITY_MISMATCH"), ("offer_available", "OFFER_UNAVAILABLE"),
    ("product_available", "PRODUCT_UNAVAILABLE"), ("publication_valid", "PUBLICATION_INVALID"),
    ("purchase_allowed", "PURCHASE_NOT_ALLOWED"), ("commerce_allowed", "COMMERCE_BLOCKED"),
    ("runtime_supported", "RUNTIME_UNSUPPORTED"), ("price_unambiguous", "PRICE_AMBIGUOUS"),
])
def test_ineligible_does_not_create_successor_or_call_runtime(scenario, field, reason):
    service, authority, runtime, factory = scenario
    authority.eligibility = replace(authority.eligibility, **{field: False})
    with pytest.raises(CheckoutUnavailable) as caught:
        resolve(scenario)
    assert caught.value.reason_code == reason
    assert runtime.calls == []
    with factory() as connection:
        assert connection.execute("SELECT count(*) AS n FROM checkout_test_transactions").fetchone()["n"] == 1
        assert connection.execute("SELECT reason_code FROM evergreen_checkout_resolution_events").fetchone()["reason_code"] == reason


@pytest.mark.parametrize("change,reason", [
    ("alias", "ALIAS_INVALID"), ("grant", "GRANT_REVOKED"),
    ("binding", "IDENTITY_MISMATCH"), ("transaction", "TRANSACTION_REVOKED"),
    ("purchase", "PURCHASE_COMPLETE"), ("admin", "TRANSACTION_INACTIVE"),
])
def test_authentication_revocation_purchase_and_binding(scenario, change, reason):
    service, authority, runtime, factory = scenario
    if change == "grant":
        authority.grant = replace(authority.grant, revoked=True)
    elif change == "binding":
        authority.transaction_binding = replace(BINDING, customer="wrong-customer")
    elif change in {"transaction", "purchase", "admin"}:
        with factory() as connection:
            connection.execute("UPDATE checkout_test_transactions SET revoked=%s,status=%s",
                (change == "transaction", "PURCHASED" if change == "purchase" else "ADMIN_CLOSED" if change == "admin" else "EXPIRED"))
    with pytest.raises(CheckoutUnavailable) as caught:
        service.resolve("wrong" if change == "alias" else authority.alias, binding=BINDING)
    assert str(caught.value) == CheckoutUnavailable.PUBLIC_MESSAGE
    assert caught.value.reason_code == reason
    assert not runtime.calls


@pytest.mark.parametrize("price", [CheckoutPrice(-1, "USD"), CheckoutPrice(100, "EUR"),
                                   CheckoutPrice(100, "usd"), CheckoutPrice(True, "USD"), None])
def test_invalid_or_ambiguous_canonical_price(scenario, price):
    scenario[1].eligibility = replace(scenario[1].eligibility, configured_price=price)
    with pytest.raises(CheckoutUnavailable) as caught:
        resolve(scenario)
    assert caught.value.reason_code == "PRICE_INVALID"
    assert not scenario[2].calls


def test_runtime_revalidation_blocks_revocation_and_existing_successor_reuse(scenario):
    service, authority, runtime, factory = scenario
    runtime.after = lambda: setattr(authority, "grant", replace(authority.grant, revoked=True))
    with pytest.raises(CheckoutUnavailable):
        resolve(scenario)
    runtime.after = None
    with pytest.raises(CheckoutUnavailable):
        resolve(scenario)
    assert len(runtime.calls) == 1


def test_destination_rejected_without_exposing_it(scenario):
    scenario[2].reconcile = lambda *args, **kwargs: "javascript:secret-provider-details"
    with pytest.raises(CheckoutUnavailable) as caught:
        resolve(scenario)
    assert caught.value.reason_code == "DESTINATION_INVALID"
    assert "secret" not in str(caught.value)


def test_runtime_retains_precise_internal_failure_reason(scenario):
    def unavailable(*args, **kwargs):
        raise CheckoutUnavailable("RUNTIME_STATE_AMBIGUOUS")
    scenario[2].reconcile = unavailable
    with pytest.raises(CheckoutUnavailable) as caught:
        resolve(scenario)
    assert caught.value.reason_code == "RUNTIME_STATE_AMBIGUOUS"
    assert str(caught.value) == CheckoutUnavailable.PUBLIC_MESSAGE
    with scenario[3]() as connection:
        assert connection.execute("SELECT runtime_reason FROM evergreen_checkout_lineage").fetchone()["runtime_reason"] == "RUNTIME_STATE_AMBIGUOUS"


def test_hard_process_exit_after_commit_reuses_persisted_successor(scenario):
    service, authority, runtime, factory = scenario
    # Kill only this child with os._exit after the local transaction commits;
    # PostgreSQL must release the session lock without Python cleanup running.
    code = '''
import importlib.util, os, sys
from contextlib import contextmanager
from uuid import UUID
from psycopg import connect
from psycopg.rows import dict_row
spec = importlib.util.spec_from_file_location('fixture', sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
@contextmanager
def factory():
    with connect(sys.argv[2], row_factory=dict_row) as connection:
        yield connection
authority = m.Authority(UUID(sys.argv[3]))
authority.grant = m.replace(authority.grant, alias_id=UUID(sys.argv[4]))
class Runtime:
    def reconcile(self, *args, **kwargs):
        os._exit(23)
service = m.EvergreenCheckoutService(namespace='ordinary-test-checkout', authority=authority,
    runtime=Runtime(), repository=m.EvergreenCheckoutRepository(connection_factory=factory), clock=lambda: m.NOW)
service.resolve(authority.alias, binding=m.BINDING)
'''
    child = subprocess.run([sys.executable, "-c", code, str(Path(__file__).resolve()),
        factory.url, str(authority.grant.original_transaction_id), str(authority.grant.alias_id)],
        timeout=20, capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert child.returncode == 23, child.stderr
    with factory() as connection:
        committed = connection.execute("SELECT * FROM evergreen_checkout_lineage").fetchone()
        assert committed["runtime_state"] == "PENDING"
    assert resolve(scenario).effective_transaction_id == committed["successor_id"]


def test_unknown_runtime_cannot_roll_into_another_generation(scenario):
    service, authority, runtime, factory = scenario
    runtime.fail = True
    with pytest.raises(CheckoutUnavailable):
        resolve(scenario)
    service.clock = lambda: NOW + timedelta(days=4)
    runtime.fail = False
    with pytest.raises(CheckoutUnavailable) as caught:
        resolve(scenario)
    assert caught.value.reason_code == "PRIOR_RUNTIME_UNRESOLVED"
    with factory() as connection:
        assert connection.execute("SELECT count(*) AS n FROM evergreen_checkout_lineage").fetchone()["n"] == 1


def test_lineage_is_immutable_and_rollback_preserves_used_history(scenario):
    resolve(scenario)
    from psycopg.errors import RaiseException
    with pytest.raises(RaiseException, match="immutable"):
        with scenario[3]() as connection:
            connection.execute("UPDATE evergreen_checkout_lineage SET predecessor_price_minor=1")
    with pytest.raises(RaiseException, match="immutable"):
        with scenario[3]() as connection:
            connection.execute("DELETE FROM evergreen_checkout_lineage")
    with pytest.raises(RaiseException, match="retain audit history"):
        with scenario[3]() as connection:
            connection.execute((ROOT / "migrations/rollback" / MIGRATION).read_text())


def test_reuse_revalidates_product_and_purchase_authority(scenario):
    result = resolve(scenario)
    scenario[1].eligibility = replace(scenario[1].eligibility, purchase_allowed=False)
    with pytest.raises(CheckoutUnavailable) as caught:
        resolve(scenario)
    assert caught.value.reason_code == "PURCHASE_NOT_ALLOWED"
    with scenario[3]() as connection:
        assert connection.execute("SELECT successor_id FROM evergreen_checkout_lineage").fetchone()["successor_id"] == result.effective_transaction_id
    assert len(scenario[2].calls) == 1


def test_migration_governance_and_rollback(database):
    assert all(SchemaManagerService.REQUIRED_TABLES[name]["migration"] == MIGRATION
               for name in ("evergreen_checkout_lineage", "evergreen_checkout_resolution_events"))
    with database() as connection:
        connection.execute("TRUNCATE evergreen_checkout_lineage, evergreen_checkout_resolution_events")
        connection.execute((ROOT / "migrations/rollback" / MIGRATION).read_text())
        assert connection.execute("SELECT to_regclass('public.evergreen_checkout_lineage') AS name").fetchone()["name"] is None
        connection.execute((ROOT / "migrations/forward" / MIGRATION).read_text())
