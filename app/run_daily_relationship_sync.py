import json
from datetime import datetime
from pathlib import Path

from app.services.fanvue_relationship_sync_orchestrator import FanvueRelationshipSyncOrchestrator


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "relationship_sync.log"
LATEST_JSON_FILE = LOG_DIR / "relationship_sync_latest.json"


def main():
    LOG_DIR.mkdir(exist_ok=True)

    print("\n=== DAILY FANVUE RELATIONSHIP SYNC START ===\n")

    orchestrator = FanvueRelationshipSyncOrchestrator(
        fanvue_account_id=1  # Amanda
    )

    result = orchestrator.sync_current_relationships()

    summary = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "fanvue_account_id": 1,
        "found": result.get("found", 0),
        "saved": result.get("saved", 0),
        "missing": result.get("missing", 0),
    }

    summary_line = (
        f"{summary['ran_at']} | "
        f"account={summary['fanvue_account_id']} | "
        f"found={summary['found']} | "
        f"saved={summary['saved']} | "
        f"missing={summary['missing']}"
    )

    print("\n=== DAILY FANVUE RELATIONSHIP SYNC COMPLETE ===")
    print(summary_line)

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(summary_line + "\n")

    with open(LATEST_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()