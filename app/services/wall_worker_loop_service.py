import time

from app.services.wall_worker_service import (
    WallWorkerService,
)


class WallWorkerLoopService:

    def __init__(
        self,
        poll_interval_seconds: int = 60,
    ):
        self.poll_interval_seconds = (
            poll_interval_seconds
        )

        self.worker_service = (
            WallWorkerService()
        )

    # =====================================================
    # RUN ONCE
    # =====================================================

    def run_once(
        self,
        limit: int = 10,
    ) -> dict:

        result = (
            self.worker_service
            .process_wall_queue(
                limit=limit,
            )
        )

        return result

    # =====================================================
    # RUN FOREVER
    # =====================================================

    def run_forever(
        self,
        limit: int = 10,
    ):

        print(
            "\n=== WALL WORKER LOOP STARTED ===\n"
        )

        while True:

            result = self.run_once(
                limit=limit,
            )

            print(
                "[WALL WORKER LOOP RESULT]",
                result,
            )

            time.sleep(
                self.poll_interval_seconds
            )