from app.database import get_db_connection
from app.repositories.cms_fanvue_upload_repository import (
    create_or_get_upload_link,
    update_upload_link_status,
)


def _table_columns(table_name: str) -> list[dict]:
    sql = """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            is_identity
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (table_name,))
            return [dict(row) for row in cur.fetchall()]


def _value_for_column(column_name: str, data_type: str):
    name = column_name.lower()

    specific_values = {
        "title": "TEST Mass PPV VIP Content",
        "name": "TEST Mass PPV VIP Content",
        "filename": "test_mass_ppv_vip.jpg",
        "file_name": "test_mass_ppv_vip.jpg",
        "file_path": "data/test/test_mass_ppv_vip.jpg",
        "local_path": "data/test/test_mass_ppv_vip.jpg",
        "media_path": "data/test/test_mass_ppv_vip.jpg",
        "upload_intent": "vip_image",
        "classification": "VIP",
        "content_classification": "VIP",
        "tag": "test_mass_ppv_vip",
        "content_tag": "test_mass_ppv_vip",
        "price": 9.99,
        "mass_ppv_price": 9.99,
        "vip_price": 9.99,
        "ppv_price": 9.99,
        "default_price": 9.99,
        "status": "approved",
        "approval_status": "approved",
        "is_approved": True,
        "ready_for_rotation": True,
        "is_active": True,
        "content_tier": "VIP",
        "distribution_type": "mass_ppv",
        "mass_ppv_price": 14.99
    }

    if name in specific_values:
        return specific_values[name]

    if data_type in ("integer", "bigint", "smallint"):
        return 1

    if data_type in ("numeric", "double precision", "real"):
        return 9.99

    if data_type == "boolean":
        return True

    if "timestamp" in data_type or data_type == "date":
        return None

    if data_type in ("json", "jsonb"):
        return "{}"

    return "test_mass_ppv_vip_seed"


def seed_content_item() -> int:
    columns = _table_columns("content_items")

    insert_columns = []
    insert_values = []

    preferred_optional_columns = {
        "title",
        "name",
        "filename",
        "file_name",
        "file_path",
        "local_path",
        "media_path",
        "upload_intent",
        "classification",
        "content_classification",
        "tag",
        "content_tag",
        "price",
        "mass_ppv_price",
        "vip_price",
        "ppv_price",
        "default_price",
        "status",
        "approval_status",
        "is_approved",
        "ready_for_rotation",
        "is_active",
        "content_tier",
        "distribution_type",
        "mass_ppv_price",
    }

    for col in columns:
        name = col["column_name"]
        data_type = col["data_type"]
        is_nullable = col["is_nullable"] == "YES"
        has_default = col["column_default"] is not None
        is_identity = col.get("is_identity") == "YES"

        if name == "id" or is_identity:
            continue

        if "created_at" in name or "updated_at" in name:
            continue

        must_insert = not is_nullable and not has_default
        useful_optional = name.lower() in preferred_optional_columns

        if must_insert or useful_optional:
            value = _value_for_column(name, data_type)

            if value is None and must_insert:
                value = "test_mass_ppv_vip_seed"

            insert_columns.append(name)
            insert_values.append(value)

    placeholders = ", ".join(["%s"] * len(insert_columns))
    column_sql = ", ".join(insert_columns)

    sql = f"""
        INSERT INTO content_items ({column_sql})
        VALUES ({placeholders})
        RETURNING id;
    """

    print("\n[SEED CONTENT ITEM]")
    print(f"columns={insert_columns}")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, insert_values)
            row = cur.fetchone()
            return row["id"]


def seed_upload_link(content_item_id: int, fanvue_account_id: int = 1):
    print("\n[SEED UPLOAD LINK]")

    create_or_get_upload_link(
        content_item_id=content_item_id,
        fanvue_account_id=fanvue_account_id,
        upload_status="pending",
        destination="vip",
        delivery_method="chat",
        vault_folder_id="test_vip_folder",
    )

    updated = update_upload_link_status(
        content_item_id=content_item_id,
        fanvue_account_id=fanvue_account_id,
        upload_status="uploaded",
        fanvue_media_uuid="fake_mass_ppv_vip_media_uuid",
        fanvue_preview_media_uuid="fake_mass_ppv_vip_preview_uuid",
        fanvue_full_media_uuid="fake_mass_ppv_vip_full_uuid",
        vault_folder_id="test_vip_folder",
        destination="vip",
        delivery_method="chat",
    )

    return updated


def run_test():
    print("\n==============================")
    print(" SEED MASS PPV VIP TEST CONTENT")
    print("==============================\n")

    fanvue_account_id = 1

    content_item_id = seed_content_item()
    print(f"✅ Created test VIP content_item_id={content_item_id}")

    upload_link = seed_upload_link(
        content_item_id=content_item_id,
        fanvue_account_id=fanvue_account_id,
    )

    print("\n✅ Seeded uploaded VIP Mass PPV media:")
    print(upload_link)

    print("\nNow run:")
    print("python -m app.test_mass_ppv_content_service")


if __name__ == "__main__":
    run_test()