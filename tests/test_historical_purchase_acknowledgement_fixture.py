from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.testing.session5_scenario_harness import (
    HistoricalPurchaseFixtureBuilder,
    SCENARIO_MANIFEST,
)


NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


class _Scenarios:
    def __init__(self, *, pending: bool):
        self._definition = SimpleNamespace(
            historical_purchase_acknowledgement_pending=pending,
        )

    def prepare(self, _scenario_id):
        return None

    def definition(self, _scenario_id):
        return self._definition

    def connection(self):
        raise AssertionError("unit fixture must not open a database connection")


def _builder(*, pending: bool):
    builder = HistoricalPurchaseFixtureBuilder(_Scenarios(pending=pending))
    builder._ensure_customer = lambda _scenario_id: {"telegram_user_id": 15}
    builder._create_intent = lambda _scenario_id, _base, **kwargs: {
        "purchase_intent_id": f"intent-{kwargs['index']}",
        "amount_minor": kwargs["amount_minor"],
        "purchased_at": kwargs["purchased_at"],
    }
    builder.emulator = SimpleNamespace(confirm=lambda **_kwargs: {
        "settlement": {"status": "PURCHASED"},
    })
    builder.derived_state = lambda _scenario_id: {"purchaseCount": 3}
    return builder


def test_historical_purchases_are_acknowledged_after_canonical_settlement(monkeypatch):
    acknowledged = []
    monkeypatch.setattr(
        PurchaseIntentRepository,
        "mark_purchase_acknowledged",
        lambda _repo, intent_id, *, at: acknowledged.append((intent_id, at)),
    )

    result = _builder(pending=False).build(
        "C15",
        [{"amount_minor": 5001, "purchased_at": NOW} for _ in range(3)],
    )

    assert acknowledged == [
        ("intent-1", NOW), ("intent-2", NOW), ("intent-3", NOW),
    ]
    assert result["derived"]["purchaseCount"] == 3


def test_c11_explicitly_preserves_one_pending_purchase_acknowledgement(monkeypatch):
    monkeypatch.setattr(
        PurchaseIntentRepository,
        "mark_purchase_acknowledged",
        lambda *_args, **_kwargs: pytest.fail("C11 acknowledgement must remain pending"),
    )

    _builder(pending=True).build(
        "C11", [{"amount_minor": 1100, "purchased_at": NOW}],
    )


def test_only_c11_requests_a_pending_historical_acknowledgement():
    definitions = {item.scenario_id: item for item in SCENARIO_MANIFEST}
    assert definitions["C11"].historical_purchase_acknowledgement_pending is True
    for scenario_id in ("C12", "C13", "C14", "C15"):
        assert (
            definitions[scenario_id].historical_purchase_acknowledgement_pending
            is False
        )
