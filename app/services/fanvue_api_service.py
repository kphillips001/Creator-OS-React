import os
import requests

from dotenv import load_dotenv

from app.services.fanvue_oauth_service import FanvueOAuthService
from app.services.global_automation_safety_service import (
    GlobalAutomationSafetyService,
)
from app.repositories.content_usage_repository import log_content_usage
from app.services.fanvue_upload_trace import (
    fanvue_response_payload,
    fanvue_upload_exception,
    fanvue_upload_trace,
)

load_dotenv()


class FanvueAPIService:
    def __init__(
        self,
        fanvue_account_id: int,
    ):
        if not fanvue_account_id:
            raise ValueError(
                "[FANVUE ACCOUNT REQUIRED] "
                "FanvueAPIService requires fanvue_account_id."
            )

        self.fanvue_account_id = fanvue_account_id

        self.base_url = os.getenv(
            "FANVUE_API_BASE_URL",
            "https://api.fanvue.com",
        )

        self.api_version = os.getenv(
            "FANVUE_API_VERSION",
            "2025-06-26",
        )

        self.oauth = FanvueOAuthService(
            fanvue_account_id=self.fanvue_account_id,
        )

        self.safety_service = GlobalAutomationSafetyService()

    def _headers(self):
        access_token = self.oauth.get_valid_access_token()

        if not access_token:
            raise ValueError("No valid Fanvue OAuth access token found.")

        return {
            "Authorization": f"Bearer {access_token}",
            "X-Fanvue-API-Version": self.api_version,
            "Content-Type": "application/json",
        }

    def test_connection(self):
        print("[FANVUE API TEST START]")

        url = f"{self.base_url}/users/me"

        try:
            response = requests.get(
                url,
                headers=self._headers(),
                timeout=20,
            )

            print(f"[FANVUE API RESPONSE] status={response.status_code}")

            if response.status_code >= 400:
                print("[FANVUE API TEST FAILED]", response.text)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response": response.text,
                }

            data = response.json()
            user_uuid = data.get("uuid")

            print("[FANVUE API TEST SUCCESS]")
            print("\n==============================")
            print("🔥 YOUR FANVUE USER UUID")
            print("==============================")
            print(user_uuid)
            print("==============================\n")

            print("[FULL USER DATA]")
            print(data)

            return {
                "success": True,
                "status_code": response.status_code,
                "response": data,
                "user_uuid": user_uuid,
            }

        except Exception as e:
            print(f"[FANVUE API TEST ERROR] {e}")
            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
            }

    def get_current_user(self):
        print("[FANVUE GET CURRENT USER START]")

        url = f"{self.base_url}/users/me"

        try:
            response = requests.get(
                url,
                headers=self._headers(),
                timeout=20,
            )

            print(f"[FANVUE GET USER RESPONSE] status={response.status_code}")

            if response.status_code >= 400:
                print("[FANVUE GET USER FAILED]", response.text)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response": response.text,
                }

            data = response.json()

            print("[FANVUE GET USER SUCCESS]")
            print(data)

            return {
                "success": True,
                "data": data,
            }

        except Exception as e:
            print(f"[FANVUE GET USER ERROR] {e}")
            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
            }

    def list_chats(
        self,
        page: int = 1,
        size: int = 15,
        sort_by: str = "most_recent_messages",
        filter_value: str | None = None,
        mark_as_read: bool = False,
    ) -> dict:
        print("[FANVUE LIST CHATS START]")
        print(
            f"page={page}, size={size}, "
            f"sort_by={sort_by}, filter={filter_value}"
        )

        url = f"{self.base_url}/chats"

        params = {
            "page": page,
            "size": size,
            "sortBy": sort_by,
        }

        if filter_value:
            params["filter"] = filter_value

        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )

            print(f"[FANVUE LIST CHATS RESPONSE] status={response.status_code}")

            if response.status_code >= 400:
                print("[FANVUE LIST CHATS FAILED]")
                print(response.text)

                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response": response.text,
                    "params": params,
                }

            data = response.json()

            return {
                "success": True,
                "status_code": response.status_code,
                "data": data.get("data", []),
                "pagination": data.get("pagination", {}),
                "raw": data,
            }

        except Exception as e:
            print(f"[FANVUE LIST CHATS ERROR] {e}")

            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
                "params": params,
            }

    def list_messages(
        self,
        user_uuid: str,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        print("[FANVUE LIST MESSAGES START]")
        print(f"user_uuid={user_uuid}, page={page}, size={size}")

        url = f"{self.base_url}/chats/{user_uuid}/messages"

        params = {
            "page": page,
            "size": size,
        }

        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )

            print(
                f"[FANVUE LIST MESSAGES RESPONSE] "
                f"status={response.status_code}"
            )

            if response.status_code >= 400:
                print("[FANVUE LIST MESSAGES FAILED]")
                print(response.text)

                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response": response.text,
                    "params": params,
                }

            data = response.json()

            return {
                "success": True,
                "data": data.get("data", []),
                "pagination": data.get("pagination", {}),
                "raw": data,
            }

        except Exception as e:
            print(f"[FANVUE LIST MESSAGES ERROR] {e}")

            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
            }

    def send_chat_message(
        self,
        user_uuid: str,
        payload: dict,
        fanvue_account_id: int | None = None,
        fanvue_user_id: int | None = None,
    ) -> dict:
        print("[FANVUE SEND MESSAGE START]")
        print(f"user_uuid={user_uuid}")

        fanvue_payload = {
            "text": payload.get("message") or payload.get("text"),
            "mediaUuids": payload.get("media_uuids")
            or payload.get("mediaUuids", []),
            "price": payload.get("price"),
        }

        fanvue_payload = {
            key: value
            for key, value in fanvue_payload.items()
            if value is not None
        }

        safety = self.safety_service.can_send_chat()

        if not safety.get("allowed"):
            print("[FANVUE SEND MESSAGE BLOCKED BY GLOBAL SAFETY]")
            print(safety)

            return {
                "success": False,
                "sent": False,
                "blocked": True,
                "reason": safety.get("reason"),
                "safety": safety,
                "payload": fanvue_payload,
                "user_uuid": user_uuid,
            }

        url = f"{self.base_url}/chats/{user_uuid}/message"

        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json=fanvue_payload,
                timeout=30,
            )

            print(f"[FANVUE SEND MESSAGE RESPONSE] status={response.status_code}")

            if response.status_code >= 400:
                print("[FANVUE SEND MESSAGE FAILED]")
                print(response.text)

                return {
                    "success": False,
                    "sent": False,
                    "blocked": False,
                    "status_code": response.status_code,
                    "response": response.text,
                    "payload": fanvue_payload,
                }

            data = response.json()

            print("[FANVUE SEND MESSAGE SUCCESS]")
            print(data)

            message_uuid = data.get("messageUuid")

            content_item_id = payload.get("content_item_id")
            content_tag = payload.get("content_tag")

            if not content_item_id:
                content_item_id = None

            if (
                fanvue_account_id
                and fanvue_user_id
                and (content_item_id or content_tag)
            ):
                try:
                    log_content_usage(
                        fanvue_account_id=fanvue_account_id,
                        fanvue_user_id=fanvue_user_id,
                        content_item_id=content_item_id,
                        send_source=payload.get("payload_type", "chat"),
                        fanvue_message_id=message_uuid,
                        caption_used=payload.get("text"),
                        price=payload.get("price"),
                        usage_type="send",
                        pipeline="chat",
                        classification=content_tag,
                    )

                    print("[13G CONTENT USAGE LOGGED AFTER SEND]")

                except Exception as log_error:
                    print("[13G LOGGING ERROR]", log_error)

            return {
                "success": True,
                "sent": True,
                "blocked": False,
                "status_code": response.status_code,
                "response": data,
                "message_uuid": message_uuid,
                "payload": fanvue_payload,
            }

        except Exception as e:
            print(f"[FANVUE SEND MESSAGE ERROR] {e}")

            return {
                "success": False,
                "sent": False,
                "blocked": False,
                "reason": "exception",
                "error": str(e),
                "payload": fanvue_payload,
            }

    def create_wall_post(
        self,
        text: str,
        media_uuids: list[str] | None = None,
        audience: str = "followers-and-subscribers",
        media_preview_uuid: str | None = None,
        price: int | None = None,
        publish_at: str | None = None,
        expires_at: str | None = None,
        collection_uuids: list[str] | None = None,
    ) -> dict:
        print("[FANVUE CREATE WALL POST START]")
        print(f"audience={audience}")

        if audience not in ["subscribers", "followers-and-subscribers"]:
            return {
                "success": False,
                "sent": False,
                "blocked": False,
                "reason": "invalid_audience",
                "audience": audience,
            }

        fanvue_payload = {
            "audience": audience,
            "text": text,
            "mediaUuids": media_uuids or [],
            "mediaPreviewUuid": media_preview_uuid,
            "price": price,
            "publishAt": publish_at,
            "expiresAt": expires_at,
            "collectionUuids": collection_uuids,
        }

        fanvue_payload = {
            key: value
            for key, value in fanvue_payload.items()
            if value is not None and value != []
        }

        safety = self.safety_service.can_send_monetization()

        if not safety.get("allowed"):
            print("[FANVUE CREATE WALL POST BLOCKED BY GLOBAL SAFETY]")
            print(safety)

            return {
                "success": False,
                "sent": False,
                "blocked": True,
                "reason": safety.get("reason"),
                "safety": safety,
                "payload": fanvue_payload,
            }

        url = f"{self.base_url}/posts"

        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json=fanvue_payload,
                timeout=30,
            )

            print(
                f"[FANVUE CREATE WALL POST RESPONSE] "
                f"status={response.status_code}"
            )

            if response.status_code >= 400:
                print("[FANVUE CREATE WALL POST FAILED]")
                print(response.text)

                return {
                    "success": False,
                    "sent": False,
                    "blocked": False,
                    "status_code": response.status_code,
                    "response": response.text,
                    "payload": fanvue_payload,
                }

            data = response.json()

            print("[FANVUE CREATE WALL POST SUCCESS]")
            print(data)

            return {
                "success": True,
                "sent": True,
                "blocked": False,
                "status_code": response.status_code,
                "response": data,
                "post_uuid": data.get("uuid"),
                "payload": fanvue_payload,
            }

        except Exception as e:
            print(f"[FANVUE CREATE WALL POST ERROR] {e}")

            return {
                "success": False,
                "sent": False,
                "blocked": False,
                "reason": "exception",
                "error": str(e),
                "payload": fanvue_payload,
            }

    def list_vault_media(self, page: int = 1, size: int = 20) -> dict:
        print("[FANVUE LIST VAULT MEDIA START]")

        url = f"{self.base_url}/media"

        params = {
            "page": page,
            "size": size,
        }

        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=30,
            )

            print(
                f"[FANVUE LIST VAULT MEDIA RESPONSE] "
                f"status={response.status_code}"
            )

            if response.status_code >= 400:
                print("[FANVUE LIST VAULT MEDIA FAILED]")
                print(response.text)

                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response": response.text,
                    "params": params,
                }

            data = response.json()

            return {
                "success": True,
                "status_code": response.status_code,
                "data": data.get("data", data),
                "raw": data,
            }

        except Exception as e:
            print(f"[FANVUE LIST VAULT MEDIA ERROR] {e}")

            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
                "params": params,
            }

    def get_fan_insights(self, fanvue_user_uuid: str) -> dict:
        print("[FANVUE API] Fetching fan insights")

        url = f"{self.base_url}/insights/fans/{fanvue_user_uuid}"

        try:
            response = requests.get(
                url,
                headers=self._headers(),
                timeout=20,
            )

            print(f"[FAN INSIGHTS RESPONSE] status={response.status_code}")

            if response.status_code >= 400:
                print("[FAN INSIGHTS ERROR]", response.text)
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response": response.text,
                }

            data = response.json()

            return {
                "success": True,
                "data": data,
            }

        except Exception as e:
            print(f"[FAN INSIGHTS EXCEPTION] {e}")
            return {
                "success": False,
                "reason": "exception",
                "error": str(e),
            }

    def list_vault_folders(self):
        print("[FANVUE LIST VAULT FOLDERS START]")

        url = f"{self.base_url}/vault/folders"

        fanvue_upload_trace(
            "fanvue_api.list_vault_folders_request",
            endpoint=url,
            method="GET",
            fanvue_account_id=self.fanvue_account_id,
            stage="folder_lookup_http_request",
        )
        try:
            response = requests.get(
                url,
                headers=self._headers(),
                timeout=20,
            )
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_api.list_vault_folders_exception",
                exc,
                endpoint=url,
                method="GET",
                fanvue_account_id=self.fanvue_account_id,
                stage="folder_lookup_http_request",
            )
            raise

        print(
            f"[FANVUE LIST VAULT FOLDERS RESPONSE] "
            f"status={response.status_code}"
        )
        fanvue_upload_trace(
            "fanvue_api.list_vault_folders_response",
            endpoint=url,
            method="GET",
            fanvue_account_id=self.fanvue_account_id,
            status_code=response.status_code,
            response=fanvue_response_payload(response),
            stage="folder_lookup_http_response",
        )

        if response.status_code >= 400:
            print("[FANVUE LIST VAULT FOLDERS FAILED]", response.text)
            return {"success": False}

        try:
            data = response.json()
        except Exception as exc:
            fanvue_upload_exception(
                "fanvue_api.list_vault_folders_parse_exception",
                exc,
                endpoint=url,
                method="GET",
                fanvue_account_id=self.fanvue_account_id,
                response=fanvue_response_payload(response),
                stage="http_response_parsing",
            )
            raise

        return {
            "success": True,
            "data": data.get("data", []),
        }
