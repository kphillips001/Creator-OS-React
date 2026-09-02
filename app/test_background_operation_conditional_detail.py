from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import background_operations as api
from app.models.background_operation import BackgroundOperation


def test_operation_detail_etag_returns_304_until_updated(monkeypatch):
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    operation = BackgroundOperation(
        operation_id=uuid4(), operation_type="content_studio_explicit_inspiration",
        originating_workspace="content_studio", creator_profile_id=7, account_id=2,
        subject_type="creator_profile", subject_id="7", idempotency_key="key", executor_key="worker",
        status="RUNNING", metadata={"hardcore": ["x" * 50_000]}, updated_at=now,
    )
    service = SimpleNamespace(get=lambda *_args, **_kwargs: operation,
                              payload=lambda value: __import__("app.services.background_operation_service", fromlist=["BackgroundOperationService"]).BackgroundOperationService(repository=object()).payload(value))
    monkeypatch.setattr(api, "_context", lambda: (7, 2))
    monkeypatch.setattr(api, "BackgroundOperationService", lambda: service)
    application = FastAPI(); application.include_router(api.router)
    client = TestClient(application)
    first = client.get(f"/api/v1/background-operations/{operation.operation_id}")
    assert first.status_code == 200 and len(first.content) > 50_000
    etag = first.headers["etag"]
    unchanged = client.get(f"/api/v1/background-operations/{operation.operation_id}", headers={"If-None-Match": etag})
    assert unchanged.status_code == 304 and unchanged.content == b""
