"""Developer-only, read-only Fanvue API Explorer."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.developer_authorization import require_developer_authorization

from app.api.provider_connections import selected_account_id
from app.repositories.fanvue_account_repository import get_account_by_id
from app.services.fanvue_api_explorer_service import FanvueAPIExplorerService


router = APIRouter(
    prefix="/api/v1/developer/fanvue-api-explorer",
    tags=["developer-fanvue-api-explorer"],
    dependencies=[Depends(require_developer_authorization)],
)


@router.get("/{operation}")
def inspect_fanvue(
    operation: str,
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    page_size: int | None = Query(default=None, ge=1, le=100),
    media_uuid: str | None = Query(default=None),
):
    try:
        account_id = selected_account_id()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    account = get_account_by_id(account_id)
    if not account or not account.get("oauth_access_token"):
        raise HTTPException(
            status_code=401,
            detail="An authenticated Fanvue creator OAuth connection is required.",
        )
    scopes = tuple(str(account.get("oauth_scope") or "").split())
    try:
        return FanvueAPIExplorerService().inspect(
            fanvue_account_id=account_id,
            operation=operation,
            scopes=scopes,
            start_date=start_date,
            end_date=end_date,
            page_size=page_size,
            media_uuid=media_uuid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
