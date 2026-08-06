from app.repositories.commerce_library_repository import CommerceLibraryRepository


class ContentDestinations:
    def __init__(self):
        self.expressions = []

    def available_inventory_predicate(self, expression):
        self.expressions.append(expression)
        return (
            "EXISTS (SELECT 1 FROM public.asset_content_destinations destination "
            f"WHERE destination.asset_id={expression} "
            "AND destination.destination='AVAILABLE_INVENTORY')"
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
            self.rows = [{"total": 50}]
        else:
            self.rows = [{
                "item_id": "asset:42", "item_kind": "asset", "asset_id": 42,
                "creator_profile_id": 7, "asset_name": "portrait.png",
                "analysis_status": "READY", "current_lifecycle": "CHAT_READY",
                "commerce_status": "Chat Ready", "deliverable_id": None,
                "shot_count": None,
            }]

    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, statements): self.statements = statements
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return Cursor(self.statements)


def test_list_projection_is_creator_scoped_paginated_and_bounded():
    statements = []
    destinations = ContentDestinations()
    repository = CommerceLibraryRepository(
        connection_factory=lambda: Connection(statements),
        content_destination_service=destinations,
    )

    result = repository.list_page(
        creator_profile_id=7, search="portrait", commerce_status="Chat Ready",
        page_size=24, page=2,
    )

    assert len(statements) == 2
    assert result.total == 50 and result.page == 2
    assert result.items[0].commerce_status == "Chat Ready"
    count_sql, count_params = statements[0]
    page_sql, page_params = statements[1]
    assert "b.creator_profile_id = %s" in count_sql
    assert "d.creator_profile_id = %s" in count_sql
    assert "LIMIT %s OFFSET %s" in page_sql
    assert page_params[-2:] == (24, 24)
    assert "chat_commerce_registrations" in page_sql
    assert "business_asset_fulfillment_registrations" in page_sql
    assert "photoshoot_intelligence_profiles" in page_sql
    assert "commercial_title" in page_sql
    assert "profile_data" not in page_sql
    assert "SELECT d.*" not in page_sql
    assert "to_regclass" not in count_sql + page_sql
    assert destinations.expressions == ["b.asset_id"]
    assert "asset_content_destinations" in count_sql
    assert "photoshoot_asset_memberships" not in count_sql


def test_query_count_does_not_grow_with_page_size():
    for page_size in (1, 24, 100):
        statements = []
        CommerceLibraryRepository(
            connection_factory=lambda: Connection(statements),
            content_destination_service=ContentDestinations(),
        ).list_page(
            creator_profile_id=7, search=None, commerce_status=None,
            page_size=page_size, page=1,
        )
        assert len(statements) == 2
