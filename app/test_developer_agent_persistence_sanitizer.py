import json
from pathlib import Path

from app.services.developer_agent_persistence_sanitizer import (
    sanitize_developer_agent_value,
)
from app.repositories.developer_agent_execution_repository import DeveloperAgentExecutionRepository
from uuid import uuid4


def test_removes_plain_embedded_nul_only():
    assert sanitize_developer_agent_value("before\x00after") == "beforeafter"


def test_sanitizes_nested_json_maps_lists_and_tuples():
    value = {"outer\x00": [{"inner": "a\u0000b"}, ("c\x00d",)]}
    assert sanitize_developer_agent_value(value) == {
        "outer": [{"inner": "ab"}, ["cd"]],
    }


def test_sanitizes_stdout_and_stderr_fields():
    value = sanitize_developer_agent_value({
        "stdout": "ok\x00done", "stderr": "warn\u0000text",
    })
    assert value == {"stdout": "okdone", "stderr": "warntext"}


def test_binary_values_become_metadata_not_decoded_text():
    assert sanitize_developer_agent_value(b"PGDMP\x00binary") == {
        "kind": "binary_value", "size_bytes": 12,
    }


def test_binary_path_becomes_safe_file_metadata(tmp_path):
    dump = tmp_path / "fanvue_backup.dump"
    dump.write_bytes(b"PGDMP\x00binary")
    assert sanitize_developer_agent_value(dump) == {
        "path": str(dump), "kind": "binary_file", "size_bytes": 12,
    }


def test_binary_file_payload_never_persists_embedded_contents():
    assert sanitize_developer_agent_value({
        "path": "fanvue_backup.dump", "content": "PGDMP\x00raw database",
    }) == {
        "path": "fanvue_backup.dump", "kind": "binary_file", "size_bytes": 18,
    }


def test_normal_unicode_emoji_and_formatting_are_preserved():
    value = "Ava 🖤\nline two\tindented — café"
    assert sanitize_developer_agent_value(value) == value
    assert json.loads(json.dumps(sanitize_developer_agent_value({"value": value}))) == {"value": value}


def test_event_repository_serializes_only_sanitized_values():
    captured = {}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): return None
        def execute(self,query,params): captured["params"] = params
        def fetchone(self): return {"event_id": 1}
    class Connection:
        def __enter__(self): return self
        def __exit__(self,*args): return None
        def cursor(self): return Cursor()
    DeveloperAgentExecutionRepository(lambda: Connection()).add_event(
        uuid4(), "CODEX\x00EVENT", "message\x00",
        {"stdout": "ok\x00", "dump": b"PGDMP\x00"},
    )
    assert captured["params"][1:3] == ("CODEXEVENT", "message")
    payload = json.loads(captured["params"][3])
    assert payload == {"stdout": "ok", "dump": {"kind": "binary_value", "size_bytes": 6}}
