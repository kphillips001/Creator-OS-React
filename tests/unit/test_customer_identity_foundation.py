from pathlib import Path
from types import SimpleNamespace

import pytest

from app.repositories.customer_repository import CustomerRepository
from app.services.canonical_customer_identity_service import CanonicalCustomerIdentityService


class FakeCanonicalIdentityRepository:
    def __init__(self, observation=None, links=()):
        self.observation = observation
        self.links = links
        self.verified = []

    def get_observed_external(self, **_values):
        return self.observation

    def verify_external(self, **values):
        self.verified.append(values)
        return {"external_numeric_id": values["external_numeric_id"]}, False

    def active_for_customer(self, **_values):
        return self.links


def test_x_preview_requires_stable_observed_numeric_identity():
    service = CanonicalCustomerIdentityService(FakeCanonicalIdentityRepository())
    with pytest.raises(ValueError, match="stable numeric"):
        service.preview_x_link(creator_profile_id=1,local_fanvue_user_id=2,
                               external_numeric_id="mcclung_wally")
    with pytest.raises(LookupError, match="Observed stable"):
        service.preview_x_link(creator_profile_id=1,local_fanvue_user_id=2,
                               external_numeric_id="12345")


def test_x_handle_is_observed_metadata_not_verification_authority():
    repository = FakeCanonicalIdentityRepository({
        "external_numeric_id":"12345","observed_username":"new_handle"})
    preview = CanonicalCustomerIdentityService(repository).preview_x_link(
        creator_profile_id=1,local_fanvue_user_id=2,external_numeric_id="12345")
    assert preview["observedUsername"] == "new_handle"
    assert preview["externalNumericIdMasked"] == "12345"


def test_customer_read_model_aggregates_fanvue_telegram_and_x_without_new_customer():
    external = FakeCanonicalIdentityRepository(links=[{
        "platform":"X","external_numeric_id":"999001","creator_profile_id":3,
        "observed_username":"renamed","observed_display_name":"W",
        "verification_method":"OPERATOR_CONFIRMED_STABLE_PROVIDER_ID",
        "verified_at":SimpleNamespace(isoformat=lambda: "2026-09-11T00:00:00Z"),
    }])
    telegram = SimpleNamespace(get_by_local_user_id=lambda *_: SimpleNamespace(
        telegram_user_id=777,telegram_chat_id=777,local_fanvue_user_id=4,is_active=True))
    repo = CustomerRepository(
        fanvue_user_by_id_fetcher=lambda account,user:{"id":user,"fanvue_account_id":account,
            "fanvue_user_uuid":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","username":"papi80"},
        memory_fetcher=lambda *_:{},chat_messages_fetcher=lambda *_:[],
        owned_content_tags_fetcher=lambda *_:[],telegram_identity_repository=telegram,
        external_identity_repository=external)
    customer=repo.get_by_legacy_fanvue_user(fanvue_account_id=3,fanvue_user_id=4)
    assert customer.customer_id == "3:4"
    assert {identity.provider for identity in customer.provider_identities} == {"fanvue","telegram","x"}


def test_migration_is_ordered_constrained_and_reversible():
    forward=Path("migrations/forward/20260911_114_verified_external_customer_identities.sql").read_text()
    rollback=Path("migrations/rollback/20260911_114_verified_external_customer_identities.sql").read_text()
    assert "external_numeric_id ~ '^[0-9]+$'" in forward
    assert "verified_external_customer_identity_active_external_idx" in forward
    assert "WHERE is_active" in forward
    assert "external_customer_identity_observations" in forward
    assert "canonical_customer_materialization_audit" in forward
    assert rollback.index("verified_external_customer_identities") < rollback.index("external_customer_identity_observations")
