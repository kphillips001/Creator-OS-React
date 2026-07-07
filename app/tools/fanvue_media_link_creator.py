"""MVP Playwright creator for Fanvue Paid Media Links.

This module is intentionally standalone. It does not touch Product models,
fulfillment logic, or the database. It assumes the persistent Fanvue profile is
already authenticated.

Run:

    .\\bot\\Scripts\\python.exe -m app.tools.fanvue_media_link_creator
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


FANVUE_HOME_URL = "https://www.fanvue.com/home"
DEFAULT_PROFILE_DIR = Path("data/playwright/fanvue_playwright_profile")
DEFAULT_FIREFOX_EXECUTABLE = Path(
    r"C:\Program Files\Mozilla Firefox\firefox.exe"
)
SCREENSHOT_DIR = Path("data/playwright/media_link_creator_screenshots")


def log(message: str) -> None:
    print(f"[fanvue-media-link-creator] {message}", flush=True)


def _save_screenshot(page: Page, filename: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / filename
    log(f"Saving screenshot: {path}")
    page.screenshot(path=str(path), full_page=True)
    log(f"Screenshot saved: {path}")


def _click_first(page: Page, step: str, locators, timeout_ms: int = 5000) -> None:
    log(f"Starting step: {step}")
    last_error = None
    for label, locator in locators:
        try:
            target = locator.first
            log(f"Trying selector for {step}: {label}")
            target.wait_for(state="visible", timeout=timeout_ms)
            target.click(timeout=timeout_ms)
            log(f"Completed step: {step} using {label}")
            return
        except Exception as error:
            last_error = error
            log(f"Selector failed for {step}: {label} ({error})")
    raise RuntimeError(f"Could not complete step '{step}': {last_error}")


def _fill_first(page: Page, step: str, value: str, locators, timeout_ms: int = 5000) -> None:
    log(f"Starting step: {step}")
    last_error = None
    for label, locator in locators:
        try:
            target = locator.first
            log(f"Trying selector for {step}: {label}")
            target.wait_for(state="visible", timeout=timeout_ms)
            target.fill(value, timeout=timeout_ms)
            log(f"Completed step: {step} using {label}")
            return
        except Exception as error:
            last_error = error
            log(f"Selector failed for {step}: {label} ({error})")
    raise RuntimeError(f"Could not complete step '{step}': {last_error}")


def _visible_scope(page: Page):
    for label, locator in (
        ("dialog", page.get_by_role("dialog")),
        ("role dialog", page.locator("[role='dialog']")),
        ("body", page.locator("body")),
    ):
        try:
            locator.first.wait_for(state="visible", timeout=1500)
            log(f"Using visible scope: {label}")
            return locator.first
        except Exception:
            continue
    return page.locator("body")


def _open_paid_media_links(page: Page) -> None:
    _click_first(
        page,
        "Open Creator Tools",
        [
            ("Creator Tools link", page.get_by_role("link", name=re.compile(r"creator tools", re.I))),
            ("Creator Tools button", page.get_by_role("button", name=re.compile(r"creator tools", re.I))),
            ("Creator Tools text", page.get_by_text(re.compile(r"creator tools", re.I))),
        ],
    )
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    _click_first(
        page,
        "Open Paid Media Links",
        [
            ("Paid Media Links link", page.get_by_role("link", name=re.compile(r"paid media links?", re.I))),
            ("Paid Media Links button", page.get_by_role("button", name=re.compile(r"paid media links?", re.I))),
            ("Paid Media Links text", page.get_by_text(re.compile(r"paid media links?", re.I))),
            ("Media Links link", page.get_by_role("link", name=re.compile(r"media links?", re.I))),
            ("Media Links button", page.get_by_role("button", name=re.compile(r"media links?", re.I))),
        ],
    )
    page.wait_for_load_state("domcontentloaded", timeout=15000)
    _save_screenshot(page, "paid_media_links.png")


def _wait_for_vault_picker(page: Page) -> None:
    log("Starting step: Wait for Vault picker")
    for label, locator in (
        ("Vault text", page.get_by_text(re.compile(r"vault", re.I))),
        ("Add Media text", page.get_by_text(re.compile(r"add media", re.I))),
        ("Dialog", page.get_by_role("dialog")),
        ("Role dialog", page.locator("[role='dialog']")),
    ):
        try:
            log(f"Trying selector for Vault picker: {label}")
            locator.first.wait_for(state="visible", timeout=10000)
            log(f"Completed step: Wait for Vault picker using {label}")
            return
        except Exception as error:
            log(f"Selector failed for Vault picker: {label} ({error})")
    raise RuntimeError("Vault picker did not appear.")


def _select_first_vault_asset(page: Page) -> None:
    log("Starting step: Select first Vault asset")
    scope = _visible_scope(page)
    last_error = None
    candidates = [
        ("First media image", scope.locator("img")),
        ("First checkbox", scope.get_by_role("checkbox")),
        ("First grid cell", scope.get_by_role("gridcell")),
        ("First list item", scope.get_by_role("listitem")),
        ("First media tile", scope.locator("[data-testid*='media' i], [data-test*='media' i]")),
    ]
    for label, locator in candidates:
        try:
            target = locator.first
            log(f"Trying selector for first asset: {label}")
            target.wait_for(state="visible", timeout=5000)
            target.click(timeout=5000)
            log(f"Completed step: Select first Vault asset using {label}")
            return
        except Exception as error:
            last_error = error
            log(f"Selector failed for first asset: {label} ({error})")
    raise RuntimeError(f"Could not select first Vault asset: {last_error}")


def _read_media_link_url(page: Page) -> str:
    log("Starting step: Read copied URL from clipboard")
    url_pattern = re.compile(r"https://(?:www\.)?fanvue\.com/[^\s\"'<>]+", re.I)
    try:
        clipboard_text = page.evaluate("navigator.clipboard.readText()")
        log(f"Clipboard text length: {len(clipboard_text or '')}")
        match = url_pattern.search(clipboard_text or "")
        if match:
            url = match.group(0).rstrip(").,]")
            log(f"Completed step: Read copied URL from clipboard ({url})")
            return url
    except Exception as error:
        log(f"Clipboard read failed: {error}")

    log("Falling back to visible Share Link modal URL extraction")
    locators = [
        page.locator("input[value*='fanvue.com']"),
        page.locator("textarea"),
        page.get_by_text(re.compile(r"https://(?:www\.)?fanvue\.com/", re.I)),
    ]
    for locator in locators:
        try:
            count = min(locator.count(), 10)
        except Exception:
            count = 1
        for index in range(count):
            item = locator.nth(index)
            try:
                value = item.input_value(timeout=1000)
            except Exception:
                try:
                    value = item.inner_text(timeout=1000)
                except Exception:
                    value = ""
            match = url_pattern.search(value or "")
            if match:
                url = match.group(0).rstrip(").,]")
                log(f"Completed step: Extract visible URL ({url})")
                return url

    raise RuntimeError("Could not read Fanvue Media Link URL from clipboard or modal.")


def create_latest_media_link(page: Page, price: str = "9.99") -> str:
    """Create a Fanvue Paid Media Link from the newest Vault asset."""

    log("Starting create_latest_media_link")
    page.set_default_timeout(10000)

    _open_paid_media_links(page)

    _click_first(
        page,
        "Click Create Link",
        [
            ("Create Link button", page.get_by_role("button", name=re.compile(r"create link", re.I))),
            ("Create Media Link button", page.get_by_role("button", name=re.compile(r"create.*media.*link", re.I))),
            ("New Link button", page.get_by_role("button", name=re.compile(r"new.*link", re.I))),
        ],
    )

    _click_first(
        page,
        "Click Add Media",
        [
            ("Add Media button", page.get_by_role("button", name=re.compile(r"add media", re.I))),
            ("Add Media text", page.get_by_text(re.compile(r"add media", re.I))),
        ],
    )

    _wait_for_vault_picker(page)
    _save_screenshot(page, "vault_picker.png")

    _select_first_vault_asset(page)

    _click_first(
        page,
        "Click Add Media in Vault picker",
        [
            ("Add Media button", page.get_by_role("button", name=re.compile(r"add media", re.I))),
            ("Add selected media button", page.get_by_role("button", name=re.compile(r"add selected", re.I))),
            ("Add button", page.get_by_role("button", name=re.compile(r"^add$", re.I))),
        ],
    )

    _fill_first(
        page,
        "Enter price",
        price,
        [
            ("Price textbox", page.get_by_role("textbox", name=re.compile(r"price|amount", re.I))),
            ("Price placeholder", page.get_by_placeholder(re.compile(r"price|amount", re.I))),
            ("Number input", page.locator("input[type='number']")),
            ("Price named input", page.locator("input[name*='price' i]")),
            ("Amount named input", page.locator("input[name*='amount' i]")),
        ],
    )
    _save_screenshot(page, "price_entry.png")

    _click_first(
        page,
        "Click Create Link final",
        [
            ("Create Link button", page.get_by_role("button", name=re.compile(r"create link", re.I))),
            ("Create Media Link button", page.get_by_role("button", name=re.compile(r"create.*media.*link", re.I))),
            ("Publish button", page.get_by_role("button", name=re.compile(r"publish", re.I))),
        ],
    )
    page.wait_for_load_state("domcontentloaded", timeout=15000)

    _click_first(
        page,
        "Click Share Link",
        [
            ("Share Link button", page.get_by_role("button", name=re.compile(r"share link", re.I))),
            ("Share button", page.get_by_role("button", name=re.compile(r"share", re.I))),
            ("Share Link text", page.get_by_text(re.compile(r"share link", re.I))),
        ],
    )
    _save_screenshot(page, "share_modal.png")

    media_link_url = _read_media_link_url(page)
    log(f"Completed create_latest_media_link: {media_link_url}")
    return media_link_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Fanvue Paid Media Link from the newest Vault asset."
    )
    parser.add_argument(
        "--price",
        default="9.99",
        help="Paid Media Link price, for example 9.99.",
    )
    parser.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Persistent Fanvue Firefox profile directory.",
    )
    parser.add_argument(
        "--firefox-executable",
        default=str(DEFAULT_FIREFOX_EXECUTABLE),
        help="System Firefox executable path.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Firefox headless. Default is headed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile_dir = Path(args.profile_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)

    log(f"Profile directory: {profile_dir}")
    log(f"Firefox executable: {args.firefox_executable}")
    log(f"Price: {args.price}")

    with sync_playwright() as playwright:
        context = playwright.firefox.launch_persistent_context(
            user_data_dir=str(profile_dir),
            executable_path=args.firefox_executable,
            headless=args.headless,
            viewport={"width": 1440, "height": 1000},
        )
        try:
            try:
                context.grant_permissions(
                    ["clipboard-read", "clipboard-write"],
                    origin="https://www.fanvue.com",
                )
            except Exception as error:
                log(f"Clipboard permission grant failed: {error}")

            page = context.pages[0] if context.pages else context.new_page()
            log(f"Opening Fanvue home: {FANVUE_HOME_URL}")
            page.goto(FANVUE_HOME_URL, wait_until="domcontentloaded", timeout=45000)
            media_link_url = create_latest_media_link(page, price=args.price)
            print(media_link_url, flush=True)
        finally:
            context.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
