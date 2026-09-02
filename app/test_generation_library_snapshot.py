import json
from contextlib import contextmanager
from pathlib import Path

from app.services.generation_library_snapshot_service import GenerationLibrarySnapshotService


class Cursor:
    def __init__(self): self.rows=[]
    def execute(self, sql, params=None):
        if "SELECT revision" in sql: self.rows=[{"revision": 12}]
        elif "SELECT record_payload" in sql: self.rows=[{"record_payload":{"image_id":"a"}},{"record_payload":{"image_id":"b"}}]
    def fetchone(self): return self.rows.pop(0)
    def fetchmany(self, size): values=self.rows[:size]; self.rows=self.rows[size:]; return values
    def __enter__(self): return self
    def __exit__(self,*args): pass


class Connection:
    def cursor(self): return Cursor()
    def __enter__(self): return self
    def __exit__(self,*args): pass


def test_snapshot_is_verified_manifested_and_retained(tmp_path):
    service=GenerationLibrarySnapshotService(lambda: Connection())
    first=service.create(tmp_path,retain=1)
    assert first["canonicalRevision"] == 12 and first["recordCount"] == 2
    snapshot=tmp_path/first["snapshotFile"]
    assert [item["image_id"] for item in json.loads(snapshot.read_text())] == ["a","b"]
    assert first["recordPayloadSha256"]
    second=service.create(tmp_path,retain=1)
    assert len([path for path in tmp_path.glob("generated_images-r*.json") if not path.name.endswith(".manifest.json")]) == 1
    assert len(list(tmp_path.glob("*.manifest.json"))) == 1
