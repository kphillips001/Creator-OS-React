"""Validate the seeded Fanvue profile in normal system Firefox.

This utility does not use Playwright. It opens Fanvue home with the seeded
profile in system Firefox 152.0.1, waits until Firefox exits, then returns.

Run:

    .\\bot\\Scripts\\python.exe -m app.tools.firefox_fanvue_profile_validate
"""

from __future__ import annotations

import subprocess
from pathlib import Path


FANVUE_HOME_URL = "https://www.fanvue.com/home"
PROFILE_DIR = Path("data/playwright/fanvue_playwright_profile")
FIREFOX_EXECUTABLE = Path(r"C:\Program Files\Mozilla Firefox\firefox.exe")


def log(message: str) -> None:
    print(f"[firefox-profile-validate] {message}", flush=True)


def main() -> int:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    if not FIREFOX_EXECUTABLE.is_file():
        raise FileNotFoundError(f"Firefox executable not found: {FIREFOX_EXECUTABLE}")

    log(f"Profile path: {PROFILE_DIR}")
    log(f"Firefox path: {FIREFOX_EXECUTABLE}")

    process = subprocess.Popen(
        [
            str(FIREFOX_EXECUTABLE),
            "-profile",
            str(PROFILE_DIR),
            FANVUE_HOME_URL,
        ]
    )
    process.wait()
    log("Firefox exited")
    return process.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
