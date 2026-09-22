import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg.errors import UniqueViolation

from app.services.private_chat_unlock_gateway_service import (
    PUBLIC_ALIAS_COLLISION_ATTEMPTS,
    PUBLIC_ALIAS_PATTERN,
    PrivateChatUnlockGatewayService,
    UnlockUnavailableError,
)


def grant(**changes):
    values = {
        "unlock_grant_id": uuid4(), "purchase_intent_id": uuid4(),
        "public_alias_hash": None, "public_alias_generation": None,
    }
    values.update(changes)
    return SimpleNamespace(**values)


class AliasRepository:
    def __init__(self, item, *, collisions=0):
        self.item = item
        self.collisions = collisions
        self.attempts = []

    def assign_public_alias(self, *, grant_id, alias_hash, generation):
        self.attempts.append((alias_hash, generation))
        if generation < self.collisions:
            raise UniqueViolation("synthetic collision")
        self.item.public_alias_hash = alias_hash
        self.item.public_alias_generation = generation
        return self.item

    def get_grant_for_intent(self, _):
        return self.item


def service(repository):
    return PrivateChatUnlockGatewayService(
        repository=repository, token_secret="s" * 32,
    )


def test_alias_format_entropy_and_hashed_persistence():
    item = grant(); repository = AliasRepository(item)
    assigned, alias = service(repository)._ensure_public_alias(item)
    assert len(alias) == 22
    assert PUBLIC_ALIAS_PATTERN.fullmatch(alias)
    assert assigned.public_alias_hash == hashlib.sha256(alias.encode()).hexdigest()
    assert alias != assigned.public_alias_hash
    assert not hasattr(assigned, "public_alias")
    assert repository.attempts == [(assigned.public_alias_hash, 0)]


def test_alias_is_stable_for_durable_retry():
    item = grant(); repository = AliasRepository(item)
    first = service(repository)._ensure_public_alias(item)[1]
    # A new service instance models API/worker restart while the database row
    # remains authoritative.
    second = service(repository)._ensure_public_alias(item)[1]
    assert first == second


def test_alias_collision_retries_with_distinct_secure_prf_output():
    item = grant(); repository = AliasRepository(item, collisions=2)
    _, alias = service(repository)._ensure_public_alias(item)
    assert item.public_alias_generation == 2
    assert len({value[0] for value in repository.attempts}) == 3
    assert hashlib.sha256(alias.encode()).hexdigest() == item.public_alias_hash


def test_alias_collision_retry_is_bounded_and_fails_closed():
    item = grant(); repository = AliasRepository(
        item, collisions=PUBLIC_ALIAS_COLLISION_ATTEMPTS,
    )
    with pytest.raises(UnlockUnavailableError, match="uniqueness"):
        service(repository)._ensure_public_alias(item)
    assert len(repository.attempts) == PUBLIC_ALIAS_COLLISION_ATTEMPTS


@pytest.mark.parametrize("value", ["", "a" * 21, "a" * 23, "bad.alias", "../escape"])
def test_malformed_alias_fails_before_repository_lookup(monkeypatch, value):
    calls = []
    gateway = service(SimpleNamespace(
        resolve_grant_by_alias=lambda _: calls.append(True)
    ))
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    with pytest.raises(UnlockUnavailableError, match="invalid"):
        gateway.resolve_alias(value)
    assert calls == []


def test_revoked_or_unknown_alias_fails_closed(monkeypatch):
    gateway = service(SimpleNamespace(resolve_grant_by_alias=lambda _: None))
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    with pytest.raises(UnlockUnavailableError, match="unavailable or revoked"):
        gateway.resolve_alias("a" * 22)


def test_active_alias_enters_the_same_authoritative_gateway(monkeypatch):
    item = grant(); item.state = "ACTIVE"; item.use_count = 0
    class Repository:
        def resolve_grant_by_alias(self, _alias):
            item.use_count += 1
            return item
    gateway = service(Repository())
    claimed = []
    gateway._resolve_claimed_grant = lambda value: claimed.append(value) or (
        "https://www.fanvue.com/avablackthorne/media/example"
    )
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    result = gateway.resolve_alias("a" * 22)
    assert result.startswith("https://www.fanvue.com/")
    assert item.use_count == 1
    assert claimed == [item]


def test_alias_resolution_persists_bounded_success_diagnostic(monkeypatch):
    item = grant(); item.state = "ACTIVE"
    diagnostics = []
    repository = SimpleNamespace(
        resolve_grant_by_alias=lambda _: item,
        record_resolution_diagnostic=lambda **values: diagnostics.append(values),
    )
    gateway = service(repository)
    gateway._resolve_claimed_grant = lambda _: (
        "https://www.fanvue.com/avablackthorne/media/example"
    )
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    gateway.resolve_alias("a" * 22)
    assert diagnostics[0]["grant_id"] == item.unlock_grant_id
    assert diagnostics[0]["status"] == "RESOLVED"
    assert diagnostics[0]["reason_code"] == "OK"


def test_expired_intent_is_rejected_before_click_or_provider_work():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    ids = {
        "telegram_user_id": 5, "telegram_chat_id": 5,
        "commercial_offering_id": uuid4(), "commercial_publication_id": uuid4(),
        "fanvue_account_id": 7,
    }
    item = grant(**ids); item.currency = "USD"
    intent = SimpleNamespace(
        purchase_intent_id=item.purchase_intent_id,
        expected_currency="USD", status="PRESENTED",
        expires_at=now - timedelta(seconds=1), **ids,
    )
    gateway = PrivateChatUnlockGatewayService(
        repository=SimpleNamespace(),
        intent_repository=SimpleNamespace(get=lambda _: intent),
        clock=lambda: now,
        purchase_intent_lifecycle=SimpleNamespace(
            record_unlock_click=lambda *_args, **_kwargs: pytest.fail(
                "expired grant must not record a click"
            )
        ),
    )
    with pytest.raises(UnlockUnavailableError) as caught:
        gateway._resolve_claimed_grant(item)
    assert caught.value.reason_code == "EXPIRED"


def test_alias_lookup_claims_only_an_active_grant_and_tracks_normal_use():
    source = Path(
        "app/repositories/private_chat_fingerprint_repository.py"
    ).read_text(encoding="utf-8")
    method = source.split("def resolve_grant_by_alias", 1)[1].split(
        "def reserve_price", 1
    )[0]
    assert "public_alias_hash=%s AND state='ACTIVE'" in method
    assert "use_count=use_count+1" in method
    assert "last_used_at=NOW()" in method


def test_migration_stores_only_alias_hash_with_unique_index():
    sql = Path(
        "migrations/forward/20260827_099_private_chat_unlock_public_alias.sql"
    ).read_text(encoding="utf-8")
    assert "public_alias_hash" in sql
    assert "CREATE UNIQUE INDEX" in sql
    assert "public_alias TEXT" not in sql
    assert "public_alias_hash ~ '^[0-9a-f]{64}$'" in sql
