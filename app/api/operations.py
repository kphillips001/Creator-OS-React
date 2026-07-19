"""Read-only operational evidence API."""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.api.customers import _account_id
from app.services.operations_workspace_service import OperationsWorkspaceService
from app.services.module_switches_service import ModuleSwitchesService


router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def _workspace_service() -> OperationsWorkspaceService:
    return OperationsWorkspaceService()


def _module_switches_service() -> ModuleSwitchesService:
    return ModuleSwitchesService()


class ModuleSwitchUpdate(BaseModel):
    value: bool | str


@router.get("/overview")
def operations_overview():
    return jsonable_encoder(_workspace_service().overview(account_id=_account_id()))


@router.get("/runtime")
def operations_runtime():
    return jsonable_encoder(_workspace_service().runtime(account_id=_account_id()))


@router.get("/workers")
def operations_workers():
    return jsonable_encoder(_workspace_service().workers(account_id=_account_id()))


@router.get("/queues")
def operations_queues():
    return jsonable_encoder(_workspace_service().queues(account_id=_account_id()))


@router.get("/publishing")
def operations_publishing():
    return jsonable_encoder(_workspace_service().publishing(account_id=_account_id()))


@router.get("/failures")
def operations_failures():
    return jsonable_encoder(_workspace_service().failures(account_id=_account_id()))


@router.get("/module-switches")
def operations_module_switches():
    return jsonable_encoder(_module_switches_service().read(creator_profile_id=_account_id()))


@router.patch("/module-switches/{module}")
def update_operations_module_switch(module: str, payload: ModuleSwitchUpdate):
    try:
        result = _module_switches_service().update(module, payload.value, creator_profile_id=_account_id())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return jsonable_encoder(result)
