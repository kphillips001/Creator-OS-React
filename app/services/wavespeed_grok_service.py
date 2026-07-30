"""Canonical Wavespeed Grok prompt helper adapted for Creator-OS imports."""

from __future__ import annotations

import re
import logging
import time

import requests

from app.config import settings

LOGGER = logging.getLogger("creator_os.canonical_planner")


def generate_prompts_with_grok(meta_prompt, api_key):
    started = time.perf_counter()
    url = "https://api.x.ai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "grok-3-mini",
        "messages": [
            {
                "role": "user",
                "content": meta_prompt,
            }
        ],
        "temperature": 1.3,
        "top_p": 0.95,
    }

    try:
        LOGGER.info(
            "[Planner] Grok request START model=%s timeout_seconds=%s prompt_chars=%s timestamp=%.6f",
            payload["model"], settings.GROK_HTTP_TIMEOUT_SECONDS, len(str(meta_prompt or "")), time.time(),
        )
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=settings.GROK_HTTP_TIMEOUT_SECONDS,
        )

        response.raise_for_status()
        LOGGER.info(
            "[Planner] Grok HTTP complete status=%s elapsed_ms=%.2f",
            response.status_code, (time.perf_counter() - started) * 1000,
        )
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            "Unable to connect to the Grok API. Check your internet connection, VPN, API key, or whether the xAI service is temporarily unavailable."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(
            "The Grok API request timed out. Check your internet connection, VPN, API key, or whether the xAI service is temporarily unavailable."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(
            "The Grok API returned an error response. Check your API key, request limits, or whether the xAI service is temporarily unavailable."
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            "Unable to complete the Grok API request. Check your internet connection, VPN, API key, or whether the xAI service is temporarily unavailable."
        ) from exc

    data = response.json()

    content = data["choices"][0]["message"]["content"].strip()
    LOGGER.info("[Planner] Grok response parsed chars=%s elapsed_ms=%.2f", len(content), (time.perf_counter() - started) * 1000)

    prompts = []

    for line in content.split("\n"):

        line = line.strip()

        if not line:
            continue

        line = re.sub(
            r"^\d+[\.\)]\s*",
            "",
            line,
        )

        if line in {"-", "*", "â€¢"}:
            continue

        lowered = line.lower()

        if (
            lowered.startswith("here are")
            or lowered.startswith("these prompts")
            or lowered.startswith("each prompt")
            or lowered.startswith("each one")
            or lowered.startswith("all prompts")
            or lowered.startswith("below are")
        ):
            continue

        if len(line) < 20:
            continue

        prompts.append(line)

    return prompts
