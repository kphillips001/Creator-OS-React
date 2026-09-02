# Generation Library snapshots

PostgreSQL `generation_library_records` is canonical. `generated_images.json` and generated snapshots are compatibility exports only and are never restored automatically.

Run from the repository root:

```powershell
python tools/snapshot_generation_library.py --retain 5
```

The command uses a repeatable-read, read-only database snapshot, writes to a temporary file, flushes it, atomically renames it, verifies record structure/count, writes a revision/checksum manifest, and retains the newest bounded set. Schedule this command externally during a low-traffic backup window; do not add an in-process scheduler.
