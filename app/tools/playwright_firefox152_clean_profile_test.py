"""Minimal system Firefox 152 persistent-context launch test.

This script does not navigate, create pages, or interact with Fanvue. It uses
system Firefox with a brand-new empty profile directory, launches a persistent
context, waits five seconds, closes the context, and exits.

Example:

    .\\bot\\Scripts\\python.exe -m app.tools.playwright_firefox152_clean_profile_test
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


DEFAULT_PROFILE_DIR = Path("data/playwright/fanvue_playwright_profile")
DEFAULT_FIREFOX_EXECUTABLE = Path(
    r"C:\Program Files\Mozilla Firefox\firefox.exe"
)


def log(message: str) -> None:
    print(f"[firefox152-clean-profile-test] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minimal system Firefox 152 persistent-context launch test."
    )
    parser.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Clean persistent Firefox 152 profile directory.",
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
    profile_dir.mkdir(parents=True, exist_ok=True)

    log("Starting Playwright")
    with sync_playwright() as playwright:
        log("About to launch persistent context")
        context = playwright.firefox.launch_persistent_context(
            user_data_dir=str(profile_dir),
            executable_path=args.firefox_executable,
            headless=False,
        )
        log("Persistent context launched")
        time.sleep(5)
        context.close()
        log("Context closed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
