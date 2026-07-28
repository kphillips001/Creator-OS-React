import json
import asyncio
import logging
import os
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
from app.api.available_inventory import router as available_inventory_router
from app.api.commercial_offerings import router as commercial_offerings_router
from app.api.commercial_publications import router as commercial_publications_router
from app.api.commercial_fulfillments import router as commercial_fulfillments_router
from app.api.commerce_sales import router as commerce_sales_router
from app.api.commerce_authoring import router as commerce_authoring_router
from app.api.photoshoot_gallery import router as photoshoot_gallery_router
from app.api.products import router as products_router
from app.api.customers import router as customers_router
from app.api.sales import router as sales_router
from app.api.operations import router as operations_router
from app.api.creator_intelligence import router as creator_intelligence_router
from app.api.creator_personality import router as creator_personality_router
from app.api.social_creative_direction import (
    router as social_creative_direction_router,
)
from app.api.creator_lifestyle import router as creator_lifestyle_router
from app.api.creator_world_model import router as creator_world_model_router
from app.api.ava_coach import router as ava_coach_router
from app.api.fanvue_api_explorer import router as fanvue_api_explorer_router
from app.api.fanvue_webhook_monitor import router as fanvue_webhook_monitor_router
from app.api.customer_commerce import router as customer_commerce_router
from app.api.purchase_intents import router as purchase_intents_router
from app.api.commerce_learning import router as commerce_learning_router
from app.api.recommendation_diagnostics import (
    router as recommendation_diagnostics_router,
)
from app.api.commerce_signals import router as commerce_signals_router
from app.api.customer_sales_brain import router as customer_sales_brain_router
from app.api.commercial_offering_selector import (
    router as commercial_offering_selector_router,
)
from app.api.provider_connections import (
    OAUTH_SESSION_FILE as REACT_OAUTH_SESSION_FILE,
    router as provider_connections_router,
)
from app.api.developer_agent_execution import (
    router as developer_agent_execution_router,
)
from app.services.fanvue_oauth_service import FanvueOAuthService
from app.services.fanvue_webhook_monitor_service import fanvue_webhook_monitor
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService
from app.services.canonical_reference_service import recover_all_active_creator_references
from app.services.developer_agent_execution_service import (
    DeveloperAgentExecutionService,
)


_heartbeat_logger = logging.getLogger("fastapi-worker-heartbeat")


def _begin_webhook_monitor(**kwargs):
    try:
        return fanvue_webhook_monitor.begin(**kwargs)
    except Exception:
        return None


def _complete_webhook_monitor(trace, **kwargs) -> None:
    if trace is None:
        return
    try:
        fanvue_webhook_monitor.complete(trace, **kwargs)
    except Exception:
        return


async def _fastapi_heartbeat_loop(service: WorkerHeartbeatService) -> None:
    while True:
        await asyncio.to_thread(record_heartbeat_safely, _heartbeat_logger, "heartbeat", service.heartbeat)
        await asyncio.sleep(30)


@asynccontextmanager
async def _application_lifespan(application: FastAPI):
    service = WorkerHeartbeatService(worker_name="FastAPI", worker_type="application_runtime", poll_interval_seconds=30)
    await asyncio.to_thread(record_heartbeat_safely, _heartbeat_logger, "startup", service.register_startup)
    await asyncio.to_thread(recover_all_active_creator_references)
    try:
        await asyncio.to_thread(
            DeveloperAgentExecutionService().recover_interrupted
        )
    except Exception:
        _heartbeat_logger.warning(
            "event=developer_agent_recovery_unavailable", exc_info=True
        )
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
app.include_router(available_inventory_router)
app.include_router(commercial_offerings_router)
app.include_router(commercial_publications_router)
app.include_router(commercial_fulfillments_router)
app.include_router(commerce_sales_router)
app.include_router(commerce_authoring_router)
app.include_router(photoshoot_gallery_router)
app.include_router(products_router)
app.include_router(customers_router)
app.include_router(sales_router)
app.include_router(operations_router)
app.include_router(creator_intelligence_router)
app.include_router(creator_personality_router)
app.include_router(social_creative_direction_router)
app.include_router(creator_lifestyle_router)
app.include_router(creator_world_model_router)
app.include_router(ava_coach_router)
app.include_router(fanvue_api_explorer_router)
app.include_router(fanvue_webhook_monitor_router)
app.include_router(customer_commerce_router)
app.include_router(purchase_intents_router)
app.include_router(commerce_learning_router)
app.include_router(recommendation_diagnostics_router)
app.include_router(commerce_signals_router)
app.include_router(customer_sales_brain_router)
app.include_router(commercial_offering_selector_router)
app.include_router(provider_connections_router)
app.include_router(developer_agent_execution_router)


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


def _react_administration_url(result: str) -> str:
    react_base_url = (
        os.getenv("CREATOR_OS_REACT_URL") or "http://localhost:5174"
    ).rstrip("/")
    return f"{react_base_url}/administration/providers?fanvue={result}"


@app.get("/api/v1/administration/providers/fanvue/callback")
async def fanvue_react_callback(request: Request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        return RedirectResponse(_react_administration_url("missing_code"))
    try:
        session = json.loads(REACT_OAUTH_SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RedirectResponse(_react_administration_url("session_error"))
    if (
        session.get("flow") != "react_administration"
        or not state
        or state != session.get("state")
    ):
        return RedirectResponse(_react_administration_url("state_error"))
    result = FanvueOAuthService(
        int(session["fanvue_account_id"]),
        redirect_uri=session["redirect_uri"],
    ).exchange_code_for_tokens(
        code=code,
        code_verifier=session["code_verifier"],
    )
    if not result.get("success"):
        return RedirectResponse(_react_administration_url("token_error"))
    REACT_OAUTH_SESSION_FILE.unlink(missing_ok=True)
    return RedirectResponse(_react_administration_url("connected"))


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

    _heartbeat_logger.info(
        "event=webhook_received path=%s", request.url.path
    )
    try:
        raw_body = await request.body()

    except Exception as e:
        monitor_trace = _begin_webhook_monitor(
            raw_body=b"",
            headers=dict(request.headers),
            request_path=request.url.path,
        )
        _complete_webhook_monitor(
            monitor_trace,
            http_status=400,
            delivery_metadata={"received": True, "bodyRead": False},
            exception=e,
        )
        print("\n[WEBHOOK ERROR] Could not read raw request body")
        print(str(e))

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "raw_body_read_failed",
            },
        )

    monitor_trace = _begin_webhook_monitor(
        raw_body=raw_body,
        headers=dict(request.headers),
        request_path=request.url.path,
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
        _heartbeat_logger.warning(
            "event=signature_rejected path=%s", request.url.path
        )
        _complete_webhook_monitor(
            monitor_trace,
            http_status=401,
            signature_valid=False,
            delivery_metadata={"received": True, "bodyRead": True},
            exception="invalid_signature",
        )
        print("\n[WEBHOOK SECURITY] Invalid Fanvue webhook signature")

        return JSONResponse(
            status_code=401,
            content={
                "success": False,
                "error": "invalid_signature",
            },
        )

    _heartbeat_logger.info(
        "event=signature_accepted path=%s", request.url.path
    )

    try:
        payload = json.loads(raw_body)

    except Exception as e:
        _complete_webhook_monitor(
            monitor_trace,
            http_status=400,
            signature_valid=True,
            delivery_metadata={
                "received": True,
                "bodyRead": True,
                "jsonParsed": False,
            },
            exception=e,
        )

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
        _complete_webhook_monitor(
            monitor_trace,
            http_status=400,
            signature_valid=True,
            delivery_metadata={
                "received": True,
                "bodyRead": True,
                "jsonParsed": True,
                "normalized": False,
            },
            exception=e,
        )
        print("\n[WEBHOOK ERROR] Normalization failed")
        print(str(e))

        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "normalization_failed",
            },
        )

    internal_event_id = normalized_event["internal_event_id"]
    external_event_id = normalized_event["external_event_id"]

    existing_event = get_webhook_event_by_external_id(
        external_event_id
    )

    if existing_event:
        _complete_webhook_monitor(
            monitor_trace,
            http_status=200,
            signature_valid=True,
            normalization_result=normalized_event,
            persistence_result={
                "persisted": False,
                "duplicate": True,
                "existingEvent": existing_event,
            },
            delivery_metadata={"received": True, "duplicate": True},
        )
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
        if webhook_event_db_id is None:
            _complete_webhook_monitor(
                monitor_trace,
                http_status=200,
                signature_valid=True,
                normalization_result=normalized_event,
                persistence_result={
                    "persisted": False,
                    "duplicate": True,
                },
                delivery_metadata={"received": True, "duplicate": True},
            )
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "duplicate": True,
                    "external_event_id": external_event_id,
                },
            )

    except Exception as e:
        _complete_webhook_monitor(
            monitor_trace,
            http_status=500,
            signature_valid=True,
            normalization_result=normalized_event,
            persistence_result={"persisted": False},
            delivery_metadata={"received": True},
            exception=e,
        )
        print("\n[WEBHOOK ERROR] Event persistence failed")
        print(str(e))

        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "event_persistence_failed",
                "internal_event_id": internal_event_id,
                "event_type": normalized_event["event_type"],
            },
        )

    processing_result = {
        "queued": True,
        "worker": "Commerce Reconciliation",
    }
    processing_error = None
    _heartbeat_logger.info(
        "event=webhook_persisted event_type=%s webhook_event_db_id=%s",
        normalized_event["event_type"], webhook_event_db_id,
    )

    _complete_webhook_monitor(
        monitor_trace,
        http_status=200,
        signature_valid=True,
        normalization_result=normalized_event,
        persistence_result={
            "persisted": True,
            "webhookEventDbId": webhook_event_db_id,
        },
        processing_result=processing_result,
        delivery_metadata={
            "received": True,
            "processedImmediately": processing_error is None,
        },
        exception=processing_error,
    )
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
