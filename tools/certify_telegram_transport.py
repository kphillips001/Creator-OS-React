"""Operator CLI for the single authorized neutral test campaign. No arbitrary peer/content."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.telegram_transport_certification_service import (
    TelegramTransportCertificationService, operation_id,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "enqueue-text", "enqueue-media"))
    args = parser.parse_args()
    service = TelegramTransportCertificationService()
    if args.action != "status":
        service.enqueue(args.action.removeprefix("enqueue-"))
    print(json.dumps({kind: asdict(row) if (row := service.repository.get(operation_id(kind)))
                      else None for kind in ("text", "media")}, default=str, indent=2))


if __name__ == "__main__":
    main()
