from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import available_inventory as api
from app.repositories.available_inventory_repository import (
    AvailableInventoryItem,
    AvailableInventoryPage,
    AvailableInventoryRepository,
)


class Destinations:
    def __init__(self):
        self.expressions = []

    def available_inventory_predicate(self, expression):
        self.expressions.append(expression)
        return (
            "EXISTS (SELECT 1 FROM public.asset_content_destinations authoritative "
            f"WHERE authoritative.asset_id={expression} "
            "AND authoritative.destination='AVAILABLE_INVENTORY')"
        )


class Cursor:
    def __init__(self, statements):
        self.statements = statements
        self.rows = []

    def __enter__(self): return self
    def __exit__(self, *_): return False

    def execute(self, sql, params):
        self.statements.append((sql, params))
        if "COUNT(*)" in sql:
            self.rows = [{"total": 41, "ready": 17}]
        else:
            self.rows = [{
                "asset_id": 42, "display_name": "Beach Day extra.jpg",
                "media_type": "image", "created_at": datetime(2026, 7, 23, tzinfo=timezone.utc),
                "registration_state": "approved", "readiness": "READY",
                "destination": "AVAILABLE_INVENTORY", "source_workflow": "photoshoot",
                "source_name": "Beach Day Photoshoot", "source_session_id": "shoot-1",
                "short_description": "A bright beach portrait.",
            }]

    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, statements): self.statements = statements
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return Cursor(self.statements)


def test_query_is_destination_authoritative_filtered_before_pagination_and_has_no_n_plus_one():
    statements = []
    destinations = Destinations()
    result = AvailableInventoryRepository(
        connection_factory=lambda: Connection(statements),
        content_destination_service=destinations,
    ).list_page(
        creator_profile_id=7, page=2, page_size=20, search="beach",
        readiness="ready", source="photoshoot", media_type="image", sort="name",
    )

    assert len(statements) == 2
    assert destinations.expressions == ["asset.id"]
    count_sql, count_params = statements[0]
    page_sql, page_params = statements[1]
    assert "AVAILABLE_INVENTORY" in count_sql
    assert "reference_library" in count_sql
    assert "analysis_status='READY'" in count_sql
    assert all(value not in count_sql for value in ("PHOTOSET", "TEASER", "BUNDLE", "photoshoot_asset_memberships"))
    assert "LIMIT %s OFFSET %s" in page_sql
    assert page_params[-2:] == (20, 20)
    assert "asset_intelligence_profiles" in page_sql
    assert "photoshoot_commerce_deliverables" in page_sql
    assert "ILIKE" in count_sql and "analysis_status" in count_sql
    assert "photoshoot_session" in count_sql
    assert result.total == 41 and result.ready == 17 and result.pending == 24
    assert result.items[0].source_name == "Beach Day Photoshoot"


def test_sorting_and_empty_result_remain_stable_and_bounded():
    for sort, expected in (
        ("newest", "asset.created_at DESC NULLS LAST, asset.id DESC"),
        ("oldest", "asset.created_at ASC NULLS LAST, asset.id ASC"),
        ("name", "LOWER(COALESCE"),
        ("readiness", "analysis_status"),
    ):
        statements = []
        AvailableInventoryRepository(
            connection_factory=lambda: Connection(statements),
            content_destination_service=Destinations(),
        ).list_page(
            creator_profile_id=7, page=1, page_size=20, search=None,
            readiness=None, source=None, media_type=None, sort=sort,
        )
        assert expected in statements[1][0]
        assert len(statements) == 2


class Service:
    def list_page(self, **_):
        item = AvailableInventoryItem(
            asset_id=42, display_name="Beach Day extra.jpg", media_type="image",
            created_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
            registration_state="approved", readiness="READY",
            destination="AVAILABLE_INVENTORY", source_workflow="photoshoot",
            source_name="Beach Day Photoshoot", source_session_id="shoot-1",
            short_description="A bright beach portrait.",
        )
        return AvailableInventoryPage((item,), 1, 1, 0, 1)


def test_read_only_api_returns_minimal_typed_projection(monkeypatch):
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "_service", lambda: Service())
    app = FastAPI()
    app.include_router(api.router)
    response = TestClient(app).get(
        "/api/v1/available-inventory?page=1&page_size=20&source=photoshoot"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["contentDestination"] == "AVAILABLE_INVENTORY"
    assert body["items"][0]["sourceName"] == "Beach Day Photoshoot"
    assert "metadata" not in body["items"][0]
