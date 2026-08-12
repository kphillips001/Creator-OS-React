"""Durable Explicit Inspire Me concept generation executor."""
from __future__ import annotations

from app.services.explicit_inspiration_service import ExplicitInspirationService


class ExplicitInspirationBackgroundExecutor:
    executor_key = "content_studio_explicit_inspiration"

    def __init__(self, inspiration=None) -> None:
        self.inspiration = inspiration or ExplicitInspirationService()

    def execute(self, operation, operations, *, worker_id: str) -> None:
        metadata = dict(operation.metadata or {})
        if str(metadata.get("phase") or "").upper() == "WAITING_SELECTION":
            operations.repository.transition(
                operation.operation_id, "WAITING_EXTERNAL", stage="WAITING_SELECTION",
                message="Explicit concepts are ready for selection.",
            )
            operations.repository.renew_lease(operation.operation_id, worker_id, lease_seconds=86400)
            return

        softcore_count = int(metadata.get("softcoreCount") or 0)
        hardcore_count = int(metadata.get("hardcoreCount") or 0)
        profile = self.inspiration.profile_loader(str(operation.account_id))
        if not profile:
            raise LookupError("An active creator profile is required.")

        hardcore: tuple[str, ...] = ()
        softcore: tuple[str, ...] = ()
        tier_errors: dict[str, str] = {}
        completed_tiers = 0
        total_tiers = int(hardcore_count > 0) + int(softcore_count > 0)
        operations.progress(
            operation.operation_id, current=0, total=max(1, total_tiers), percent=0,
            stage="GENERATING_CONCEPTS", message=str(metadata.get("requestLabel") or "Generating explicit concepts…"),
            metadata={"phase": "GENERATING_CONCEPTS"},
        )
        if hardcore_count:
            try:
                hardcore = self.inspiration._generate_tier(tier="hardcore", count=hardcore_count)
            except Exception as error:
                tier_errors["hardcore"] = str(error)
            completed_tiers += 1
            operations.progress(
                operation.operation_id, current=completed_tiers, total=total_tiers,
                percent=completed_tiers / total_tiers * 100, stage="GENERATING_CONCEPTS",
                message=str(metadata.get("requestLabel") or "Generating explicit concepts…"),
                metadata={"hardcore": list(hardcore), "tierErrors": tier_errors},
            )
        if softcore_count:
            try:
                softcore = self.inspiration._generate_tier(
                    tier="softcore", count=softcore_count, avoid_overlap=hardcore,
                )
            except Exception as error:
                tier_errors["softcore"] = str(error)
            completed_tiers += 1

        concepts = [
            *({"id": f"hardcore-{index}", "tier": "hardcore", "concept": value, "ordinal": index}
              for index, value in enumerate(hardcore)),
            *({"id": f"softcore-{index}", "tier": "softcore", "concept": value,
               "ordinal": len(hardcore) + index} for index, value in enumerate(softcore)),
        ]
        result_metadata = {
            "phase": "WAITING_SELECTION", "conceptGenerationStatus": "PARTIAL" if tier_errors else "READY",
            "hardcore": list(hardcore), "softcore": list(softcore), "concepts": concepts,
            "tierErrors": tier_errors,
        }
        if not concepts:
            raise RuntimeError("; ".join(tier_errors.values()) or "Explicit inspiration returned no usable concepts.")
        operations.repository.transition(
            operation.operation_id, "WAITING_EXTERNAL", stage="WAITING_SELECTION",
            message="Explicit concepts are ready for selection.", metadata=result_metadata,
        )
        operations.repository.renew_lease(operation.operation_id, worker_id, lease_seconds=86400)
