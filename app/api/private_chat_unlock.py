"""Public one-click redirect for durable private Telegram commerce offers."""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, RedirectResponse

from app.services.private_chat_unlock_gateway_service import (
    PrivateChatUnlockGatewayService,
    UnlockUnavailableError,
)


router = APIRouter(prefix="/api/v1/commerce", tags=["commerce"])
public_alias_router = APIRouter(tags=["commerce"])
logger = logging.getLogger("private-chat-unlock")
_NO_STORE_HEADERS = {"Cache-Control": "no-store"}
_CUSTOMER_ERROR = {
    "detail": "This Unlock link is unavailable. Please return to Telegram and try again."
}


@router.get("/unlock/{opaque_token}", include_in_schema=False)
def unlock_private_chat_offer(opaque_token: str):
    return _unlock_response(
        lambda: PrivateChatUnlockGatewayService().resolve(opaque_token)
    )


@public_alias_router.get("/u/{public_alias}", include_in_schema=False)
def unlock_private_chat_offer_alias(public_alias: str):
    return _unlock_response(
        lambda: PrivateChatUnlockGatewayService().resolve_alias(public_alias)
    )


def _unlock_response(resolve_destination):
    try:
        destination = resolve_destination()
    except UnlockUnavailableError as error:
        logger.warning(
            "event=unlock_unavailable reason=%s",
            str(error),
        )
        return JSONResponse(
            status_code=409,
            content=_CUSTOMER_ERROR,
            headers=_NO_STORE_HEADERS,
        )
    except Exception as error:
        logger.error(
            "event=unlock_unexpected_failure error_type=%s",
            type(error).__name__,
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content=_CUSTOMER_ERROR,
            headers=_NO_STORE_HEADERS,
        )
    return RedirectResponse(
        destination,
        status_code=302,
        headers=_NO_STORE_HEADERS,
    )
