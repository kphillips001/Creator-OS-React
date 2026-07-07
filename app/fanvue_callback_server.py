import json
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


app = FastAPI()


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
        processor = WebhookEventProcessorService()
       
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