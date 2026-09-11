"""Read-only Creator Intelligence Center API."""

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from app.api.customers import _account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.creator_intelligence_service import CreatorIntelligenceService
from app.services.performance_snapshot_service import PerformanceSnapshotService
from app.models.performance_snapshot import ReportingPeriodKey
from app.services.x_link_performance_service import XLinkPerformanceService
from app.repositories.performance_snapshot_repository import PerformanceSnapshotRepository
from app.services.operations_workspace_service import OperationsWorkspaceService


router = APIRouter(prefix="/api/v1/creator-intelligence", tags=["creator-intelligence"])


def _service() -> CreatorIntelligenceService:
    return CreatorIntelligenceService()


@router.get("")
def creator_intelligence():
    account_id = _account_id()
    profile = get_active_creator_profile(str(account_id)) or {}
    creator_profile_id = int(profile.get("id") or 0)
    if not creator_profile_id:
        creator_profile_id = account_id
    return jsonable_encoder(
        _service().dashboard(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
        )
    )


def _snapshot_scope():
    account_id = _account_id()
    profile = get_active_creator_profile(str(account_id)) or {}
    if not profile.get("id"):
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail="Active creator profile is required.")
    return int(profile["id"]), int(account_id)


@router.get("/snapshot")
def performance_snapshot(period: ReportingPeriodKey = ReportingPeriodKey.TODAY):
    creator_profile_id, account_id = _snapshot_scope()
    return jsonable_encoder(PerformanceSnapshotService().snapshot(
        creator_profile_id=creator_profile_id, fanvue_account_id=account_id,
        period=period.value))


@router.get("/snapshot/drill-down")
def performance_snapshot_drill_down(
    metric: str, period: ReportingPeriodKey = ReportingPeriodKey.TODAY,
):
    from fastapi import HTTPException
    creator_profile_id, account_id = _snapshot_scope()
    try:
        result = PerformanceSnapshotService().drill_down(
            creator_profile_id=creator_profile_id, fanvue_account_id=account_id,
            period=period.value, metric=metric)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return jsonable_encoder(result)


@router.get("/sales-status")
def current_sales_status():
    creator_profile_id, account_id = _snapshot_scope()
    state = PerformanceSnapshotRepository().current_sales_status(
        creator_profile_id=creator_profile_id, fanvue_account_id=account_id,
    )
    failures = OperationsWorkspaceService().failures(account_id=account_id)
    return {
        "activeSalesSessions": int(state.get("active_sales_sessions") or 0),
        "activePurchaseIntents": int(state.get("active_purchase_intents") or 0),
        "commercialFailures": int(failures.get("total") or len(failures.get("items") or ())),
        "asOf": "CURRENT",
    }


@router.get("/x-link-performance")
def x_link_performance(period: ReportingPeriodKey = ReportingPeriodKey.TODAY):
    creator_profile_id, account_id = _snapshot_scope()
    return jsonable_encoder(XLinkPerformanceService().report(
        creator_profile_id=creator_profile_id,
        fanvue_account_id=account_id,
        period=period.value,
    ))
