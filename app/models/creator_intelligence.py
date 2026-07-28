"""Immutable, persistence-neutral creator knowledge contract."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


NormalizedDocument = Mapping[str, str | int | bool | None]


@dataclass(frozen=True, slots=True)
class CreatorIntelligence:
    """Canonical creator knowledge assembled from the three source documents."""

    personality: NormalizedDocument
    lifestyle: NormalizedDocument
    social_creative_direction: NormalizedDocument

    @staticmethod
    def immutable_document(
        values: dict[str, str | int | bool | None],
    ) -> NormalizedDocument:
        return MappingProxyType(dict(values))
