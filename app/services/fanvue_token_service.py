import json
from pathlib import Path


TOKEN_FILE = Path("data/config/fanvue_tokens.json")


def load_fanvue_token():
    if not TOKEN_FILE.exists():
        raise Exception("Fanvue tokens not found")

    return json.loads(TOKEN_FILE.read_text())