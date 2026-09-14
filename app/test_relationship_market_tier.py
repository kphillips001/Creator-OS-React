from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import relationships
from app.models.relationship_market_tier import RelationshipMarketTierRecord
from app.services.relationship_market_tier_service import RelationshipMarketTierService


SCOPE = dict(creator_profile_id=11, fanvue_account_id=22,
             telegram_user_id=33, telegram_chat_id=44)


class MemoryRepository:
    def __init__(self):
        self.rows = []

    def active(self, **scope):
        return next((row for row in reversed(self.rows)
                     if all(getattr(row, key) == value for key, value in scope.items())
                     and row.removed_at is None), None)

    def set(self, *, market_tier, changed_by, reason=None, **scope):
        current = self.active(**scope)
        if current and current.market_tier.value == market_tier:
            return current, False
        if current:
            self.rows[-1] = RelationshipMarketTierRecord(
                **{**current.__dict__, "removed_by": changed_by,
                   "removed_at": datetime.now(timezone.utc)})
        row = RelationshipMarketTierRecord(
            market_tier_id=uuid4(), market_tier=__import__(
                "app.models.relationship_market_tier", fromlist=["RelationshipMarketTier"]
            ).RelationshipMarketTier(market_tier),
            version=max((row.version for row in self.rows), default=0) + 1,
            changed_by=changed_by, changed_at=datetime.now(timezone.utc),
            reason=reason, **scope)
        self.rows.append(row)
        return row, True

    def remove(self, *, removed_by, **scope):
        current = self.active(**scope)
        if current is None:
            return None
        removed = RelationshipMarketTierRecord(
            **{**current.__dict__, "removed_by": removed_by,
               "removed_at": datetime.now(timezone.utc)})
        self.rows[-1] = removed
        return removed


@pytest.mark.parametrize(("tier", "hvp", "buyer", "expected"), [
    ("HIGH", True, False, "MAXIMUM"),
    ("HIGH", False, False, "HIGH"),
    ("MEDIUM", True, False, "HIGH"),
    ("MEDIUM", False, False, "STANDARD"),
    (None, True, False, "HIGH"),
    (None, False, False, "STANDARD"),
    ("LOW", False, False, "LOW"),
    ("LOW", True, False, "LOW"),
    ("LOW", True, True, "BUYER_AUTHORITY"),
])
def test_market_tier_projection(tier, hvp, buyer, expected):
    assert RelationshipMarketTierService.effective_investment(
        market_tier=tier, high_value_prospect=hvp,
        verified_buyer=buyer).value == expected


def test_set_replace_remove_and_closed_values():
    repository = MemoryRepository()
    service = RelationshipMarketTierService(repository)
    assert service.read(**SCOPE)["marketTier"] == "UNCLASSIFIED"
    first = service.set(**SCOPE, market_tier="HIGH", changed_by="operator")
    assert first["changed"] and first["record"]["version"] == 1
    assert not service.set(**SCOPE, market_tier="HIGH", changed_by="operator")["changed"]
    second = service.set(**SCOPE, market_tier="LOW", changed_by="operator")
    assert second["record"]["version"] == 2
    assert service.remove(**SCOPE, removed_by="operator") == {
        "marketTier": "UNCLASSIFIED", "effectiveProspectInvestment": "STANDARD",
        "highValueProspect": False, "verifiedBuyer": False, "record": None,
        "changed": True,
    }
    with pytest.raises(ValueError):
        service.set(**SCOPE, market_tier="high", changed_by="operator")
    with pytest.raises(ValueError):
        service.set(**SCOPE, market_tier="VIP", changed_by="operator")


def test_api_is_authenticated_closed_and_returns_authoritative_state(monkeypatch):
    service = RelationshipMarketTierService(MemoryRepository())
    monkeypatch.setattr(relationships, "_market_tier_context",
                        lambda _key: (service, SCOPE, False, False))
    application = FastAPI()
    application.include_router(relationships.router)
    client = TestClient(application)
    path = "/api/v1/relationships/telegram:11:22:33/market-tier"
    assert client.get(path).status_code == 403
    headers = {"X-Creator-OS-Developer": "true"}
    assert client.get(path, headers=headers).json()["marketTier"] == "UNCLASSIFIED"
    assert client.put(path, headers=headers, json={"marketTier": "high"}).status_code == 422
    result = client.put(path, headers=headers, json={"marketTier": "MEDIUM"})
    assert result.status_code == 200 and result.json()["marketTier"] == "MEDIUM"
    result = client.delete(path, headers=headers)
    assert result.status_code == 200 and result.json()["marketTier"] == "UNCLASSIFIED"


def test_relationship_scope_rejects_cross_account_and_missing_relationship(monkeypatch):
    monkeypatch.setattr(relationships, "_snapshot_scope", lambda: (11, 22))
    with pytest.raises(Exception) as error:
        relationships._relationship_scope("telegram:11:999:33")
    assert error.value.status_code == 404
