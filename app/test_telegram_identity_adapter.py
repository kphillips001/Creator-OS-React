import ast
import unittest
from pathlib import Path

from app.models.telegram_identity import TelegramMvpIdentityInput
from app.services.telegram_identity_adapter import (
    POSTGRES_BIGINT_MAX,
    InvalidTelegramMvpIdentityError,
    TelegramIdentityAdapter,
)


class TelegramIdentityAdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = TelegramIdentityAdapter(engine_account_id=7)

    def test_mapping_is_deterministic(self):
        identity = TelegramMvpIdentityInput(
            telegram_user_id=123456789,
            telegram_chat_id=987654321,
        )

        first = self.adapter.adapt(identity)
        second = self.adapter.adapt(identity)

        self.assertEqual(first, second)
        self.assertEqual(first.engine_user_id, "7:-123456789")

    def test_optional_chat_id_does_not_change_user_identity(self):
        without_chat = self.adapter.adapt(
            TelegramMvpIdentityInput(telegram_user_id=123456789)
        )
        with_private_chat = self.adapter.adapt(
            TelegramMvpIdentityInput(
                telegram_user_id=123456789,
                telegram_chat_id=123456789,
            )
        )
        with_negative_chat = self.adapter.adapt(
            TelegramMvpIdentityInput(
                telegram_user_id=123456789,
                telegram_chat_id=-100123456789,
            )
        )

        self.assertEqual(without_chat, with_private_chat)
        self.assertEqual(without_chat, with_negative_chat)

    def test_different_user_ids_generate_different_keys(self):
        first = self.adapter.adapt(
            TelegramMvpIdentityInput(telegram_user_id=10001)
        )
        second = self.adapter.adapt(
            TelegramMvpIdentityInput(telegram_user_id=10002)
        )

        self.assertNotEqual(first.engine_user_id, second.engine_user_id)

    def test_generated_key_uses_negative_compatibility_namespace(self):
        result = self.adapter.adapt(
            TelegramMvpIdentityInput(telegram_user_id=42)
        )
        account_id, temporary_user_id = result.engine_user_id.split(":")

        self.assertEqual(account_id, "7")
        self.assertEqual(int(temporary_user_id), -42)
        self.assertLess(int(temporary_user_id), 0)

    def test_largest_supported_telegram_user_id_is_deterministic(self):
        result = self.adapter.adapt(
            TelegramMvpIdentityInput(
                telegram_user_id=POSTGRES_BIGINT_MAX
            )
        )

        self.assertEqual(
            result.engine_user_id,
            f"7:-{POSTGRES_BIGINT_MAX}",
        )

    def test_invalid_user_ids_are_rejected(self):
        invalid_values = (
            None,
            True,
            False,
            "123",
            0,
            -1,
            POSTGRES_BIGINT_MAX + 1,
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(InvalidTelegramMvpIdentityError):
                    self.adapter.adapt(
                        TelegramMvpIdentityInput(telegram_user_id=value)
                    )

    def test_invalid_optional_chat_ids_are_rejected(self):
        invalid_values = (
            True,
            "123",
            0,
            POSTGRES_BIGINT_MAX + 1,
            -(2**63) - 1,
        )

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(InvalidTelegramMvpIdentityError):
                    self.adapter.adapt(
                        TelegramMvpIdentityInput(
                            telegram_user_id=123,
                            telegram_chat_id=value,
                        )
                    )

    def test_invalid_engine_account_ids_are_rejected(self):
        for value in (None, True, "1", 0, -1, POSTGRES_BIGINT_MAX + 1):
            with self.subTest(value=value):
                with self.assertRaises(InvalidTelegramMvpIdentityError):
                    TelegramIdentityAdapter(engine_account_id=value)

    def test_wrong_input_contract_is_rejected(self):
        with self.assertRaises(InvalidTelegramMvpIdentityError):
            self.adapter.adapt(123)

    def test_adapter_has_no_external_or_persistence_imports(self):
        path = (
            Path(__file__).resolve().parent
            / "services"
            / "telegram_identity_adapter.py"
        )
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        forbidden_fragments = (
            "psycopg",
            "sqlalchemy",
            "repositories",
            "database",
            "telegram.",
            "telethon",
            "aiogram",
            "fanvue",
            "kviqa",
            "core_user",
            "requests",
            "httpx",
        )
        for module in imports:
            with self.subTest(module=module):
                self.assertFalse(
                    any(fragment in module.lower() for fragment in forbidden_fragments),
                    module,
                )


if __name__ == "__main__":
    unittest.main()
