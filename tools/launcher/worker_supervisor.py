import argparse

from app.services.worker_launcher_supervision_service import WorkerLauncherSupervisionService


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start-enabled", "stop-managed", "configuration", "monitor-telegram"))
    args = parser.parse_args()
    service = WorkerLauncherSupervisionService()
    if args.action == "start-enabled": results = service.start_enabled()
    elif args.action == "stop-managed": results = service.stop_managed()
    elif args.action == "configuration": results = service.configuration()
    else:
        service.monitor_telegram()
        return 0
    for result in results: print(result)
    failed = {"startup_failed", "startup_blocked", "shutdown_blocked"}
    return 1 if any(result.get("lastLauncherAction") in failed for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
