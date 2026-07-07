from app.repositories.memory_repository import (
    get_user_memory_row,
    set_memory_field,
    update_memory_fields,
    reset_user_memory,
    increment_message_count,
    increment_outbound_message_count,
    create_user_memory_row,
)


class MemoryService:
    def _parse_user_id(self, user_id: str) -> tuple[int, int]:
        """
        Expected format: 'fanvue_account_id:fanvue_user_id'
        Example: '2:4'
        """
        try:
            account_id_str, fanvue_user_id_str = user_id.split(":")
            return int(account_id_str), int(fanvue_user_id_str)
        except ValueError as exc:
            raise ValueError(
                f"Invalid user_id format '{user_id}'. Expected 'account_id:user_id'."
            ) from exc

    def get_user_memory(self, user_id: str) -> dict:
        fanvue_account_id, fanvue_user_id = self._parse_user_id(user_id)
        row = get_user_memory_row(fanvue_account_id, fanvue_user_id)
        return row if row else {}

    def update_user_memory(self, user_id: str, data: dict) -> None:
        fanvue_account_id, fanvue_user_id = self._parse_user_id(user_id)
        update_memory_fields(fanvue_account_id, fanvue_user_id, data)

    def set_field(self, user_id: str, key: str, value) -> None:
        fanvue_account_id, fanvue_user_id = self._parse_user_id(user_id)
        set_memory_field(fanvue_account_id, fanvue_user_id, key, value)

    def get_field(self, user_id: str, key: str, default=None):
        memory = self.get_user_memory(user_id)
        return memory.get(key, default)

    def seed_test_memory(self, user_id: str) -> dict:
        self.update_user_memory(
            user_id,
            {
                "last_user_message": "Kevin",
                "last_bot_response": "VIP content",
            },
        )
        return self.get_user_memory(user_id)

    def clear_user_memory(self, user_id: str) -> None:
        fanvue_account_id, fanvue_user_id = self._parse_user_id(user_id)
        reset_user_memory(fanvue_account_id, fanvue_user_id)

    def increment_inbound_message(self, user_id: str) -> dict:
        fanvue_account_id, fanvue_user_id = self._parse_user_id(user_id)
        row = increment_message_count(fanvue_account_id, fanvue_user_id)
        return row if row else {}

    def increment_outbound_message(self, user_id: str) -> dict:
        fanvue_account_id, fanvue_user_id = self._parse_user_id(user_id)
        row = increment_outbound_message_count(fanvue_account_id, fanvue_user_id)
        return row if row else {}
    
    def get_or_create_user_memory(self, user_id: str) -> dict:
        fanvue_account_id, fanvue_user_id = self._parse_user_id(user_id)
        row = get_user_memory_row(fanvue_account_id, fanvue_user_id)

        if row:
            return row

        return create_user_memory_row(fanvue_account_id, fanvue_user_id)