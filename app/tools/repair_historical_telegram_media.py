"""Dry-run by default; use --execute only after reviewing the inventory."""

import argparse
import json

from app.services.historical_telegram_media_normalization_service import (
    HistoricalTelegramMediaNormalizationService,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    service = HistoricalTelegramMediaNormalizationService()
    values = service.execute() if args.execute else service.dry_run()
    print(json.dumps([
        value if isinstance(value, dict) else value.__dict__ for value in values
    ], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
