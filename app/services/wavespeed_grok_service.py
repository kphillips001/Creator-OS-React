"""Canonical Wavespeed Grok prompt helper adapted for Creator-OS imports."""

from __future__ import annotations

import re

import requests


def generate_prompts_with_grok(meta_prompt, api_key):
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
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=120,
        )

        response.raise_for_status()
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
