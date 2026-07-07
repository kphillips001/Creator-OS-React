import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from app.repositories.fanvue_user_repository import get_relationship_stats
from app.services.fanvue_relationship_sync_orchestrator import FanvueRelationshipSyncOrchestrator


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "relationship_sync.log"
LATEST_JSON_FILE = LOG_DIR / "relationship_sync_latest.json"


def write_sync_log(result: dict, stats: dict, fanvue_account_id: int):
    LOG_DIR.mkdir(exist_ok=True)

    summary = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "fanvue_account_id": fanvue_account_id,
        "found": result.get("found", 0),
        "saved": result.get("saved", 0),
        "missing": result.get("missing", 0),
        "total_users": stats.get("total_users", 0),
        "followers": stats.get("followers", 0),
        "subscribers": stats.get("subscribers", 0),
        "missing_users": stats.get("missing", 0),
    }

    line = (
        f"{summary['ran_at']} | "
        f"account={summary['fanvue_account_id']} | "
        f"found={summary['found']} | "
        f"saved={summary['saved']} | "
        f"missing={summary['missing']} | "
        f"total_users={summary['total_users']} | "
        f"followers={summary['followers']} | "
        f"subscribers={summary['subscribers']} | "
        f"missing_users={summary['missing_users']}"
    )

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    with open(LATEST_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def parse_log_history():
    if not LOG_FILE.exists():
        return []

    rows = []

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = [p.strip() for p in line.strip().split("|")]

            if not parts or len(parts) < 2:
                continue

            row = {"ran_at": parts[0]}

            for part in parts[1:]:
                if "=" in part:
                    key, value = part.split("=", 1)

                    try:
                        value = int(value)
                    except ValueError:
                        pass

                    row[key] = value

            rows.append(row)

    for i, row in enumerate(rows):
        if i == 0:
            row["followers_delta"] = 0
            row["subscribers_delta"] = 0
            row["missing_delta"] = 0
        else:
            prev = rows[i - 1]
            row["followers_delta"] = row.get("followers", 0) - prev.get("followers", 0)
            row["subscribers_delta"] = row.get("subscribers", 0) - prev.get("subscribers", 0)
            row["missing_delta"] = row.get("missing_users", 0) - prev.get("missing_users", 0)

    return rows


def render():

    active_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    active_account = (
        st.session_state.get(
            "active_fanvue_account",
            {}
        )
    )

    st.title("Provider Relationship Sync")

    st.info(
        f"Syncing relationships for: "
        f"{active_account.get('display_name') or active_account.get('username')}"
    )

    if not active_account_id:
        st.warning(
            "No active provider account selected."
        )
        return

    stats = get_relationship_stats(
        active_account_id
    )

    st.subheader("Current Stats")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total Users", stats["total_users"])
    col2.metric("Followers", stats["followers"])
    col3.metric("Subscribers", stats["subscribers"])
    col4.metric("Missing Users", stats["missing"])

    st.divider()

    st.subheader("Manual Sync")

    if st.button("Run Relationship Sync Now"):
        with st.spinner("Running provider relationship sync..."):
            orchestrator = FanvueRelationshipSyncOrchestrator(
                fanvue_account_id=active_account_id
            )

            result = orchestrator.sync_current_relationships()

            updated_stats = get_relationship_stats(
                active_account_id
            )

            write_sync_log(
                result,
                updated_stats,
                active_account_id,
            )

        st.success("Relationship sync complete.")
        st.json(result)
        st.rerun()

    st.divider()

    st.subheader("Daily Sync History")

    history = [
        row
        for row in parse_log_history()
        if str(row.get("account")) == str(active_account_id)
    ]

    if history:
        st.dataframe(
            history,
            use_container_width=True,
        )
    else:
        st.info("No sync history found yet.")
