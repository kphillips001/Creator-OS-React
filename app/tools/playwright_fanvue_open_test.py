"""Temporary Playwright smoke test for opening Fanvue with Firefox.

This script only launches a persistent Firefox context, navigates to Fanvue
home, waits briefly, logs URLs, and exits. It does not click or interact with
Fanvue.

Example:

    .\\bot\\Scripts\\python.exe -m app.tools.playwright_fanvue_open_test --profile-dir "C:\\Fanvue-Chatbot\\data\\playwright\\fanvue_playwright_profile" --firefox-executable "C:\\Program Files\\Mozilla Firefox\\firefox.exe"
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


FANVUE_HOME_URL = "https://www.fanvue.com/home"
DEFAULT_PROFILE_DIR = Path("data/playwright/fanvue_playwright_profile")
DEFAULT_FIREFOX_EXECUTABLE = Path(
    r"C:\Program Files\Mozilla Firefox\firefox.exe"
)


def log(message: str) -> None:
    print(f"[fanvue-open-test] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch Firefox with a persistent profile and open Fanvue."
    )
    parser.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Persistent Playwright/Firefox profile directory.",
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

    with sync_playwright() as playwright:
        log("Launching browser")
        context = playwright.firefox.launch_persistent_context(
            user_data_dir=str(profile_dir),
            executable_path=args.firefox_executable,
            headless=False,
            viewport={"width": 1440, "height": 1000},
        )
        log("Browser launched")
        log("Context created")
        log(f"Existing pages count: {len(context.pages)}")
        try:
            page = context.pages[0] if context.pages else context.new_page()
            log(f"Current page URL: {page.url}")
            log("Navigating to Fanvue")
            page.goto(
                FANVUE_HOME_URL,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            log("Navigation complete")
            page.wait_for_timeout(15000)
            log(f"Final page URL: {page.url}")
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
