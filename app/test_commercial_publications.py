from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import commercial_publications as api
from app.models.commercial_offering import CommercialOfferingStatus, PrimarySalesChannel
from app.models.commercial_publication import (
    CommercialPublication,
    CommercialPublicationProvider,
    CommercialPublicationStatus,
)
from app.repositories.commercial_publication_repository import CommercialPublicationRepository
from app.services.commercial_publication_service import CommercialPublicationService


OFFERING_ID = uuid4()


def publication(status=CommercialPublicationStatus.READY_TO_PUBLISH):
    now = datetime.now(timezone.utc)
    return CommercialPublication(
        uuid4(), OFFERING_ID, CommercialPublicationProvider.FANVUE, status,
        None, None, now, now, None, 0, {},
    )


class Offerings:
    def __init__(self, exists=True, archived=False, channel=True):
        self.exists, self.archived, self.channel = exists, archived, channel
    def get(self, offering_id, *, creator_profile_id):
        if not self.exists: return None
        return SimpleNamespace(
            offering_id=offering_id, creator_profile_id=creator_profile_id,
            status=CommercialOfferingStatus.ARCHIVED if self.archived else CommercialOfferingStatus.DRAFT,
            primary_sales_channel=PrimarySalesChannel.AI_CHAT if self.channel else None,
        )


class Publications:
    def __init__(self, existing=None):
        self.existing = existing
        self.created = None
        self.current = None
        self.updated = None
    def get_by_offering_provider(self, *_): return self.existing
    def create(self, **values):
        self.created = values
        return publication(values["status"])
    def get(self, *_args, **_kwargs): return self.current
    def list(self, **_): return tuple(filter(None, (self.existing,)))
    def update_status(self, publication_id, **values):
        self.updated = values
        return publication(values["status"])


class CommerciallyEligible:
    def require_offering(self, *_args, **_kwargs): pass


def test_publication_creation_is_ready_and_does_not_change_offering():
    publications = Publications()
    offerings = Offerings()
    result = CommercialPublicationService(
        repository=publications, offering_repository=offerings,
        commercial_eligibility=CommerciallyEligible(),
    ).create_publication(
        creator_profile_id=7, commercial_offering_id=OFFERING_ID,
        provider="FANVUE",
    )
    assert result.status == CommercialPublicationStatus.READY_TO_PUBLISH
    assert publications.created["provider"] == CommercialPublicationProvider.FANVUE


def test_duplicate_provider_invalid_provider_and_invalid_offering_are_rejected():
    with pytest.raises(ValueError, match="already exists"):
        CommercialPublicationService(
            repository=Publications(publication()), offering_repository=Offerings(),
            commercial_eligibility=CommerciallyEligible(),
        ).create_publication(
            creator_profile_id=7, commercial_offering_id=OFFERING_ID, provider="FANVUE",
        )
    with pytest.raises(ValueError, match="Unsupported publication provider"):
        CommercialPublicationService(
            repository=Publications(), offering_repository=Offerings(),
            commercial_eligibility=CommerciallyEligible(),
        ).create_publication(
            creator_profile_id=7, commercial_offering_id=OFFERING_ID, provider="WEBSITE",
        )
    for offerings, message in (
        (Offerings(exists=False), "not found"),
        (Offerings(archived=True), "Archived"),
        (Offerings(channel=False), "Primary Sales Channel"),
    ):
        with pytest.raises(ValueError, match=message):
            CommercialPublicationService(
                repository=Publications(), offering_repository=offerings,
                commercial_eligibility=CommerciallyEligible(),
            ).create_publication(
                creator_profile_id=7, commercial_offering_id=OFFERING_ID, provider="FANVUE",
            )


def test_lifecycle_transitions_mark_failed_and_mark_live():
    service = CommercialPublicationService(
        repository=Publications(), offering_repository=Offerings(),
        commercial_eligibility=CommerciallyEligible(),
    )
    service.validate_transition("READY_TO_PUBLISH", "PUBLISHING")
    service.validate_transition("PUBLISHING", "FAILED")
    service.validate_transition("PUBLISHING", "LIVE")
    service.validate_transition("LIVE", "ARCHIVED")
    with pytest.raises(ValueError, match="Invalid publication transition"):
        service.validate_transition("READY_TO_PUBLISH", "LIVE")
    with pytest.raises(ValueError, match="Invalid publication transition"):
        service.validate_transition("ARCHIVED", "READY_TO_PUBLISH")

    service.repository.current = publication(CommercialPublicationStatus.PUBLISHING)
    failed = service.mark_failed(
        service.repository.current.publication_id,
        creator_profile_id=7, error="Provider unavailable",
    )
    assert failed.status == CommercialPublicationStatus.FAILED
    assert service.repository.updated["last_error"] == "Provider unavailable"
    service.repository.current = publication(CommercialPublicationStatus.PUBLISHING)
    live = service.mark_live(
        service.repository.current.publication_id,
        creator_profile_id=7, external_product_id="external-1",
    )
    assert live.status == CommercialPublicationStatus.LIVE
    assert service.repository.updated["published_at"] is not None


class Cursor:
    def __init__(self, statements):
        self.statements = statements
        self.row = None
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params):
        self.statements.append((sql, params))
        if "INSERT INTO public.commercial_publications" in sql:
            now = datetime.now(timezone.utc)
            self.row = {
                "publication_id": params[0], "commercial_offering_id": params[1],
                "provider": params[2], "status": params[3],
                "external_product_id": None, "published_at": None,
                "created_at": now, "updated_at": now, "last_error": None,
                "retry_count": 0, "publication_metadata": {},
            }
    def fetchone(self): return self.row


class Connection:
    def __init__(self, statements): self.statements = statements
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return Cursor(self.statements)


def test_repository_creates_only_a_publication_record_and_database_prevents_duplicates():
    statements = []
    result = CommercialPublicationRepository(
        connection_factory=lambda: Connection(statements)
    ).create(
        commercial_offering_id=OFFERING_ID,
        provider=CommercialPublicationProvider.FANVUE,
        status=CommercialPublicationStatus.READY_TO_PUBLISH,
    )
    assert result.status == CommercialPublicationStatus.READY_TO_PUBLISH
    assert len(statements) == 1
    assert "commercial_publications" in statements[0][0]
    migration = open(
        "migrations/forward/20260723_003_commercial_publications_foundation.sql",
        encoding="utf-8",
    ).read()
    assert "UNIQUE (commercial_offering_id, provider)" in migration


class ApiService:
    def create_publication(self, **_): return publication()
    def list_publications(self, **_): return (publication(),)
    def get_publication(self, *_args, **_kwargs): return publication()
    def update_status(self, *_args, **_kwargs): return publication(CommercialPublicationStatus.PUBLISHING)


def test_publication_api_create_list_get_and_patch(monkeypatch):
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "_service", ApiService)
    app = FastAPI(); app.include_router(api.router)
    client = TestClient(app)
    created = client.post("/api/v1/commercial-publications", json={
        "commercialOfferingId": str(OFFERING_ID), "provider": "FANVUE",
    })
    assert created.status_code == 201
    assert created.json()["status"] == "READY_TO_PUBLISH"
    assert client.get("/api/v1/commercial-publications").json()["items"]
    publication_id = created.json()["publicationId"]
    assert client.get(f"/api/v1/commercial-publications/{publication_id}").status_code == 200
    patched = client.patch(
        f"/api/v1/commercial-publications/{publication_id}",
        json={"status": "PUBLISHING"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "PUBLISHING"
