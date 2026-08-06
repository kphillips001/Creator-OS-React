"""One-time repair for legacy Photoshoots missing Session Sales Strategy."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.repositories.photoshoot_session_sales_strategy_repository import (
    PhotoshootSessionSalesStrategyRepository,
)
from app.services.photoshoot_session_sales_strategy_service import (
    SESSION_SALES_STRATEGY_VERSION,
    PhotoshootSessionSalesStrategyService,
)


class RepairPrerequisiteError(RuntimeError):
    """A legacy Photoshoot is not safe to repair."""


class MissingSessionSalesStrategyRepair:
    def __init__(self, *, photoshoots=None, strategies=None, strategy_service=None):
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.strategies = strategies or PhotoshootSessionSalesStrategyRepository()
        self.strategy_service = strategy_service or PhotoshootSessionSalesStrategyService(
            repository=self.strategies, photoshoots=self.photoshoots,
        )

    def run(self, *, deliverable_id: str | None = None, session_id: str | None = None):
        if bool(deliverable_id) == bool(session_id):
            raise RepairPrerequisiteError("Provide exactly one Photoshoot Deliverable ID or Session ID.")
        deliverable = (
            self.photoshoots.get(str(deliverable_id))
            if deliverable_id else self.photoshoots.get_by_session(str(session_id))
        )
        if deliverable is None:
            raise RepairPrerequisiteError("Photoshoot: NOT FOUND. No data was modified.")

        canonical_session_id = str(deliverable["photoshoot_session_id"])
        canonical_deliverable_id = str(deliverable["deliverable_id"])
        title = str(
            deliverable.get("display_title") or deliverable.get("display_name")
            or canonical_deliverable_id
        )
        existing = self.strategies.latest(canonical_session_id)
        if existing is not None:
            return self._result(title, canonical_deliverable_id, canonical_session_id,
                                existing, generated=False)

        intelligence = self.photoshoots.get_intelligence(canonical_session_id)
        if not intelligence or intelligence.get("status") != "READY":
            raise RepairPrerequisiteError("Production Intelligence: NOT READY. No data was modified.")
        version = str(intelligence.get("intelligence_version") or "").strip()
        if not version or not dict(intelligence.get("production_analysis") or {}):
            raise RepairPrerequisiteError("Production Intelligence: MISSING. No data was modified.")
        if not dict(intelligence.get("cross_validation") or {}):
            raise RepairPrerequisiteError("Cross-validation: MISSING. No data was modified.")

        members = tuple(self.photoshoots.members(canonical_session_id))
        if not members:
            raise RepairPrerequisiteError("Approved Photoshoot Assets: MISSING. No data was modified.")
        member_ids = tuple(int(item["asset_id"]) for item in members)
        if len(member_ids) != len(set(member_ids)):
            raise RepairPrerequisiteError("Approved Photoshoot Assets: DUPLICATED. No data was modified.")

        shots = tuple(self.photoshoots.shot_intelligence(canonical_session_id, version))
        shot_ids = tuple(int(item["asset_id"]) for item in shots)
        complete_shots = (
            len(shots) == len(members)
            and len(shot_ids) == len(set(shot_ids))
            and set(shot_ids) == set(member_ids)
            and all(item.get("status") == "READY" and dict(item.get("profile_data") or {}) for item in shots)
        )
        if not complete_shots:
            raise RepairPrerequisiteError(
                "Shot Intelligence: INCOMPLETE for approved Photoshoot Assets. No data was modified."
            )

        strategy = self.strategy_service.generate(
            canonical_deliverable_id,
            creator_profile_id=int(deliverable["creator_profile_id"]),
            strategy_version=SESSION_SALES_STRATEGY_VERSION,
        )
        persisted = self.strategies.latest(canonical_session_id)
        if (
            persisted is None or persisted.status != "READY"
            or persisted.strategy_version != SESSION_SALES_STRATEGY_VERSION
            or persisted.strategy_version != strategy.strategy_version
        ):
            raise RuntimeError("Session Sales Strategy generation did not persist a canonical READY result.")
        return self._result(title, canonical_deliverable_id, canonical_session_id,
                            persisted, generated=True)

    @staticmethod
    def _result(title, deliverable_id, session_id, strategy, *, generated):
        return {
            "photoshoot": title,
            "deliverable_id": deliverable_id,
            "session_id": session_id,
            "production_intelligence": "FOUND",
            "shot_intelligence": "FOUND",
            "cross_validation": "FOUND",
            "approved_assets": "FOUND",
            "session_strategy": "GENERATED" if generated else "ALREADY READY — NO WORK",
            "strategy_version": strategy.strategy_version,
            "status": strategy.status,
            "generated": generated,
        }


def _print_summary(result: dict) -> None:
    print(f"Photoshoot: {result['photoshoot']}")
    print(f"Deliverable ID: {result['deliverable_id']}")
    print(f"Session ID: {result['session_id']}")
    print(f"Production Intelligence: {result['production_intelligence']}")
    print(f"Shot Intelligence: {result['shot_intelligence']}")
    print(f"Cross-validation: {result['cross_validation']}")
    print(f"Approved Assets: {result['approved_assets']}")
    print(f"Session Strategy: {result['session_strategy']}")
    print(f"Strategy Version: {result['strategy_version']}")
    print(f"Status: {result['status']}")
    print("No other Photoshoot data modified.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--deliverable-id")
    identity.add_argument("--session-id")
    arguments = parser.parse_args(argv)
    try:
        result = MissingSessionSalesStrategyRepair().run(
            deliverable_id=arguments.deliverable_id, session_id=arguments.session_id,
        )
    except RepairPrerequisiteError as error:
        print(f"Repair stopped: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"Repair failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
