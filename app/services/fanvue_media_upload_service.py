from pathlib import Path
import os
import requests
import uuid
from urllib.parse import quote

from app.services.fanvue_oauth_service import FanvueOAuthService
from app.services.runtime_media_resolver import RuntimeMediaResolver


class FanvueMediaUploadService:
    def __init__(
        self,
        fanvue_account_id: int | None = None,
        runtime_media_resolver: RuntimeMediaResolver | None = None,
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

    def _headers(self):
        access_token = self.oauth.get_valid_access_token()

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

    def attach_media_to_vault_folder(self, media_uuid: str, folder_name: str) -> dict:
        if not media_uuid:
            return {
                "success": False,
                "folder_name": folder_name,
                "error": "Missing media_uuid",
                "raw": None,
            }

        if not folder_name:
            return {
                "success": False,
                "folder_name": folder_name,
                "error": "Missing folder_name",
                "raw": None,
            }

        encoded_folder_name = quote(folder_name, safe="")

        headers = self._headers()
        headers["X-Fanvue-API-Version"] = "2025-06-26"

        payload = {
            "mediaUuids": [media_uuid],
        }

        response = requests.post(
            f"{self.base_url}/vault/folders/{encoded_folder_name}/media",
            headers=headers,
            json=payload,
            timeout=30,
        )

        print(
            f"[FANVUE FOLDER ATTACH] folder={folder_name} "
            f"media_uuid={media_uuid} status={response.status_code}"
        )

        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}

        if response.status_code >= 400:
            return {
                "success": False,
                "folder_name": folder_name,
                "error": body,
                "raw": body,
            }

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

        file_path = self._resolve_upload_file_path(item)

        if not file_path:
            return {
                "success": False,
                "media_uuid": None,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": f"File not found: {item.get('file_path')}",
            }

        ext = file_path.suffix.lower()

        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            media_type = "image"
        elif ext in [".mp4", ".mov", ".webm"]:
            media_type = "video"
        else:
            return {
                "success": False,
                "media_uuid": None,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": f"Unsupported media type: {ext}",
            }

        print(f"\n[FANVUE UPLOAD START] content_id={item.get('id')} file={file_path.name}")

        # 1. Create upload session
        session_payload = {
            "name": file_path.name,
            "filename": file_path.name,
            "mediaType": media_type,
        }

        session_response = requests.post(
            f"{self.base_url}/media/uploads",
            headers=self._headers(),
            json=session_payload,
            timeout=30,
        )

        print(f"[FANVUE UPLOAD SESSION] status={session_response.status_code}")

        try:
            session_body = session_response.json()
        except Exception:
            session_body = {"raw": session_response.text}

        if session_response.status_code >= 400:
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

        if not media_uuid or not upload_id:
            return {
                "success": False,
                "media_uuid": None,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": f"Missing mediaUuid/uploadId in response: {session_body}",
            }

        # 2. Get signed URL for part 1
        signed_url_response = requests.get(
            f"{self.base_url}/media/uploads/{upload_id}/parts/1/url",
            headers=self._headers(),
            timeout=30,
        )

        print(f"[FANVUE SIGNED URL] status={signed_url_response.status_code}")

        if signed_url_response.status_code >= 400:
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

        print(f"[SIGNED URL] {signed_url}")

        # 3. Upload file bytes to signed URL
        with open(file_path, "rb") as f:
            put_response = requests.put(
                signed_url,
                data=f,
                timeout=120,
            )

        print(f"[FANVUE FILE PUT] status={put_response.status_code}")

        if put_response.status_code >= 400:
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

        complete_response = requests.patch(
            f"{self.base_url}/media/uploads/{upload_id}",
            headers=self._headers(),
            json=complete_payload,
            timeout=30,
        )

        print(f"[FANVUE UPLOAD COMPLETE] status={complete_response.status_code}")

        try:
            complete_body = complete_response.json()
        except Exception:
            complete_body = {"raw": complete_response.text}

        if complete_response.status_code >= 400:
            return {
                "success": False,
                "media_uuid": media_uuid,
                "preview_uuid": None,
                "full_uuid": None,
                "status": None,
                "error": complete_body,
            }

        upload_status = complete_body.get("status", "processing")

        folder_name = (
            item.get("folder_name")
            or self._folder_name_for_classification(item.get("classification"))
        )

        folder_result = None

        if folder_name:
            folder_result = self.attach_media_to_vault_folder(
                media_uuid=media_uuid,
                folder_name=folder_name,
            )

            if not folder_result.get("success"):
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

        print(
            "[FANVUE UPLOAD SUCCESS] "
            f"content_id={item.get('id')} media_uuid={media_uuid} "
            f"status={upload_status} folder={folder_name}"
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
