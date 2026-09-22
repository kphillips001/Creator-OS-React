"""Read-only certification of the configured Creator-OS scenario database."""
from __future__ import annotations

import json
from pathlib import Path

from psycopg import connect
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from app import database
from app.testing.postgres_safety import (
    require_isolated_test_database_url,
    verify_isolated_test_connection,
)


def _configured_name() -> str:
    path = Path(".env.session5.local")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.startswith("CREATOR_OS_SCENARIO_LAB_DATABASE_NAME="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("CREATOR_OS_SCENARIO_LAB_DATABASE_NAME is required")


def scenario_url() -> str:
    values = conninfo_to_dict(database.DATABASE_URL)
    values["dbname"] = _configured_name()
    return make_conninfo(**values)


def main() -> None:
    production = database.DATABASE_URL
    guarded = require_isolated_test_database_url(scenario_url(), production)
    configured = conninfo_to_dict(guarded)
    with connect(guarded, row_factory=dict_row) as connection:
        identity = verify_isolated_test_connection(connection, guarded, production)
        marker = connection.execute(
            "SELECT purpose FROM public.session5_database_purpose"
        ).fetchall()
    print(json.dumps({
        "configured": {
            "database": configured.get("dbname"),
            "host": configured.get("host"),
            "port": str(configured.get("port") or "5432"),
            "credentialsRedacted": True,
        },
        "actual": identity,
        "productionDatabase": conninfo_to_dict(production).get("dbname"),
        "productionExcluded": identity["database"] != "fanvue_chatbot",
        "purpose": [row["purpose"] for row in marker],
        "failClosedGuard": True,
    }, default=str))


if __name__ == "__main__":
    main()
