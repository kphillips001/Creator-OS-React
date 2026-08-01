from contextlib import contextmanager
from uuid import uuid4

from app.repositories.commercial_ownership_coverage_repository import (
    CommercialOwnershipCoverageRepository,
)


class Cursor:
    def __init__(self):
        self.rows = []
        self.entitlement_params = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        if "customer_entitlements" in sql:
            self.entitlement_params = params
            self.rows = [{
                "id": uuid4(), "product_id": uuid4(),
                "status": "active", "source_type": "purchase",
                "expires_at": None, "asset_ids": [41],
                "core_user_id": params[0],
                "legacy_fanvue_account_id": None,
                "legacy_fanvue_user_id": None,
            }]
        else:
            self.rows = []

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, cursor):
        self.value = cursor

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.value


def test_core_user_entitlement_is_canonical_ownership_evidence():
    cursor = Cursor()

    @contextmanager
    def factory():
        yield Connection(cursor)

    core_user_id = uuid4()
    result = CommercialOwnershipCoverageRepository(
        connection_factory=factory
    ).get(
        creator_profile_id=9,
        fanvue_account_id=4,
        external_fanvue_user_uuid=None,
        telegram_user_id=None,
        legacy_fanvue_user_id=None,
        core_user_id=core_user_id,
    )

    assert result["owned_asset_ids"] == (41,)
    assert result["entitlement_asset_ids"] == (41,)
    assert result["evidence_sources"] == (
        "CORE_USER_PRODUCT_ENTITLEMENT",
    )
    assert cursor.entitlement_params == (core_user_id, 9)


def test_all_ownership_sources_deduplicate_assets_and_retain_provenance():
    offering_id = uuid4()
    core_user_id = uuid4()

    class CombinedCursor(Cursor):
        def execute(self, sql, params):
            if "purchase_intents" in sql:
                self.rows = [{
                    "purchase_intent_id": uuid4(),
                    "commercial_offering_id": offering_id,
                    "status": "PURCHASED",
                    "attribution_result": "ATTRIBUTED",
                    "asset_ids": [41], "sales_session_id": None,
                }]
            elif "customer_entitlements" in sql:
                self.rows = [
                        {
                        "id": uuid4(), "product_id": uuid4(),
                        "status": "active", "source_type": "purchase",
                        "expires_at": None, "asset_ids": [41],
                        "core_user_id": core_user_id,
                        "legacy_fanvue_account_id": None,
                        "legacy_fanvue_user_id": None,
                    },
                        {
                        "id": uuid4(), "product_id": uuid4(),
                        "status": "fulfilled", "source_type": "purchase",
                        "expires_at": None, "asset_ids": [42],
                        "core_user_id": None,
                        "legacy_fanvue_account_id": 4,
                        "legacy_fanvue_user_id": "legacy-7",
                    },
                ]
            elif "content_usage_log" in sql:
                self.rows = [
                    {"id": 1, "content_item_id": 42, "content_tag": None,
                     "usage_type": "owned"},
                    {"id": 2, "content_item_id": None,
                     "content_tag": "legacy-only",
                     "usage_type": "content_unlocked"},
                ]

    cursor = CombinedCursor()

    @contextmanager
    def factory():
        yield Connection(cursor)

    result = CommercialOwnershipCoverageRepository(
        connection_factory=factory
    ).get(
        creator_profile_id=9, fanvue_account_id=4,
        external_fanvue_user_uuid=uuid4(), telegram_user_id=8,
        legacy_fanvue_user_id="legacy-7", core_user_id=core_user_id,
    )

    assert result["owned_offering_ids"] == (offering_id,)
    assert result["owned_asset_ids"] == (41, 42)
    assert result["purchase_asset_ids"] == (41,)
    assert result["entitlement_asset_ids"] == (41, 42)
    assert result["legacy_asset_ids"] == (42,)
    assert result["evidence_sources"] == (
        "ATTRIBUTED_COMMERCIAL_OFFERING_PURCHASE",
        "CORE_USER_PRODUCT_ENTITLEMENT",
        "PRODUCT_ENTITLEMENT",
        "LEGACY_CONTENT_USAGE",
    )
    assert result["incomplete"] is True
