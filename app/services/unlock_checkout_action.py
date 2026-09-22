"""Exclude recognized previews without adding a customer confirmation step.

These are traffic hints, not authentication. Unmarked clients may look like
browsers; the gateway still validates bearer authority and serializes resolution.
"""
import re
from fastapi.responses import Response

_CRAWLER = re.compile(r"telegrambot|twitterbot|facebookexternalhit|facebot|slackbot|discordbot|linkedinbot|whatsapp|googlebot|bingbot|applebot|duckduckbot|yandexbot|baiduspider|crawler|spider|(?:^|[ /;_-])bot(?:[ /;_-]|$)", re.I)

def recognized_preview(request):
    if request is None:
        return False
    if request.method.upper() != "GET":
        return True
    headers = request.headers
    purpose = " ".join(headers.get(k, "").lower() for k in
                       ("purpose", "sec-purpose", "x-purpose", "x-moz"))
    if any(hint in purpose for hint in ("prefetch", "preview", "prerender")):
        return True
    # Fetch Metadata explicitly describing a non-navigation is stronger than UA.
    mode = headers.get("sec-fetch-mode", "").lower()
    destination = headers.get("sec-fetch-dest", "").lower()
    if mode and mode != "navigate":
        return True
    if destination and destination != "document":
        return True
    if headers.get("sec-fetch-user") == "?0":
        return True
    return bool(_CRAWLER.search(headers.get("user-agent", "")))

def preview_response():
    return Response(status_code=204, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Robots-Tag": "noindex, nofollow",
    })
