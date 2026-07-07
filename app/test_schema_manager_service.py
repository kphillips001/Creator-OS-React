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


if __name__ == "__main__":
    unittest.main()
