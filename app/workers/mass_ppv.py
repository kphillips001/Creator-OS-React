from app.services.mass_ppv_worker_loop_service import MassPPVWorkerLoopService


def main() -> None:
    MassPPVWorkerLoopService().run_loop()


if __name__ == "__main__":
    main()
