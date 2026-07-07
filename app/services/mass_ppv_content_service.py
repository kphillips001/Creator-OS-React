from app.database import get_db_connection
from app.services.content_media_delivery_service import ContentMediaDeliveryService
import random

class MassPPVContentService:
    """
    Mass PPV Step 2 — CMS-backed Premium PPV content selection.

    Rules:
    - CMS/Fanvue uploaded content only
    - Premium destination only
    - chat_ppv delivery only
    - requires blurred preview UUID
    - requires full media UUID
    - no hardcoded content
    """

    DESTINATION = "vip"
    REQUESTED_DELIVERY = "chat_ppv"

    def __init__(self, content_delivery_service=None):
        self.content_delivery_service = (
            content_delivery_service or ContentMediaDeliveryService()
        )

    def get_mass_ppv_content(self, fanvue_account_id: int) -> dict | None:
        print("\n[MASS PPV CONTENT SERVICE]")
        print(f"fanvue_account_id={fanvue_account_id}")

        delivery_result = self.content_delivery_service.get_media_for_delivery(
            fanvue_account_id=fanvue_account_id,
            destination=self.DESTINATION,
            requested_delivery=self.REQUESTED_DELIVERY,
            limit=10,
        )

        media_items = delivery_result.get("media") or []

        if not media_items:
            print("[MASS PPV CONTENT] No uploaded premium PPV media available")
            return None

        for media in media_items:
            normalized = self._normalize_media_record(media)

            if not self._is_valid_mass_ppv_content(normalized):
                print("[MASS PPV CONTENT] Skipping invalid record")
                print(normalized)
                continue

            print("[MASS PPV CONTENT] Selected valid CMS PPV content")
            return normalized

        print("[MASS PPV CONTENT] No valid PPV content passed final checks")
        return None

    def _normalize_media_record(self, media: dict) -> dict:
        content_item_id = media.get("content_item_id")

        cms_details = self._get_cms_content_details(content_item_id)

        preview_uuid = (
            media.get("fanvue_preview_media_uuid")
            or media.get("preview_uuid")
        )

        full_uuid = (
            media.get("fanvue_full_media_uuid")
            or media.get("fanvue_media_uuid")
            or media.get("media_uuid")
        )

        return {
            "content_item_id": content_item_id,
            "media_uuid": full_uuid,
            "preview_uuid": preview_uuid,
            "price": cms_details.get("price"),
            "tag": cms_details.get("tag"),
            "destination": media.get("destination"),
            "requested_delivery": self.REQUESTED_DELIVERY,
            "upload_status": media.get("upload_status"),
        }

    def _get_cms_content_details(self, content_item_id: int | None) -> dict:
        if not content_item_id:
            return {}

        sql = """
            SELECT *
            FROM content_items
            WHERE id = %s
            LIMIT 1;
        """

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (content_item_id,))
                row = cur.fetchone()

        if not row:
            return {}

        row = dict(row)

        # --- BASE PRICE (CMS OR FALLBACK) ---
        base_price = (
            row.get("mass_ppv_price")
            or row.get("vip_price")
            or row.get("price")
            or row.get("ppv_price")
            or row.get("default_price")
            or 19.99
        )

        # --- HYBRID PRICING LOGIC ---
        
        variation = random.choice([-2.00, -1.00, 0.00, 2.00, 5.00])

        base_price = float(base_price)
        price = round(base_price + variation, 2)

        # Clamp to Mass PPV safe range
        price = max(9.99, min(price, 29.99))

        # --- TAG / CLASSIFICATION ---
        tag = (
            row.get("tag")
            or row.get("content_tag")
            or row.get("classification")
            or row.get("content_classification")
            or row.get("upload_intent")
            or f"content_{content_item_id}"
        )

        return {
            "price": price,
            "tag": tag,
        }

    def _is_valid_mass_ppv_content(self, content: dict) -> bool:
        destination = (content.get("destination") or "").lower()
        tier = (content.get("content_tier") or "").upper()
        dist = (content.get("distribution_type") or "").lower()

        # fallback fields
        classification = (content.get("tag") or "").lower()
        upload_intent = (content.get("upload_intent") or "").lower()

        if not content.get("content_item_id"):
            print("[MASS PPV BLOCKED] Missing content_item_id")
            return False

        if destination != "vip":
            print("[MASS PPV BLOCKED] Not VIP destination")
            return False

        # -------------------------------
        # NEW STRUCTURED FIELD LOGIC
        # -------------------------------
        if tier:
            if tier == "PREMIUM":
                print("[MASS PPV BLOCKED] Premium content not allowed")
                return False

            if tier != "VIP":
                print("[MASS PPV BLOCKED] Not VIP content")
                return False

            if dist and dist not in ("mass_ppv", "both"):
                print("[MASS PPV BLOCKED] Distribution not allowed")
                return False

        else:
            # -------------------------------
            # FALLBACK (OLD LOGIC)
            # -------------------------------
            if "premium" in classification or "premium" in upload_intent:
                print("[MASS PPV BLOCKED] Premium content not allowed (fallback)")
                return False

            is_vip = "vip" in classification or "vip" in upload_intent
            if not is_vip:
                print("[MASS PPV BLOCKED] Not VIP content (fallback)")
                return False

        if (content.get("upload_status") or "").lower() != "uploaded":
            print("[MASS PPV BLOCKED] Not uploaded")
            return False

        if not content.get("media_uuid"):
            print("[MASS PPV BLOCKED] Missing media_uuid")
            return False

        if not content.get("preview_uuid"):
            print("[MASS PPV BLOCKED] Missing preview_uuid")
            return False

        if content.get("price") is None:
            print("[MASS PPV BLOCKED] Missing price")
            return False

        if not content.get("tag"):
            print("[MASS PPV BLOCKED] Missing tag")
            return False

        return True