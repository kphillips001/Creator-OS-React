import json
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse

from app.services.webhook_normalizer_service import WebhookNormalizerService
from app.services.webhook_signature_service import WebhookSignatureService
from app.services.webhook_event_processor_service import (
    WebhookEventProcessorService,
)
from app.repositories.webhook_event_repository import (
    create_webhook_event,
    get_webhook_event_by_external_id,
)
from app.api.content_studio import router as content_studio_router
from app.api.generation_library_publishing import router as generation_library_publishing_router
from app.api.edit_studio import router as edit_studio_router
from app.api.generation_library import router as generation_library_router
from app.api.posted_content import router as posted_content_router
from app.api.photoshoot import router as photoshoot_router
from app.api.reference_library import router as reference_library_router
from app.api.asset_library import router as asset_library_router
from app.api.test_chat import router as test_chat_router
from app.api.business_assets import router as business_assets_router
from app.api.products import router as products_router
from app.api.customers import router as customers_router
from app.api.sales import router as sales_router
from app.api.operations import router as operations_router
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


_heartbeat_logger = logging.getLogger("fastapi-worker-heartbeat")


async def _fastapi_heartbeat_loop(service: WorkerHeartbeatService) -> None:
    while True:
        await asyncio.to_thread(record_heartbeat_safely, _heartbeat_logger, "heartbeat", service.heartbeat)
        await asyncio.sleep(30)


@asynccontextmanager
async def _application_lifespan(application: FastAPI):
    service = WorkerHeartbeatService(worker_name="FastAPI", worker_type="application_runtime", poll_interval_seconds=30)
    await asyncio.to_thread(record_heartbeat_safely, _heartbeat_logger, "startup", service.register_startup)
    task = asyncio.create_task(_fastapi_heartbeat_loop(service))
    application.state.worker_heartbeat_service = service
    application.state.worker_heartbeat_task = task
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.to_thread(record_heartbeat_safely, _heartbeat_logger, "stopping", service.record_stopping)
        await asyncio.to_thread(record_heartbeat_safely, _heartbeat_logger, "shutdown", service.record_shutdown)


app = FastAPI(lifespan=_application_lifespan)
app.include_router(content_studio_router)
app.include_router(generation_library_publishing_router)
app.include_router(edit_studio_router)
app.include_router(generation_library_router)
app.include_router(posted_content_router)
app.include_router(photoshoot_router)
app.include_router(reference_library_router)
app.include_router(asset_library_router)
app.include_router(test_chat_router)
app.include_router(business_assets_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(sales_router)
app.include_router(operations_router)


@app.get("/callback")
async def fanvue_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if not code:
        return {
            "success": False,
            "error": "Missing code from Fanvue callback",
        }

    redirect_url = f"http://localhost:8501?code={code}"

    if state:
        redirect_url += f"&state={state}"

    return RedirectResponse(redirect_url)


@app.post("/webhooks/fanvue")
async def fanvue_webhook(request: Request):
    """
    STEP 11.17
    Live Fanvue webhook ingestion.

    Flow:
    raw request body
    -> signature verification
    -> JSON parse
    -> normalize event
    -> deduplicate
    -> persist event
    -> process event immediately
    -> return success
    """

    try:
        raw_body = await request.body()

    except Exception as e:
        print("\n[WEBHOOK ERROR] Could not read raw request body")
        print(str(e))

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "raw_body_read_failed",
            },
        )

    signature_service = WebhookSignatureService()

    signature_header = request.headers.get(
        WebhookSignatureService.SIGNATURE_HEADER
    )

    signature_valid = signature_service.verify_signature(
        raw_body=raw_body,
        signature_header=signature_header,
    )

    if not signature_valid:
        print("\n[WEBHOOK SECURITY] Invalid Fanvue webhook signature")

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_signature",
            },
        )

    try:
        payload = json.loads(raw_body)

    except Exception as e:
        print("\n[WEBHOOK ERROR] Invalid JSON payload")
        print(str(e))

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "invalid_json",
            },
        )

    try:
        normalizer = WebhookNormalizerService()
        normalized_event = normalizer.normalize(
            payload=payload,
            headers=dict(request.headers),
        )

    except Exception as e:
        print("\n[WEBHOOK ERROR] Normalization failed")
        print(str(e))

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "normalization_failed",
                "details": str(e),
            },
        )

    internal_event_id = normalized_event["internal_event_id"]
    external_event_id = normalized_event["external_event_id"]

    existing_event = get_webhook_event_by_external_id(
        external_event_id
    )

    if existing_event:
        print("\n[WEBHOOK DEDUPLICATION]")
        print(f"duplicate external_event_id={external_event_id}")

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "duplicate": True,
                "external_event_id": external_event_id,
            },
        )

    try:
        webhook_event_db_id = create_webhook_event(
            normalized_event
        )

    except Exception as e:
        print("\n[WEBHOOK ERROR] Event persistence failed")
        print(str(e))

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "event_persistence_failed",
                "details": str(e),
                "internal_event_id": internal_event_id,
                "event_type": normalized_event["event_type"],
            },
        )

    processing_result = None
    processing_error = None

    try:
        processor = WebhookEventProcessorService(
            worker_instance_id=request.app.state.worker_heartbeat_service.worker_instance_id
        )
       
        processing_result = processor.process_pending_events()

    except Exception as e:
        processing_error = str(e)

        print("\n[WEBHOOK ERROR] Immediate event processing failed")
        print(processing_error)

    print("\n==================================================")
    print(" FANVUE WEBHOOK RECEIVED ")
    print("==================================================")

    print(f"webhook_event_db_id={webhook_event_db_id}")
    print(f"internal_event_id={internal_event_id}")
    print(f"received_at={datetime.now(timezone.utc).isoformat()}")

    print("\nSIGNATURE:")
    print("valid=True")

    print("\nHEADERS:")
    for key, value in request.headers.items():
        print(f"{key}: {value}")

    print("\nRAW PAYLOAD:")
    print(json.dumps(payload, indent=2))

    print("\nNORMALIZED EVENT:")
    print(json.dumps(normalized_event, indent=2, default=str))

    print("\nPROCESSING RESULT:")
    print(json.dumps(processing_result, indent=2, default=str))

    if processing_error:
        print("\nPROCESSING ERROR:")
        print(processing_error)

    print("==================================================\n")

    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "received": True,
            "signature_valid": True,
            "persisted": True,
            "processed_immediately": processing_error is None,
            "processing_error": processing_error,
            "processing_result": processing_result,
            "webhook_event_db_id": webhook_event_db_id,
            "internal_event_id": internal_event_id,
            "event_type": normalized_event["event_type"],
            "external_event_id": normalized_event["external_event_id"],
        },
    )
