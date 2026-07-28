"""Read-only executive projection for Creator OS."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.creator_intelligence import CreatorIntelligence, NormalizedDocument
from app.repositories.creator_intelligence_repository import CreatorIntelligenceRepository
from app.repositories.creator_lifestyle_repository import CreatorLifestyleRepository
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.social_creative_direction_repository import (
    SocialCreativeDirectionRepository,
)
from app.services.generation_library_service import GenerationLibraryService
from app.services.operations_workspace_service import OperationsWorkspaceService
from app.services.schema_manager_service import SchemaManagerService
from app.services.commerce_mode_service import CommerceModeService
from app.services.developer_agent_execution_service import (
    DeveloperAgentExecutionService,
)
from app.services.explainable_diagnostic_service import ExplainableDiagnosticService
from app.services.schema_manager_service import SchemaCertificationReport
from app.repositories.ava_coach_repository import AvaCoachRepository


class CreatorIntelligenceService:
    PERSONALITY_FIELDS = (
        "persona_name", "age", "gender", "location", "is_active", "archetype",
        "personality_description", "backstory", "lifestyle_context",
        "lifestyle_vibe", "daily_routine", "hobbies", "likes", "dislikes",
        "ideal_user_type", "turn_ons", "turn_offs", "sexual_style",
        "sexual_likes", "sexual_dislikes", "kinks", "fantasy_style",
        "tone_style", "flirt_style", "tease_intensity", "push_pull_style",
        "mystery_level", "response_style", "pacing_style",
        "question_frequency", "emotional_depth", "affection_style",
        "jealousy_style", "availability_style", "conversation_hooks",
        "retention_hooks", "escalation_style", "escalation_triggers",
        "self_value_style", "persona_intensity", "boundaries",
        "sexual_boundaries", "hard_limits", "response_rules",
    )
    LIFESTYLE_FIELDS = (
        "career", "lifestyle_overview", "favorite_activities",
        "weekend_escapes", "small_town_roots", "outdoor_lifestyle",
        "personal_style",
    )
    SOCIAL_CREATIVE_DIRECTION_FIELDS = (
        "purpose", "wardrobe", "visual_style", "seasonal_guidance",
        "things_to_avoid",
    )

    def __init__(
        self,
        *,
        repository: Any | None = None,
        operations: Any | None = None,
        generation_library: Any | None = None,
        schema_manager: Any | None = None,
        ava_coach_repository: Any | None = None,
        creator_profile_loader: Any | None = None,
        lifestyle_repository: Any | None = None,
        social_creative_direction_repository: Any | None = None,
        now: Any | None = None,
    ) -> None:
        self.repository = repository or CreatorIntelligenceRepository()
        self.operations = operations or OperationsWorkspaceService()
        self.generation_library = generation_library or GenerationLibraryService()
        self.schema_manager = schema_manager or SchemaManagerService()
        self.ava_coach_repository = ava_coach_repository or AvaCoachRepository()
        self.creator_profile_loader = (
            creator_profile_loader or get_active_creator_profile
        )
        self.lifestyle_repository = (
            lifestyle_repository or CreatorLifestyleRepository()
        )
        self.social_creative_direction_repository = (
            social_creative_direction_repository
            or SocialCreativeDirectionRepository()
        )
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.commerce_modes = CommerceModeService()

    def get_for_account(self, *, fanvue_account_id: int | str) -> CreatorIntelligence:
        """Load and assemble the active account's canonical creator documents."""
        account_id = str(fanvue_account_id)
        personality = self.creator_profile_loader(account_id)
        if not personality:
            raise LookupError(
                f"No active creator profile exists for account {account_id}."
            )

        creator_profile_id = int(personality["id"])
        lifestyle = self.lifestyle_repository.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
        )
        social_direction = self.social_creative_direction_repository.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
        )
        if lifestyle is None:
            raise LookupError(
                f"No lifestyle document exists for creator profile "
                f"{creator_profile_id} in account {account_id}."
            )
        if social_direction is None:
            raise LookupError(
                f"No social creative direction exists for creator profile "
                f"{creator_profile_id} in account {account_id}."
            )

        return CreatorIntelligence(
            personality=self._normalize(
                personality, self.PERSONALITY_FIELDS
            ),
            lifestyle=self._normalize(lifestyle, self.LIFESTYLE_FIELDS),
            social_creative_direction=self._normalize(
                social_direction, self.SOCIAL_CREATIVE_DIRECTION_FIELDS
            ),
        )

    @staticmethod
    def _normalize(
        source: dict,
        fields: tuple[str, ...],
    ) -> NormalizedDocument:
        """Project repository rows onto the immutable public document schema."""
        return CreatorIntelligence.immutable_document(
            {field: source.get(field) for field in fields}
        )

    def dashboard(self, *, creator_profile_id: int, fanvue_account_id: int) -> dict:
        current = self.now()
        today = current.replace(hour=0, minute=0, second=0, microsecond=0)
        facts = self.repository.snapshot(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            today=today,
        )
        operations = self.operations.overview(account_id=fanvue_account_id)
        try:
            schema = self.schema_manager.certify()
        except Exception as exc:
            schema = SchemaCertificationReport(
                status="FAIL", migrations_applied=(), migrations_recorded=(),
                missing_migrations=(),
                drift=(),
                tables=(),
                evidence={
                    "internal_exception": {
                        "type": type(exc).__name__, "message": str(exc),
                    }
                },
            )
        try:
            developer_agent = DeveloperAgentExecutionService().readiness()
        except Exception as exc:
            developer_agent = {
                "overallReadiness": "UNAVAILABLE",
                "reason": f"Developer Agent readiness unavailable: {exc}",
            }
        records = self.generation_library.list_records()
        active = sum(record.status == "active" for record in records)
        staged = sum(record.status == "staged_asset_library" for record in records)
        archived = sum(record.status not in {"active", "staged_asset_library"} for record in records)
        offers = int(facts.get("offers_today") or 0)
        purchases = int(facts.get("purchases_today") or 0)
        conversion = round((purchases / offers) * 100, 1) if offers else 0.0
        try:
            coach_summary = self.ava_coach_repository.coach_summary(fanvue_account_id)
        except Exception:
            coach_summary = {
                "latest_analysis_at": None, "conversations_reviewed": 0,
                "pending_recommendations": 0, "approved_for_version": 0,
            }

        health = self._health(operations, schema, developer_agent)
        pipeline = {
            "generationLibrary": active,
            "assetLibrary": staged,
            "canonicalAssets": int(facts.get("canonical_assets") or 0),
            "readyAssets": int(facts.get("ready_assets") or 0),
            "availableInventory": int(facts.get("available_inventory") or 0),
            "commercialOfferings": int(facts.get("offerings") or 0),
            "readyOfferings": int(facts.get("ready_offerings") or 0),
            "readyToPublish": int(facts.get("ready_to_publish") or 0),
            "live": int(facts.get("live_publications") or 0),
            "archive": archived,
        }
        recommendations = self._recommendations(facts, pipeline, operations, schema.status)
        problems = [
            {
                "title": item["label"], "detail": item["summary"],
                "severity": item["status"], "diagnostic": item,
            }
            for item in health
            if item["status"] != "Healthy"
        ]
        if int(facts.get("failed_publications") or 0):
            problems.append({
                "title": "Publication failures",
                "detail": f"{facts['failed_publications']} provider publication records require attention.",
                "severity": "Needs Attention",
            })

        return {
            "generatedAt": current,
            "relationshipMode": {
                "mode": self.commerce_modes.get_mode().value,
                "customersMet": int(facts.get("customers_met") or 0),
                "returningVisitors": int(facts.get("repeat_buyers") or 0),
                "wouldHaveSoldToday": int(facts.get("would_have_sold_today") or 0),
                "mostRequestedOffering": facts.get("top_offering_type") or "No evidence",
                "customersReadyForCommerce": int(
                    facts.get("pre_launch_interest_customers") or 0
                ),
                "highInterestCustomers": int(
                    facts.get("pre_launch_interest_customers") or 0
                ),
            },
            "systemHealth": health,
            "today": {
                "activeConversations": None,
                "waitingReplies": None,
                "purchaseIntentsWaiting": int(facts.get("waiting_intents") or 0),
                "offers": offers,
                "purchases": purchases,
                "revenueMinor": int(facts.get("revenue_today_minor") or 0),
                "conversionRate": conversion,
                "recommendations": len(recommendations),
                "learningEvents": int(facts.get("learning_events_today") or 0),
            },
            "recommendations": recommendations,
            "avaCoachSummary": coach_summary,
            "commerceLearning": {
                "profiles": int(facts.get("learning_profiles") or 0),
                "eventsToday": int(facts.get("learning_events_today") or 0),
                "confidence": (
                    f"{float(facts['average_learning_confidence']) * 100:.0f}%"
                    if facts.get("average_learning_confidence") is not None else "No evidence"
                ),
                "trend": "Tracked" if int(facts.get("learning_events_today") or 0) else "No activity today",
                "signals": [
                    {"label": "Top themes", "value": "Untracked"},
                    {"label": "Activity", "value": f"{int(facts.get('learning_events_today') or 0)} events today"},
                    {"label": "Location", "value": "Untracked"},
                    {"label": "Outfits", "value": "Untracked"},
                    {"label": "Content types", "value": facts.get("top_media_type") or "No evidence"},
                    {"label": "Collections", "value": facts.get("top_offering_type") or "No evidence"},
                    {"label": "New interests", "value": "No structured evidence today"},
                ],
            },
            "contentPipeline": pipeline,
            "customerOpportunities": [
                {"label": "Active offers waiting", "value": int(facts.get("waiting_intents") or 0)},
                {"label": "Repeat buyers", "value": int(facts.get("repeat_buyers") or 0)},
                {"label": "High-value customers", "value": int(facts.get("high_value_buyers") or 0)},
                {"label": "Expired purchase intents", "value": int(facts.get("expired_intents") or 0)},
                {"label": "Ignored or expired offers", "value": int(facts.get("ignored_offers") or 0)},
            ],
            "revenueOpportunities": [
                {"label": "READY offerings", "value": int(facts.get("ready_offerings") or 0)},
                {"label": "Never-offered photosets", "value": int(facts.get("never_offered_photosets") or 0)},
                {"label": "Available inventory", "value": int(facts.get("available_inventory") or 0)},
                {"label": "Waiting to publish", "value": int(facts.get("ready_to_publish") or 0)},
            ],
            "problems": problems,
        }

    @staticmethod
    def _health(
        operations: dict, schema: Any, developer_agent: dict | None = None,
    ) -> list[dict]:
        workers = operations.get("workerCounts", {})
        worker_status = "Healthy" if not (workers.get("failed", 0) or workers.get("stale", 0)) else "Needs Attention"
        database = operations.get("database", {})
        database_status = "Healthy" if str(database.get("status", "")).lower() in {"healthy", "pass", "ok"} else "Warning"
        overall = "Healthy" if str(operations.get("overallHealth", "")).lower() in {"healthy", "pass", "ok"} else "Warning"
        schema_status = "Healthy" if schema.status == "PASS" else "Needs Attention"
        developer_agent = developer_agent or {
            "overallReadiness": "UNAVAILABLE",
            "reason": "Developer Agent readiness was not collected.",
        }
        developer_status = (
            "Healthy"
            if developer_agent.get("overallReadiness") == "READY"
            else "Warning"
            if developer_agent.get("overallReadiness") == "DEGRADED"
            else "Offline"
        )
        explain = ExplainableDiagnosticService
        worker_summary = (
            f"{workers.get('healthy', 0)} healthy, {workers.get('stale', 0)} stale, "
            f"{workers.get('failed', 0)} failed."
        )
        provider_warnings = operations.get("providerWarnings") or []
        return [
            explain.health(
                label="Backend", status=overall,
                summary=f"Operations health: {operations.get('overallHealth', 'untracked')}; score {operations.get('healthScore', 'untracked')}.",
                classification="HEALTHY" if overall == "Healthy" else "HEALTH_SCORE_DEDUCTION",
                root_cause=("No backend health deduction detected." if overall == "Healthy"
                            else "One or more Operations health checks deducted from the backend score."),
                evidence=[
                    {"kind": "health_score", "value": operations.get("healthScore")},
                    {"kind": "provider_warnings", "value": provider_warnings},
                    {"kind": "worker_counts", "value": workers},
                    {"kind": "database", "value": database},
                    {"kind": "failing_checks", "value": operations.get("failingChecks") or []},
                ],
                automatic=overall != "Healthy",
                recommended_action=("No action required." if overall == "Healthy"
                                    else "Repair each listed deduction and rerun backend health."),
            ),
            explain.health(
                label="Frontend", status="Warning",
                summary="Browser rendering is active; an independent frontend heartbeat is not instrumented.",
                classification="OBSERVABILITY_GAP",
                root_cause="No independent frontend heartbeat source exists.",
                evidence=[{"kind": "missing_signal", "value": "frontend heartbeat"}],
                automatic=True,
                recommended_action="Add an independent frontend heartbeat diagnostic.",
            ),
            explain.health(
                label="Workers", status=worker_status, summary=worker_summary,
                classification="HEALTHY" if worker_status == "Healthy" else "WORKER_HEALTH_FAILURE",
                root_cause=("No failed or stale workers detected." if worker_status == "Healthy"
                            else "Persisted worker heartbeats contain stale or failed workers."),
                evidence=[{"kind": "worker_counts", "value": workers},
                          {"kind": "warnings", "value": operations.get("warnings") or []}],
                automatic=worker_status != "Healthy",
                recommended_action=("No action required." if worker_status == "Healthy"
                                    else "Inspect affected worker heartbeats, recover the worker, and verify a fresh heartbeat."),
            ),
            explain.health(
                label="Recommendation Engine", status="Healthy",
                summary="Deterministic recommendation diagnostics are installed.",
                classification="HEALTHY", root_cause="No failure detected.",
                evidence=[{"kind": "diagnostic", "value": "installed"}],
                automatic=False, recommended_action="No action required.",
            ),
            explain.health(
                label="Commerce Learning", status="Healthy",
                summary="Commerce learning persistence is available.",
                classification="HEALTHY", root_cause="No failure detected.",
                evidence=[{"kind": "persistence", "value": "available"}],
                automatic=False, recommended_action="No action required.",
            ),
            explain.health(
                label="Fanvue",
                status="Warning" if provider_warnings else "Healthy",
                summary=("Provider configuration warnings are present." if provider_warnings
                         else "No Fanvue provider warning is present."),
                classification="CONFIGURATION_REQUIRED" if provider_warnings else "HEALTHY",
                root_cause=("Operations reported provider configuration warnings." if provider_warnings
                            else "No failure detected."),
                evidence=[{"kind": "provider_warnings", "value": provider_warnings}],
                automatic=False,
                recommended_action=("Open Provider Connections and resolve the listed configuration."
                                    if provider_warnings else "No action required."),
            ),
            explain.health(
                label="Telegram", status=worker_status,
                summary="Status is derived from persisted worker heartbeat evidence.",
                classification="HEALTHY" if worker_status == "Healthy" else "WORKER_HEALTH_FAILURE",
                root_cause=("No worker failure detected." if worker_status == "Healthy"
                            else "The shared worker evidence contains a stale or failed process."),
                evidence=[{"kind": "worker_counts", "value": workers}],
                automatic=worker_status != "Healthy",
                recommended_action=("No action required." if worker_status == "Healthy"
                                    else "Inspect Telegram and worker heartbeat diagnostics."),
            ),
            explain.health(
                label="Database", status=database_status,
                summary=str(database.get("summary") or database.get("status") or "Untracked"),
                classification="HEALTHY" if database_status == "Healthy" else "DATABASE_UNAVAILABLE",
                root_cause=("Database connection check passed." if database_status == "Healthy"
                            else "The database connection check did not report a healthy result."),
                evidence=[{"kind": "database_check", "value": database}],
                automatic=False,
                recommended_action=("No action required." if database_status == "Healthy"
                                    else "Verify database configuration and availability."),
            ),
            explain.health(
                label="Operations", status=overall,
                summary=f"Health score {operations.get('healthScore', 'untracked')}.",
                classification="HEALTHY" if overall == "Healthy" else "OPERATIONS_CHECK_FAILURE",
                root_cause=("No failing Operations check detected." if overall == "Healthy"
                            else "Operations reported one or more failing health checks."),
                evidence=[
                    {"kind": "failing_checks", "value": operations.get("failingChecks") or []},
                    {"kind": "operations_summary", "value": {
                        "healthScore": operations.get("healthScore"),
                        "failureCount": operations.get("failureCount"),
                        "publishingAttention": operations.get("publishingAttention"),
                    }},
                ],
                automatic=overall != "Healthy",
                recommended_action=("No action required." if overall == "Healthy"
                                    else "Open Operations and repair each failing check."),
            ),
            explain.schema(schema) | {"label": "Schema Certification"},
            explain.health(
                label="Developer Agent", status=developer_status,
                summary=str(developer_agent.get("reason") or "Readiness unavailable."),
                classification=("HEALTHY" if developer_status == "Healthy"
                                else "DEVELOPER_AGENT_UNAVAILABLE"),
                root_cause=("Developer Agent readiness passed." if developer_status == "Healthy"
                            else str(developer_agent.get("reason") or "Readiness evidence is unavailable.")),
                evidence=[{"kind": "readiness", "value": developer_agent}],
                automatic=False,
                recommended_action=("No action required." if developer_status == "Healthy"
                                    else "Open Operations and satisfy the reported readiness requirement."),
            ),
        ]

    @staticmethod
    def _recommendations(facts: dict, pipeline: dict, operations: dict, schema_status: str) -> list[dict]:
        items: list[dict] = []
        if pipeline["availableInventory"] and not pipeline["readyOfferings"]:
            items.append({"title": "Package available inventory", "why": f"{pipeline['availableInventory']} available assets exist but no offering is READY.", "action": "/commerce"})
        if int(facts.get("never_offered_photosets") or 0):
            items.append({"title": "Review unoffered photosets", "why": f"{facts['never_offered_photosets']} READY photosets have never been presented.", "action": "/commerce/offerings"})
        if pipeline["readyToPublish"]:
            items.append({"title": "Review publication queue", "why": f"{pipeline['readyToPublish']} publications are READY_TO_PUBLISH.", "action": "/commerce"})
        if int(facts.get("expired_intents") or 0):
            items.append({"title": "Inspect expired purchase intents", "why": f"{facts['expired_intents']} intents expired without a verified purchase.", "action": "/developer/purchase-intents"})
        if operations.get("publishingAttention"):
            items.append({"title": "Resolve publishing attention", "why": f"{operations['publishingAttention']} publishing records require attention.", "action": "/business/operations"})
        if schema_status != "PASS":
            items.append({"title": "Review schema certification", "why": "The current database schema certification is not passing.", "action": "/business/operations"})
        return items[:6]
