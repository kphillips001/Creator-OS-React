from __future__ import annotations

import json

from app.database import get_db_connection


IDS = [
    "3e411d0d-2de7-43b4-88f1-b851c384c3a0",
    "f89072fb-b47e-4e06-827d-7e304786b4c9",
    "366c2d37-bc40-4cfe-81da-ea6f6d0171",
    "59de4ed0-4573-46d3-9172-54a75e085a95",
    "ffbb100d-c6d0-4cfe-81da-ea81c9e595d5",
    "78738f01-6325-424f-b3ee-c5dd6002768e",
    "1d88d371-a83c-4ddf-a2ee-a5834170c693",
]


def clean(row):
    return {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}


with get_db_connection() as connection, connection.cursor() as cursor:
    cursor.execute("SELECT current_database() AS db")
    output = {"db": cursor.fetchone()["db"]}
    cursor.execute(
        "SELECT migration_name,count(*) AS n FROM schema_migrations "
        "WHERE migration_name=%s GROUP BY migration_name",
        ("20260916_139_ordinary_reply_preparation_window.sql",),
    )
    output["migration139"] = [clean(row) for row in cursor.fetchall()]
    cursor.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='ordinary_chat_reply_operations' "
        "AND column_name IN ('preparation_eligible_at','scheduled_delivery_at') ORDER BY 1"
    )
    output["columns"] = [row["column_name"] for row in cursor.fetchall()]
    cursor.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname='public' "
        "AND tablename='ordinary_chat_reply_operations' "
        "AND indexname='idx_ordinary_reply_preparation_due'"
    )
    output["index"] = [row["indexname"] for row in cursor.fetchall()]
    cursor.execute(
        "SELECT state,count(*) AS n,count(*) FILTER (WHERE claim_owner IS NOT NULL "
        "AND lease_expires_at>NOW()) AS active FROM ordinary_chat_reply_operations "
        "WHERE state IN ('GENERATING','SENDING') GROUP BY state"
    )
    output["active"] = [clean(row) for row in cursor.fetchall()]
    cursor.execute(
        "SELECT operation_id::text,state,inbound_telegram_message_id,"
        "generation_attempt_count,send_attempt_count,response_payload IS NOT NULL AS has_payload,"
        "response_text IS NOT NULL AS has_text,outbound_telegram_message_id,claim_owner,"
        "lease_expires_at,next_retry_at,preparation_eligible_at,scheduled_delivery_at,last_error "
        "FROM ordinary_chat_reply_operations WHERE inbound_telegram_message_id=ANY(%s::bigint[]) "
        "ORDER BY inbound_telegram_message_id",
        ([6373, 6375, 6376, 6378, 6379, 6380, 6381],),
    )
    output["operations"] = [clean(row) for row in cursor.fetchall()]

print(json.dumps(output, default=str))
