from app.database import get_db_connection
from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    administrative_import_context,
)
from app.services.asset_ingestion_service import AssetIngestionService
import json


# A.2 ownership boundary for the legacy content_items compatibility table:
#
# Asset-owned fields:
# file_path, file_name, classification, confidence, detected_themes,
# suggested_tags, nudity/safety fields, status/is_test, creator_profile_id,
# analysis metadata/results, media_metadata, local_vault_path.
#
# Product-owned compatibility fields:
# upload_intent, ready_for_rotation, content_type, content_tier,
# distribution_type, mass_ppv_price.
#
# Publishing-owned compatibility fields:
# fanvue_account_id, fanvue_upload_status, fanvue_upload_error, and downstream
# Fanvue media/upload columns updated by update_content_fanvue_upload_result.
#
# This module intentionally preserves the mixed insert/update surface until
# later phases extract Product and Publishing lifecycles without changing
# existing CMS behavior.
_CONTENT_ITEM_COLUMNS = (
    "file_path",
    "file_name",
    "classification",
    "confidence",
    "detected_themes",
    "suggested_tags",
    "nudity_labels",
    "nudity_level",
    "sexual_intensity",
    "is_explicit",
    "is_active",
    "is_test",
    "upload_intent",
    "requires_nudenet",
    "requires_blur",
    "requires_vision",
    "status",
    "ready_for_rotation",
    "content_type",
    "fanvue_account_id",
    "fanvue_upload_status",
    "fanvue_upload_error",
    "content_tier",
    "distribution_type",
    "mass_ppv_price",
    "creator_profile_id",
    "short_safe_summary",
    "risk_flags",
    "analysis_reasoning",
    "analysis_provenance",
    "media_metadata",
    "local_vault_path",
    "gpt_vision_result",
    "nudenet_result",
    "classification_result",
)

_JSONB_COLUMNS = {
    "detected_themes",
    "suggested_tags",
    "nudity_labels",
    "risk_flags",
    "analysis_provenance",
    "media_metadata",
    "gpt_vision_result",
    "nudenet_result",
    "classification_result",
}

_CONTENT_ITEM_COLUMN_CACHE: set[str] | None = None


def _get_existing_content_item_columns(conn) -> set[str]:
    global _CONTENT_ITEM_COLUMN_CACHE
    if _CONTENT_ITEM_COLUMN_CACHE is not None:
        return _CONTENT_ITEM_COLUMN_CACHE

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'content_items'
            """
        )
        _CONTENT_ITEM_COLUMN_CACHE = {row["column_name"] for row in cur.fetchall()}
    return _CONTENT_ITEM_COLUMN_CACHE


def insert_content_item(data: dict):
    data = dict(data or {})
    media_metadata = data.get("media_metadata") or {}
    if isinstance(media_metadata, str):
        media_metadata = json.loads(media_metadata)
    if isinstance(media_metadata, dict) and ASSET_PROVENANCE_METADATA_KEY not in media_metadata:
        media_metadata[ASSET_PROVENANCE_METADATA_KEY] = administrative_import_context(
            source="ContentRepository.insert_content_item",
            source_workflow="legacy_content_repository",
            metadata={"explicit_non_commerce_path": True},
        )
        data["media_metadata"] = media_metadata
    with get_db_connection() as conn:
        existing_columns = _get_existing_content_item_columns(conn)
        values = {}
        columns = []
        placeholders = []

        for column in _CONTENT_ITEM_COLUMNS:
            if column not in data or column not in existing_columns:
                continue
            value = data[column]
            if column in _JSONB_COLUMNS and isinstance(value, (dict, list, tuple)):
                value = json.dumps(value)
            values[column] = value
            columns.append(column)
            suffix = "::jsonb" if column in _JSONB_COLUMNS else ""
            placeholders.append(f"%({column})s{suffix}")

        query = f"""
            INSERT INTO content_items (
                {", ".join(columns)}
            )
            VALUES (
                {", ".join(placeholders)}
            )
            RETURNING id;
        """

        with conn.cursor() as cur:
            cur.execute(query, values)
            row = cur.fetchone()
            content_id = row["id"] if row else None

            if content_id and data.get("file_path"):
                vault_metadata = AssetIngestionService().copy_to_local_vault(
                    content_item_id=content_id,
                    source_path=data["file_path"],
                )
                media_metadata = data.get("media_metadata") or {}

                if isinstance(media_metadata, str):
                    media_metadata = json.loads(media_metadata)

                media_metadata.update(vault_metadata)
                media_metadata.setdefault(
                    "original_filename",
                    data.get("file_name"),
                )

                if "local_vault_path" in existing_columns:
                    cur.execute(
                        """
                        UPDATE content_items
                        SET
                            media_metadata = %s::jsonb,
                            local_vault_path = %s
                        WHERE id = %s
                        """,
                        (
                            json.dumps(media_metadata),
                            vault_metadata["local_vault_path"],
                            content_id,
                        ),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE content_items
                        SET media_metadata = %s::jsonb
                        WHERE id = %s
                        """,
                        (
                            json.dumps(media_metadata),
                            content_id,
                        ),
                    )

            return content_id
        

def get_content_by_classification(classification: str, limit: int = 20):
    """
    Fetch approved, blurred, ready content by classification.
    """

    print(f"[CONTENT FETCH START] classification={classification}")

    query = """
        SELECT
            id,
            file_path,
            local_vault_path,
            media_metadata,
            file_name,
            classification,
            blurred_preview_path,
            created_at
        FROM content_items
        WHERE classification = %s
          AND status = 'approved'
          AND ready_for_rotation = TRUE
          AND blurred_preview_path IS NOT NULL
        ORDER BY created_at DESC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (classification, limit))
            results = cur.fetchall()

    if not results:
        print(f"[CONTENT FETCH EMPTY] classification={classification}")
        return []

    print(f"[CONTENT FILTER APPLIED] classification={classification} count={len(results)}")

    for item in results:
        print(
            "[CONTENT SELECTED] "
            f"id={item.get('id')} "
            f"classification={item.get('classification')} "
            f"file={item.get('file_name')}"
        )

    return results


def has_user_seen_content(
    fanvue_account_id: int,
    fanvue_user_id: int,
    content_item_id: int,
) -> bool:
    query = """
        SELECT 1
        FROM content_usage_log
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s
          AND content_item_id = %s
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (fanvue_account_id, fanvue_user_id, content_item_id),
            )
            return cur.fetchone() is not None


def log_content_usage(
    content_item_id: int,
    fanvue_account_id: int,
    fanvue_user_id: int,
    usage_type: str,
    pipeline: str = None,
    classification: str = None,
    message_text: str = None,
    price: float = None,
    metadata: dict = None,
):
    query = """
        INSERT INTO content_usage_log (
            content_item_id,
            fanvue_account_id,
            fanvue_user_id,
            usage_type,
            pipeline,
            classification,
            message_text,
            price,
            metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb);
    """

    metadata_json = json.dumps(metadata) if metadata is not None else None

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    content_item_id,
                    fanvue_account_id,
                    fanvue_user_id,
                    usage_type,
                    pipeline,
                    classification,
                    message_text,
                    price,
                    metadata_json,
                ),
            )


def get_smart_content_for_user(
    classification: str,
    fanvue_account_id: int,
    fanvue_user_id: int,
    cooldown_hours: int = 24,
):
    """
    Gets one approved, rotation-ready content item the user has NOT already received.

    CMS now stores content by upload_intent, so offer classifications are mapped:
    - TEASE   -> teaser_image / teaser_video
    - VIP     -> ppv_image / ppv_video
    - PREMIUM -> ppv_image / ppv_video
    """

    classification = (classification or "").upper()

    upload_intent_map = {
        "TEASE": ["teaser_image", "teaser_video"],
        "TEASER": ["teaser_image", "teaser_video"],
        "VIP": ["ppv_image", "ppv_video"],
        "PREMIUM": ["ppv_image", "ppv_video"],
        "WALL": ["wall_image", "wall_video"],
    }

    upload_intents = upload_intent_map.get(classification, [])

    print("\n========== CONTENT QUERY DEBUG ==========")
    print(f"classification={classification}")
    print(f"upload_intents={upload_intents}")
    print(f"user_id={fanvue_user_id}")
    print(f"account_id={fanvue_account_id}")
    print(f"cooldown_hours={cooldown_hours}")
    print("========================================\n")

    if not upload_intents:
        print(f"[CONTENT NONE FOUND] No upload_intent mapping for classification={classification}")
        return None

    if has_recent_content_send(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        classification=classification,
        hours=cooldown_hours,
    ):
        print(
            f"[CONTENT COOLDOWN] user={fanvue_user_id} "
            f"classification={classification} "
            f"cooldown_hours={cooldown_hours}"
        )
        return None

    query = """
        SELECT ci.*
        FROM content_items ci
        WHERE ci.upload_intent = ANY(%s)
          AND ci.status = 'approved'
          AND ci.ready_for_rotation = TRUE
          AND NOT EXISTS (
              SELECT 1
              FROM content_usage_log cul
              WHERE cul.content_item_id = ci.id
                AND cul.fanvue_account_id = %s
                AND cul.fanvue_user_id = %s
          )
        ORDER BY ci.created_at ASC
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (upload_intents, fanvue_account_id, fanvue_user_id),
            )

            row = cur.fetchone()

            print(
                f"[CONTENT QUERY RESULT] classification={classification} "
                f"upload_intents={upload_intents} row={row}"
            )

            if not row:
                print(
                    f"[CONTENT NONE FOUND] "
                    f"classification={classification} "
                    f"upload_intents={upload_intents} "
                    f"account_id={fanvue_account_id} "
                    f"user_id={fanvue_user_id}"
                )
                return None

            content = dict(row)
            content["classification"] = classification
            return content


def get_tease_content_for_user(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    print(f"\n[CONTENT FETCH] type=TEASE user_id={fanvue_user_id}")

    content = get_smart_content_for_user(
        classification="TEASE",
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        cooldown_hours=24,
    )

    print(f"[CONTENT FETCH RESULT] type=TEASE content={content}\n")

    return content


def get_vip_content_for_user(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    print(f"\n[CONTENT FETCH] type=VIP user_id={fanvue_user_id}")

    content = get_smart_content_for_user(
        classification="VIP",
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        cooldown_hours=48,
    )

    print(f"[CONTENT FETCH RESULT] type=VIP content={content}\n")

    return content

def get_premium_content_for_user(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    print(f"\n[CONTENT FETCH] type=PREMIUM user_id={fanvue_user_id} account_id={fanvue_account_id}")

    content = get_smart_content_for_user(
        classification="PREMIUM",
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        cooldown_hours=72,
    )

    print(f"[CONTENT FETCH RESULT] type=PREMIUM content={content}\n")

    return content


def has_content_file_been_scanned(file_path: str) -> bool:
    query = """
        SELECT 1
        FROM content_items
        WHERE file_path = %s
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (file_path,))
            return cur.fetchone() is not None
        
def has_recent_content_send(
    fanvue_account_id: int,
    fanvue_user_id: int,
    classification: str = None,
    hours: int = 24,
) -> bool:
    """
    Checks whether this user recently received content.

    If classification is provided:
        - checks recent sends for that tier only (TEASE / VIP / PREMIUM)

    If classification is None:
        - checks any recent content send
    """

    if classification:
        query = """
            SELECT 1
            FROM content_usage_log
            WHERE fanvue_account_id = %s
              AND fanvue_user_id = %s
              AND classification = %s
              AND created_at >= NOW() - (%s || ' hours')::interval
            LIMIT 1;
        """
        params = (
            fanvue_account_id,
            fanvue_user_id,
            classification,
            hours,
        )
    else:
        query = """
            SELECT 1
            FROM content_usage_log
            WHERE fanvue_account_id = %s
              AND fanvue_user_id = %s
              AND created_at >= NOW() - (%s || ' hours')::interval
            LIMIT 1;
        """
        params = (
            fanvue_account_id,
            fanvue_user_id,
            hours,
        )

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone() is not None
        
def get_approved_content(limit: int = 20):
    """
    Fetch approved, blurred, rotation-ready content only.

    14K rule:
    - status = approved
    - ready_for_rotation = TRUE
    - blurred_preview_path IS NOT NULL
    """

    print("[CONTENT FETCH START] Fetching approved ready content")

    query = """
        SELECT
            id,
            file_path,
            local_vault_path,
            media_metadata,
            file_name,
            classification,
            blurred_preview_path,
            ready_for_rotation,
            status,
            created_at
        FROM content_items
        WHERE status = 'approved'
          AND ready_for_rotation = TRUE
          AND blurred_preview_path IS NOT NULL
        ORDER BY created_at DESC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            results = cur.fetchall()

    if not results:
        print("[CONTENT FETCH EMPTY] No approved ready content found")
        return []

    print(f"[CONTENT FILTER APPLIED] approved_ready_only count={len(results)}")

    for item in results:
        print(
            "[CONTENT SELECTED] "
            f"id={item.get('id')} "
            f"classification={item.get('classification')} "
            f"file_name={item.get('file_name')}"
        )

    return results

def get_random_content_for_now(classification: str = None):
    """
    Fetch one random approved, blurred, ready content item.

    Optional:
    - classification filter: TEASE / VIP / PREMIUM
    """

    print("[CONTENT RANDOM FETCH START]")

    query = """
        SELECT
            id,
            file_path,
            local_vault_path,
            media_metadata,
            file_name,
            classification,
            blurred_preview_path,
            ready_for_rotation,
            status,
            created_at
        FROM content_items
        WHERE status = 'approved'
          AND ready_for_rotation = TRUE
          AND blurred_preview_path IS NOT NULL
    """

    params = []

    if classification:
        query += " AND classification = %s"
        params.append(classification)
        print(f"[CONTENT FILTER APPLIED] classification={classification}")

    query += " ORDER BY RANDOM() LIMIT 1;"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            result = cur.fetchone()

    if not result:
        print("[CONTENT FETCH EMPTY] random selection found nothing")
        return None

    print(
        "[CONTENT RANDOM SELECTED] "
        f"id={result.get('id')} "
        f"classification={result.get('classification')} "
        f"file={result.get('file_name')}"
    )

    return result

def get_content_ready_for_fanvue_upload(limit: int = 20):
    """
    Fetch approved, blurred, rotation-ready content that still needs Fanvue upload.

    Used by:
    - 14L Fanvue API Test Panel
    - 14M Fanvue Media Upload Service

    Rules:
    - Must be approved
    - Must be rotation-ready
    - Must have a blurred preview
    - Must NOT already have Fanvue preview/full UUIDs
    """

    print("[FANVUE UPLOAD QUEUE FETCH START]")

    query = """
        SELECT
            id,
            file_path,
            local_vault_path,
            media_metadata,
            file_name,
            classification,
            blurred_preview_path,
            ready_for_rotation,
            status,
            upload_status,
            fanvue_upload_status,
            fanvue_media_preview_uuid,
            fanvue_media_full_uuid,
            created_at
        FROM content_items
        WHERE status = 'approved'
          AND ready_for_rotation = TRUE
          AND blurred_preview_path IS NOT NULL
          AND (
              fanvue_upload_status IS NULL
              OR fanvue_upload_status = 'pending'
          )
          AND fanvue_media_preview_uuid IS NULL
          AND fanvue_media_full_uuid IS NULL
        ORDER BY created_at ASC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            results = cur.fetchall()

    if not results:
        print("[FANVUE UPLOAD QUEUE EMPTY] No pending Fanvue uploads found")
        return []

    print(f"[FANVUE UPLOAD QUEUE FOUND] count={len(results)}")

    for item in results:
        print(
            "[FANVUE UPLOAD QUEUE ITEM] "
            f"id={item.get('id')} "
            f"classification={item.get('classification')} "
            f"fanvue_upload_status={item.get('fanvue_upload_status')} "
            f"file={item.get('file_name')}"
        )

    return results

def update_content_fanvue_upload_result(
    content_id: int,
    preview_uuid: str | None,
    full_uuid: str | None,
    upload_status: str = "processing",
    upload_error: str | None = None,
    raw_response: dict | None = None,
):
    import json

    from app.database import get_db_connection

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE content_items
                SET
                    fanvue_media_preview_uuid = %s,
                    fanvue_media_full_uuid = %s,
                    fanvue_preview_upload_status = %s,
                    fanvue_full_upload_status = %s,
                    fanvue_upload_status = %s,
                    fanvue_upload_error = %s,
                    fanvue_upload_metadata = %s::jsonb,
                    fanvue_uploaded_at = NOW()
                WHERE id = %s
                """,
                (
                    preview_uuid,
                    full_uuid,
                    upload_status if preview_uuid else None,
                    upload_status if full_uuid else None,
                    upload_status,
                    upload_error,
                    json.dumps(raw_response or {}),
                    content_id,
                ),
            )

        conn.commit()

def get_content_ready_for_ptv_set_creation(limit: int = 10):
    """
    Return content items that have uploaded Fanvue media
    but do not yet have a Fanvue PTV set created.
    """

    query = """
        SELECT
            id,
            file_name,
            classification,
            fanvue_media_preview_uuid,
            fanvue_media_full_uuid,
            fanvue_ptv_set_id,
            fanvue_set_status
        FROM content_items
        WHERE fanvue_media_preview_uuid IS NOT NULL
          AND fanvue_media_full_uuid IS NOT NULL
          AND fanvue_ptv_set_id IS NULL
          AND COALESCE(fanvue_set_status, 'not_created') = 'not_created'
          AND last_fanvue_message_uuid IS NULL
        ORDER BY id ASC
        LIMIT %s
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (limit,))
            return cur.fetchall()

def update_content_item(item_id: int, fields: dict):
    """
    Update selected fields on a content item.
    """

    if not fields:
        return None

    set_clauses = []
    values = []

    for key, value in fields.items():
        set_clauses.append(f"{key} = %s")
        values.append(value)

    values.append(item_id)

    query = f"""
        UPDATE content_items
        SET {", ".join(set_clauses)}
        WHERE id = %s
        RETURNING id
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            conn.commit()
            return cur.fetchone()
