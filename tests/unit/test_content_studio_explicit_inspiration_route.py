from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import content_studio


@pytest.fixture
def explicit_inspiration_route(monkeypatch):
    created_operations = []

    class Service:
        def create(self, **values):
            created_operations.append(values)
            return SimpleNamespace(operation_id=uuid4()), True

        def payload(self, operation):
            return {
                "operationId": str(operation.operation_id),
                "status": "PENDING",
                "currentStage": "QUEUED",
            }

    monkeypatch.setattr(
        "app.services.background_operation_service.BackgroundOperationService",
        Service,
    )
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 7)
    monkeypatch.setattr(
        content_studio,
        "get_active_creator_profile",
        lambda account_id: {"id": 42},
    )

    application = FastAPI()
    application.include_router(content_studio.router)
    return TestClient(application), created_operations


@pytest.mark.parametrize(
    ("payload", "softcore_count", "hardcore_count"),
    [
        ({"tierMode": "both", "count": 10}, 5, 5),
        ({"tierMode": "softcore", "count": 5}, 5, 0),
        ({"tierMode": "hardcore", "count": 5}, 0, 5),
        ({"tierMode": "both", "count": 12}, 6, 6),
    ],
)
def test_explicit_inspiration_route_creates_queued_durable_operation(
    explicit_inspiration_route,
    payload,
    softcore_count,
    hardcore_count,
):
    client, created_operations = explicit_inspiration_route

    response = client.post("/api/v1/content-studio/explicit/inspire", json=payload)

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["operation"]["status"] == "PENDING"
    assert response.json()["operation"]["currentStage"] == "QUEUED"
    assert len(created_operations) == 1
    operation = created_operations[0]
    assert operation["operation_type"] == "content_studio_explicit_inspiration"
    assert operation["current_stage"] == "QUEUED"
    assert operation["metadata"]["softcoreCount"] == softcore_count
    assert operation["metadata"]["hardcoreCount"] == hardcore_count


def test_explicit_inspiration_route_rejects_count_above_maximum_without_500(
    explicit_inspiration_route,
):
    client, created_operations = explicit_inspiration_route

    response = client.post(
        "/api/v1/content-studio/explicit/inspire",
        json={"tierMode": "both", "count": 13},
    )

    assert response.status_code == 422
    assert created_operations == []


def test_explicit_inspiration_route_preserves_legacy_count_per_tier_contract(
    explicit_inspiration_route,
):
    client, created_operations = explicit_inspiration_route

    response = client.post(
        "/api/v1/content-studio/explicit/inspire",
        json={"countPerTier": 5},
    )

    assert response.status_code == 200
    operation = created_operations[0]
    assert operation["metadata"]["requestedCount"] == 10
    assert operation["metadata"]["softcoreCount"] == 5
    assert operation["metadata"]["hardcoreCount"] == 5
