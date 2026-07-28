"""Small deterministic text normalization for Commerce ranking."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedRecommendationText:
    normalized: str
    tokens: tuple[str, ...]
    phrases: tuple[str, ...]


class RecommendationTextNormalizer:
    STOPWORDS = frozenset({
        "a", "an", "and", "can", "content", "for", "give", "i", "image",
        "me", "of", "photo", "photos", "picture", "please", "see", "show",
        "something", "some", "the", "to", "want", "with", "you",
    })
    _punctuation = re.compile(r"[^\w\s-]+", re.UNICODE)
    _whitespace = re.compile(r"\s+")

    def normalize(self, *values: str | None) -> NormalizedRecommendationText:
        text = " ".join(str(value or "") for value in values)
        normalized = self._whitespace.sub(
            " ", self._punctuation.sub(" ", text.lower())
        ).strip()
        tokens = tuple(dict.fromkeys(
            token for token in normalized.split()
            if token not in self.STOPWORDS and len(token) > 1
        ))
        phrases = tuple(dict.fromkeys(
            phrase for size in (3, 2) for phrase in (
                " ".join(tokens[index:index + size])
                for index in range(max(0, len(tokens) - size + 1))
            ) if phrase
        ))
        return NormalizedRecommendationText(normalized, tokens, phrases)
