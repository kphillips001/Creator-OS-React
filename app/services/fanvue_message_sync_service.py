from app.services.fanvue_api_service import FanvueAPIService
from app.repositories.fanvue_message_repository import (
    save_fanvue_chat_message,
    get_latest_message_timestamp,
)

class FanvueMessageSyncService:
    def __init__(
        self,
        fanvue_account_id: int,
    ):
        self.fanvue_account_id = fanvue_account_id

        self.fanvue_api = FanvueAPIService(
            fanvue_account_id=self.fanvue_account_id,
        )

    def fetch_chat_threads(
        self,
        page: int = 1,
        size: int = 15,
        sort_by: str = "most_recent_messages",
        filter_value: str | None = None,
    ) -> dict:
        """
        13A-1 — Thread Fetch.

        Fetches chat threads from Fanvue.
        No DB writes yet.
        """

        print("[13A-1 THREAD FETCH START]")

        result = self.fanvue_api.list_chats(
            page=page,
            size=size,
            sort_by=sort_by,
            filter_value=filter_value,
        )

        if not result.get("success"):
            print("[13A-1 THREAD FETCH FAILED]")
            return result

        threads = result.get("data", [])
        pagination = result.get("pagination", {})

        print(f"[13A-1 THREADS FOUND] {len(threads)}")
        print(f"[13A-1 PAGINATION] {pagination}")

        normalized_threads = []

        for chat in threads:
            user = chat.get("user") or {}
            last_message = chat.get("lastMessage") or {}

            normalized = {
                "fanvue_user_uuid": user.get("uuid"),
                "handle": user.get("handle"),
                "display_name": user.get("displayName"),
                "nickname": user.get("nickname"),
                "last_message_at": chat.get("lastMessageAt"),
                "is_read": chat.get("isRead"),
                "is_muted": chat.get("isMuted"),
                "unread_messages_count": chat.get("unreadMessagesCount", 0),
                "last_message_uuid": last_message.get("uuid"),
                "last_message_text": last_message.get("text"),
                "last_message_sent_at": last_message.get("sentAt"),
                "last_message_sender_uuid": last_message.get("senderUuid"),
                "raw": chat,
            }

            normalized_threads.append(normalized)

        return {
            "success": True,
            "count": len(normalized_threads),
            "threads": normalized_threads,
            "pagination": pagination,
        }
    
    def fetch_messages_for_thread(
        self,
        fanvue_user_uuid: str,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """
        13A-2 — Message Fetch Per Thread
        """

        print("[13A-2 MESSAGE FETCH START]")
        print(f"user_uuid={fanvue_user_uuid}")

        result = self.fanvue_api.list_messages(
            user_uuid=fanvue_user_uuid,
            page=page,
            size=size,
        )

        if not result.get("success"):
            print("[13A-2 MESSAGE FETCH FAILED]")
            return result

        messages = result.get("data", [])
        pagination = result.get("pagination", {})

        print(f"[13A-2 MESSAGES FOUND] {len(messages)}")

        normalized_messages = []

        for msg in messages:
            normalized = {
                "message_uuid": msg.get("uuid"),
                "text": msg.get("text"),
                "sender_uuid": msg.get("senderUuid"),
                "sent_at": msg.get("sentAt"),
                "is_read": msg.get("isRead"),
                "raw": msg,
            }

            normalized_messages.append(normalized)

        return {
            "success": True,
            "count": len(normalized_messages),
            "messages": normalized_messages,
            "pagination": pagination,
        }
    
    def fetch_new_messages_for_thread(
        self,
        fanvue_user_uuid: str,
        last_seen_timestamp: str | None = None,
    ) -> dict:
        """
        13A-3 — Incremental Message Sync

        Fetch only NEW messages after last_seen_timestamp.
        """

        print("[13A-3 INCREMENTAL SYNC START]")
        print(f"user_uuid={fanvue_user_uuid}")
        print(f"last_seen_timestamp={last_seen_timestamp}")

        result = self.fetch_messages_for_thread(
            fanvue_user_uuid=fanvue_user_uuid,
            page=1,
            size=20,
        )

        if not result.get("success"):
            print("[13A-3 FAILED]")
            return result

        messages = result.get("messages", [])

        if not last_seen_timestamp:
            print("[13A-3 NO TIMESTAMP PROVIDED — RETURN ALL]")
            return result

        new_messages = []

        for msg in messages:
            msg_time = msg.get("sent_at")

            if msg_time and msg_time > last_seen_timestamp:
                new_messages.append(msg)

        print(f"[13A-3 NEW MESSAGES FOUND] {len(new_messages)}")

        return {
            "success": True,
            "count": len(new_messages),
            "messages": new_messages,
        }
    
    def dedupe_messages(
        self,
        messages: list,
        seen_message_uuids: set | None = None,
    ) -> dict:
        """
        13A-4 — Deduplication

        Removes messages already seen.
        """

        print("[13A-4 DEDUP START]")

        if seen_message_uuids is None:
            seen_message_uuids = set()

        new_messages = []
        skipped = 0

        for msg in messages:
            msg_uuid = msg.get("message_uuid")

            if not msg_uuid:
                continue

            if msg_uuid in seen_message_uuids:
                skipped += 1
                continue

            seen_message_uuids.add(msg_uuid)
            new_messages.append(msg)

        print(f"[13A-4 NEW UNIQUE] {len(new_messages)}")
        print(f"[13A-4 SKIPPED DUPES] {skipped}")

        return {
            "messages": new_messages,
            "seen_message_uuids": seen_message_uuids,
            "skipped": skipped,
        }
    
    def process_inbound_messages(
        self,
        messages: list,
        my_user_uuid: str,
    ) -> list:
        """
        13A-5 — Chat Trigger Pipeline (Inbound Detection)

        Filters only inbound messages (not sent by us).
        """

        print("[13A-5 INBOUND PROCESS START]")
        print(f"my_user_uuid={my_user_uuid}")

        inbound_messages = []

        for msg in messages:
            sender_uuid = msg.get("sender_uuid")

            # Skip messages we sent
            if sender_uuid == my_user_uuid:
                continue

            inbound_messages.append(msg)

        print(f"[13A-5 INBOUND COUNT] {len(inbound_messages)}")

        for msg in inbound_messages:
            print("\n[INBOUND MESSAGE DETECTED]")
            print(f"user_uuid: {msg.get('sender_uuid')}")
            print(f"text: {msg.get('text')}")
            print(f"sent_at: {msg.get('sent_at')}")

        return inbound_messages
    
    def sync_messages_to_db(
        self,
        fanvue_account_id: int,
        fanvue_user_uuid: str,
        my_user_uuid: str,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """
        13A-6 — Store synced Fanvue messages in DB.
        """

        print("[13A-6 DB MESSAGE SYNC START]")
        if fanvue_account_id != self.fanvue_account_id:
            return {
                "success": False,
                "status": "blocked",
                "reason": "fanvue_account_id_mismatch",
                "service_account_id": self.fanvue_account_id,
                "requested_account_id": fanvue_account_id,
            }
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"fanvue_user_uuid={fanvue_user_uuid}")

        last_seen_timestamp = get_latest_message_timestamp(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_uuid=fanvue_user_uuid,
        )

        print(f"[13A-6 LAST DB MESSAGE TIMESTAMP] {last_seen_timestamp}")

        result = self.fetch_messages_for_thread(
            fanvue_user_uuid=fanvue_user_uuid,
            page=page,
            size=size,
        )

        if not result.get("success"):
            return result

        messages = result.get("messages", [])

        if last_seen_timestamp:
            messages = [
                msg for msg in messages
                if msg.get("sent_at") and msg.get("sent_at") > last_seen_timestamp
            ]

        inserted = 0
        skipped = 0

        for msg in messages:
            save_result = save_fanvue_chat_message(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_uuid=fanvue_user_uuid,
                message=msg,
                my_user_uuid=my_user_uuid,
            )

            if save_result.get("inserted"):
                inserted += 1
            else:
                skipped += 1

        print(f"[13A-6 INSERTED] {inserted}")
        print(f"[13A-6 SKIPPED] {skipped}")

        return {
            "success": True,
            "fetched": len(messages),
            "inserted": inserted,
            "skipped": skipped,
        }