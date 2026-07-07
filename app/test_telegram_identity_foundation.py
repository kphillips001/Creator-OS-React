import unittest
from uuid import UUID

from app.models.telegram_identity import TelegramIdentityMapping
from app.repositories.telegram_identity_repository import (
    TelegramIdentityConflictError,
    TelegramIdentityIntegrityError,
)
from app.services.telegram_identity_service import (
    DuplicateTelegramIdentityError,
    InactiveTelegramIdentityError,
    InvalidTelegramIdentityError,
    TelegramIdentityService,
)


FANVUE_UUID_42 = UUID("00000000-0000-4000-8000-000000000042")
FANVUE_UUID_43 = UUID("00000000-0000-4000-8000-000000000043")


def build_mapping(
    *,
    mapping_id: int = 1,
    telegram_user_id: int = 10001,
    telegram_chat_id: int = 10001,
    fanvue_account_id: int = 1,
    local_fanvue_user_id: int = 42,
    external_fanvue_user_uuid: UUID = FANVUE_UUID_42,
    is_active: bool = True,
) -> TelegramIdentityMapping:
    return TelegramIdentityMapping(
        id=mapping_id,
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id,
        fanvue_account_id=fanvue_account_id,
        local_fanvue_user_id=local_fanvue_user_id,
        external_fanvue_user_uuid=external_fanvue_user_uuid,
        is_active=is_active,
    )


class FakeTelegramIdentityRepository:
    def __init__(self):
        self.mappings: list[TelegramIdentityMapping] = []

    def get_by_telegram_user_id(
        self,
        telegram_user_id,
        *,
        include_inactive=False,
    ):
        for mapping in self.mappings:
            if mapping.telegram_user_id != telegram_user_id:
                continue
            if include_inactive or mapping.is_active:
                return mapping
        return None

    def get_by_local_user_id(
        self,
        fanvue_account_id,
        local_fanvue_user_id,
        *,
        include_inactive=False,
    ):
        for mapping in self.mappings:
            if (
                mapping.fanvue_account_id != fanvue_account_id
                or mapping.local_fanvue_user_id
                != local_fanvue_user_id
            ):
                continue
            if include_inactive or mapping.is_active:
                return mapping
        return None

    def get_by_id(self, mapping_id):
        return next(
            (
                mapping
                for mapping in self.mappings
                if mapping.id == mapping_id
            ),
            None,
        )

    def create_mapping(self, **values):
        mapping = TelegramIdentityMapping(
            id=len(self.mappings) + 1,
            **values,
        )
        self.mappings.append(mapping)
        return mapping

    def update_mapping(self, *, mapping_id, **values):
        current = self.get_by_id(mapping_id)
        if not current:
            return None

        updated = TelegramIdentityMapping(
            id=current.id,
            telegram_user_id=current.telegram_user_id,
            **values,
        )
        self.mappings[self.mappings.index(current)] = updated
        return updated

    def deactivate_mapping(self, mapping_id):
        current = self.get_by_id(mapping_id)
        if not current:
            return None

        inactive = TelegramIdentityMapping(
            id=current.id,
            telegram_user_id=current.telegram_user_id,
            telegram_chat_id=current.telegram_chat_id,
            fanvue_account_id=current.fanvue_account_id,
            local_fanvue_user_id=current.local_fanvue_user_id,
            external_fanvue_user_uuid=(
                current.external_fanvue_user_uuid
            ),
            is_active=False,
        )
        self.mappings[self.mappings.index(current)] = inactive
        return inactive


class TelegramIdentityFoundationTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeTelegramIdentityRepository()
        self.service = TelegramIdentityService(self.repository)

    def test_create_mapping(self):
        mapping = self.service.create_mapping(
            telegram_user_id=10001,
            telegram_chat_id=10001,
            fanvue_account_id=1,
            local_fanvue_user_id=42,
            external_fanvue_user_uuid=FANVUE_UUID_42,
        )

        self.assertEqual(mapping.telegram_user_id, 10001)
        self.assertEqual(mapping.local_fanvue_user_id, 42)
        self.assertEqual(mapping.engine_user_id, "1:42")
        self.assertEqual(len(self.repository.mappings), 1)

    def test_resolve_mapping_returns_canonical_identity(self):
        self.repository.mappings.append(build_mapping())

        identity = self.service.resolve_telegram_identity(10001)

        self.assertEqual(identity.fanvue_account_id, 1)
        self.assertEqual(identity.local_fanvue_user_id, 42)
        self.assertEqual(
            identity.external_fanvue_user_uuid,
            FANVUE_UUID_42,
        )
        self.assertEqual(identity.engine_user_id, "1:42")

    def test_duplicate_telegram_user_is_rejected(self):
        self.repository.mappings.append(build_mapping())

        with self.assertRaises(DuplicateTelegramIdentityError):
            self.service.create_mapping(
                telegram_user_id=10001,
                telegram_chat_id=20002,
                fanvue_account_id=1,
                local_fanvue_user_id=43,
                external_fanvue_user_uuid=FANVUE_UUID_43,
            )

    def test_duplicate_canonical_user_is_rejected(self):
        self.repository.mappings.append(build_mapping())

        with self.assertRaises(DuplicateTelegramIdentityError):
            self.service.create_mapping(
                telegram_user_id=20002,
                telegram_chat_id=20002,
                fanvue_account_id=1,
                local_fanvue_user_id=42,
                external_fanvue_user_uuid=FANVUE_UUID_42,
            )

    def test_inactive_mapping_is_not_resolved(self):
        self.repository.mappings.append(
            build_mapping(is_active=False)
        )

        with self.assertRaises(InactiveTelegramIdentityError):
            self.service.resolve_telegram_identity(10001)

    def test_deactivate_mapping(self):
        self.repository.mappings.append(build_mapping())

        mapping = self.service.deactivate_mapping(1)

        self.assertFalse(mapping.is_active)
        with self.assertRaises(InactiveTelegramIdentityError):
            self.service.resolve_telegram_identity(10001)

    def test_update_mapping(self):
        self.repository.mappings.append(build_mapping())

        mapping = self.service.update_mapping(
            mapping_id=1,
            telegram_chat_id=-100123,
            fanvue_account_id=1,
            local_fanvue_user_id=42,
            external_fanvue_user_uuid=FANVUE_UUID_42,
        )

        self.assertEqual(mapping.telegram_chat_id, -100123)
        self.assertTrue(mapping.is_active)

    def test_uuid_string_is_parsed_and_normalized(self):
        mapping = self.service.create_mapping(
            telegram_user_id=10001,
            telegram_chat_id=10001,
            fanvue_account_id=1,
            local_fanvue_user_id=42,
            external_fanvue_user_uuid=(
                "00000000-0000-4000-8000-000000000042"
            ),
        )

        self.assertIsInstance(mapping.external_fanvue_user_uuid, UUID)
        self.assertEqual(
            mapping.external_fanvue_user_uuid,
            FANVUE_UUID_42,
        )

    def test_invalid_uuid_is_rejected(self):
        with self.assertRaises(InvalidTelegramIdentityError):
            self.service.create_mapping(
                telegram_user_id=10001,
                telegram_chat_id=10001,
                fanvue_account_id=1,
                local_fanvue_user_id=42,
                external_fanvue_user_uuid="not-a-uuid",
            )

    def test_non_boolean_active_state_is_rejected(self):
        self.repository.mappings.append(build_mapping())

        with self.assertRaises(InvalidTelegramIdentityError):
            self.service.update_mapping(
                mapping_id=1,
                telegram_chat_id=10001,
                fanvue_account_id=1,
                local_fanvue_user_id=42,
                external_fanvue_user_uuid=FANVUE_UUID_42,
                is_active=1,
            )

    def test_repository_duplicate_race_is_translated(self):
        class ConflictRepository(FakeTelegramIdentityRepository):
            def create_mapping(self, **values):
                raise TelegramIdentityConflictError("duplicate")

        service = TelegramIdentityService(ConflictRepository())

        with self.assertRaises(DuplicateTelegramIdentityError):
            service.create_mapping(
                telegram_user_id=10001,
                telegram_chat_id=10001,
                fanvue_account_id=1,
                local_fanvue_user_id=42,
                external_fanvue_user_uuid=FANVUE_UUID_42,
            )

    def test_repository_integrity_error_is_translated(self):
        class IntegrityRepository(FakeTelegramIdentityRepository):
            def create_mapping(self, **values):
                raise TelegramIdentityIntegrityError("invalid mapping")

        service = TelegramIdentityService(IntegrityRepository())

        with self.assertRaises(InvalidTelegramIdentityError):
            service.create_mapping(
                telegram_user_id=10001,
                telegram_chat_id=10001,
                fanvue_account_id=1,
                local_fanvue_user_id=42,
                external_fanvue_user_uuid=FANVUE_UUID_42,
            )


if __name__ == "__main__":
    unittest.main()
