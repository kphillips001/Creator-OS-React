import os
import unittest
from contextlib import contextmanager
from uuid import UUID, uuid4

from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.telegram_identity_repository import (
    TelegramIdentityConflictError,
    TelegramIdentityRepository,
)
from app.services.telegram_identity_service import (
    DuplicateTelegramIdentityError,
    InactiveTelegramIdentityError,
    InvalidTelegramIdentityError,
    TelegramIdentityService,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "TEST_DATABASE_URL is required for PostgreSQL integration tests.",
)
class TelegramIdentityPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        @contextmanager
        def connection_factory():
            with connect(
                TEST_DATABASE_URL,
                row_factory=dict_row,
            ) as connection:
                yield connection

        cls.repository = TelegramIdentityRepository(connection_factory)
        cls.service = TelegramIdentityService(cls.repository)

        with connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, fanvue_account_id, fanvue_user_uuid
                    FROM public.fanvue_users
                    ORDER BY id
                    LIMIT 2;
                    """
                )
                cls.users = cursor.fetchall()

        if len(cls.users) < 2:
            raise unittest.SkipTest(
                "Two restored Fanvue users are required."
            )

        cls.connection_factory = staticmethod(connection_factory)

    def setUp(self):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "TRUNCATE public.telegram_identity_map "
                    "RESTART IDENTITY CASCADE;"
                )

    def create_first_mapping(self, telegram_user_id=700000001):
        user = self.users[0]
        self.repository.observe(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_user_id,
        )
        mapping, _ = self.repository.create_verified_mapping(
            telegram_user_id=telegram_user_id,
            fanvue_account_id=user["fanvue_account_id"],
            local_fanvue_user_id=user["id"],
            verification_method="POSTGRES_TEST",
            operator_source="TEST_SUITE",
            evidence={"synthetic": True},
        )
        return mapping

    def test_schema_uses_native_database_types(self):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                )
                types = {
                    row["column_name"]: row["data_type"]
                    for row in cursor.fetchall()
                }

        self.assertEqual(types["fanvue_account_id"], "bigint")
        self.assertEqual(types["local_fanvue_user_id"], "bigint")
        self.assertEqual(types["external_fanvue_user_uuid"], "uuid")

    def test_create_and_resolve_mapping_with_uuid(self):
        mapping = self.create_first_mapping()
        identity = self.service.resolve_telegram_identity(
            mapping.telegram_user_id
        )

        self.assertIsInstance(
            identity.external_fanvue_user_uuid,
            UUID,
        )
        self.assertEqual(
            identity.external_fanvue_user_uuid,
            self.users[0]["fanvue_user_uuid"],
        )
        self.assertEqual(
            identity.engine_user_id,
            f"{self.users[0]['fanvue_account_id']}:"
            f"{self.users[0]['id']}",
        )

    def test_database_duplicate_constraint_is_translated(self):
        mapping = self.create_first_mapping()

        with self.assertRaises(TelegramIdentityConflictError):
            self.repository.create_mapping(
                telegram_user_id=mapping.telegram_user_id,
                telegram_chat_id=mapping.telegram_chat_id,
                fanvue_account_id=mapping.fanvue_account_id,
                local_fanvue_user_id=mapping.local_fanvue_user_id,
                external_fanvue_user_uuid=(
                    mapping.external_fanvue_user_uuid
                ),
            )

    def test_duplicate_race_is_translated_by_service(self):
        mapping = self.create_first_mapping()
        real_repository = self.repository

        class RaceRepository:
            def get_by_telegram_user_id(self, *args, **kwargs):
                return None

            def get_by_local_user_id(self, *args, **kwargs):
                return None

            def create_mapping(self, **values):
                return real_repository.create_mapping(**values)

        race_service = TelegramIdentityService(RaceRepository())

        with self.assertRaises(DuplicateTelegramIdentityError):
            race_service.create_mapping(
                telegram_user_id=mapping.telegram_user_id,
                telegram_chat_id=mapping.telegram_chat_id,
                fanvue_account_id=mapping.fanvue_account_id,
                local_fanvue_user_id=mapping.local_fanvue_user_id,
                external_fanvue_user_uuid=(
                    mapping.external_fanvue_user_uuid
                ),
            )

    def test_invalid_canonical_triple_is_rejected(self):
        user = self.users[0]

        with self.assertRaises(InvalidTelegramIdentityError):
            self.service.create_mapping(
                telegram_user_id=700000002,
                telegram_chat_id=700000002,
                fanvue_account_id=user["fanvue_account_id"],
                local_fanvue_user_id=user["id"],
                external_fanvue_user_uuid=uuid4(),
            )

    def test_deactivate_and_reactivate(self):
        mapping = self.create_first_mapping()
        inactive = self.service.deactivate_mapping(mapping.id)
        self.assertFalse(inactive.is_active)

        with self.assertRaises(InactiveTelegramIdentityError):
            self.service.resolve_telegram_identity(
                mapping.telegram_user_id
            )

        active = self.service.update_mapping(
            mapping_id=mapping.id,
            telegram_chat_id=-700000001,
            fanvue_account_id=mapping.fanvue_account_id,
            local_fanvue_user_id=mapping.local_fanvue_user_id,
            external_fanvue_user_uuid=(
                mapping.external_fanvue_user_uuid
            ),
            is_active=True,
        )
        self.assertTrue(active.is_active)
        self.assertEqual(active.telegram_chat_id, -700000001)

    def test_update_to_another_valid_canonical_user(self):
        mapping = self.create_first_mapping()
        other = self.users[1]

        updated = self.service.update_mapping(
            mapping_id=mapping.id,
            telegram_chat_id=700000003,
            fanvue_account_id=other["fanvue_account_id"],
            local_fanvue_user_id=other["id"],
            external_fanvue_user_uuid=other["fanvue_user_uuid"],
        )

        self.assertEqual(
            updated.local_fanvue_user_id,
            other["id"],
        )
        self.assertEqual(
            updated.external_fanvue_user_uuid,
            other["fanvue_user_uuid"],
        )


if __name__ == "__main__":
    unittest.main()
