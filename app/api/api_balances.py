"""Authenticated, read-only API balance projection."""
from fastapi import APIRouter, Depends, Query

from app.api.developer_authorization import require_developer_authorization
from app.services.api_balance_service import ApiBalanceService

router = APIRouter(prefix="/api/v1/business/api-balances", tags=["api-balances"],
                   dependencies=[Depends(require_developer_authorization)])


@router.get("")
def api_balances(refresh: bool = Query(default=False)):
    return ApiBalanceService().balances(force=refresh)
