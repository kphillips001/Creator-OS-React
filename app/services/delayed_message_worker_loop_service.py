import logging
import time
import traceback

from app.services.delayed_message_worker_service import (
    DelayedMessageWorkerService,
)


class DelayedMessageWorkerLoopService:
    """
    Delayed Message Worker Loop Service

    PURPOSE:
    Continuously processes delayed/scheduled
    messages from the delayed queue.

    FLOW:
    while True
    → process_due_messages()
    → sleep(interval)
    → repeat safely

    IMPORTANT:
    - crash protected
    - operational logging
    - safe continuous execution
    """

    def __init__(
        self,
        poll_interval_seconds: int = 15,
    ):
        self.logger = logging.getLogger(__name__)

        self.poll_interval_seconds = (
            poll_interval_seconds
        )

        self.worker_service = (
            DelayedMessageWorkerService()
        )

    def start_loop(self):
        self.logger.info(
            "[DELAYED WORKER LOOP] "
            "Starting delayed worker loop..."
        )

        while True:
            try:
                results = (
                    self.worker_service
                    .process_due_messages()
                )

                if results:
                    self.logger.info(
                        f"[DELAYED WORKER LOOP] "
                        f"processed={len(results)}"
                    )

                    for result in results:
                        self.logger.info(
                            f"[DELAYED RESULT] "
                            f"{result}"
                        )

                else:
                    self.logger.info(
                        "[DELAYED WORKER LOOP] "
                        "No due delayed messages"
                    )

            except Exception as e:
                self.logger.error(
                    f"[DELAYED WORKER LOOP ERROR] "
                    f"{e}"
                )

                traceback.print_exc()

            time.sleep(
                self.poll_interval_seconds
            )