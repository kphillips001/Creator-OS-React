"""Backfill canonical intelligence for one legacy completed Photoshoot."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import get_db_connection
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.repositories.photoshoot_session_sales_strategy_repository import PhotoshootSessionSalesStrategyRepository
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService
from app.services.photoshoot_commercial_intelligence_service import PHOTOSHOOT_INTELLIGENCE_VERSION
from app.services.photoshoot_sale_preparation_service import PhotoshootSalePreparationService
from app.services.photoshoot_session_sales_strategy_service import (
    SESSION_SALES_STRATEGY_VERSION, PhotoshootSessionSalesStrategyService,
)


COMMERCIAL_FIELDS = (
    "commercial_title", "subtitle", "commercial_summary", "story", "theme", "experience",
    "emotional_journey", "buyer_profile", "sales_strategy", "sales_brain_brief",
    "input_snapshot", "model", "generated_at",
)


class BackfillPrerequisiteError(RuntimeError):
    """The target is not a safe legacy backfill candidate."""


class BackfillAuditRepository:
    """Read-only guards around data the intelligence pipeline must not mutate."""

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def protected_snapshot(self, deliverable_id: str, session_id: str) -> dict:
        return {
            "memberships": self._rows("""SELECT asset_id,shot_order,approved,is_hero
                FROM public.photoshoot_asset_memberships WHERE photoshoot_session_id=%s
                ORDER BY shot_order,asset_id""", (session_id,)),
            "content_intelligence": self._rows("""SELECT ci.* FROM public.content_intelligence_profiles ci
                JOIN public.photoshoot_asset_memberships m ON m.asset_id=ci.asset_id
                WHERE m.photoshoot_session_id=%s ORDER BY ci.asset_id""", (session_id,)),
            "deliverable": self._rows("""SELECT * FROM public.photoshoot_commerce_deliverables
                WHERE deliverable_id=%s""", (deliverable_id,)),
            "offerings": self._rows("""SELECT * FROM public.commercial_offerings
                WHERE source_photoshoot_deliverable_id=%s ORDER BY offering_id""", (deliverable_id,)),
            "publications": self._rows("""SELECT p.* FROM public.commercial_publications p
                JOIN public.commercial_offerings o ON o.offering_id=p.commercial_offering_id
                WHERE o.source_photoshoot_deliverable_id=%s ORDER BY p.publication_id""", (deliverable_id,)),
        }

    def _rows(self, sql: str, parameters: tuple) -> tuple[dict, ...]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, parameters)
                return tuple(dict(row) for row in cursor.fetchall())


class LegacyPhotoshootIntelligenceBackfill:
    def __init__(self, *, photoshoots=None, strategies=None, pipeline=None,
                 strategy_service=None, sale_preparation=None, audit=None):
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.strategies = strategies or PhotoshootSessionSalesStrategyRepository()
        self.pipeline = pipeline or PhotoshootCommerceDeliverableService(repository=self.photoshoots)
        self.strategy_service = strategy_service or PhotoshootSessionSalesStrategyService(
            repository=self.strategies, photoshoots=self.photoshoots,
        )
        self.sale_preparation = sale_preparation or PhotoshootSalePreparationService(
            photoshoots=self.photoshoots, strategies=self.strategies,
        )
        self.audit = audit or BackfillAuditRepository()

    def run(self, *, deliverable_id: str | None = None, session_id: str | None = None) -> dict:
        if bool(deliverable_id) == bool(session_id):
            raise BackfillPrerequisiteError("Provide exactly one --deliverable-id or --session-id.")
        deliverable = (self.photoshoots.get(str(deliverable_id)) if deliverable_id
                       else self.photoshoots.get_by_session(str(session_id)))
        if deliverable is None:
            raise BackfillPrerequisiteError("Photoshoot: FAILED (not found). No data was modified.")

        deliverable_id = str(deliverable["deliverable_id"])
        session_id = str(deliverable["photoshoot_session_id"])
        title = str(deliverable.get("display_title") or deliverable.get("display_name") or deliverable_id)
        members = tuple(self.photoshoots.members(session_id))
        self._validate_members(deliverable, members)
        intelligence = self.photoshoots.get_intelligence(session_id)
        if not self._has_legacy_commercial_intelligence(intelligence):
            raise BackfillPrerequisiteError("Commercial Intelligence: FAILED (missing). No data was modified.")

        existing_shots = tuple(self.photoshoots.latest_shot_intelligence(session_id))
        existing_strategy = self.strategies.latest(session_id)
        if self._has_canonical_intelligence(intelligence, existing_shots) or existing_strategy is not None:
            return self._skipped(title, deliverable_id, session_id, len(members), intelligence,
                                 existing_shots, existing_strategy)

        protected_before = copy.deepcopy(self.audit.protected_snapshot(deliverable_id, session_id))
        commercial_before = self._commercial_snapshot(intelligence)
        session = self.pipeline.queue.get_session(session_id)
        if int(session.creator_profile_id) != int(deliverable["creator_profile_id"]):
            raise BackfillPrerequisiteError("Photoshoot ownership mismatch. No data was modified.")

        self.pipeline.run_canonical_intelligence(
            session, intelligence_version=PHOTOSHOOT_INTELLIGENCE_VERSION, force=True,
            preserve_commercial_intelligence=True,
        )
        canonical = self.photoshoots.get_intelligence(session_id)
        shots = tuple(self.photoshoots.shot_intelligence(session_id, PHOTOSHOOT_INTELLIGENCE_VERSION))
        self._verify_canonical(canonical, shots, members)
        if self._commercial_snapshot(canonical) != commercial_before:
            raise RuntimeError("Legacy Commercial Intelligence changed during canonical backfill.")
        if self.audit.protected_snapshot(deliverable_id, session_id) != protected_before:
            raise RuntimeError("Protected Photoshoot or commerce data changed during canonical backfill.")

        strategy = self.strategy_service.generate(
            deliverable_id, creator_profile_id=int(deliverable["creator_profile_id"]),
            strategy_version=SESSION_SALES_STRATEGY_VERSION,
        )
        persisted_strategy = self.strategies.latest(session_id)
        if (persisted_strategy is None or persisted_strategy.status != "READY"
                or persisted_strategy.strategy_version != SESSION_SALES_STRATEGY_VERSION
                or strategy.strategy_version != persisted_strategy.strategy_version):
            raise RuntimeError("Session Sales Strategy: FAILED (canonical READY result not persisted).")
        inspection = self.sale_preparation.inspect(
            deliverable_id, creator_profile_id=int(deliverable["creator_profile_id"]),
        )
        if len(inspection.get("steps") or ()) != len(members):
            raise RuntimeError("Prepare for Sale: FAILED (strategy steps do not match approved Assets).")
        if self.audit.protected_snapshot(deliverable_id, session_id) != protected_before:
            raise RuntimeError("Protected Photoshoot or commerce data changed during strategy generation.")
        return {
            "photoshoot": title, "deliverable_id": deliverable_id, "session_id": session_id,
            "approved_assets": f"FOUND ({len(members)})", "commercial_intelligence": "FOUND",
            "production_intelligence": "GENERATED", "shot_intelligence": f"GENERATED ({len(shots)})",
            "cross_validation": "GENERATED", "session_strategy": "GENERATED",
            "intelligence_version": PHOTOSHOOT_INTELLIGENCE_VERSION,
            "strategy_version": SESSION_SALES_STRATEGY_VERSION, "status": "COMPLETE",
            "prepare_for_sale": "READY", "generated": True,
        }

    @staticmethod
    def _validate_members(deliverable: dict, members: tuple[dict, ...]) -> None:
        if not members:
            raise BackfillPrerequisiteError("Approved Assets: FAILED (none found). No data was modified.")
        ids = tuple(int(row["asset_id"]) for row in members)
        orders = tuple(int(row["shot_order"]) for row in members)
        expected_ids = tuple(int(value) for value in (deliverable.get("ordered_member_asset_ids") or ()))
        if (len(ids) != len(set(ids)) or orders != tuple(range(1, len(members) + 1))
                or not all(bool(row.get("approved")) for row in members) or ids != expected_ids):
            raise BackfillPrerequisiteError("Approved membership ordering is invalid. No data was modified.")

    @staticmethod
    def _has_legacy_commercial_intelligence(row: dict | None) -> bool:
        if not row:
            return False
        profile = dict(row.get("profile_data") or {})
        return bool(row.get("commercial_title") or profile.get("commercial_title"))

    @staticmethod
    def _has_canonical_intelligence(row: dict | None, shots: tuple[dict, ...]) -> bool:
        return bool(row and (dict(row.get("production_analysis") or {})
                            or dict(row.get("cross_validation") or {})
                            or row.get("analysis_completed_at")
                            or row.get("pipeline_stage") == "COMPLETE"
                            or shots))

    @staticmethod
    def _commercial_snapshot(row: dict) -> dict:
        profile = dict(row.get("profile_data") or {})
        return {field: copy.deepcopy(profile[field] if field in profile else row.get(field))
                for field in COMMERCIAL_FIELDS}

    @staticmethod
    def _verify_canonical(row: dict | None, shots: tuple[dict, ...], members: tuple[dict, ...]) -> None:
        member_pairs = tuple((int(item["asset_id"]), int(item["shot_order"])) for item in members)
        shot_pairs = tuple((int(item["asset_id"]), int(item["shot_order"])) for item in shots)
        if not row or row.get("status") != "READY" or row.get("pipeline_stage") != "COMPLETE":
            raise RuntimeError("Production Intelligence: FAILED (pipeline is not COMPLETE).")
        if row.get("intelligence_version") != PHOTOSHOOT_INTELLIGENCE_VERSION:
            raise RuntimeError("Production Intelligence: FAILED (unexpected version).")
        if not dict(row.get("production_analysis") or {}) or not row.get("analysis_completed_at"):
            raise RuntimeError("Production Intelligence: FAILED (canonical result missing).")
        if not dict(row.get("cross_validation") or {}):
            raise RuntimeError("Cross-validation: FAILED (canonical result missing).")
        if shot_pairs != member_pairs or any(item.get("status") != "READY" for item in shots):
            raise RuntimeError("Shot Intelligence: FAILED (approved Asset coverage mismatch).")

    @staticmethod
    def _skipped(title, deliverable_id, session_id, count, intelligence, shots, strategy):
        return {
            "photoshoot": title, "deliverable_id": deliverable_id, "session_id": session_id,
            "approved_assets": f"FOUND ({count})", "commercial_intelligence": "FOUND",
            "production_intelligence": "FOUND" if intelligence and intelligence.get("production_analysis") else "SKIPPED",
            "shot_intelligence": f"FOUND ({len(shots)})" if shots else "SKIPPED",
            "cross_validation": "FOUND" if intelligence and intelligence.get("cross_validation") else "SKIPPED",
            "session_strategy": "FOUND" if strategy else "SKIPPED", "status": "SKIPPED",
            "prepare_for_sale": "SKIPPED", "generated": False,
        }


def _print(result: dict) -> None:
    for label, key in (("Photoshoot", "photoshoot"), ("Approved Assets", "approved_assets"),
                       ("Commercial Intelligence", "commercial_intelligence"),
                       ("Production Intelligence", "production_intelligence"),
                       ("Shot Intelligence", "shot_intelligence"), ("Cross-validation", "cross_validation"),
                       ("Session Sales Strategy", "session_strategy"), ("Status", "status"),
                       ("Prepare for Sale", "prepare_for_sale")):
        print(f"{label}: {result[key]}")
    print(f"Deliverable ID: {result['deliverable_id']}")
    print(f"Canonical Session ID: {result['session_id']}")
    if result.get("intelligence_version"): print(f"Intelligence Version: {result['intelligence_version']}")
    if result.get("strategy_version"): print(f"Strategy Version: {result['strategy_version']}")
    print("No Photoshoot assets, memberships, legacy intelligence, Offerings, Publications, or Fanvue resources were modified.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--deliverable-id")
    identity.add_argument("--session-id")
    arguments = parser.parse_args(argv)
    try:
        result = LegacyPhotoshootIntelligenceBackfill().run(
            deliverable_id=arguments.deliverable_id, session_id=arguments.session_id,
        )
    except BackfillPrerequisiteError as error:
        print(f"Backfill stopped: {error}", file=sys.stderr); return 2
    except Exception as error:
        print(f"Backfill failed: {type(error).__name__}: {error}", file=sys.stderr); return 1
    _print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
