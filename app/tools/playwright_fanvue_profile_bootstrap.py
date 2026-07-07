"""Bootstrap a Playwright-owned Fanvue Firefox profile.

This script uses Playwright's bundled Firefox, opens Fanvue with a persistent
profile, and waits while you log in manually. It does not automate login or
interact with Fanvue.

Run:

    .\\bot\\Scripts\\python.exe -m app.tools.playwright_fanvue_profile_bootstrap
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


FANVUE_HOME_URL = "https://www.fanvue.com/home"
PROFILE_DIR = Path("data/playwright/fanvue_playwright_profile")
FIREFOX_EXECUTABLE = Path(r"C:\Program Files\Mozilla Firefox\firefox.exe")


def log(message: str) -> None:
    print(f"[fanvue-profile-bootstrap] {message}", flush=True)


def main() -> int:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    log("Starting Playwright")
    with sync_playwright() as playwright:
        log("Launching persistent context")
        context = playwright.firefox.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=str(FIREFOX_EXECUTABLE),
            headless=False,
            viewport={"width": 1440, "height": 1000},
        )
        log("Persistent context launched")
        try:
            page = context.pages[0] if context.pages else context.new_page()
            log("Navigating to Fanvue")
            page.goto(
                FANVUE_HOME_URL,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            log("Fanvue loaded")

            print("Log into Fanvue manually.", flush=True)
            input("Press ENTER when login is complete.")

            log(f"Final page URL: {page.url}")
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
