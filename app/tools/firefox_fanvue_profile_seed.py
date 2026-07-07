"""Open the Fanvue Playwright profile in normal system Firefox for manual login.

This utility does not use Playwright. It launches system Firefox with the exact
profile directory used by the Fanvue Playwright automation profile, opens
Fanvue home, waits until Firefox exits, then reports completion.

Run:

    .\\bot\\Scripts\\python.exe -m app.tools.firefox_fanvue_profile_seed
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


FANVUE_HOME_URL = "https://www.fanvue.com/home"
DEFAULT_PROFILE_DIR = Path("data/playwright/fanvue_playwright_profile")
DEFAULT_FIREFOX_EXECUTABLE = Path(
    r"C:\Program Files\Mozilla Firefox\firefox.exe"
)


def log(message: str) -> None:
    print(f"[firefox-profile-seed] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open Fanvue in normal system Firefox using the automation profile."
    )
    parser.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Firefox profile directory to seed with manual Fanvue login.",
    )
    parser.add_argument(
        "--firefox-executable",
        default=str(DEFAULT_FIREFOX_EXECUTABLE),
        help="System Firefox executable path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile_dir = Path(args.profile_dir)
    firefox_executable = Path(args.firefox_executable)
    profile_dir.mkdir(parents=True, exist_ok=True)

    if not firefox_executable.is_file():
        raise FileNotFoundError(f"Firefox executable not found: {firefox_executable}")

    command = [
        str(firefox_executable),
        "-profile",
        str(profile_dir),
        FANVUE_HOME_URL,
    ]

    log(f"Launching Firefox: {firefox_executable}")
    log(f"Profile directory: {profile_dir}")
    log(f"Opening: {FANVUE_HOME_URL}")
    process = subprocess.Popen(command)
    process.wait()
    log("Firefox exited")
    log("Manual profile seeding complete")
    return process.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
