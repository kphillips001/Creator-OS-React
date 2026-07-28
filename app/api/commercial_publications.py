"""Commercial Publication record API; deliberately contains no provider logic."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.asset_library import _creator_profile
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.fanvue_media_link_publication_executor import FanvueMediaLinkPublicationExecutor
from app.services.fanvue_commercial_publication_reconciliation_service import (
    FanvueCommercialPublicationReconciliationService,
)
from app.api.provider_connections import selected_account_id
from app.services.fanvue_oauth_service import (
    FanvueOAuthService, FanvueReauthorizationRequired,
)


router = APIRouter(prefix="/api/v1/commercial-publications", tags=["commercial-publications"])


class CreatePublicationRequest(BaseModel):
    commercialOfferingId: UUID
    provider: str
    publicationMetadata: dict[str, Any] = Field(default_factory=dict)


class UpdatePublicationStatusRequest(BaseModel):
    status: str
    externalProductId: str | None = None
    lastError: str | None = None

class ExecutePublicationRequest(BaseModel):
    fanvueAccountId: int | None = None


def _service() -> CommercialPublicationService:
    return CommercialPublicationService()


def _payload(publication):
    return {
        "publicationId": str(publication.publication_id),
        "commercialOfferingId": str(publication.commercial_offering_id),
        "provider": publication.provider.value,
        "status": publication.status.value,
        "externalProductId": publication.external_product_id,
        "publishedAt": publication.published_at.isoformat() if publication.published_at else None,
        "createdAt": publication.created_at.isoformat(),
        "updatedAt": publication.updated_at.isoformat(),
        "lastError": publication.last_error,
        "retryCount": publication.retry_count,
        "publicationMetadata": dict(publication.publication_metadata),
        "providerResourceStatus": publication.provider_resource_status.value,
        "lastReconciledAt": (
            publication.last_reconciled_at.isoformat()
            if publication.last_reconciled_at else None
        ),
        "reconciliationResult": publication.reconciliation_result,
    }

def _execute_background(publication_id: UUID, creator_profile_id: int, account_id: int):
    try:
        FanvueMediaLinkPublicationExecutor().execute(
            publication_id, creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
        )
    except Exception:
        # Executor persists a sanitized failure on the publication/checkpoint.
        return


@router.get("")
def list_publications(commercial_offering_id: UUID | None = Query(None)):
    publications = _service().list_publications(
        creator_profile_id=int(_creator_profile()["id"]),
        commercial_offering_id=commercial_offering_id,
    )
    return {"items": [_payload(item) for item in publications]}


@router.get("/{publication_id}")
def get_publication(publication_id: UUID):
    publication = _service().get_publication(
        publication_id, creator_profile_id=int(_creator_profile()["id"])
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Commercial Publication not found.")
    return _payload(publication)


@router.post("", status_code=201)
def create_publication(request: CreatePublicationRequest):
    try:
        publication = _service().create_publication(
            creator_profile_id=int(_creator_profile()["id"]),
            commercial_offering_id=request.commercialOfferingId,
            provider=request.provider,
            publication_metadata=request.publicationMetadata,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _payload(publication)


@router.patch("/{publication_id}")
def update_publication(publication_id: UUID, request: UpdatePublicationStatusRequest):
    try:
        publication = _service().update_status(
            publication_id, creator_profile_id=int(_creator_profile()["id"]),
            status=request.status, external_product_id=request.externalProductId,
            last_error=request.lastError,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if publication is None:
        raise HTTPException(status_code=404, detail="Commercial Publication not found.")
    return _payload(publication)

@router.post("/{publication_id}/execute", status_code=202)
def execute_publication(
    publication_id: UUID, request: ExecutePublicationRequest,
    background_tasks: BackgroundTasks,
):
    profile = _creator_profile()
    creator_profile_id = int(profile["id"])
    account_id = request.fanvueAccountId or profile.get("fanvue_account_id")
    if not account_id:
        raise HTTPException(status_code=400, detail="A linked Fanvue account is required.")
    service = _service()
    publication = service.get_publication(
        publication_id, creator_profile_id=creator_profile_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="Commercial Publication not found.")
    offering = service.offerings.get(
        publication.commercial_offering_id, creator_profile_id=creator_profile_id)
    try:
        FanvueMediaLinkPublicationExecutor._validate(publication, offering)
        FanvueOAuthService(int(account_id)).require_scopes(
            "read:creator", "write:creator", "read:media", "write:media")
    except FanvueReauthorizationRequired as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    metadata = dict(publication.publication_metadata)
    metadata["fanvue_account_id"] = int(account_id)
    service.repository.update_metadata(
        publication.publication_id, creator_profile_id=creator_profile_id, metadata=metadata)
    if publication.status.value != "PUBLISHING":
        publication = service.update_status(
            publication.publication_id, creator_profile_id=creator_profile_id,
            status="PUBLISHING")
    background_tasks.add_task(
        _execute_background, publication_id, creator_profile_id, int(account_id))
    return _payload(publication)

@router.post("/{publication_id}/retry", status_code=202)
def retry_publication(
    publication_id: UUID, request: ExecutePublicationRequest,
    background_tasks: BackgroundTasks,
):
    return execute_publication(publication_id, request, background_tasks)


@router.post("/{publication_id}/reconcile")
def reconcile_publication(publication_id: UUID):
    try:
        result = FanvueCommercialPublicationReconciliationService().reconcile(
            publication_id,
            creator_profile_id=int(_creator_profile()["id"]),
            fanvue_account_id=selected_account_id(),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "publicationId": str(result.publication_id),
        "providerResourceStatus": result.provider_resource_status.value,
        "reconciliationResult": result.result,
        "publicationStatus": result.publication_status,
        "lastReconciledAt": (
            result.last_reconciled_at.isoformat()
            if result.last_reconciled_at else None
        ),
    }
