"""Run Telegram certification with a verified disposable DB and no external sockets."""
import os
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from psycopg.conninfo import conninfo_to_dict
import psycopg

values = dotenv_values(".env")
url = values["TEST_DATABASE_URL"]
identity = conninfo_to_dict(url)
if identity.get("dbname") != "creator_os_telegram_transport_test_20260920":
    raise RuntimeError("Only the dedicated disposable transport database is allowed")
with psycopg.connect(url) as connection:
    assert connection.execute("SELECT current_database()").fetchone()[0] == identity["dbname"]

os.environ["TEST_DATABASE_URL"] = url
os.environ["DATABASE_URL"] = "postgresql://forbidden@127.0.0.1:1/fanvue_chatbot"
os.environ["CREATOR_OS_PRODUCTION_DATABASE_URL"] = os.environ["DATABASE_URL"]
import app.database
app.database.DATABASE_URL = url

original_connect = socket.socket.connect
def local_database_only(sock, address):
    if isinstance(address, tuple) and address[0] in {"localhost", "127.0.0.1", "::1"}:
        return original_connect(sock, address)
    raise RuntimeError("External network access is forbidden during Telegram certification")
socket.socket.connect = local_database_only

import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
