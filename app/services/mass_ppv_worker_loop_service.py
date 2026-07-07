import time

from app.services.mass_ppv_worker_service import (
    MassPPVWorkerService,
)


class MassPPVWorkerLoopService:
    """
    Mass PPV Worker Loop Service

    PURPOSE:
    Runs the Mass PPV queue worker repeatedly.

    IMPORTANT:
    This does NOT bypass safety.
    All sends still flow through:

    MassPPVWorkerService
    -> MassPPVSendService
    -> ContentDeliveryGuardService
    -> GlobalAutomationSafetyService
    """

    def __init__(self):
        self.worker_service = MassPPVWorkerService()

    def run_once(
        self,
        limit: int = 25,
    ):
        print(
            "\n[MASS PPV WORKER LOOP] "
            "run_once starting"
        )

        results = (
            self.worker_service
            .process_all_available_queue(
                pending_limit=limit,
                retry_limit=5,
            )
        )

        print(
            "[MASS PPV WORKER LOOP] "
            f"run_once complete processed={len(results)}"
        )

        return {
            "success": True,
            "mode": "once",
            "processed_count": len(results),
            "results": results,
        }

    def run_loop(
        self,
        limit: int = 25,
        sleep_seconds: int = 30,
        max_cycles: int | None = None,
    ):
        print(
            "\n[MASS PPV WORKER LOOP START]"
        )

        cycle = 0
        all_results = []

        while True:
            cycle += 1

            print(
                f"\n[MASS PPV WORKER LOOP CYCLE] "
                f"cycle={cycle}"
            )

            result = self.run_once(
                limit=limit,
            )

            all_results.append(result)

            if max_cycles is not None and cycle >= max_cycles:
                print(
                    "\n[MASS PPV WORKER LOOP STOP] "
                    f"max_cycles={max_cycles}"
                )
                break

            print(
                f"[MASS PPV WORKER LOOP SLEEP] "
                f"seconds={sleep_seconds}"
            )

            time.sleep(sleep_seconds)

        return {
            "success": True,
            "mode": "loop",
            "cycles": cycle,
            "results": all_results,
        }