"""Read-only API for the temporary process-local Fanvue webhook monitor."""

from fastapi import APIRouter, Depends
from app.api.developer_authorization import require_developer_authorization

from app.services.fanvue_webhook_monitor_service import fanvue_webhook_monitor


router = APIRouter(
    prefix="/api/v1/developer/fanvue-webhook-monitor",
    tags=["developer-fanvue-webhook-monitor"],
    dependencies=[Depends(require_developer_authorization)],
)


@router.get("")
def list_webhook_monitor_items():
    items = fanvue_webhook_monitor.list_items()
    return {
        "items": items,
        "lastWebhookReceived": items[0]["timestamp"] if items else None,
        "storage": "process-memory",
        "limit": 100,
    }
