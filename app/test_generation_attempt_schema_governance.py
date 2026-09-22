from app.services.schema_manager_service import SchemaManagerService


def test_migrations_135_and_136_have_complete_schema_governance():
    expected = {
        "active_offer_follow_through_events": (
            "20260914_135_active_offer_follow_through.sql",
            "active_offer_follow_through_scope_idx",
        ),
        "ordinary_reply_generation_attempts": (
            "20260915_136_ordinary_reply_generation_attempts.sql",
            "ordinary_reply_generation_attempt_scope_idx",
        ),
    }
    for table, (migration, index) in expected.items():
        required = SchemaManagerService.REQUIRED_TABLES[table]
        ownership = SchemaManagerService.TABLE_OWNERSHIP[table]
        assert required["migration"] == migration
        assert ownership["migration"] == migration
        assert set(required["columns"]) == set(ownership["columns"])
        assert table in SchemaManagerService.MIGRATION_SCHEMA_REQUIREMENTS[migration]
        assert index in SchemaManagerService.REQUIRED_INDEXES[table]


def test_generation_attempt_governance_covers_all_migration_columns():
    columns = set(
        SchemaManagerService.TABLE_OWNERSHIP[
            "ordinary_reply_generation_attempts"
        ]["columns"]
    )
    assert columns == {
        "attempt_id", "operation_id", "attempt_number", "creator_profile_id",
        "fanvue_account_id", "telegram_account_scope", "telegram_chat_id",
        "telegram_user_id", "provider", "candidate_text",
        "quality_disposition", "quality_reasons", "turn_obligations",
        "satisfied_obligations", "unsatisfied_obligations", "repair_outcome",
        "sent_confirmed", "outbound_telegram_message_id", "attempted_at",
        "sent_confirmed_at",
    }
