"""Canonical rolling-window policy for X competitor posts."""
from datetime import timedelta

# Product visibility remains a strict trailing seven-day view.
POSTS_VISIBLE_WINDOW = timedelta(days=7)
# One extra day lets a future weekly refresh capture a mature final observation.
POST_METRIC_AUTO_REFRESH_WINDOW = timedelta(days=8)

