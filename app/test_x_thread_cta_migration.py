from pathlib import Path
from app.services.schema_manager_service import SchemaManagerService
def test_x_thread_cta_migration_has_durable_safety_constraints():
    forward=Path("migrations/forward/20260914_133_x_thread_cta_jobs.sql").read_text()
    rollback=Path("migrations/rollback/20260914_133_x_thread_cta_jobs.sql").read_text()
    assert "sampled_delay_seconds BETWEEN 1800 AND 3600" in forward
    assert "SEND_UNCERTAIN" in forward and "FOR UPDATE" not in forward
    assert "uq_x_thread_cta_job_operation" in forward
    assert "WHERE state='SCHEDULED'" in forward
    assert "DROP TABLE IF EXISTS public.x_thread_cta_jobs" in rollback

def test_x_thread_cta_delivery_migration_is_non_queue_and_closed():
    forward=Path("migrations/forward/20260916_138_x_thread_cta_deliveries.sql").read_text()
    rollback=Path("migrations/rollback/20260916_138_x_thread_cta_deliveries.sql").read_text()
    assert "x_thread_cta_deliveries" in forward
    assert "timing IN ('ASAP','DELAY_30_60')" in forward
    assert "SEND_UNCERTAIN" in forward
    assert "uq_x_thread_cta_delivery_operation" in forward
    assert "scheduled_at" not in forward
    assert "DROP TABLE IF EXISTS public.x_thread_cta_deliveries" in rollback

def test_x_thread_cta_delivery_schema_is_governed():
    columns = (
        "delivery_id","creator_profile_id","fanvue_account_id",
        "publish_operation_id","x_account_name","primary_x_post_id",
        "x_link_attribution_id","timing","cta_text","cta_url","state",
        "resulting_x_reply_id","provider_output_url","failure_reason",
        "sent_at","created_at","updated_at",
    )
    ownership = SchemaManagerService.TABLE_OWNERSHIP["x_thread_cta_deliveries"]
    assert ownership["migration"] == "20260916_138_x_thread_cta_deliveries.sql"
    assert ownership["repository"] == "XThreadCtaDeliveryRepository"
    assert ownership["service"] == "XThreadCtaPublisher"
    assert ownership["columns"] == columns
    assert SchemaManagerService.REQUIRED_TABLES["x_thread_cta_deliveries"]["columns"] == columns
    assert SchemaManagerService.MIGRATION_SCHEMA_REQUIREMENTS[
        "20260916_138_x_thread_cta_deliveries.sql"
    ]["x_thread_cta_deliveries"] == columns
    assert SchemaManagerService.REQUIRED_INDEXES["x_thread_cta_deliveries"] == (
        "idx_x_thread_cta_deliveries_scope",
    )
    assert SchemaManagerService.CRITICAL_FOREIGN_KEYS["x_thread_cta_deliveries"] == (
        "x_thread_cta_deliveries_x_link_attribution_id_fkey",
    )
