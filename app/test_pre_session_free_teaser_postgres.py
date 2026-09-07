"""Real PostgreSQL proof for free-teaser continuity and later graduation."""
import os
from types import SimpleNamespace

import pytest

from app.repositories.telegram_provisional_sales_session_repository import (
    TelegramProvisionalSalesSessionRepository,
)
from app.test_private_chat_settlement_postgres import (
    connection_factory,
    fixture,
    settle,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required"
)


def test_confirmed_free_teaser_is_zero_paid_commerce_then_settlement_graduates():
    values = fixture(session=False, offering_type="PHOTOSET")
    repository = TelegramProvisionalSalesSessionRepository(connection_factory)
    provisional = repository.create_or_get(
        prospect=SimpleNamespace(
            telegram_sales_prospect_id=values["prospect_id"],
            creator_profile_id=values["creator"],
            fanvue_account_id=values["account"],
            telegram_user_id=values["telegram"],
            telegram_chat_id=values["telegram"],
        ),
        photoshoot_reference="synthetic-free-teaser-foundation",
        session_strategy="test-v1", configured_base_price_minor=1499,
        commercial_context={"authority": "PRE_SESSION_FREE_TEASER"},
    )
    confirmed = repository.record_free_teaser_delivery(
        provisional_session_id=provisional.provisional_session_id,
        asset_id=values["asset"], provider="TEST_TRANSPORT",
        provider_delivery_id="free-delivery-1",
        metadata={
            "photoshoot_session_id": "synthetic-free-teaser-foundation",
        },
    )
    assert confirmed.current_position == 2
    assert confirmed.progression_stage == "PROGRESSION"
    assert confirmed.first_purchase_intent_id is None
    assert confirmed.commercial_context["freeTeaserDelivery"]["salesRole"] == (
        "FREE_TEASER"
    )
    replayed = repository.record_free_teaser_delivery(
        provisional_session_id=provisional.provisional_session_id,
        asset_id=values["asset"], provider="TEST_TRANSPORT",
        provider_delivery_id="free-delivery-1",
        metadata={
            "photoshoot_session_id": "synthetic-free-teaser-foundation",
        },
    )
    assert replayed.current_position == 2
    assert replayed.commercial_context["freeTeaserDelivery"] == (
        confirmed.commercial_context["freeTeaserDelivery"]
    )
    with connection_factory() as connection:
        zero = connection.execute("""SELECT
            (SELECT count(*) FROM provider_purchase_asset_ownership
              WHERE fanvue_account_id=%s) AS ownership,
            (SELECT count(*) FROM purchase_intents
              WHERE telegram_user_id=%s AND status='PURCHASED') AS purchases,
            (SELECT count(*) FROM purchase_intents
              WHERE telegram_user_id=%s
                AND provider_transaction_order_id IS NOT NULL) AS transactions""",
            (values["account"], values["telegram"], values["telegram"]),
        ).fetchone()
    assert dict(zero) == {"transactions": 0, "ownership": 0, "purchases": 0}

    repository.associate_intent(
        provisional.provisional_session_id, values["intent_id"]
    )
    settle(values)
    with connection_factory() as connection:
        graduated = connection.execute("""SELECT state,mapped_sales_session_id
            FROM telegram_provisional_sales_sessions
            WHERE provisional_session_id=%s""",
            (provisional.provisional_session_id,),
        ).fetchone()
        session = connection.execute("""SELECT commercial_foundation_reference
            FROM sales_sessions WHERE sales_session_id=%s""",
            (graduated["mapped_sales_session_id"],),
        ).fetchone()
    assert graduated["state"] == "GRADUATED"
    assert session["commercial_foundation_reference"] == (
        "synthetic-free-teaser-foundation"
    )


def test_unconfirmed_free_teaser_does_not_advance_provisional_session():
    values = fixture(session=False, offering_type="PHOTOSET")
    repository = TelegramProvisionalSalesSessionRepository(connection_factory)
    provisional = repository.create_or_get(
        prospect=SimpleNamespace(
            telegram_sales_prospect_id=values["prospect_id"],
            creator_profile_id=values["creator"],
            fanvue_account_id=values["account"],
            telegram_user_id=values["telegram"],
            telegram_chat_id=values["telegram"],
        ),
        photoshoot_reference="synthetic-failed-teaser-foundation",
        session_strategy="test-v1", configured_base_price_minor=1499,
        commercial_context={"authority": "PRE_SESSION_FREE_TEASER"},
    )
    assert provisional.current_position == 1
    assert provisional.progression_stage == "DISCOVERY"
    assert "freeTeaserDelivery" not in provisional.commercial_context
