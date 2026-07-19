from app.services.wall_worker_loop_service import WallWorkerLoopService


def main() -> None:
    WallWorkerLoopService().run_forever()


if __name__ == "__main__":
    main()
