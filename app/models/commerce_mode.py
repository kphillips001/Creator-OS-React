"""Commerce execution mode, intentionally independent from RuntimeMode."""

from enum import Enum


class CommerceMode(str, Enum):
    OFF = "OFF"
    RELATIONSHIP = "RELATIONSHIP"
    LIVE = "LIVE"
