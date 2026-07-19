from app.services.delayed_message_worker_loop_service import DelayedMessageWorkerLoopService


def main() -> None:
    DelayedMessageWorkerLoopService().start_loop()


if __name__ == "__main__":
    main()
