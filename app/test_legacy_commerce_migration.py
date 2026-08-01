import pytest

from app.services.legacy_commerce_migration_service import (
    LegacyCommerceMigrationService,
    RecordClassification,
)
from app.services.legacy_commerce_path import LegacyCommercePathDisabledError
from app.services.cms_fanvue_upload_link_service import CMSFanvueUploadLinkService
from app.services.cms_fanvue_media_sync_service import CMSFanvueMediaSyncService
from app.services.content_media_delivery_service import ContentMediaDeliveryService


def record(record_id=1, **overrides):
    value = {
        "id": record_id, "creator_profile_id": 7,
        "local_vault_path": f"vault/{record_id}.jpg", "file_path": None,
        "classification": "TEASE", "is_active": True,
        "product_id": None, "offering_ids": (), "price_minor": None,
        "sale_intent": None,
    }
    value.update(overrides)
    return value


def classify(*items):
    return LegacyCommerceMigrationService.classify_records(items)


def test_existing_reference_asset_is_reused_without_commerce_fabrication():
    decision = classify(record(classification="REFERENCE"))[0]
    assert decision.classification == RecordClassification.CANONICAL_ASSET_ALREADY_EXISTS.value
    assert decision.canonical_asset_id == 1
    assert decision.commerce_action == "ASSET_ONLY"
    assert decision.exclusion_reason == "reference_asset_not_sellable"


def test_historical_content_is_explicitly_excluded():
    decision = classify(record(is_active=False))[0]
    assert decision.classification == RecordClassification.HISTORICAL_ONLY.value
    assert decision.commerce_action == "NONE"
    assert decision.exclusion_reason == "inactive_historical_content"


@pytest.mark.parametrize("overrides,reason", [
    ({"creator_profile_id": None}, "missing_creator_scope"),
    ({"local_vault_path": None, "file_path": None}, "missing_media_reference"),
    ({"local_vault_path": "vault/file.bin"}, "unsupported_media"),
])
def test_invalid_records_block_migration(overrides, reason):
    decision = classify(record(**overrides))[0]
    assert decision.classification == RecordClassification.INVALID_OR_INCOMPLETE.value
    assert decision.commerce_action == "BLOCKED"
    assert decision.exclusion_reason == reason


def test_duplicate_media_is_not_registered_or_composed_twice():
    decisions = classify(record(1, local_vault_path="vault/same.jpg"), record(2, local_vault_path="VAULT/SAME.JPG"))
    assert {item.classification for item in decisions} == {RecordClassification.DUPLICATE.value}
    assert all(item.commerce_action == "NONE" for item in decisions)


def test_already_migrated_record_revalidates_existing_identity():
    decision = classify(record(product_id="product-1", offering_ids=("offering-1",)))[0]
    assert decision.classification == RecordClassification.ALREADY_MIGRATED.value
    assert decision.commerce_action == "REVALIDATE"


def test_sellable_evidence_requires_offering_not_automatic_product():
    decision = classify(record(price_minor=999, sale_intent="mass_ppv"))[0]
    assert decision.commerce_action == "OFFERING_ONLY"
    assert decision.product_id is None


@pytest.mark.parametrize("service,method,args", [
    (CMSFanvueUploadLinkService(), "create_upload_link", (1, 2)),
    (CMSFanvueMediaSyncService(), "upload_and_store_media_ids", ({"id": 1}, 2)),
    (ContentMediaDeliveryService(), "get_media_for_delivery", (2, "vip", "chat_ppv")),
])
def test_legacy_cms_commerce_paths_are_explicitly_disabled(service, method, args):
    with pytest.raises(LegacyCommercePathDisabledError, match="canonical Commercial Offering"):
        getattr(service, method)(*args)

