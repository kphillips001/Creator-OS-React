from app.services.explainable_diagnostic_service import ExplainableDiagnosticService
from app.services.schema_manager_service import SchemaCertificationReport, SchemaTableAudit
from app.services.creator_intelligence_service import CreatorIntelligenceService


def report(*, status="FAIL", missing=(), drift=(), tables=(), evidence=None):
    return SchemaCertificationReport(
        status=status, migrations_applied=(), migrations_recorded=(),
        missing_migrations=tuple(missing), drift=tuple(drift),
        tables=tuple(tables), evidence=evidence or {},
    )


def test_pending_migration_is_machine_actionable():
    diagnostic = ExplainableDiagnosticService.schema(
        report(missing=("20260726_014_example.sql",))
    )
    assert diagnostic["classification"] == "PENDING_MIGRATION"
    assert diagnostic["automatic_resolution"] is True
    assert diagnostic["evidence"][0]["values"] == ["20260726_014_example.sql"]


def test_checksum_mismatch_requires_supervision():
    diagnostic = ExplainableDiagnosticService.schema(
        report(drift=("Migration checksum mismatch: 001.sql",))
    )
    assert diagnostic["classification"] == "CHECKSUM_MISMATCH"
    assert diagnostic["automatic_resolution"] is False


def test_schema_drift_and_missing_table_are_explained():
    missing = SchemaTableAudit(
        table_name="example", owner="test", migration="001.sql",
        repository="Repo", service="Service", exists=False,
    )
    diagnostic = ExplainableDiagnosticService.schema(report(tables=(missing,)))
    assert diagnostic["classification"] == "MISSING_TABLE"
    assert "example" in diagnostic["root_cause"]


def test_unknown_failure_states_why_it_is_unknown():
    diagnostic = ExplainableDiagnosticService.schema(report())
    assert diagnostic["classification"] == "UNKNOWN_INTERNAL_FAILURE"
    assert diagnostic["confidence"] < 0.5
    assert any(item["kind"] == "unknown_reason" for item in diagnostic["evidence"])


def test_stale_certification_requires_refresh_not_repair():
    diagnostic = ExplainableDiagnosticService.schema(
        report(drift=("Cached certification is stale.",))
    )
    assert diagnostic["classification"] == "STALE_CERTIFICATION"
    assert diagnostic["automatic_resolution"] is False
    assert "Refresh" in diagnostic["recommended_action"]


def test_passing_certification_has_complete_contract():
    diagnostic = ExplainableDiagnosticService.schema(report(status="PASS"))
    assert diagnostic["classification"] == "HEALTHY"
    assert set(diagnostic) == {
        "status", "summary", "classification", "root_cause", "evidence",
        "confidence", "automatic_resolution", "resolution_reason",
        "recommended_action", "affected_components", "last_updated",
    }


def test_backend_health_exposes_score_deductions():
    diagnostics = CreatorIntelligenceService._health(
        {
            "overallHealth": "warning", "healthScore": 97,
            "providerWarnings": [{"name": "Frontend heartbeat", "weight": -2}],
            "workerCounts": {"healthy": 4, "stale": 0, "failed": 0},
            "database": {"status": "healthy", "summary": "Connected"},
            "warnings": [],
        },
        report(status="PASS"),
        {"overallReadiness": "READY", "reason": "Ready"},
    )
    backend = next(item for item in diagnostics if item["label"] == "Backend")
    assert backend["classification"] == "HEALTH_SCORE_DEDUCTION"
    assert {"kind": "health_score", "value": 97} in backend["evidence"]
    assert any(item["kind"] == "provider_warnings" for item in backend["evidence"])
