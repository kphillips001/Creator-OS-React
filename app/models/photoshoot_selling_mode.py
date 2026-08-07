"""Operator-owned commercial mode for a completed Photoshoot."""

from enum import Enum


class PhotoshootSellingMode(str, Enum):
    SESSION = "SESSION"
    BUNDLE = "BUNDLE"

    @classmethod
    def parse(cls, value: object) -> "PhotoshootSellingMode":
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError as error:
            raise ValueError("Selling mode must be SESSION or BUNDLE.") from error
