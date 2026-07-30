"""Reusable collection-level diversity guidance for creative ideation."""

from __future__ import annotations


CREATIVE_DIVERSITY_DIMENSIONS = (
    "Environment",
    "Time of day",
    "Camera framing",
    "Composition and body position",
    "Mood",
    "Lighting",
    "Story premise",
    "Wardrobe state",
    "Visual style",
)


def creative_diversity_guidance(*, concept_count: int) -> str:
    """Return mode-neutral objectives for a deliberately varied concept set."""

    dimensions = "\n".join(f"- {dimension}" for dimension in CREATIVE_DIVERSITY_DIMENSIONS)
    return f"""CREATIVE DIVERSITY ENGINE
Treat the {concept_count} concepts as one editorial collection, not isolated answers.

DIVERSITY DIMENSIONS:
{dimensions}

COLLECTION REVIEW:
- Explore meaningful variation across every dimension when the creative mode allows it.
- Do not use fixed slots, scene templates, lookup tables, quotas, or deterministic combinations.
- Do not repeat the same combination of environment, time, framing, body position, and mood.
- A change in one minor detail does not make an otherwise repeated scene distinct.
- When two concepts overlap heavily, revise one across several dimensions.
- Prefer contrast that creates a balanced collection while preserving the requested creative tier.
- Review the complete collection before returning it and remove near-duplicate premises,
  locations, poses, wardrobe states, lighting treatments, and visual rhythms.
- Diversity is an editorial objective, not permission to introduce unsupported creator facts."""
