from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.fingerprint_purchase_attribution_service import FingerprintPurchaseAttributionService
from app.services.telegram_provisional_sales_session_service import TelegramProvisionalSalesSessionService


def test_provisional_session_preserves_configured_price_separately():
    captured = {}
    prospect = SimpleNamespace(
        telegram_sales_prospect_id=uuid4(), creator_profile_id=2,
        fanvue_account_id=7, telegram_user_id=44, telegram_chat_id=44)
    service = TelegramProvisionalSalesSessionService(
        repository=SimpleNamespace(create_or_get=lambda **values: captured.update(values) or values),
        prospect_service=SimpleNamespace(context=lambda **_: SimpleNamespace(prospect=prospect)),
    )
    result = service.create_or_get(
        creator_profile_id=2, fanvue_account_id=7, telegram_user_id=44,
        telegram_chat_id=44, photoshoot_reference="shoot-1",
        session_strategy="ESCALATING", configured_base_price_minor=1499,
        commercial_context={"nextConfiguredPriceMinor": 1999})
    assert result["configured_base_price_minor"] == 1499
    assert result["commercial_context"]["nextConfiguredPriceMinor"] == 1999
    assert "actual_fingerprint_price_minor" not in result


def test_first_purchase_graduates_session_with_actual_charge_without_repricing_strategy():
    reservation_id, intent_id = uuid4(), uuid4()
    intent = SimpleNamespace(
        purchase_intent_id=intent_id, creator_profile_id=2,
        fanvue_account_id=7, telegram_user_id=44)
    mapping = SimpleNamespace(id=9, telegram_user_id=44,
                              external_fanvue_user_uuid=None,
                              local_fanvue_user_id=12)
    class Repository:
        def match_purchase(self, **_):
            return [{"runtime_state": "ACTIVE", "purchase_intent_id": intent_id,
                     "fingerprint_reservation_id": reservation_id}]
        def mark_purchased(self, **_): return intent_id
    class Intents:
        def get(self, _): return intent
        def update(self, _, **values):
            for key, value in values.items(): setattr(intent, key, value)
            return intent
        def mark_purchased(self, *_args, **_kwargs): return intent
    class Identities:
        def get_verified_by_telegram_user_id(self, _): return None
        def get_verified_by_external_fanvue_user_uuid(self, *_): return None
        def create_verified_mapping(self, **_): return mapping, True
    graduated = []
    provisional = SimpleNamespace(graduate=lambda **values: graduated.append(values) or "session")
    prospects = SimpleNamespace(graduate=lambda **_: None)
    buyer_uuid = uuid4()
    settlement_calls = []
    settlement = SimpleNamespace(settle=lambda **values:
        settlement_calls.append(values) or {"provisional_session": "session"})
    result = FingerprintPurchaseAttributionService(
        repository=Repository(), intents=Intents(), identities=Identities(),
        fanvue_user_resolver=lambda *_: {"id": 12},
        provisional_session_service=provisional, prospect_service=prospects,
        settlement_service=settlement,
    ).attribute(
        fanvue_account_id=7, currency="USD", gross_minor=1497,
        source="media_link", buyer_uuid=buyer_uuid, transaction_id="tx-1",
        payment_id="pay-1", event_id="event-1",
        purchased_at=datetime.now(timezone.utc))
    assert result["provisional_session"] == "session"
    assert settlement_calls[0]["gross_minor"] == 1497
