"""Build evidence-based diagnostics without guessing from display summaries."""
from __future__ import annotations

from typing import Any

from app.models.explainable_diagnostic import ExplainableDiagnostic


class ExplainableDiagnosticService:
    @staticmethod
    def schema(report: Any) -> dict[str, Any]:
        missing = list(report.missing_migrations)
        drift = list(report.drift)
        missing_tables = [
            item.table_name for item in report.tables if not item.exists
        ]
        missing_columns = [
            {"table": item.table_name, "columns": list(item.missing_columns)}
            for item in report.tables if item.missing_columns
        ]
        evidence = [
            {"kind": "pending_migrations", "values": missing},
            {"kind": "schema_drift", "values": drift},
            {"kind": "missing_tables", "values": missing_tables},
            {"kind": "missing_columns", "values": missing_columns},
            {"kind": "certification_evidence", "values": dict(report.evidence)},
        ]
        if report.status == "PASS":
            return ExplainableDiagnostic(
                status="Healthy", summary="Schema certification passed.",
                classification="HEALTHY", root_cause="No schema failure detected.",
                evidence=[
                    {"kind": "pending_migrations", "values": missing},
                    {"kind": "schema_drift", "values": drift},
                    {"kind": "certification_evidence", "values": dict(report.evidence)},
                ],
                confidence=1.0, automatic_resolution=False,
                resolution_reason="No repair is required.",
                recommended_action="No action required.",
                affected_components=["Schema Certification"],
                last_updated=ExplainableDiagnostic.timestamp(),
            ).as_dict()
        if missing:
            classification = "PENDING_MIGRATION"
            root = f"{len(missing)} forward migration(s) are not recorded as applied."
            action = "Apply the listed migrations in repository order and recertify."
            automatic = True
        elif any("checksum" in value.lower() for value in drift):
            classification = "CHECKSUM_MISMATCH"
            root = "An applied migration checksum differs from its immutable source file."
            action = "Restore the applied migration source or perform supervised migration recovery."
            automatic = False
        elif any("order" in value.lower() for value in drift):
            classification = "MIGRATION_ORDER_VIOLATION"
            root = "Migration history violates forward migration ordering."
            action = "Review migration history and perform supervised ordering recovery."
            automatic = False
        elif any(
            token in value.lower() for value in drift
            for token in ("cached", "stale", "projection mismatch")
        ):
            classification = "STALE_CERTIFICATION"
            root = "Certification evidence is cached, stale, or inconsistent with the current projection."
            action = "Refresh schema discovery and rerun certification without executing repairs."
            automatic = False
        elif any("verification" in value.lower() for value in drift):
            classification = "FAILED_VERIFICATION"
            root = "A schema verification check failed after discovery."
            action = "Inspect the failed verification evidence and repair its owning schema object."
            automatic = True
        elif missing_tables:
            classification = "MISSING_TABLE"
            root = f"Required table(s) are absent: {', '.join(missing_tables)}."
            action = "Apply the owning migration and recertify."
            automatic = True
        elif any("index" in value.lower() for value in drift):
            classification = "MISSING_INDEX"
            root = "One or more required database indexes are absent."
            action = "Restore the declared index through the owning migration."
            automatic = True
        elif drift or missing_columns:
            classification = "SCHEMA_DRIFT"
            root = "The discovered database schema differs from the declared schema contract."
            action = "Repair the listed drift through a reviewed forward migration."
            automatic = True
        else:
            classification = "UNKNOWN_INTERNAL_FAILURE"
            root = "Certification returned FAIL without a recognized failure detail."
            action = "Inspect the certification exception and collect additional evidence."
            automatic = False
            evidence.append({
                "kind": "unknown_reason",
                "values": ["The certification report contained no pending migration, drift, or missing object."],
            })
        return ExplainableDiagnostic(
            status="Needs Attention", summary=f"Schema certification failed: {root}",
            classification=classification, root_cause=root, evidence=evidence,
            confidence=0.98 if classification != "UNKNOWN_INTERNAL_FAILURE" else 0.25,
            automatic_resolution=automatic,
            resolution_reason=(
                "Repository and migration tooling can repair this classification."
                if automatic else "This classification requires supervised recovery or more evidence."
            ),
            recommended_action=action,
            affected_components=["Schema Certification", "Database"],
            last_updated=ExplainableDiagnostic.timestamp(),
        ).as_dict()

    @staticmethod
    def health(
        *, label: str, status: str, summary: str, evidence: list[dict[str, Any]],
        classification: str, root_cause: str, automatic: bool,
        recommended_action: str, affected: list[str] | None = None,
        confidence: float = 0.95,
    ) -> dict[str, Any]:
        return ExplainableDiagnostic(
            status=status, summary=summary, classification=classification,
            root_cause=root_cause, evidence=evidence, confidence=confidence,
            automatic_resolution=automatic,
            resolution_reason=(
                "The failure is repairable through repository or local runtime changes."
                if automatic else "The failure requires configuration, an operator action, or has no safe automatic repair."
            ),
            recommended_action=recommended_action,
            affected_components=affected or [label],
            last_updated=ExplainableDiagnostic.timestamp(),
        ).as_dict() | {"label": label}
