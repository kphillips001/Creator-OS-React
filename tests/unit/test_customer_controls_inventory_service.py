from app.services.customer_controls_inventory_service import CustomerControlsInventoryService
from pathlib import Path


class Repository:
    def __init__(self, rows):
        self.data = rows
        self.calls = 0

    def rows(self, **_scope):
        self.calls += 1
        return self.data


def row(**changes):
    value = {
        "row_kind": "CANONICAL_CUSTOMER", "row_key": "customer:2:2:7245",
        "local_fanvue_user_id": 7245, "display_name": "papi80", "best_username": "papi80",
        "canonical_username": None, "canonical_display_name": None, "canonical_source": None,
        "fanvue_handle": "papi80", "purchase_count": 5, "lifetime_gross_minor": 11996,
        "lifetime_net_minor": 9596, "first_purchase_at": None, "last_purchase_at": None,
        "last_synced_at": None, "telegram_status": "NOT_OBSERVED", "x_status": "NOT_OBSERVED",
        "control_availability": "UNAVAILABLE", "relationship_key": None, "telegram_user_id": None,
        "telegram_username": None, "telegram_display_name": None, "x_numeric_id": None,
        "x_username": None, "latest_activity_at": None,
        "operational_eligibility_reason": "VERIFIED_EXTERNAL_MAPPING",
    }
    value.update(changes)
    return value


def test_verified_mapping_buyer_is_visible_without_fake_controls_or_conversation():
    repo = Repository([row()])
    item = CustomerControlsInventoryService(repo).list(creator_profile_id=2, fanvue_account_id=2)["items"][0]
    assert item["rowKey"] == "customer:2:2:7245"
    assert item["commerce"] == {"lifetimeGrossMinor": 11996, "lifetimeNetMinor": 9596, "purchaseCount": 5, "firstPurchaseAt": None, "lastPurchaseAt": None, "lastSyncedAt": None, "ownedAssetCount": 0}
    assert item["controlAvailability"] == "UNAVAILABLE"
    assert item["controls"] is None and item["hasConversation"] is False
    assert repo.calls == 1


def test_fanvue_only_buyer_is_excluded_and_search_cannot_resurrect_it():
    repo = Repository([row(operational_eligibility_reason=None)])
    service = CustomerControlsInventoryService(repo)
    assert service.list(creator_profile_id=2, fanvue_account_id=2)["total"] == 0
    assert service.list(
        creator_profile_id=2, fanvue_account_id=2,
        filter="FANVUE", search="papi80",
    )["total"] == 0


def test_provider_filters_search_numeric_ids_and_pagination_use_one_snapshot():
    rows = [
        row(),
        row(row_key="telegram:2:2:99", row_kind="TELEGRAM_PROSPECT", local_fanvue_user_id=None,
            display_name="Prospect", best_username="tgname", purchase_count=0, lifetime_gross_minor=None,
            lifetime_net_minor=None, telegram_status="OBSERVED_UNVERIFIED", control_availability="AVAILABLE",
            relationship_key="telegram:2:2:99", telegram_user_id=99),
        row(row_key="customer:2:2:7", local_fanvue_user_id=7, display_name="X person", best_username="elsewhere",
            purchase_count=0, x_status="VERIFIED", x_numeric_id="123456", x_username="xhandle"),
    ]
    repo = Repository(rows)
    service = CustomerControlsInventoryService(repo)
    assert service.list(creator_profile_id=2, fanvue_account_id=2, filter="PROSPECTS")["items"][0]["rowKey"] == "telegram:2:2:99"
    assert service.list(creator_profile_id=2, fanvue_account_id=2, filter="X", search="123456")["total"] == 1
    assert service.list(creator_profile_id=2, fanvue_account_id=2, page=2, page_size=2)["items"][0]["rowKey"] == "customer:2:2:7"
    assert repo.calls == 3


def test_inventory_missing_control_rows_project_default_on_permissions():
    source = Path("app/repositories/customer_controls_inventory_repository.py").read_text()
    assert source.count("COALESCE(control.content_selling_enabled,true)") == 2
    assert source.count("COALESCE(control.session_selling_enabled,true)") == 2
    assert "COALESCE(control.content_selling_enabled,false)" not in source
