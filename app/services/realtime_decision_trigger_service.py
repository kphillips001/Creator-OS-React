from app.main import decision_engine
from app.database import get_db_connection

from app.services.fanvue_api_service import FanvueAPIService
from app.config import ENABLE_REALTIME_FANVUE_SEND

from app.repositories.chat_message_repository import (
    get_or_create_chat_thread,
    save_chat_message,
)

from app.services.decisionengine_refresh_hook_service import (
    DecisionEngineRefreshHookService,
)

from app.services.global_send_execution_guard_service import (
    GlobalSendExecutionGuardService,
)


class RealtimeDecisionTriggerService:
    """
    SECTION 3.1 / 3C

    Realtime inbound Fanvue message
    → DecisionEngine
    → GPT response generated
    → outbound response saved locally
    → optional Fanvue outbound send

    IMPORTANT:
    Fanvue outbound sending is controlled by:
    ENABLE_REALTIME_FANVUE_SEND
    and GlobalSendExecutionGuardService.
    """

    def __init__(self):
        self.fanvue_api = None

        self.refresh_hook_service = (
            DecisionEngineRefreshHookService()
        )

        self.global_execution_guard = (
            GlobalSendExecutionGuardService()
        )

    def trigger_for_inbound_message(
        self,
        fanvue_user_id: int,
        fanvue_account_id: int,
        chat_message_id: int,
        message_text: str,
        thread_id: str | None = None,

        # 3D.17.6
        monetization_event: dict | None = None,
        buyer_stats: dict | None = None,
        memory_sync_result: dict | None = None,
    ):
        print("\n[REALTIME DECISION TRIGGER]")
        print(f"fanvue_user_id={fanvue_user_id}")
        print(f"fanvue_account_id={fanvue_account_id}")
        print(f"chat_message_id={chat_message_id}")
        print(f"thread_id={thread_id}")
        print(f"message_text={message_text}")

        if not fanvue_user_id or not fanvue_account_id:
            return {
                "success": False,
                "triggered": False,
                "error": "Missing fanvue_user_id or fanvue_account_id",
            }

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id,
                        fanvue_account_id
                    FROM fanvue_users
                    WHERE fanvue_user_uuid = %s
                      AND fanvue_account_id = %s
                    LIMIT 1;
                    """,
                    (
                        str(fanvue_user_id),
                        int(fanvue_account_id),
                    ),
                )

                row = cursor.fetchone()

        if not row:
            print("[REALTIME DECISION SKIPPED]")
            print("Reason: local_user_not_found")
            print(f"fanvue_user_uuid={fanvue_user_id}")
            print(f"fanvue_account_id={fanvue_account_id}")

            return {
                "success": False,
                "triggered": False,
                "skipped": True,
                "reason": "local_user_not_found",
                "fanvue_user_uuid": str(fanvue_user_id),
                "fanvue_account_id": int(fanvue_account_id),
            }

        local_fanvue_user_id = row["id"]
        local_fanvue_account_id = row["fanvue_account_id"]

        self.fanvue_api = FanvueAPIService(
            fanvue_account_id=local_fanvue_account_id,
        )

        engine_user_id = (
            f"{local_fanvue_account_id}:"
            f"{local_fanvue_user_id}"
        )

        chat_history = []
        decisionengine_injection = None

        if monetization_event:
            refresh_payload = (
                self.refresh_hook_service
                .build_refresh_payload(
                    monetization_event=monetization_event,
                    buyer_stats=buyer_stats,
                    memory_sync_result=memory_sync_result,
                )
            )

            decisionengine_injection = (
                refresh_payload.get(
                    "decisionengine_injection"
                )
            )

            print("\n[DECISIONENGINE INJECTION]")
            print(decisionengine_injection)

        decision_result = decision_engine.process_message(
            user_id=engine_user_id,
            message=message_text,
            chat_history=chat_history,
            runtime_injection=decisionengine_injection,
        )

        if not decision_result:
            return {
                "success": False,
                "triggered": True,
                "engine_user_id": engine_user_id,
                "error": "DecisionEngine returned no result",
            }

        response_text = decision_result.get("response")

        local_thread_id = None
        outbound_message = None

        if thread_id:
            local_thread = get_or_create_chat_thread(
                fanvue_account_id=local_fanvue_account_id,
                fanvue_user_id=local_fanvue_user_id,
                fanvue_chat_uuid=str(thread_id),
            )

            local_thread_id = local_thread["id"]

        if response_text and local_thread_id:
            outbound_message = save_chat_message(
                fanvue_account_id=local_fanvue_account_id,
                thread_id=local_thread_id,
                fanvue_user_id=local_fanvue_user_id,
                direction="outbound",
                sender_type="bot",
                text=response_text,
            )

        fanvue_send_result = None
        execution_guard_result = None

        if response_text:
            execution_guard_result = (
                self.global_execution_guard.validate_execution(
                    execution_type="chat_reply",
                    dry_run=not ENABLE_REALTIME_FANVUE_SEND,
                )
            )

            print("\n[GLOBAL EXECUTION GUARD]")
            print("execution_type=chat_reply")
            print(execution_guard_result)

            if execution_guard_result.get("blocked"):
                print(
                    "\n[CHAT REPLY BLOCKED] "
                    f"{execution_guard_result.get('reason')}"
                )

                fanvue_send_result = {
                    "success": False,
                    "blocked": True,
                    "reason": execution_guard_result.get("reason"),
                    "execution_guard_result": (
                        execution_guard_result
                    ),
                }

            elif not ENABLE_REALTIME_FANVUE_SEND:
                print(
                    "[REALTIME FANVUE SEND SKIPPED] "
                    "disabled by config"
                )

                fanvue_send_result = {
                    "success": True,
                    "sent": False,
                    "status": "send_disabled",
                    "reason": "realtime_fanvue_send_disabled",
                    "execution_guard_result": (
                        execution_guard_result
                    ),
                }

            else:
                try:
                    print("\n[REALTIME FANVUE SEND START]")

                    fanvue_send_result = (
                        self.fanvue_api.send_chat_message(
                            user_uuid=str(fanvue_user_id),
                            payload={
                                "text": response_text,
                                "payload_type": "realtime_chat",
                            },
                            fanvue_account_id=(
                                local_fanvue_account_id
                            ),
                            fanvue_user_id=(
                                local_fanvue_user_id
                            ),
                        )
                    )

                    print("[REALTIME FANVUE SEND RESULT]")
                    print(fanvue_send_result)

                except Exception as send_error:
                    print("[REALTIME FANVUE SEND ERROR]")
                    print(send_error)

                    fanvue_send_result = {
                        "success": False,
                        "error": str(send_error),
                        "execution_guard_result": (
                            execution_guard_result
                        ),
                    }

        print("[REALTIME DECISION RESULT]")
        print(f"engine_user_id={engine_user_id}")
        print(f"response={response_text}")
        print(f"fanvue_send_enabled={ENABLE_REALTIME_FANVUE_SEND}")
        print(f"fanvue_send_result={fanvue_send_result}")

        return {
            "success": True,
            "triggered": True,
            "sent_to_fanvue": (
                bool(
                    fanvue_send_result
                    and fanvue_send_result.get("success")
                    and fanvue_send_result.get("sent", True)
                )
            ),
            "engine_user_id": engine_user_id,
            "chat_message_id": chat_message_id,
            "outbound_message_id": (
                outbound_message["id"]
                if outbound_message
                else None
            ),
            "thread_id": thread_id,
            "local_thread_id": local_thread_id,
            "response": response_text,
            "decision_result": decision_result,
            "decisionengine_injection": (
                decisionengine_injection
            ),
            "fanvue_send_enabled": ENABLE_REALTIME_FANVUE_SEND,
            "fanvue_send_result": fanvue_send_result,
            "execution_guard_result": execution_guard_result,
            "fanvue_user_id": local_fanvue_user_id,
            "fanvue_account_id": local_fanvue_account_id,
            "webhook_fanvue_user_uuid": str(fanvue_user_id),
            "webhook_fanvue_account_uuid": str(fanvue_account_id),
        }