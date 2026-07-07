from app.services.mass_ppv_worker_loop_service import (
    MassPPVWorkerLoopService,
)


def main():
    print(
        "\n=== MASS PPV WORKER LOOP SERVICE TEST ===\n"
    )

    service = MassPPVWorkerLoopService()

    result = service.run_loop(
        limit=5,
        sleep_seconds=2,
        max_cycles=2,
    )

    print(
        "\n=== MASS PPV WORKER LOOP RESULT ===\n"
    )

    print(result)

    print(
        "\n=== MASS PPV WORKER LOOP SERVICE TEST COMPLETE ===\n"
    )


if __name__ == "__main__":
    main()