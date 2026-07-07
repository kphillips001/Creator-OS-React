"""Playwright POC for creating Fanvue Media Links from uploaded Vault media.

This is a local, headed-browser proof of concept. It does not persist anything
to the database and does not store Fanvue credentials. The first run opens a
persistent browser profile so the creator can log into Fanvue manually; later
runs reuse that browser session.

Install once:

    .\\bot\\Scripts\\python.exe -m pip install -r requirements-playwright.txt
    .\\bot\\Scripts\\python.exe -m playwright install firefox

Example run:

    .\\bot\\Scripts\\python.exe -m app.tools.fanvue_media_link_playwright_poc --media-search "Premium 20260529" --price-cents 1499 --product-id ac107a53-1548-4414-b243-e68d59672dd8

The Fanvue web UI may change. If a selector is not found, the script pauses so
you can navigate or complete a manual step in the opened browser, then press
Enter in the terminal to let the script continue.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


FANVUE_HOME_URL = "https://www.fanvue.com/home"
DEFAULT_CREATOR_USERNAME = "avablackthorne"
DEFAULT_PROFILE_DIR = Path("data/playwright/fanvue_playwright_profile")
DEFAULT_FIREFOX_EXECUTABLE = Path(
    r"C:\Program Files\Mozilla Firefox\firefox.exe"
)


class POCError(RuntimeError):
    pass


@dataclass(frozen=True)
class POCArgs:
    creator_username: str
    media_search: str
    price_cents: int
    product_id: str | None
    headless: bool
    profile_dir: Path
    firefox_executable: Path
    start_url: str
    manual: bool
    slow_mo_ms: int

    @property
    def price_decimal(self) -> str:
        return f"{self.price_cents / 100:.2f}"


def _import_playwright():
    try:
        from playwright.sync_api import (  # type: ignore
            Error as PlaywrightError,
            TimeoutError as PlaywrightTimeoutError,
            sync_playwright,
        )
    except ImportError as exc:
        raise POCError(
            "Playwright is not installed. Run: "
            ".\\bot\\Scripts\\python.exe -m pip install -r requirements-playwright.txt "
            "then: .\\bot\\Scripts\\python.exe -m playwright install firefox"
        ) from exc
    return sync_playwright, PlaywrightError, PlaywrightTimeoutError


def parse_args(argv: list[str] | None = None) -> POCArgs:
    parser = argparse.ArgumentParser(
        description=(
            "Local headed-browser POC for creating a Fanvue Media Link from "
            "already-uploaded Vault media."
        )
    )
    parser.add_argument(
        "--creator-username",
        default=DEFAULT_CREATOR_USERNAME,
        help="Creator username. Default: avablackthorne",
    )
    parser.add_argument(
        "--media-search",
        required=True,
        help="Target Vault media identifier, title, or search text.",
    )
    parser.add_argument(
        "--price-cents",
        required=True,
        type=int,
        help="Price in cents, for example 1499 for $14.99.",
    )
    parser.add_argument(
        "--product-id",
        default=None,
        help="Optional local product id for console traceability only.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run headless. Default is headed for first POC testing.",
    )
    parser.add_argument(
        "--profile-dir",
        default=str(DEFAULT_PROFILE_DIR),
        help="Persistent Playwright profile directory.",
    )
    parser.add_argument(
        "--firefox-executable",
        default=str(DEFAULT_FIREFOX_EXECUTABLE),
        help="System Firefox executable path.",
    )
    parser.add_argument(
        "--start-url",
        default=FANVUE_HOME_URL,
        help="Initial Fanvue URL to open.",
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Pause at each major step for manual navigation/confirmation.",
    )
    parser.add_argument(
        "--slow-mo-ms",
        default=150,
        type=int,
        help="Playwright slow motion delay in milliseconds.",
    )
    parsed = parser.parse_args(argv)

    if parsed.price_cents < 0:
        raise POCError("--price-cents must be zero or greater.")

    return POCArgs(
        creator_username=parsed.creator_username.strip().lstrip("@"),
        media_search=parsed.media_search.strip(),
        price_cents=parsed.price_cents,
        product_id=parsed.product_id,
        headless=parsed.headless,
        profile_dir=Path(parsed.profile_dir),
        firefox_executable=Path(parsed.firefox_executable),
        start_url=parsed.start_url,
        manual=parsed.manual,
        slow_mo_ms=parsed.slow_mo_ms,
    )


def log(message: str) -> None:
    print(f"[fanvue-media-link-poc] {message}", flush=True)


def pause(message: str, *, required: bool = False) -> None:
    prefix = "ACTION REQUIRED" if required else "Manual checkpoint"
    input(f"\n[{prefix}] {message}\nPress Enter to continue...")


def _button_names(names: Iterable[str]) -> list[re.Pattern[str]]:
    return [re.compile(name, re.I) for name in names]


def click_first(page, candidates: list[tuple[str, object]], *, timeout_ms: int = 2500) -> str | None:
    last_error = None
    for label, locator in candidates:
        try:
            target = locator.first
            target.wait_for(state="visible", timeout=timeout_ms)
            target.click(timeout=timeout_ms)
            return label
        except Exception as exc:  # Playwright raises several locator errors.
            last_error = exc
    if last_error:
        log(f"No candidate clicked; last selector error: {last_error}")
    return None


def fill_first(page, candidates: list[tuple[str, object]], value: str, *, timeout_ms: int = 2500) -> str | None:
    last_error = None
    for label, locator in candidates:
        try:
            target = locator.first
            target.wait_for(state="visible", timeout=timeout_ms)
            target.fill(value, timeout=timeout_ms)
            return label
        except Exception as exc:
            last_error = exc
    if last_error:
        log(f"No candidate filled; last selector error: {last_error}")
    return None


def text_or_none(locator, *, timeout_ms: int = 1500) -> str | None:
    try:
        locator.first.wait_for(state="visible", timeout=timeout_ms)
        return locator.first.inner_text(timeout=timeout_ms)
    except Exception:
        return None


def maybe_wait_for_login(page) -> None:
    login_indicators = [
        page.get_by_role("button", name=re.compile(r"log in|sign in", re.I)),
        page.get_by_role("link", name=re.compile(r"log in|sign in", re.I)),
        page.locator("input[type='email']"),
        page.locator("input[name='email']"),
    ]
    for locator in login_indicators:
        try:
            if locator.first.is_visible(timeout=1200):
                pause(
                    "Fanvue login appears to be required. Complete login, MFA, "
                    "or CAPTCHA manually in the browser. Do not enter credentials "
                    "into this script.",
                    required=True,
                )
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                return
        except Exception:
            continue


def navigate_to_media_links(page, args: POCArgs) -> None:
    log("Navigating toward Fanvue Media Links.")
    candidates = [
        (
            "Media Links navigation",
            page.get_by_role("link", name=re.compile(r"media links?", re.I)),
        ),
        (
            "Media Links button",
            page.get_by_role("button", name=re.compile(r"media links?", re.I)),
        ),
        ("Media Links text", page.get_by_text(re.compile(r"media links?", re.I))),
        ("Vault navigation", page.get_by_role("link", name=re.compile(r"vault", re.I))),
        ("Vault button", page.get_by_role("button", name=re.compile(r"vault", re.I))),
    ]
    clicked = click_first(page, candidates)
    if clicked:
        log(f"Clicked {clicked}.")
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        return

    pause(
        "Could not find Media Links/Vault navigation. In the browser, navigate "
        "to the Fanvue Media Links creation area for the creator account.",
        required=True,
    )


def start_create_link(page) -> None:
    log("Starting Media Link creation.")
    candidates = [
        (
            "Create Media Link",
            page.get_by_role("button", name=re.compile(r"create.*media.*link", re.I)),
        ),
        (
            "New Media Link",
            page.get_by_role("button", name=re.compile(r"new.*media.*link", re.I)),
        ),
        ("Create Link", page.get_by_role("button", name=re.compile(r"create.*link", re.I))),
        ("Add Link", page.get_by_role("button", name=re.compile(r"add.*link", re.I))),
        (
            "Create Media Link text",
            page.get_by_text(re.compile(r"create.*media.*link", re.I)),
        ),
    ]
    clicked = click_first(page, candidates)
    if clicked:
        log(f"Clicked {clicked}.")
        return

    pause(
        "Could not find a Create/New Media Link control. Open the Create Media "
        "Link dialog manually.",
        required=True,
    )


def select_media(page, args: POCArgs) -> None:
    log(f"Selecting target media: {args.media_search!r}.")
    search_candidates = [
        ("Search input", page.get_by_placeholder(re.compile(r"search", re.I))),
        ("Search textbox", page.get_by_role("textbox", name=re.compile(r"search", re.I))),
        ("Generic search", page.locator("input[type='search']")),
    ]
    filled = fill_first(page, search_candidates, args.media_search)
    if filled:
        log(f"Filled {filled}.")
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
    else:
        log("No search field found; trying visible media text directly.")

    media_candidates = [
        (f"Text {args.media_search}", page.get_by_text(args.media_search, exact=False)),
        (
            "Media checkbox near text",
            page.locator(
                f"text={args.media_search}"
            ).locator("xpath=ancestor-or-self::*[self::div or self::li][1]//input[@type='checkbox']"),
        ),
    ]
    clicked = click_first(page, media_candidates)
    if clicked:
        log(f"Selected media using {clicked}.")
        return

    pause(
        f"Could not automatically select media {args.media_search!r}. Select "
        "the uploaded Vault media manually in the browser.",
        required=True,
    )


def set_price(page, args: POCArgs) -> None:
    log(f"Setting price to {args.price_decimal}.")
    candidates = [
        ("Price textbox", page.get_by_role("textbox", name=re.compile(r"price|amount", re.I))),
        ("Price placeholder", page.get_by_placeholder(re.compile(r"price|amount", re.I))),
        ("Number input", page.locator("input[type='number']")),
        ("Price named input", page.locator("input[name*='price' i]")),
        ("Amount named input", page.locator("input[name*='amount' i]")),
    ]
    filled = fill_first(page, candidates, args.price_decimal)
    if filled:
        log(f"Filled {filled}.")
        return

    pause(
        f"Could not find a price input. Set the Media Link price manually to "
        f"{args.price_decimal}.",
        required=True,
    )


def create_link(page) -> None:
    log("Submitting Media Link creation.")
    candidates = [
        (
            "Create Media Link",
            page.get_by_role("button", name=re.compile(r"create.*media.*link", re.I)),
        ),
        ("Generate Link", page.get_by_role("button", name=re.compile(r"generate.*link", re.I))),
        ("Create Link", page.get_by_role("button", name=re.compile(r"create.*link", re.I))),
        ("Save", page.get_by_role("button", name=re.compile(r"save", re.I))),
        ("Publish", page.get_by_role("button", name=re.compile(r"publish", re.I))),
    ]
    clicked = click_first(page, candidates)
    if clicked:
        log(f"Clicked {clicked}.")
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_timeout(2500)
        return

    pause(
        "Could not find the final create/generate button. Submit the Media Link "
        "creation manually in the browser.",
        required=True,
    )


def extract_media_link(page, args: POCArgs) -> str:
    log("Looking for generated Media Link URL.")
    page.wait_for_timeout(1000)

    url_patterns = [
        re.compile(r"https://(?:www\.)?fanvue\.com/[^\s\"'<>]+/media/[^\s\"'<>]+", re.I),
        re.compile(r"https://(?:www\.)?fanvue\.com/[^\s\"'<>]+/media-links?/[^\s\"'<>]+", re.I),
        re.compile(r"https://(?:www\.)?fanvue\.com/[^\s\"'<>]*fvml[^\s\"'<>]*", re.I),
    ]

    candidate_locators = [
        page.locator("input[value*='fanvue.com']"),
        page.locator("textarea"),
        page.get_by_text(re.compile(r"https://(?:www\.)?fanvue\.com/", re.I)),
    ]
    for locator in candidate_locators:
        try:
            count = min(locator.count(), 10)
        except Exception:
            count = 1
        for index in range(count):
            item = locator.nth(index)
            try:
                value = item.input_value(timeout=1000)
            except Exception:
                value = text_or_none(item)
            if not value:
                continue
            for pattern in url_patterns:
                match = pattern.search(value)
                if match:
                    return match.group(0).rstrip(").,]")

    body = text_or_none(page.locator("body"), timeout_ms=2000) or ""
    for pattern in url_patterns:
        match = pattern.search(body)
        if match:
            return match.group(0).rstrip(").,]")

    pause(
        "The generated Media Link URL was not found automatically. Copy the "
        "Fanvue Media Link URL from the browser, paste it here, and press Enter.",
        required=True,
    )
    manual_url = input("Fanvue Media Link URL: ").strip()
    if not re.match(r"^https://(?:www\.)?fanvue\.com/", manual_url, re.I):
        raise POCError("The supplied URL does not look like a Fanvue URL.")
    return manual_url


def run(args: POCArgs) -> str:
    sync_playwright, _, _ = _import_playwright()
    args.profile_dir.mkdir(parents=True, exist_ok=True)

    log(f"Creator username: {args.creator_username}")
    log(f"Media search: {args.media_search}")
    log(f"Price: {args.price_decimal}")
    if args.product_id:
        log(f"Product ID: {args.product_id}")
    log(f"Browser executable: {args.firefox_executable}")
    log(f"Persistent profile: {args.profile_dir}")

    with sync_playwright() as playwright:
        log("Launching browser")
        context = playwright.firefox.launch_persistent_context(
            user_data_dir=str(args.profile_dir),
            executable_path=str(args.firefox_executable),
            headless=args.headless,
            slow_mo=args.slow_mo_ms,
            viewport={"width": 1440, "height": 1000},
        )
        log("Browser launched")
        log("Context created")
        log(f"Existing pages count: {len(context.pages)}")
        log(f"Total page count: {len(context.pages)}")
        for index, existing_page in enumerate(context.pages):
            log(
                f"Page {index}: url={existing_page.url} "
                f"is_closed={existing_page.is_closed()}"
            )
        try:
            if context.pages:
                selected_page_index = 0
                page = context.pages[selected_page_index]
            else:
                page = context.new_page()
                selected_page_index = 0
                log("No existing pages found; created a new page")
            log(f"Selected page index: {selected_page_index}")
            log(f"Current page URL: {page.url}")
            log(f"First navigation target: {args.start_url}")
            log(f"Page URL before goto: {page.url}")
            page.goto(args.start_url, wait_until="domcontentloaded", timeout=45000)
            log(f"Page URL after goto: {page.url}")
            log("Navigation complete")
            maybe_wait_for_login(page)
            if args.manual:
                pause("Confirm the Fanvue session is logged in and ready.")

            navigate_to_media_links(page, args)
            if args.manual:
                pause("Confirm you are on the Media Links creation area.")

            start_create_link(page)
            if args.manual:
                pause("Confirm the Create Media Link flow/dialog is open.")

            select_media(page, args)
            if args.manual:
                pause("Confirm the target media is selected.")

            set_price(page, args)
            if args.manual:
                pause("Confirm the price is set correctly.")

            create_link(page)
            media_link_url = extract_media_link(page, args)
            log(f"MEDIA_LINK_URL={media_link_url}")
            return media_link_url
        finally:
            context.close()


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        media_link_url = run(args)
    except POCError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130

    print(media_link_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
