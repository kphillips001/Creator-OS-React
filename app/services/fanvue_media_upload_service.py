from pathlib import Path
import mimetypes
import os
import requests
import time
import uuid
from urllib.parse import quote

from app.services.fanvue_oauth_service import FanvueOAuthService
from app.services.fanvue_upload_trace import (
    fanvue_response_payload,
    fanvue_upload_exception,
    fanvue_upload_trace,
)
from app.services.runtime_media_resolver import RuntimeMediaResolver


def _trace_payload(trace_context: dict | None = None, **payload):
    merged = dict(trace_context or {})
    for key, value in payload.items():
        if key not in merged:
            merged[key] = value
        elif merged.get(key) != value:
            merged[f"explicit_{key}"] = value
    return merged


class FanvueMediaUploadService:
    def __init__(
        self,
        fanvue_account_id: int | None = None,
        runtime_media_resolver: RuntimeMediaResolver | None = None,
        processing_poll_interval_seconds: float = 2.0,
        processing_timeout_seconds: float = 60.0,
    ):

        self.base_url = "https://api.fanvue.com"

        self.fanvue_account_id = (
            fanvue_account_id
        )

        self.oauth = FanvueOAuthService(
            fanvue_account_id=fanvue_account_id,
        )
        self.runtime_media_resolver = (
            runtime_media_resolver or RuntimeMediaResolver()
        )
        self.processing_poll_interval_seconds = processing_poll_interval_seconds
        self.processing_timeout_seconds = processing_timeout_seconds

    def _headers(self):
        try:
            access_token = self.oauth.get_valid_access_token()
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.authentication_exception",
                exc,
                fanvue_account_id=self.fanvue_account_id,
                stage="authentication",
            )
            raise

        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    def _web_headers(self):
        web_cookie = os.getenv("FANVUE_WEB_COOKIE")

        if not web_cookie:
            print("[PPV ERROR] Missing FANVUE_WEB_COOKIE in .env")
            return None

        return {
            "Content-Type": "application/json",
            "Cookie": web_cookie,
            "Origin": "https://www.fanvue.com",
            "Referer": "https://www.fanvue.com/messages",
            "User-Agent": "Mozilla/5.0",
        }
    
    def _folder_name_for_classification(self, classification: str) -> str | None:
        classification = (classification or "").upper()

        folder_map = {
            "TEASER_IMAGE": "Teasers",
            "TEASER_VIDEO": "Teasers",

            "VIP_IMAGE": "VIP",
            "VIP_VIDEO": "VIP",

            "PREMIUM_IMAGE": "Premium",
            "PREMIUM_VIDEO": "Premium",

            "WALL_IMAGE": "Wall",
            "WALL_VIDEO": "Wall",
        }

        return folder_map.get(classification)

    def _resolve_upload_file_path(self, item: dict) -> Path | None:
        return self.runtime_media_resolver.resolve_original_path(
            item,
            require_exists=True,
        )

    def _wait_for_media_ready(
        self,
        media_uuid: str,
        *,
        trace_context: dict | None = None,
    ) -> dict:
        trace_context = dict(trace_context or {})
        start = time.monotonic()
        endpoint = f"{self.base_url}/media/{media_uuid}"
        final_status = None
        final_body = None

        while True:
            elapsed = time.monotonic() - start
            fanvue_upload_trace(
                "fanvue_media_upload.processing_poll_request",
                **_trace_payload(
                    trace_context,
                    endpoint=endpoint,
                    media_uuid=media_uuid,
                    elapsed_seconds=round(elapsed, 3),
                ),
            )
            try:
                response = requests.get(
                    endpoint,
                    headers=self._headers(),
                    timeout=30,
                )
            except Exception as exc:
                fanvue_upload_exception(
                    "fanvue_media_upload.processing_poll_request_exception",
                    exc,
                    **_trace_payload(
                        trace_context,
                        endpoint=endpoint,
                        method="GET",
                        media_uuid=media_uuid,
                        elapsed_seconds=round(elapsed, 3),
                        stage="media_status_http_request",
                    ),
                )
                raise
            try:
                body = response.json()
            except Exception as exc:
                fanvue_upload_exception(
                    "fanvue_media_upload.processing_poll_response_parse_exception",
                    exc,
                    **_trace_payload(
                        trace_context,
                        endpoint=endpoint,
                        method="GET",
                        media_uuid=media_uuid,
                        response=fanvue_response_payload(response),
                        stage="http_response_parsing",
                    ),
                )
                body = {"raw": response.text}

            status = str(body.get("status") or "").strip().lower() if isinstance(body, dict) else ""
            final_status = status or None
            final_body = body
            fanvue_upload_trace(
                "fanvue_media_upload.processing_poll_response",
                **_trace_payload(
                    trace_context,
                    status_code=response.status_code,
                    media_uuid=media_uuid,
                    status=final_status,
                    elapsed_seconds=round(elapsed, 3),
                    response=body,
                    http_response=fanvue_response_payload(response),
                ),
            )

            if response.status_code >= 400:
                return {
                    "success": False,
                    "reason": "media_status_lookup_failed",
                    "status_code": response.status_code,
                    "status": final_status,
                    "elapsed_seconds": elapsed,
                    "raw": body,
                }

            if status == "ready":
                fanvue_upload_trace(
                    "fanvue_media_upload.processing_ready",
                    **_trace_payload(
                        trace_context,
                        media_uuid=media_uuid,
                        status=status,
                        elapsed_seconds=round(elapsed, 3),
                    ),
                )
                return {
                    "success": True,
                    "status": status,
                    "elapsed_seconds": elapsed,
                    "raw": body,
                }

            if elapsed >= self.processing_timeout_seconds:
                fanvue_upload_trace(
                    "fanvue_media_upload.processing_timeout",
                    **_trace_payload(
                        trace_context,
                        media_uuid=media_uuid,
                        status=final_status,
                        elapsed_seconds=round(elapsed, 3),
                        timeout_seconds=self.processing_timeout_seconds,
                        response=final_body,
                    ),
                )
                return {
                    "success": False,
                    "reason": "media_processing_timeout",
                    "status": final_status,
                    "elapsed_seconds": elapsed,
                    "timeout_seconds": self.processing_timeout_seconds,
                    "raw": final_body,
                }

            time.sleep(self.processing_poll_interval_seconds)

    def attach_media_to_vault_folder(
        self,
        media_uuid: str,
        folder_name: str,
        *,
        trace_context: dict | None = None,
    ) -> dict:
        trace_context = dict(trace_context or {})
        fanvue_upload_trace(
            "fanvue_media_upload.folder_attach_enter",
            **_trace_payload(
                trace_context,
                media_uuid=media_uuid,
                folder_name=folder_name,
                stage="folder_attach",
            ),
        )
        if not media_uuid:
            fanvue_upload_trace(
                "fanvue_media_upload.folder_attach_missing_media_uuid",
                **_trace_payload(
                    trace_context,
                    folder_name=folder_name,
                    media_uuid=media_uuid,
                    stage="folder_attach_guard",
                ),
            )
            return {
                "success": False,
                "folder_name": folder_name,
                "error": "Missing media_uuid",
                "raw": None,
            }

        if not folder_name:
            fanvue_upload_trace(
                "fanvue_media_upload.folder_attach_missing_folder",
                **_trace_payload(
                    trace_context,
                    media_uuid=media_uuid,
                    folder_name=folder_name,
                    stage="folder_attach_guard",
                ),
            )
            return {
                "success": False,
                "folder_name": folder_name,
                "error": "Missing folder_name",
                "raw": None,
            }

        encoded_folder_name = quote(folder_name, safe="")

        headers = self._headers()
        headers["X-Fanvue-API-Version"] = "2025-06-26"
        fanvue_upload_trace(
            "fanvue_media_upload.folder_attach_headers_ready",
            **_trace_payload(
                trace_context,
                media_uuid=media_uuid,
                folder_name=folder_name,
                stage="folder_attach_authentication",
            ),
        )

        payload = {
            "mediaUuids": [media_uuid],
        }
        endpoint = f"{self.base_url}/vault/folders/{encoded_folder_name}/media"
        fanvue_upload_trace(
            "fanvue_media_upload.folder_attach_request",
            **_trace_payload(
                trace_context,
                endpoint=endpoint,
                method="POST",
                folder_name=folder_name,
                media_uuid=media_uuid,
                payload=payload,
                stage="vault_folder_attachment_http_request",
            ),
        )

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=30,
            )
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.folder_attach_request_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    endpoint=endpoint,
                    method="POST",
                    folder_name=folder_name,
                    media_uuid=media_uuid,
                    payload=payload,
                    stage="vault_folder_attachment_http_request",
                ),
            )
            raise

        print(
            f"[FANVUE FOLDER ATTACH] folder={folder_name} "
            f"media_uuid={media_uuid} status={response.status_code}"
        )

        try:
            body = response.json()
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.folder_attach_response_parse_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    endpoint=endpoint,
                    method="POST",
                    folder_name=folder_name,
                    media_uuid=media_uuid,
                    response=fanvue_response_payload(response),
                    stage="http_response_parsing",
                ),
            )
            body = {"raw": response.text}

        if response.status_code >= 400:
            fanvue_upload_trace(
                "fanvue_media_upload.folder_attach_failed",
                **_trace_payload(
                    trace_context,
                    status_code=response.status_code,
                    folder_name=folder_name,
                    media_uuid=media_uuid,
                    response=body,
                    http_response=fanvue_response_payload(response),
                ),
            )
            return {
                "success": False,
                "folder_name": folder_name,
                "error": body,
                "raw": body,
            }

        fanvue_upload_trace(
            "fanvue_media_upload.folder_attach_success",
            **_trace_payload(
                trace_context,
                status_code=response.status_code,
                folder_name=folder_name,
                media_uuid=media_uuid,
                response=body,
                http_response=fanvue_response_payload(response),
            ),
        )
        return {
            "success": True,
            "folder_name": folder_name,
            "error": None,
            "raw": body,
        }
    
    
    def upload_media_item(self, item: dict) -> dict:
        """
        Upload one local media file to Fanvue media/vault.

        Expected item:
        {
            "id": 123,
            "file_path": "data/uploads/example.png",
            "classification": "TEASE"
        }

        Returns:
        {
            "success": True/False,
            "media_uuid": "...",
            "preview_uuid": "...",
            "full_uuid": "...",
            "status": "...",
            "error": None
        }
        """

        trace_context = dict(item.get("_fanvue_trace") or {})
        fanvue_upload_trace(
            "fanvue_media_upload.asset_lookup_start",
            **_trace_payload(
                trace_context,
                item_id=item.get("id"),
                file_path=item.get("file_path"),
                classification=item.get("classification"),
                folder_name=item.get("folder_name"),
                stage="asset_lookup",
            ),
        )
        try:
            file_path = self._resolve_upload_file_path(item)
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.asset_lookup_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    item_id=item.get("id"),
                    file_path=item.get("file_path"),
                    stage="asset_lookup",
                ),
            )
            raise

        if not file_path:
            fanvue_upload_trace(
                "fanvue_media_upload.local_file_missing",
                **_trace_payload(
                    trace_context,
                    item_id=item.get("id"),
                    file_path=item.get("file_path"),
                ),
            )
            return {
                "success": False,
                "media_uuid": None,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": f"File not found: {item.get('file_path')}",
            }

        ext = file_path.suffix.lower()
        mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        fanvue_upload_trace(
            "fanvue_media_upload.image_loading_start",
            **_trace_payload(
                trace_context,
                item_id=item.get("id"),
                filename=file_path.name,
                absolute_path=str(file_path.resolve()),
                file_exists=file_path.exists(),
                file_size=file_path.stat().st_size if file_path.exists() else None,
                mime_type=mime_type,
                stage="image_loading",
            ),
        )

        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            media_type = "image"
        elif ext in [".mp4", ".mov", ".webm"]:
            media_type = "video"
        else:
            fanvue_upload_trace(
                "fanvue_media_upload.unsupported_media_type",
                **_trace_payload(
                    trace_context,
                    item_id=item.get("id"),
                    file_path=str(file_path.resolve()),
                    extension=ext,
                    mime_type=mime_type,
                ),
            )
            return {
                "success": False,
                "media_uuid": None,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": f"Unsupported media type: {ext}",
            }

        fanvue_upload_trace(
            "fanvue_media_upload.image_preprocessing",
            **_trace_payload(
                trace_context,
                item_id=item.get("id"),
                filename=file_path.name,
                mime_type=mime_type,
                media_type=media_type,
                preprocessing="none",
                stage="image_preprocessing",
            ),
        )

        print(f"\n[FANVUE UPLOAD START] content_id={item.get('id')} file={file_path.name}")

        # 1. Create upload session
        session_payload = {
            "name": file_path.name,
            "filename": file_path.name,
            "mediaType": media_type,
        }
        session_endpoint = f"{self.base_url}/media/uploads"
        fanvue_upload_trace(
            "fanvue_media_upload.multipart_construction",
            **_trace_payload(
                trace_context,
                endpoint=session_endpoint,
                method="POST",
                filename=file_path.name,
                mime_type=mime_type,
                media_type=media_type,
                payload=session_payload,
                multipart_form_data=False,
                upload_strategy="Fanvue upload session JSON plus signed URL PUT",
                stage="multipart_form_data_construction",
            ),
        )
        fanvue_upload_trace(
            "fanvue_media_upload.upload_session_request",
            **_trace_payload(
                trace_context,
                endpoint=session_endpoint,
                method="POST",
                filename=file_path.name,
                absolute_path=str(file_path.resolve()),
                file_size=file_path.stat().st_size,
                mime_type=mime_type,
                media_type=media_type,
                payload=session_payload,
                stage="http_request",
            ),
        )

        try:
            session_response = requests.post(
                session_endpoint,
                headers=self._headers(),
                json=session_payload,
                timeout=30,
            )
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.upload_session_request_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    endpoint=session_endpoint,
                    method="POST",
                    filename=file_path.name,
                    absolute_path=str(file_path.resolve()),
                    file_size=file_path.stat().st_size,
                    mime_type=mime_type,
                    payload=session_payload,
                    stage="http_request",
                ),
            )
            raise

        print(f"[FANVUE UPLOAD SESSION] status={session_response.status_code}")

        try:
            session_body = session_response.json()
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.upload_session_response_parse_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    endpoint=session_endpoint,
                    method="POST",
                    response=fanvue_response_payload(session_response),
                    stage="http_response_parsing",
                ),
            )
            session_body = {"raw": session_response.text}

        if session_response.status_code >= 400:
            fanvue_upload_trace(
                "fanvue_media_upload.upload_session_failed",
                **_trace_payload(
                    trace_context,
                    status_code=session_response.status_code,
                    response=session_body,
                    http_response=fanvue_response_payload(session_response),
                ),
            )
            return {
                "success": False,
                "media_uuid": None,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": session_body,
            }

        media_uuid = session_body.get("mediaUuid")
        upload_id = session_body.get("uploadId")
        fanvue_upload_trace(
            "fanvue_media_upload.upload_session_response",
            **_trace_payload(
                trace_context,
                status_code=session_response.status_code,
                media_uuid=media_uuid,
                upload_id=upload_id,
                response=session_body,
                http_response=fanvue_response_payload(session_response),
            ),
        )

        if not media_uuid or not upload_id:
            fanvue_upload_trace(
                "fanvue_media_upload.upload_session_missing_ids",
                **_trace_payload(
                    trace_context,
                    response=session_body,
                ),
            )
            return {
                "success": False,
                "media_uuid": None,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": f"Missing mediaUuid/uploadId in response: {session_body}",
            }

        # 2. Get signed URL for part 1
        signed_url_endpoint = f"{self.base_url}/media/uploads/{upload_id}/parts/1/url"
        fanvue_upload_trace(
            "fanvue_media_upload.signed_url_request",
            **_trace_payload(
                trace_context,
                endpoint=signed_url_endpoint,
                method="GET",
                upload_id=upload_id,
                media_uuid=media_uuid,
                stage="http_request",
            ),
        )
        try:
            signed_url_response = requests.get(
                signed_url_endpoint,
                headers=self._headers(),
                timeout=30,
            )
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.signed_url_request_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    endpoint=signed_url_endpoint,
                    method="GET",
                    upload_id=upload_id,
                    media_uuid=media_uuid,
                    stage="http_request",
                ),
            )
            raise
        fanvue_upload_trace(
            "fanvue_media_upload.signed_url_response",
            **_trace_payload(
                trace_context,
                status_code=signed_url_response.status_code,
                upload_id=upload_id,
                media_uuid=media_uuid,
                http_response=fanvue_response_payload(signed_url_response, include_body=False),
            ),
        )

        print(f"[FANVUE SIGNED URL] status={signed_url_response.status_code}")

        if signed_url_response.status_code >= 400:
            fanvue_upload_trace(
                "fanvue_media_upload.signed_url_failed",
                **_trace_payload(
                    trace_context,
                    endpoint=signed_url_endpoint,
                    method="GET",
                    status_code=signed_url_response.status_code,
                    upload_id=upload_id,
                    media_uuid=media_uuid,
                    response=fanvue_response_payload(signed_url_response),
                ),
            )
            return {
                "success": False,
                "media_uuid": media_uuid,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": signed_url_response.text,
            }

        # Fanvue returns the signed upload URL as plain text
        signed_url = signed_url_response.text.strip()

        print("[SIGNED URL] <redacted signed upload URL>")

        # 3. Upload file bytes to signed URL
        try:
            with open(file_path, "rb") as f:
                put_response = requests.put(
                    signed_url,
                    data=f,
                    timeout=120,
                )
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.file_put_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    endpoint="<redacted signed upload URL>",
                    method="PUT",
                    filename=file_path.name,
                    absolute_path=str(file_path.resolve()),
                    file_size=file_path.stat().st_size,
                    mime_type=mime_type,
                    upload_id=upload_id,
                    media_uuid=media_uuid,
                    stage="image_loading_or_signed_upload_put",
                ),
            )
            raise
        fanvue_upload_trace(
            "fanvue_media_upload.file_put_response",
            **_trace_payload(
                trace_context,
                status_code=put_response.status_code,
                upload_id=upload_id,
                media_uuid=media_uuid,
                etag=put_response.headers.get("ETag"),
                endpoint="<redacted signed upload URL>",
                method="PUT",
                mime_type=mime_type,
                http_response=fanvue_response_payload(put_response),
            ),
        )

        print(f"[FANVUE FILE PUT] status={put_response.status_code}")

        if put_response.status_code >= 400:
            fanvue_upload_trace(
                "fanvue_media_upload.file_put_failed",
                **_trace_payload(
                    trace_context,
                    status_code=put_response.status_code,
                    upload_id=upload_id,
                    media_uuid=media_uuid,
                    endpoint="<redacted signed upload URL>",
                    method="PUT",
                    mime_type=mime_type,
                    response=fanvue_response_payload(put_response),
                ),
            )
            return {
                "success": False,
                "media_uuid": media_uuid,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": put_response.text,
            }

        etag = put_response.headers.get("ETag")

        # 4. Complete upload session
        complete_payload = {
            "parts": [
                {
                    "PartNumber": 1,
                    **({"ETag": etag} if etag else {}),
                }
            ]
        }

        complete_endpoint = f"{self.base_url}/media/uploads/{upload_id}"
        fanvue_upload_trace(
            "fanvue_media_upload.complete_request",
            **_trace_payload(
                trace_context,
                endpoint=complete_endpoint,
                method="PATCH",
                upload_id=upload_id,
                media_uuid=media_uuid,
                payload=complete_payload,
                stage="upload_completion",
            ),
        )
        try:
            complete_response = requests.patch(
                complete_endpoint,
                headers=self._headers(),
                json=complete_payload,
                timeout=30,
            )
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.complete_request_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    endpoint=complete_endpoint,
                    method="PATCH",
                    upload_id=upload_id,
                    media_uuid=media_uuid,
                    payload=complete_payload,
                    stage="upload_completion",
                ),
            )
            raise

        print(f"[FANVUE UPLOAD COMPLETE] status={complete_response.status_code}")

        try:
            complete_body = complete_response.json()
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_media_upload.complete_response_parse_exception",
                exc,
                **_trace_payload(
                    trace_context,
                    endpoint=complete_endpoint,
                    method="PATCH",
                    upload_id=upload_id,
                    media_uuid=media_uuid,
                    response=fanvue_response_payload(complete_response),
                    stage="http_response_parsing",
                ),
            )
            complete_body = {"raw": complete_response.text}

        if complete_response.status_code >= 400:
            fanvue_upload_trace(
                "fanvue_media_upload.complete_failed",
                **_trace_payload(
                    trace_context,
                    status_code=complete_response.status_code,
                    media_uuid=media_uuid,
                    upload_id=upload_id,
                    response=complete_body,
                    http_response=fanvue_response_payload(complete_response),
                ),
            )
            return {
                "success": False,
                "media_uuid": media_uuid,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": complete_body,
            }

        upload_status = complete_body.get("status", "processing")
        fanvue_upload_trace(
            "fanvue_media_upload.complete_response",
            **_trace_payload(
                trace_context,
                status_code=complete_response.status_code,
                media_uuid=media_uuid,
                upload_id=upload_id,
                upload_status=upload_status,
                response=complete_body,
                http_response=fanvue_response_payload(complete_response),
            ),
        )

        ready_result = {
            "success": str(upload_status or "").strip().lower() == "ready",
            "status": str(upload_status or "").strip().lower(),
            "raw": complete_body,
            "elapsed_seconds": 0,
        }
        if not ready_result["success"]:
            ready_result = self._wait_for_media_ready(
                media_uuid,
                trace_context=trace_context,
            )
            upload_status = ready_result.get("status") or upload_status
        if not ready_result.get("success"):
            fanvue_upload_trace(
                "fanvue_media_upload.branch_return_processing_not_ready",
                **_trace_payload(
                    trace_context,
                    media_uuid=media_uuid,
                    upload_status=upload_status,
                    ready_result=ready_result,
                    stage="post_processing",
                ),
            )
            return {
                "success": False,
                "media_uuid": media_uuid,
                "preview_uuid": media_uuid,
                "full_uuid": media_uuid,
                "status": upload_status,
                "folder_name": None,
                "folder_success": False,
                "error": {
                    "message": "Fanvue accepted the upload but did not finish processing the media.",
                    "processing_result": ready_result,
                },
                "raw": complete_body,
                "processing_raw": ready_result.get("raw"),
            }

        fanvue_upload_trace(
            "fanvue_media_upload.enter_post_processing",
            **_trace_payload(
                trace_context,
                media_uuid=media_uuid,
                upload_status=upload_status,
                ready_result=ready_result,
                item_folder_name=item.get("folder_name"),
                classification=item.get("classification"),
                classification_folder_name=self._folder_name_for_classification(
                    item.get("classification")
                ),
                stage="post_processing",
            ),
        )
        folder_name = (
            item.get("folder_name")
            or self._folder_name_for_classification(item.get("classification"))
        )

        folder_result = None

        if folder_name:
            fanvue_upload_trace(
                "fanvue_media_upload.branch_attach_enabled",
                **_trace_payload(
                    trace_context,
                    media_uuid=media_uuid,
                    upload_status=upload_status,
                    folder_name=folder_name,
                    item_folder_name=item.get("folder_name"),
                    classification=item.get("classification"),
                    stage="post_processing",
                ),
            )
            try:
                folder_result = self.attach_media_to_vault_folder(
                    media_uuid=media_uuid,
                    folder_name=folder_name,
                    trace_context=trace_context,
                )
            except Exception as exc:
                fanvue_upload_exception(
                    "fanvue_media_upload.branch_exception",
                    exc,
                    **_trace_payload(
                        trace_context,
                        media_uuid=media_uuid,
                        upload_status=upload_status,
                        folder_name=folder_name,
                        stage="post_processing_attach",
                    ),
                )
                raise
            fanvue_upload_trace(
                "fanvue_media_upload.branch_attach_result",
                **_trace_payload(
                    trace_context,
                    media_uuid=media_uuid,
                    upload_status=upload_status,
                    folder_name=folder_name,
                    folder_result=folder_result,
                    stage="post_processing",
                ),
            )

            if not folder_result.get("success"):
                fanvue_upload_trace(
                    "fanvue_media_upload.branch_return_attach_failed",
                    **_trace_payload(
                        trace_context,
                        media_uuid=media_uuid,
                        upload_status=upload_status,
                        folder_name=folder_name,
                        folder_result=folder_result,
                        stage="post_processing",
                    ),
                )
                return {
                    "success": False,
                    "media_uuid": media_uuid,
                    "preview_uuid": media_uuid,
                    "full_uuid": media_uuid,
                    "status": upload_status,
                    "folder_name": folder_name,
                    "folder_success": False,
                    "error": {
                        "message": "Media uploaded but failed to attach to Fanvue vault folder",
                        "folder_error": folder_result.get("error"),
                    },
                    "raw": complete_body,
                    "folder_raw": folder_result.get("raw"),
                }
        else:
            fanvue_upload_trace(
                "fanvue_media_upload.branch_skip_attach",
                **_trace_payload(
                    trace_context,
                    media_uuid=media_uuid,
                    upload_status=upload_status,
                    folder_name=folder_name,
                    item_folder_name=item.get("folder_name"),
                    classification=item.get("classification"),
                    classification_folder_name=self._folder_name_for_classification(
                        item.get("classification")
                    ),
                    stage="post_processing",
                ),
            )

        print(
            "[FANVUE UPLOAD SUCCESS] "
            f"content_id={item.get('id')} media_uuid={media_uuid} "
            f"status={upload_status} folder={folder_name}"
        )
        fanvue_upload_trace(
            "fanvue_media_upload.success",
            **_trace_payload(
                trace_context,
                item_id=item.get("id"),
                media_uuid=media_uuid,
                status=upload_status,
                folder_name=folder_name,
                folder_success=bool(folder_result.get("success")) if folder_result else False,
            ),
        )
        fanvue_upload_trace(
            "fanvue_media_upload.branch_return_success",
            **_trace_payload(
                trace_context,
                item_id=item.get("id"),
                media_uuid=media_uuid,
                upload_status=upload_status,
                folder_name=folder_name,
                folder_success=bool(folder_result.get("success")) if folder_result else False,
                stage="post_processing",
            ),
        )

        return {
            "success": True,
            "media_uuid": media_uuid,
            "preview_uuid": media_uuid,
            "full_uuid": media_uuid,
            "status": upload_status,
            "folder_name": folder_name,
            "folder_success": bool(folder_result.get("success")) if folder_result else False,
            "error": None,
            "raw": complete_body,
            "folder_raw": folder_result.get("raw") if folder_result else None,
        }

        return {
            "success": True,
            "media_uuid": media_uuid,
            "preview_uuid": media_uuid,
            "full_uuid": media_uuid,
            "status": upload_status,
            "error": None,
            "raw": complete_body,
        }

    def create_ptv_set(self, item: dict):
        """
        Build payload for Fanvue PTV set (NOT sent yet)
        """

        print("\n[PTV SET] Creating set for item:", item["id"])

        preview_uuid = item["fanvue_media_preview_uuid"]
        full_uuid = item["fanvue_media_full_uuid"]
        classification = (item["classification"] or "").upper()

        is_free = classification == "TEASE"

        payload = {
            "title": item["file_name"],
            "isFree": is_free,
            "previewMediaUuid": preview_uuid,
            "mediaUuids": [preview_uuid] if is_free else [preview_uuid, full_uuid],
        }

        print("[PTV SET] Payload:")
        print(payload)

        return payload

    def send_paid_message(self, item: dict, recipient_uuid: str, price: int, text: str = ""):
        print("\n[PPV] Sending paid message for item:", item["id"])

        headers = self._web_headers()

        if not headers:
            return {
                "success": False,
                "reason": "missing_fanvue_web_cookie",
                "raw": None,
                "message_uuid": None,
                "status": None,
            }

        preview_uuid = item["fanvue_media_preview_uuid"]
        full_uuid = item["fanvue_media_full_uuid"]

        payload = {
            "json": {
                "mediaPreviewUuid": preview_uuid,
                "mediaUuids": [full_uuid],
                "price": price,
                "recipientUuid": recipient_uuid,
                "text": text,
                "textGenerationDiagnostic": None,
                "replyToMessageUuid": None,
                "clonedFromTemplateMessageUuid": None,
                "sendingMessageUuid": str(uuid.uuid4()),
            },
            "meta": {
                "values": {
                    "textGenerationDiagnostic": ["undefined"],
                    "replyToMessageUuid": ["undefined"],
                    "clonedFromTemplateMessageUuid": ["undefined"],
                }
            },
        }

        print("[PPV] PAID Payload:")
        print(payload)

        url = "https://www.fanvue.com/trpc/chat.sendSingleChatMessage"

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )

        print(f"[PPV RESPONSE] status={response.status_code}")

        try:
            body = response.json()
        except Exception:
            body = response.text

        print("[PPV RESPONSE BODY]")
        print(body)

        message_uuid = None
        message_status = None

        try:
            message_data = body["result"]["data"]["json"]
            message_uuid = message_data.get("uuid")
            message_status = message_data.get("status")
        except Exception:
            print("[PPV WARNING] Could not parse response UUID/status")

        return {
            "raw": body,
            "message_uuid": message_uuid,
            "status": message_status,
            "http_status": response.status_code,
        }
