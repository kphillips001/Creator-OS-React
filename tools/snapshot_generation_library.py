"""Create a verified compatibility backup from canonical PostgreSQL records."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.generation_library_snapshot_service import GenerationLibrarySnapshotService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="backups/generation_library")
    parser.add_argument("--retain", type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(GenerationLibrarySnapshotService().create(args.output_dir, retain=args.retain), indent=2))


if __name__ == "__main__": main()
