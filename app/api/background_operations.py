"""Creator/account-scoped Background Operations API."""
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.encoders import jsonable_encoder

from app.api.content_studio import _current_account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.background_operation_service import BackgroundOperationService

router = APIRouter(prefix="/api/v1/background-operations", tags=["background-operations"])


def _context():
    account_id = _current_account_id()
    if account_id is None:
        raise ValueError("Creator account required.")
    creator = get_active_creator_profile(str(account_id))
    if not creator:
        raise ValueError("Active Creator Profile required.")
    return int(creator["id"]), int(account_id)


@router.get("")
def list_background_operations(status: str = Query("active"), workspace: str | None = None,
                               subject_type: str | None = None, subject_id: str | None = None):
    try:
        creator_id, account_id = _context()
        service = BackgroundOperationService()
        operations = service.list(creator_profile_id=creator_id, account_id=account_id,
                                  status=status, workspace=workspace,
                                  subject_type=subject_type, subject_id=subject_id)
        return {"success": True, "operations": [service.summary_payload(item) for item in operations]}
    except ValueError as error:
        return JSONResponse(status_code=400, content={"success": False, "error": str(error)})


@router.get("/{operation_id}")
def get_background_operation(operation_id: str, request: Request):
    creator_id, account_id = _context()
    service = BackgroundOperationService()
    operation = service.get(operation_id, creator_profile_id=creator_id, account_id=account_id)
    if operation is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "Operation not found."})
    version = str(int(operation.updated_at.timestamp() * 1_000_000)) if operation.updated_at else "0"
    etag = f'"operation-{operation.operation_id}-{version}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, no-cache"})
    return JSONResponse(
        content=jsonable_encoder({"success": True, "operation": service.payload(operation)}),
        headers={"ETag": etag, "Cache-Control": "private, no-cache"},
    )


@router.post("/{operation_id}/cancel")
def cancel_background_operation(operation_id: str):
    creator_id, _ = _context()
    service = BackgroundOperationService()
    try:
        operation = service.repository.request_cancellation(
            operation_id, creator_profile_id=creator_id)
        # Client-orchestrated batches have no worker lease that could observe
        # CANCEL_REQUESTED. Finalize them immediately through the canonical
        # terminal lifecycle; their independently durable provider children
        # continue reconciliation without advancing the cancelled parent.
        if (operation.status == "CANCEL_REQUESTED"
                and operation.executor_key == "content_studio_explicit_batch_client"):
            operation = service.cancel(
                operation.operation_id,
                "Generation stopped by operator. Completed images were preserved.",
            )
        return {"success": True, "operation": service.payload(operation)}
    except KeyError as error:
        return JSONResponse(status_code=404, content={"success": False, "error": str(error)})
    except ValueError as error:
        return JSONResponse(status_code=409, content={"success": False, "error": str(error)})


@router.post("/{operation_id}/retry")
def retry_background_operation(operation_id: str):
    creator_id, _ = _context()
    service = BackgroundOperationService()
    try:
        operation = service.repository.retry(operation_id, creator_profile_id=creator_id)
        return {"success": True, "operation": service.payload(operation)}
    except KeyError as error:
        return JSONResponse(status_code=404, content={"success": False, "error": str(error)})
    except ValueError as error:
        return JSONResponse(status_code=409, content={"success": False, "error": str(error)})
