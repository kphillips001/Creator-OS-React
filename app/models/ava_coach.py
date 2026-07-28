"""Ava Coach Phase 1 observational domain."""
from enum import Enum


class CoachingRecommendationStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED_FOR_VERSION = "APPROVED_FOR_VERSION"
    REJECTED = "REJECTED"
    DISMISSED = "DISMISSED"
    ACTIVATED = "ACTIVATED"
