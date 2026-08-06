import unittest

from app.services.schema_manager_service import SchemaManagerService


class SchemaManagerServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = SchemaManagerService()

    def test_final_database_certification_passes(self):
        report = self.service.certify()

        self.assertEqual(report.status, "PASS")
        self.assertEqual(report.drift, ())
        self.assertEqual(report.missing_migrations, ())

    def test_every_live_table_has_ownership_and_migration_origin(self):
        schema = self.service.discover_schema()
        matrix = {item.table_name: item for item in self.service.audit_tables(schema)}

        self.assertEqual(set(schema), set(matrix))
        for table_name in schema:
            with self.subTest(table=table_name):
                entry = matrix[table_name]
                self.assertTrue(entry.owner)
                self.assertTrue(entry.repository)
                self.assertTrue(entry.service)
                self.assertTrue(entry.migration)

    def test_repository_schema_creation_removed(self):
        self.assertEqual(self.service.detect_repository_schema_creation(), ())

    def test_commerce_era_tables_have_evidenced_ownership(self):
        expected = {
            "asset_content_destinations",
            "asset_content_destination_history",
            "content_intelligence_profiles",
            "business_asset_registrations",
            "commerce_destination_history",
            "commerce_destination_routing_intents",
            "business_asset_fulfillment_registrations",
            "business_asset_fulfillment_history",
            "chat_commerce_registrations",
            "chat_commerce_registration_history",
            "ready_asset_chat_registration_jobs",
            "commercial_offerings",
            "commercial_offering_assets",
            "commercial_publications",
            "commercial_publication_uploads",
        }
        matrix = self.service.TABLE_OWNERSHIP
        self.assertTrue(expected.issubset(matrix))
        for table_name in expected:
            with self.subTest(table=table_name):
                metadata = matrix[table_name]
                self.assertTrue(metadata["migration"].endswith(".sql"))
                self.assertNotEqual(metadata["repository"], "None")
                self.assertNotEqual(metadata["service"], "None")
                self.assertEqual(metadata["compatibility"], "CANONICAL")

    def test_required_indexes_are_present(self):
        self.assertEqual(self.service.detect_missing_indexes(), ())

    def test_critical_foreign_keys_are_present_or_documented(self):
        self.assertEqual(self.service.detect_missing_foreign_keys(), ())
        self.assertIn(
            "runtime_control_records.creator_profile_id",
            self.service.DOCUMENTED_FK_DEBT,
        )
        self.assertIn(
            "content_opportunity_records.creator_profile_id",
            self.service.DOCUMENTED_FK_DEBT,
        )

    def test_ppv_canonical_and_legacy_tables_are_classified(self):
        matrix = {item.table_name: item for item in self.service.audit_tables()}

        self.assertEqual(matrix["ppv_broadcast_logs"].compatibility_status, "CANONICAL")
        self.assertEqual(
            matrix["ppv_broadcast_log"].compatibility_status,
            "CANDIDATE_FOR_RETIREMENT",
        )

    def test_provider_specific_tables_are_classified(self):
        matrix = {item.table_name: item for item in self.service.audit_tables()}

        for table_name in (
            "fanvue_accounts",
            "fanvue_users",
            "fanvue_messages",
            "fanvue_threads",
        ):
            with self.subTest(table=table_name):
                self.assertEqual(
                    matrix[table_name].compatibility_status,
                    "PROVIDER_SPECIFIC",
                )

    def test_fanvue_provider_primary_keys_are_canonical(self):
        matrix = {item.table_name: item for item in self.service.audit_tables()}

        self.assertNotIn("id", self.service.TABLE_OWNERSHIP["fanvue_messages"]["columns"])
        self.assertNotIn("id", self.service.TABLE_OWNERSHIP["fanvue_threads"]["columns"])
        self.assertIn("fanvue_message_id", self.service.TABLE_OWNERSHIP["fanvue_messages"]["columns"])
        self.assertIn("thread_id", self.service.TABLE_OWNERSHIP["fanvue_threads"]["columns"])
        self.assertEqual(matrix["fanvue_messages"].missing_columns, ())
        self.assertEqual(matrix["fanvue_threads"].missing_columns, ())


if __name__ == "__main__":
    unittest.main()
