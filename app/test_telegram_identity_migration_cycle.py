import os
import unittest
from pathlib import Path

from psycopg import connect


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORWARD_MIGRATION = (
    PROJECT_ROOT
    / "migrations"
    / "forward"
    / "20260619_001_create_telegram_identity_map.sql"
)
ROLLBACK_MIGRATION = (
    PROJECT_ROOT
    / "migrations"
    / "rollback"
    / "20260619_001_drop_telegram_identity_map.sql"
)


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "TEST_DATABASE_URL is required for migration-cycle tests.",
)
class TelegramIdentityMigrationCycleTests(unittest.TestCase):
    def test_forward_and_rollback_migrations(self):
        forward_sql = FORWARD_MIGRATION.read_text(encoding="utf-8")
        rollback_sql = ROLLBACK_MIGRATION.read_text(encoding="utf-8")

        with connect(TEST_DATABASE_URL, autocommit=True) as connection:
            self.assertIsNone(
                connection.execute(
                    "SELECT to_regclass(%s)",
                    ("public.telegram_identity_map",),
                ).fetchone()[0]
            )

            try:
                connection.execute(forward_sql)

                types = dict(
                    connection.execute(
                        """
                        SELECT column_name, data_type
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'telegram_identity_map'
                          AND column_name IN (
                              'fanvue_account_id',
                              'local_fanvue_user_id',
                              'external_fanvue_user_uuid'
                          );
                        """
                    ).fetchall()
                )
                self.assertEqual(types["fanvue_account_id"], "bigint")
                self.assertEqual(
                    types["local_fanvue_user_id"],
                    "bigint",
                )
                self.assertEqual(
                    types["external_fanvue_user_uuid"],
                    "uuid",
                )

                connection.execute(rollback_sql)

                self.assertIsNone(
                    connection.execute(
                        "SELECT to_regclass(%s)",
                        ("public.telegram_identity_map",),
                    ).fetchone()[0]
                )
                self.assertIsNone(
                    connection.execute(
                        "SELECT to_regprocedure(%s)",
                        (
                            "public."
                            "validate_telegram_identity_"
                            "canonical_user()",
                        ),
                    ).fetchone()[0]
                )
                self.assertIsNotNone(
                    connection.execute(
                        "SELECT to_regclass(%s)",
                        ("public.fanvue_users",),
                    ).fetchone()[0]
                )
            finally:
                if connection.execute(
                    "SELECT to_regclass(%s)",
                    ("public.telegram_identity_map",),
                ).fetchone()[0]:
                    connection.execute(rollback_sql)


if __name__ == "__main__":
    unittest.main()
