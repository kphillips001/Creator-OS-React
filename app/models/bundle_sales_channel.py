"""Operator-owned sales channel for Photoshoot Bundles."""

from enum import Enum


class BundleSalesChannel(str, Enum):
    CHAT = "CHAT"
    CONTENT_WALL = "CONTENT_WALL"

    @classmethod
    def parse(cls, value) -> "BundleSalesChannel":
        try:
            return cls(str(getattr(value, "value", value)).strip().upper())
        except ValueError as error:
            raise ValueError(
                "Bundle sales channel must be CHAT or CONTENT_WALL."
            ) from error
