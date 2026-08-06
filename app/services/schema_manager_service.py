"""Schema reconciliation and certification for Creator OS PostgreSQL."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from app.database import get_db_connection


FORWARD_MIGRATION_DIR = Path("migrations/forward")


@dataclass(frozen=True)
class MigrationFile:
    name: str
    path: Path
    checksum: str
    sql: str


@dataclass(frozen=True)
class SchemaTableAudit:
    table_name: str
    owner: str
    migration: str
    repository: str
    service: str
    dashboard_consumers: tuple[str, ...] = ()
    legacy_status: str = "current"
    compatibility_status: str = "canonical"
    exists: bool = True
    missing_columns: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaCertificationReport:
    status: str
    migrations_applied: tuple[str, ...]
    migrations_recorded: tuple[str, ...]
    missing_migrations: tuple[str, ...]
    drift: tuple[str, ...]
    tables: tuple[SchemaTableAudit, ...]
    evidence: Mapping[str, Any] = field(default_factory=dict)


class SchemaManagerService:
    """Owns Creator OS schema discovery, migration history, and reconciliation."""

    REQUIRED_TABLES: Mapping[str, Mapping[str, Any]] = {
        "photoshoot_session_sales_strategies": {
            "owner": "Photoshoot Session Sales Brain",
            "migration": "20260804_037_photoshoot_session_sales_strategies.sql",
            "repository": "PhotoshootSessionSalesStrategyRepository",
            "service": "PhotoshootSessionSalesStrategyService",
            "dashboard": ("Customer Sales Brain",),
            "columns": (
                "photoshoot_session_id", "deliverable_id", "creator_profile_id",
                "strategy_version", "intelligence_version", "status",
                "strategy_data", "model", "generated_at",
            ),
        },
        "customer_photoshoot_lifecycles": {
            "owner": "Photoshoot Sales Opportunity",
            "migration": "20260804_033_photoshoot_sales_opportunities.sql",
            "repository": "CustomerPhotoshootLifecycleRepository",
            "service": "CustomerPhotoshootLifecycleService",
            "dashboard": ("Customer Sales Brain",),
            "columns": (
                "lifecycle_id", "creator_profile_id",
                "customer_commerce_profile_id", "photoshoot_id", "status",
                "current_position", "selected_offering_id",
                "last_sales_session_id", "last_purchase_intent_id",
                "expires_at", "closed_at", "finale_decision",
                "objection_attempts", "objection_at",
            ),
        },
        "customer_photoshoot_lifecycle_events": {
            "owner": "Customer Photoshoot Lifecycle Audit",
            "migration": "20260805_038_free_teaser_delivery_events.sql",
            "repository": "CustomerPhotoshootLifecycleRepository",
            "service": "CustomerPhotoshootLifecycleService",
            "dashboard": ("Developer Diagnostics",),
            "columns": (
                "event_id", "lifecycle_id", "event_type", "previous_status",
                "new_status", "asset_id", "purchase_outcome_id",
                "sales_session_id", "purchase_intent_id", "provider",
                "provider_delivery_id", "metadata",
            ),
        },
        "customer_photoshoot_lifecycle_sessions": {
            "owner": "Customer Photoshoot Sales Session Association",
            "migration": "20260803_031_customer_photoshoot_lifecycle.sql",
            "repository": "CustomerPhotoshootLifecycleRepository",
            "service": "CustomerPhotoshootLifecycleService",
            "dashboard": ("Developer Diagnostics",),
            "columns": ("lifecycle_id", "sales_session_id", "associated_at"),
        },
        "autonomous_sales_actions": {
            "owner": "Autonomous Sales Progression",
            "migration": "20260803_032_autonomous_sales_progression.sql",
            "repository": "AutonomousSalesProgressionRepository",
            "service": "AutonomousSalesProgressionService",
            "dashboard": ("Customer Sales Brain", "Developer Diagnostics"),
            "columns": (
                "action_id", "creator_profile_id",
                "customer_commerce_profile_id", "lifecycle_id", "action",
                "action_fingerprint", "decision", "expires_at",
                "completed_at",
            ),
        },
        "hosted_asset_references": {
            "owner": "Canonical Reference Hosting",
            "migration": "20260721_008_hosted_asset_references.sql",
            "repository": "HostedAssetReferenceRepository",
            "service": "HostedAssetReferenceService",
            "dashboard": (),
            "columns": (
                "reference_id", "asset_id", "host_name", "hosted_url",
                "source_checksum", "source_path", "status", "is_current",
                "verified_at", "last_used_at",
            ),
        },
        "content_items": {
            "owner": "Asset Library / CMS Import",
            "migration": "20260702_001_content_item_local_vault_path.sql",
            "repository": "AssetRepository / ContentRepository",
            "service": "AssetLibraryService / RuntimeMediaResolver",
            "dashboard": ("Asset Library", "Creator HQ"),
            "columns": ("id", "file_path", "local_vault_path"),
            "legacy": "provider-compatibility",
            "compatibility": "COMPATIBILITY",
        },
        "asset_lineage_relationships": {
            "owner": "Asset Lineage",
            "migration": "20260731_028_asset_lineage.sql",
            "repository": "AssetLineageRepository",
            "service": "AssetLineageService",
            "dashboard": (),
            "columns": (
                "relationship_id", "source_asset_id", "derived_asset_id",
                "source_position", "derivation_kind", "provenance",
            ),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "asset_intelligence_profiles": {
            "owner": "Asset Intelligence",
            "migration": "20260715_001_asset_intelligence_foundation.sql",
            "repository": "AssetIntelligenceRepository",
            "service": "AssetIntelligenceService",
            "dashboard": ("Asset Library",),
            "columns": (
                "asset_id",
                "creator_profile_id",
                "schema_version",
                "analysis_status",
                "profile_data",
            ),
        },
        "asset_intelligence_provider_results": {
            "owner": "Asset Intelligence Provider Evidence",
            "migration": "20260715_001_asset_intelligence_foundation.sql",
            "repository": "AssetIntelligenceRepository",
            "service": "AssetIntelligenceService / AssetIntelligenceMerger",
            "dashboard": (),
            "columns": (
                "result_id",
                "asset_id",
                "creator_profile_id",
                "provider",
                "status",
                "raw_response",
            ),
        },
        "asset_intelligence_runs": {
            "owner": "Asset Intelligence Orchestration",
            "migration": "20260715_002_asset_intelligence_provider_execution.sql",
            "repository": "AssetIntelligenceRunRepository",
            "service": "AssetIntelligenceOrchestrator",
            "dashboard": (),
            "columns": ("run_id", "asset_id", "creator_profile_id", "status", "is_current", "required_providers", "optional_providers"),
        },
        "asset_intelligence_provider_executions": {
            "owner": "Asset Intelligence Provider Execution",
            "migration": "20260715_002_asset_intelligence_provider_execution.sql",
            "repository": "AssetIntelligenceRunRepository",
            "service": "AssetIntelligenceOrchestrator",
            "dashboard": (),
            "columns": ("execution_id", "run_id", "asset_id", "provider_name", "attempt_number", "status", "result_id"),
        },
        "products": {
            "owner": "Product Business",
            "migration": "20260621_001_create_commerce_foundation.sql",
            "repository": "ProductRepository",
            "service": "ProductCatalogService / ProductBusinessService",
            "dashboard": ("Product Catalog", "Creator HQ"),
            "columns": ("id", "creator_profile_id", "internal_name", "display_name", "price_cents", "status"),
        },
        "product_assets": {
            "owner": "Product Asset Relationships",
            "migration": "20260621_001_create_commerce_foundation.sql",
            "repository": "ProductAssetRepository",
            "service": "ProductCatalogService",
            "dashboard": ("Product Catalog", "Asset Library"),
            "columns": ("product_id", "asset_id", "position", "role"),
        },
        "customer_entitlements": {
            "owner": "Customer Commerce",
            "migration": "20260621_001_create_commerce_foundation.sql",
            "repository": "CustomerEntitlementRepository",
            "service": "TelegramCommerceService / DeliveryManagementService",
            "dashboard": ("Customer Workspace", "Creator HQ"),
            "columns": (
                "id",
                "core_user_id",
                "legacy_fanvue_account_id",
                "legacy_fanvue_user_id",
                "product_id",
                "status",
                "source_type",
            ),
            "legacy": "compatibility-bridge",
            "compatibility": "COMPATIBILITY",
        },
        "creator_profiles": {
            "owner": "Creator Workspace",
            "migration": "legacy bootstrap",
            "repository": "CreatorProfileRepository",
            "service": "CreatorWorkspaceService",
            "dashboard": ("Creator Workspace", "Creator HQ"),
            "columns": ("id", "fanvue_account_id"),
            "legacy": "legacy",
            "compatibility": "CANONICAL",
        },
        "publishing_jobs": {
            "owner": "Publishing",
            "migration": "20260703_001_publishing_jobs.sql",
            "repository": "PublishingRepository",
            "service": "PublishingService / PublishingAutomationService",
            "dashboard": ("Publishing Queue", "Creator HQ"),
            "columns": ("id", "product_id", "asset_id", "provider", "status", "media_link_status"),
        },
        "telegram_identity_map": {
            "owner": "Telegram Runtime Identity",
            "migration": "20260619_001_create_telegram_identity_map.sql",
            "repository": "TelegramIdentityRepository",
            "service": "TelegramIdentityService / TelegramInboundAdapter",
            "dashboard": ("Developer Agent",),
            "columns": ("id", "telegram_user_id", "telegram_chat_id", "fanvue_account_id", "local_fanvue_user_id", "external_fanvue_user_uuid"),
        },
        "content_opportunity_records": {
            "owner": "Content Opportunity Intelligence",
            "migration": "20260707_001_content_opportunity_records.sql",
            "repository": "ContentOpportunityRepository",
            "service": "ContentOpportunityService",
            "dashboard": ("Creator HQ Content Opportunity Center",),
            "columns": ("record_type", "record_id", "payload", "created_at", "updated_at"),
        },
        "runtime_control_records": {
            "owner": "Runtime Control",
            "migration": "20260707_002_runtime_control_records.sql",
            "repository": "RuntimeControlRepository",
            "service": "RuntimeControlService",
            "dashboard": ("Creator HQ Runtime Control", "Developer Agent"),
            "columns": ("creator_profile_id", "mode", "status", "current_runtime_provider", "observed_recommendations"),
        },
        "worker_heartbeats": {
            "owner": "Runtime Operations",
            "migration": "20260719_001_worker_heartbeats.sql",
            "repository": "WorkerHeartbeatRepository",
            "service": "WorkerHeartbeatService",
            "dashboard": ("Business Operations",),
            "columns": (
                "heartbeat_id", "worker_name", "worker_instance_id", "worker_type",
                "creator_profile_id", "account_id", "process_id", "host_name",
                "application_version", "status", "started_at", "last_heartbeat_at",
                "last_poll_at", "last_success_at", "last_failure_at", "last_error",
                "shutdown_at", "metadata", "created_at", "updated_at",
            ),
        },
        "ppv_broadcast_logs": {
            "owner": "PPV Broadcast",
            "migration": "20260707_003_reconcile_ppv_broadcast_logs.sql",
            "repository": "PpvBroadcastRepository",
            "service": "PpvBroadcastService / MassPpv services",
            "dashboard": ("Mass PPV Dashboard",),
            "columns": ("id", "fanvue_account_id", "fanvue_user_id", "content_tag", "created_at"),
            "legacy": "canonicalized",
            "compatibility": "CANONICAL",
        },
        "customer_commerce_profiles": {
            "owner": "Customer Commerce Intelligence",
            "migration": "20260725_006_customer_commerce_intelligence.sql",
            "repository": "CustomerCommerceRepository",
            "service": "CustomerCommerceService",
            "dashboard": ("Customer Commerce",),
            "columns": (
                "customer_commerce_profile_id", "creator_profile_id",
                "fanvue_account_id", "external_fanvue_user_uuid",
                "lifetime_gross_minor", "purchase_count",
            ),
        },
        "customer_commerce_transactions": {
            "owner": "Customer Commerce Intelligence",
            "migration": "20260725_006_customer_commerce_intelligence.sql",
            "repository": "CustomerCommerceRepository",
            "service": "CustomerCommerceService",
            "dashboard": ("Customer Commerce",),
            "columns": (
                "customer_commerce_transaction_id",
                "customer_commerce_profile_id", "fanvue_account_id",
                "transaction_order_id", "gross_minor", "net_minor",
            ),
        },
        "purchase_intents": {
            "owner": "Offer Lifecycle",
            "migration": "20260725_007_purchase_intent_offer_lifecycle.sql",
            "repository": "PurchaseIntentRepository",
            "service": "PurchaseIntentService",
            "dashboard": ("Purchase Intents",),
            "columns": (
                "purchase_intent_id", "creator_profile_id",
                "fanvue_account_id", "commercial_offering_id",
                "commercial_publication_id", "status", "expires_at",
            ),
        },
        "developer_agent_tasks": {
            "owner": "Developer Agent Task Approval",
            "migration": "20260726_012_developer_agent_execution.sql",
            "repository": "DeveloperAgentExecutionRepository",
            "service": "DeveloperAgentExecutionService",
            "dashboard": ("Creator Intelligence", "Notification Center"),
            "columns": (
                "task_id", "issue_identifier", "investigation_package",
                "implementation_task", "repository_path", "expected_branch",
                "status", "approved_at",
            ),
        },
        "developer_agent_executions": {
            "owner": "Developer Agent Execution",
            "migration": "20260726_012_developer_agent_execution.sql",
            "repository": "DeveloperAgentExecutionRepository",
            "service": "DeveloperAgentExecutionService",
            "dashboard": ("Creator Intelligence", "Notification Center"),
            "columns": (
                "execution_id", "task_id", "status", "codex_session_id",
                "initial_git_status", "initial_branch", "initial_head",
                "final_report",
            ),
        },
        "developer_agent_events": {
            "owner": "Developer Agent Event Stream",
            "migration": "20260726_012_developer_agent_execution.sql",
            "repository": "DeveloperAgentExecutionRepository",
            "service": "DeveloperAgentExecutionService",
            "dashboard": ("Creator Intelligence",),
            "columns": (
                "event_id", "execution_id", "event_type", "message",
                "event_data", "created_at",
            ),
        },
        "developer_agent_notifications": {
            "owner": "Developer Agent Notifications",
            "migration": "20260726_012_developer_agent_execution.sql",
            "repository": "DeveloperAgentExecutionRepository",
            "service": "DeveloperAgentExecutionService",
            "dashboard": ("Notification Center",),
            "columns": (
                "notification_id", "task_id", "execution_id",
                "notification_type", "title", "detail", "is_read",
            ),
        },
        "developer_agent_reviews": {
            "owner": "Developer Agent Result Review",
            "migration": "20260726_012_developer_agent_execution.sql",
            "repository": "DeveloperAgentExecutionRepository",
            "service": "DeveloperAgentExecutionService",
            "dashboard": ("Creator Intelligence",),
            "columns": ("review_id", "execution_id", "status", "reviewed_at"),
        },
        "autonomous_issue_resolutions": {
            "owner": "Autonomous Issue Resolution",
            "migration": "20260726_013_autonomous_issue_resolution.sql",
            "repository": "AutonomousIssueResolutionRepository",
            "service": "AutonomousIssueResolutionService",
            "dashboard": ("Creator Intelligence",),
            "columns": (
                "resolution_id", "issue_identifier", "issue_snapshot",
                "decision", "decision_reason", "developer_agent_task_id",
                "developer_agent_execution_id", "validation_status",
                "validation_evidence", "outcome", "resolved_at",
            ),
        },
        "ava_personality_versions": {
            "owner": "Ava Coach Version History",
            "migration": "20260726_014_ava_coach_phase1.sql",
            "repository": "AvaCoachRepository",
            "service": "AvaCoachService",
            "dashboard": ("Ava Coach",),
            "columns": (
                "version_id", "version_label", "status",
                "parent_version_id", "notes",
            ),
        },
        "ava_coach_snapshots": {
            "owner": "Ava Coach Conversation Overview",
            "migration": "20260726_014_ava_coach_phase1.sql",
            "repository": "AvaCoachRepository",
            "service": "AvaCoachService",
            "dashboard": ("Ava Coach",),
            "columns": (
                "snapshot_id", "fanvue_account_id", "overview",
                "evidence_metadata", "created_at",
            ),
        },
        "ava_conversation_insights": {
            "owner": "Ava Coach Evidence",
            "migration": "20260726_014_ava_coach_phase1.sql",
            "repository": "AvaCoachRepository",
            "service": "AvaCoachService",
            "dashboard": ("Ava Coach",),
            "columns": (
                "insight_id", "snapshot_id", "fanvue_account_id",
                "insight_type", "evidence", "confidence",
            ),
        },
        "ava_coaching_recommendations": {
            "owner": "Ava Coach Recommendation Approval",
            "migration": "20260726_014_ava_coach_phase1.sql",
            "repository": "AvaCoachRepository",
            "service": "AvaCoachService",
            "dashboard": ("Ava Coach",),
            "columns": (
                "recommendation_id", "fanvue_account_id",
                "recommendation_key", "target_version_id", "evidence",
                "confidence", "status",
            ),
        },
        "ava_applied_improvements": {
            "owner": "Ava Coach Applied History",
            "migration": "20260726_014_ava_coach_phase1.sql",
            "repository": "AvaCoachRepository",
            "service": "AvaCoachService",
            "dashboard": ("Ava Coach",),
            "columns": (
                "improvement_id", "recommendation_id", "version_id",
                "evidence", "status", "applied_at",
            ),
        },
        "social_creative_directions": {
            "owner": "Creator Social Creative Direction",
            "migration": "20260727_016_social_creative_direction.sql",
            "repository": "SocialCreativeDirectionRepository",
            "service": "Creator Social Creative Direction API",
            "dashboard": ("Social Creative Direction",),
            "columns": (
                "id", "creator_profile_id", "fanvue_account_id", "purpose",
                "wardrobe", "visual_style", "seasonal_guidance",
                "things_to_avoid", "created_at", "updated_at",
            ),
        },
        "creator_lifestyles": {
            "owner": "Creator Lifestyle",
            "migration": "20260727_017_creator_lifestyle.sql",
            "repository": "CreatorLifestyleRepository",
            "service": "Creator Lifestyle API",
            "dashboard": ("Lifestyle",),
            "columns": (
                "id", "creator_profile_id", "fanvue_account_id", "career",
                "lifestyle_overview", "favorite_activities",
                "weekend_escapes", "small_town_roots", "outdoor_lifestyle",
                "personal_style", "created_at", "updated_at",
            ),
        },
        "creator_world_models": {
            "owner": "Creator World Model",
            "migration": "20260727_018_creator_world_model.sql",
            "repository": "CreatorWorldModelRepository",
            "service": "Creator World Model API",
            "dashboard": ("World Model",),
            "columns": (
                "id", "creator_profile_id", "fanvue_account_id",
                "internal_home_base", "public_location_description",
                "home_and_indoor_environments", "coastal_environments",
                "mountains_lakes_and_small_town_escapes",
                "climate_and_seasonal_behavior", "seasonal_activities",
                "holiday_rhythm", "travel_and_variety_guidance",
                "created_at", "updated_at",
            ),
        },
        "creative_intelligence_profiles": {
            "owner": "Creator Creative Intelligence",
            "migration": "20260727_019_creative_intelligence_learning.sql",
            "repository": "CreativeIntelligenceRepository",
            "service": "CreativeIntelligenceLearningService",
            "dashboard": (),
            "columns": (
                "id", "creator_profile_id", "fanvue_account_id",
                "positive_event_count", "negative_event_count",
                "analyzed_image_count", "learned_attributes",
                "created_at", "updated_at",
            ),
        },
        "creative_intelligence_events": {
            "owner": "Creator Creative Intelligence Events",
            "migration": "20260727_019_creative_intelligence_learning.sql",
            "repository": "CreativeIntelligenceRepository",
            "service": "CreativeIntelligenceLearningService",
            "dashboard": (),
            "columns": (
                "id", "event_key", "creator_profile_id", "fanvue_account_id",
                "source_image_id", "source_asset_id", "image_reference",
                "event_type", "source_workflow", "signal", "analysis",
                "analysis_status", "analysis_provider", "analysis_error",
                "operational_metadata", "created_at",
            ),
        },
        "commerce_signal_reconciliations": {
            "owner": "Commerce Signal Integration",
            "migration": "20260725_008_commerce_signal_integration.sql",
            "repository": "CommerceSignalRepository",
            "service": "CommerceSignalService",
            "dashboard": (
                "Customer Commerce", "Purchase Intents",
                "Fanvue Webhook Monitor",
            ),
            "columns": (
                "reconciliation_id", "fanvue_account_id",
                "creator_profile_id", "provider_event_id",
                "observed_transaction_id", "state", "next_attempt_at",
            ),
        },
    }

    MIGRATION_SCHEMA_REQUIREMENTS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
        "20260727_019_creative_intelligence_learning.sql": {
            "creative_intelligence_profiles": (
                "id", "creator_profile_id", "fanvue_account_id",
                "positive_event_count", "negative_event_count",
                "analyzed_image_count", "learned_attributes",
            ),
            "creative_intelligence_events": (
                "id", "event_key", "creator_profile_id", "fanvue_account_id",
                "image_reference", "event_type", "source_workflow", "signal",
                "analysis", "analysis_status",
            ),
        },
        "20260727_018_creator_world_model.sql": {
            "creator_world_models": (
                "id", "creator_profile_id", "fanvue_account_id",
                "internal_home_base", "public_location_description",
                "home_and_indoor_environments", "coastal_environments",
                "mountains_lakes_and_small_town_escapes",
                "climate_and_seasonal_behavior", "seasonal_activities",
                "holiday_rhythm", "travel_and_variety_guidance",
            ),
        },
        "20260727_017_creator_lifestyle.sql": {
            "creator_lifestyles": (
                "id", "creator_profile_id", "fanvue_account_id", "career",
                "lifestyle_overview", "favorite_activities",
                "weekend_escapes", "small_town_roots", "outdoor_lifestyle",
                "personal_style",
            ),
        },
        "20260727_016_social_creative_direction.sql": {
            "social_creative_directions": (
                "id", "creator_profile_id", "fanvue_account_id", "purpose",
                "wardrobe", "visual_style", "seasonal_guidance",
                "things_to_avoid",
            ),
        },
        "20260726_014_ava_coach_phase1.sql": {
            "ava_personality_versions": (
                "version_id", "version_label", "status",
            ),
            "ava_coach_snapshots": (
                "snapshot_id", "fanvue_account_id", "overview",
            ),
            "ava_conversation_insights": (
                "insight_id", "snapshot_id", "evidence",
            ),
            "ava_coaching_recommendations": (
                "recommendation_id", "target_version_id", "status",
            ),
            "ava_applied_improvements": (
                "improvement_id", "recommendation_id", "status",
            ),
        },
        "20260726_013_autonomous_issue_resolution.sql": {
            "autonomous_issue_resolutions": (
                "resolution_id", "issue_identifier", "decision", "outcome",
                "validation_status", "developer_agent_execution_id",
            ),
        },
        "20260726_012_developer_agent_execution.sql": {
            "developer_agent_tasks": (
                "task_id", "implementation_task", "status",
            ),
            "developer_agent_executions": (
                "execution_id", "task_id", "status", "final_report",
            ),
            "developer_agent_events": (
                "event_id", "execution_id", "event_type",
            ),
            "developer_agent_notifications": (
                "notification_id", "execution_id", "is_read",
            ),
            "developer_agent_reviews": (
                "review_id", "execution_id", "status",
            ),
        },
        "20260725_010_commerce_recommendation_learning.sql": {
            "commerce_recommendation_outcomes": (
                "outcome_id", "creator_profile_id", "source_event_key",
                "recommendation_trace",
            ),
            "customer_commerce_learning_profiles": (
                "learning_profile_id", "creator_profile_id",
                "external_fanvue_user_uuid", "preferences",
            ),
        },
        "20260725_008_commerce_signal_integration.sql": {
            "commerce_signal_reconciliations": (
                "reconciliation_id", "fanvue_account_id",
                "creator_profile_id", "provider_event_id",
                "observed_transaction_id", "state",
            ),
        },
        "20260725_007_purchase_intent_offer_lifecycle.sql": {
            "purchase_intents": (
                "purchase_intent_id", "creator_profile_id",
                "fanvue_account_id", "status", "expires_at",
            ),
        },
        "20260725_006_customer_commerce_intelligence.sql": {
            "customer_commerce_profiles": (
                "customer_commerce_profile_id", "creator_profile_id",
                "external_fanvue_user_uuid",
            ),
            "customer_commerce_transactions": (
                "customer_commerce_transaction_id", "transaction_order_id",
            ),
        },
        "20260721_008_hosted_asset_references.sql": {
            "hosted_asset_references": (
                "reference_id", "asset_id", "host_name", "hosted_url",
                "source_checksum", "source_path", "status", "is_current",
            ),
        },
        "20260715_002_asset_intelligence_provider_execution.sql": {
            "asset_intelligence_runs": ("run_id", "asset_id", "status", "is_current"),
            "asset_intelligence_provider_executions": ("execution_id", "run_id", "provider_name", "attempt_number", "status"),
            "asset_intelligence_provider_results": ("run_id", "execution_id"),
        },
        "20260715_001_asset_intelligence_foundation.sql": {
            "asset_intelligence_profiles": (
                "asset_id",
                "creator_profile_id",
                "schema_version",
                "analysis_status",
                "profile_data",
            ),
            "asset_intelligence_provider_results": (
                "result_id",
                "asset_id",
                "creator_profile_id",
                "provider",
                "status",
                "raw_response",
            ),
        },
        "20260619_001_create_telegram_identity_map.sql": {
            "telegram_identity_map": (
                "id",
                "telegram_user_id",
                "telegram_chat_id",
                "fanvue_account_id",
                "local_fanvue_user_id",
                "external_fanvue_user_uuid",
            ),
        },
        "20260621_001_create_commerce_foundation.sql": {
            "products": ("id", "creator_profile_id", "internal_name", "display_name"),
            "product_assets": ("product_id", "asset_id", "role"),
            "customer_entitlements": ("id", "product_id", "status"),
        },
        "20260621_002_align_product_catalog.sql": {
            "products": ("internal_name", "display_name", "price_cents", "media_link", "tags", "themes"),
        },
        "20260621_003_ai_product_drafting.sql": {
            "content_items": (
                "short_safe_summary",
                "risk_flags",
                "analysis_reasoning",
                "analysis_provenance",
                "media_metadata",
                "creator_profile_id",
            ),
        },
        "20260621_004_repair_content_item_upload_scope.sql": {
            "content_items": ("content_type", "fanvue_account_id"),
        },
        "20260621_005_autonomous_product_activation.sql": {
            "products": (
                "base_price_cents",
                "min_price_cents",
                "max_price_cents",
                "activation_source",
                "activated_at",
            ),
        },
        "20260622_001_product_fulfillment_strategy.sql": {
            "products": ("fulfillment_strategy",),
        },
        "20260622_002_product_fulfillment_status.sql": {
            "products": ("fulfillment_status",),
        },
        "20260622_003_content_item_fanvue_upload_metadata.sql": {
            "content_items": ("fanvue_upload_metadata",),
        },
        "20260702_001_content_item_local_vault_path.sql": {
            "content_items": ("local_vault_path",),
        },
        "20260703_001_publishing_jobs.sql": {
            "publishing_jobs": (
                "id",
                "product_id",
                "asset_id",
                "provider",
                "status",
                "media_link_status",
            ),
        },
        "20260707_001_content_opportunity_records.sql": {
            "content_opportunity_records": (
                "record_type",
                "record_id",
                "payload",
                "created_at",
                "updated_at",
            ),
        },
        "20260707_002_runtime_control_records.sql": {
            "runtime_control_records": (
                "creator_profile_id",
                "mode",
                "status",
                "current_runtime_provider",
                "observed_recommendations",
            ),
        },
        "20260707_003_reconcile_ppv_broadcast_logs.sql": {
            "ppv_broadcast_logs": (
                "id",
                "fanvue_account_id",
                "fanvue_user_id",
                "content_tag",
                "created_at",
            ),
        },
        "20260707_004_legacy_provider_schema_hardening.sql": {
            "automated_reactions": ("id", "fanvue_account_id", "status"),
            "delayed_message_queue": ("id", "fanvue_account_id", "status", "scheduled_for"),
            "fanvue_chat_messages": ("id", "fanvue_account_id", "fanvue_message_uuid"),
            "outreach_queue": ("id", "fanvue_account_id", "queue_status", "scheduled_for"),
            "send_log": ("id", "fanvue_account_id", "send_status"),
            "wall_post_history": ("id", "fanvue_account_id", "content_item_id"),
            "wall_post_queue": ("id", "fanvue_account_id", "queue_status", "scheduled_for"),
        },
        "20260719_001_worker_heartbeats.sql": {
            "worker_heartbeats": (
                "heartbeat_id", "worker_name", "worker_instance_id", "worker_type",
                "creator_profile_id", "account_id", "process_id", "host_name",
                "status", "started_at", "last_heartbeat_at", "metadata",
            ),
        },
        "20260719_002_atomic_queue_claims.sql": {
            "outreach_queue": ("worker_instance_id", "claimed_at", "lease_expires_at"),
            "delayed_message_queue": ("worker_instance_id", "claimed_at", "lease_expires_at"),
            "mass_ppv_queue": ("worker_instance_id", "claimed_at", "lease_expires_at"),
            "wall_post_queue": ("worker_instance_id", "claimed_at", "lease_expires_at"),
            "webhook_events": ("worker_instance_id", "claimed_at", "lease_expires_at"),
        },
        "20260730_025_commercial_roles.sql": {
            "commercial_role_assignments": (
                "assignment_id", "asset_id", "creator_profile_id",
                "role", "state", "origin",
            ),
            "commercial_role_history": (
                "history_id", "assignment_id", "asset_id",
                "role", "event_type", "new_state",
            ),
        },
        "20260730_027_sales_sessions.sql": {
            "sales_sessions": (
                "sales_session_id", "creator_profile_id",
                "fanvue_account_id", "fanvue_user_id", "state",
                "progression_stage", "commercial_foundation_reference",
            ),
            "sales_session_purchase_intents": (
                "sales_session_id", "purchase_intent_id", "sequence_index",
            ),
            "sales_session_history": (
                "history_id", "sales_session_id", "event_type",
                "new_state", "new_progression_stage",
            ),
        },
    }

    TABLE_OWNERSHIP: Mapping[str, Mapping[str, Any]] = {
        **REQUIRED_TABLES,
        "commerce_recommendation_outcomes": {
            "owner": "Commerce Recommendation Learning",
            "migration": "20260725_010_commerce_recommendation_learning.sql",
            "repository": "CommerceLearningRepository",
            "service": "CommerceLearningService",
            "dashboard": (
                "Commerce Learning", "Recommendation Diagnostics",
            ),
            "columns": (
                "outcome_id", "creator_profile_id", "fanvue_account_id",
                "external_fanvue_user_uuid", "commercial_offering_id",
                "outcome_type", "source_event_key", "recommendation_trace",
            ),
        },
        "customer_commerce_learning_profiles": {
            "owner": "Commerce Recommendation Learning",
            "migration": "20260725_010_commerce_recommendation_learning.sql",
            "repository": "CommerceLearningRepository",
            "service": "CommerceLearningService",
            "dashboard": (
                "Commerce Learning", "Recommendation Diagnostics",
            ),
            "columns": (
                "learning_profile_id", "creator_profile_id",
                "fanvue_account_id", "external_fanvue_user_uuid",
                "preferences", "outcome_counts", "confidence",
            ),
        },
        "asset_content_destinations": {
            "owner": "Content Destination",
            "migration": "20260723_001_content_destination_foundation.sql",
            "repository": "ContentDestinationRepository",
            "service": "ContentDestinationService",
            "dashboard": ("Available Inventory", "Commerce"),
            "columns": ("asset_id", "destination", "creator_profile_id", "assigned_at"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "asset_content_destination_history": {
            "owner": "Content Destination Audit",
            "migration": "20260723_001_content_destination_foundation.sql",
            "repository": "ContentDestinationRepository",
            "service": "ContentDestinationService",
            "dashboard": (),
            "columns": ("history_id", "asset_id", "event_type", "new_destination", "created_at"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "content_intelligence_profiles": {
            "owner": "Content Intelligence",
            "migration": "20260712_001_content_intelligence_profiles.sql",
            "repository": "ContentIntelligenceProfileRepository",
            "service": "ContentIntelligenceService",
            "dashboard": ("Asset Library", "Commerce Library"),
            "columns": ("asset_id", "status", "schema_version", "content_profile", "updated_at"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "business_asset_registrations": {
            "owner": "Business Asset Registration",
            "migration": "20260712_002_business_asset_registrations.sql",
            "repository": "CommerceRegistrationRepository",
            "service": "CommerceRegistrationService",
            "dashboard": ("Asset Library", "Commerce Library"),
            "columns": ("registration_id", "asset_id", "creator_profile_id", "business_lifecycle_state"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "commerce_destination_history": {
            "owner": "Commerce Destination Audit",
            "migration": "20260712_003_commerce_destinations.sql",
            "repository": "CommerceDestinationRepository",
            "service": "CommerceDestinationService",
            "dashboard": (),
            "columns": ("history_id", "asset_id", "new_destination", "created_at"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "commerce_destination_routing_intents": {
            "owner": "Commerce Destination Routing",
            "migration": "20260712_003_commerce_destinations.sql",
            "repository": "CommerceDestinationRepository",
            "service": "CommerceDestinationService",
            "dashboard": ("Commerce Library",),
            "columns": ("routing_intent_id", "asset_id", "selected_destination", "routing_status"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "business_asset_fulfillment_registrations": {
            "owner": "Business Asset Fulfillment",
            "migration": "20260712_004_fulfillment_registrations.sql",
            "repository": "FulfillmentRegistrationRepository",
            "service": "FulfillmentRegistrationService",
            "dashboard": ("Commerce Library",),
            "columns": ("fulfillment_id", "asset_id", "route", "lifecycle_state"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "business_asset_fulfillment_history": {
            "owner": "Business Asset Fulfillment Audit",
            "migration": "20260712_004_fulfillment_registrations.sql",
            "repository": "FulfillmentRegistrationRepository",
            "service": "FulfillmentRegistrationService",
            "dashboard": (),
            "columns": ("history_id", "fulfillment_id", "asset_id", "lifecycle_state"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "chat_commerce_registrations": {
            "owner": "Chat Commerce Registration",
            "migration": "20260712_005_chat_commerce_registrations.sql",
            "repository": "ChatCommerceRegistrationRepository",
            "service": "ChatCommerceRegistrationService",
            "dashboard": ("Commerce Library",),
            "columns": ("chat_registration_id", "asset_id", "availability_state", "chat_ready"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "chat_commerce_registration_history": {
            "owner": "Chat Commerce Registration Audit",
            "migration": "20260712_005_chat_commerce_registrations.sql",
            "repository": "ChatCommerceRegistrationRepository",
            "service": "ChatCommerceRegistrationService",
            "dashboard": (),
            "columns": ("history_id", "chat_registration_id", "asset_id", "created_at"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "ready_asset_chat_registration_jobs": {
            "owner": "Ready Asset Chat Registration",
            "migration": "20260720_006_ready_asset_chat_bridge.sql",
            "repository": "ReadyAssetChatRegistrationJobRepository",
            "service": "ReadyAssetChatRegistrationWorkerService",
            "dashboard": ("Business Operations",),
            "columns": ("asset_id", "status", "attempt_count", "updated_at"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "commercial_offerings": {
            "owner": "Commercial Offerings",
            "migration": "20260723_002_commercial_offerings_foundation.sql",
            "repository": "CommercialOfferingRepository",
            "service": "CommercialOfferingService",
            "dashboard": ("Commerce",),
            "columns": ("offering_id", "creator_profile_id", "offering_type", "status"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "commercial_offering_assets": {
            "owner": "Commercial Offering Composition",
            "migration": "20260723_002_commercial_offerings_foundation.sql",
            "repository": "CommercialOfferingRepository",
            "service": "CommercialOfferingService",
            "dashboard": ("Commerce",),
            "columns": ("offering_id", "asset_id", "position", "is_hero"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "commercial_role_assignments": {
            "owner": "Commercial Intelligence",
            "migration": "20260730_025_commercial_roles.sql",
            "repository": "CommercialRoleRepository",
            "service": "CommercialRoleService",
            "dashboard": ("Asset Library",),
            "columns": (
                "assignment_id", "asset_id", "creator_profile_id",
                "role", "state", "origin",
            ),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "commercial_role_history": {
            "owner": "Commercial Intelligence Audit",
            "migration": "20260730_025_commercial_roles.sql",
            "repository": "CommercialRoleRepository",
            "service": "CommercialRoleService",
            "dashboard": ("Asset Library",),
            "columns": (
                "history_id", "assignment_id", "asset_id",
                "role", "event_type", "new_state",
            ),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "sales_sessions": {
            "owner": "Commercial Intelligence",
            "migration": "20260730_027_sales_sessions.sql",
            "repository": "SalesSessionRepository",
            "service": "SalesSessionService",
            "dashboard": ("Customer Sales Brain",),
            "columns": (
                "sales_session_id", "creator_profile_id",
                "fanvue_account_id", "fanvue_user_id", "state",
                "progression_stage", "commercial_foundation_reference",
            ),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "sales_session_purchase_intents": {
            "owner": "Commercial Intelligence",
            "migration": "20260730_027_sales_sessions.sql",
            "repository": "SalesSessionRepository",
            "service": "SalesSessionService",
            "dashboard": ("Customer Sales Brain",),
            "columns": (
                "sales_session_id", "purchase_intent_id", "sequence_index",
            ),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "sales_session_history": {
            "owner": "Commercial Intelligence Audit",
            "migration": "20260730_027_sales_sessions.sql",
            "repository": "SalesSessionRepository",
            "service": "SalesSessionService",
            "dashboard": ("Customer Sales Brain",),
            "columns": (
                "history_id", "sales_session_id", "event_type",
                "new_state", "new_progression_stage",
            ),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "commercial_publications": {
            "owner": "Commercial Publications",
            "migration": "20260723_003_commercial_publications_foundation.sql",
            "repository": "CommercialPublicationRepository",
            "service": "CommercialPublicationService",
            "dashboard": ("Commerce",),
            "columns": ("publication_id", "commercial_offering_id", "provider", "status"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "commercial_publication_uploads": {
            "owner": "Commercial Publication Upload Checkpoints",
            "migration": "20260723_004_fanvue_media_link_automation.sql",
            "repository": "CommercialPublicationUploadRepository",
            "service": "FanvueMediaLinkPublicationExecutor",
            "dashboard": ("Commerce",),
            "columns": ("publication_upload_id", "publication_id", "asset_id", "upload_status"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "photoshoot_asset_memberships": {
            "owner": "Photoshoot Commerce",
            "migration": "20260721_001_photoshoot_commerce_deliverables.sql",
            "repository": "PhotoshootCommerceRepository",
            "service": "PhotoshootCommerceDeliverableService",
            "dashboard": ("Photoshoot Gallery", "Commerce Library"),
            "columns": ("photoshoot_session_id", "asset_id", "shot_order", "approved", "is_hero"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "photoshoot_intelligence_profiles": {
            "owner": "Photoshoot Commercial Intelligence",
            "migration": "20260804_034_photoshoot_commercial_intelligence.sql",
            "repository": "PhotoshootCommerceRepository",
            "service": "PhotoshootCommerceDeliverableService",
            "dashboard": ("Photoshoot Gallery", "Commerce Library"),
            "columns": ("photoshoot_session_id", "status", "profile_data", "commercial_title",
                        "commercial_summary", "input_snapshot", "generation_status",
                        "intelligence_version", "pipeline_stage", "production_analysis",
                        "cross_validation", "analysis_completed_at"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "photoshoot_shot_intelligence_profiles": {
            "owner": "Photoshoot Commercial Intelligence",
            "migration": "20260804_035_canonical_completed_photoshoot_intelligence.sql",
            "repository": "PhotoshootCommerceRepository",
            "service": "PhotoshootCommercialIntelligenceService",
            "dashboard": ("Photoshoot Gallery", "Commerce Library"),
            "columns": ("photoshoot_session_id", "asset_id", "intelligence_version",
                        "shot_order", "status", "profile_data", "production_context"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "photoshoot_commerce_deliverables": {
            "owner": "Photoshoot Commerce",
            "migration": "20260721_001_photoshoot_commerce_deliverables.sql",
            "repository": "PhotoshootCommerceRepository",
            "service": "PhotoshootCommerceDeliverableService",
            "dashboard": ("Photoshoot Gallery", "Commerce Library"),
            "columns": ("deliverable_id", "photoshoot_session_id", "creator_profile_id", "shot_count", "is_active", "is_archived"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "photoshoot_analysis_workflows": {
            "owner": "Photoshoot Analysis",
            "migration": "20260721_006_photoshoot_analysis_orchestrator.sql",
            "repository": "PhotoshootAnalysisWorkflowRepository",
            "service": "PhotoshootAnalysisOrchestratorService",
            "dashboard": ("Commerce Library",),
            "columns": ("deliverable_id", "current_stage", "worker_id", "lease_expires_at", "attempt_count"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "photoshoot_auto_runs": {
            "owner": "Photoshoot Auto Run",
            "migration": "20260721_007_photoshoot_auto_run.sql",
            "repository": "PhotoshootAutoRunRepository",
            "service": "PhotoshootAutoRunService",
            "dashboard": ("Photoshoot",),
            "columns": ("session_id", "state", "current_plan_index", "total_frames", "worker_id", "lease_expires_at", "attempt_count"),
            "legacy": "current", "compatibility": "CANONICAL",
        },
        "automated_reactions": {
            "owner": "Automated Reaction",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "AutomatedReactionRepository",
            "service": "AutomatedReactionPersistenceService",
            "dashboard": ("Activity Feed",),
            "columns": ("id", "fanvue_account_id", "status", "reaction_type"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "buyer_intelligence": {
            "owner": "Customer Intelligence",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "BuyerIntelligenceRepository",
            "service": "BuyerIntelligenceService",
            "dashboard": ("Customer Workspace",),
            "columns": ("id", "fanvue_account_id", "fanvue_user_id", "buyer_tier"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "chat_messages": {
            "owner": "Conversation Operations",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "ChatMessageRepository",
            "service": "ConversationOperationsService",
            "dashboard": ("Chat Console",),
            "columns": ("id", "thread_id", "fanvue_user_id", "fanvue_account_id"),
            "legacy": "provider-cache",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "chat_threads": {
            "owner": "Conversation Operations",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "ChatMessageRepository",
            "service": "ConversationOperationsService",
            "dashboard": ("Chat Console",),
            "columns": ("id", "fanvue_user_id", "fanvue_account_id"),
            "legacy": "provider-cache",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "cms_fanvue_upload_links": {
            "owner": "Publishing",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "CmsFanvueUploadRepository",
            "service": "CmsFanvueUploadLinkService",
            "dashboard": ("CMS Upload", "Publishing Queue"),
            "columns": ("id", "content_item_id", "fanvue_account_id", "upload_status"),
            "legacy": "provider-specific",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "content_catalog": {
            "owner": "Legacy Content Catalog",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "ContentRepository",
            "service": "ContentService",
            "dashboard": ("Asset Library",),
            "columns": ("id", "fanvue_account_id", "content_tag"),
            "legacy": "legacy",
            "compatibility": "LEGACY",
        },
        "content_usage_log": {
            "owner": "Business Learning",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "ContentUsageRepository",
            "service": "ContentUsageService",
            "dashboard": ("Creator HQ",),
            "columns": ("id", "content_item_id", "fanvue_account_id", "usage_type"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "delayed_message_queue": {
            "owner": "Activity Feed",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "DelayedMessageQueueRepository",
            "service": "DelayedMessageWorkerService",
            "dashboard": ("Delayed Messages", "Activity Feed"),
            "columns": ("id", "fanvue_account_id", "status", "scheduled_for"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "fanvue_accounts": {
            "owner": "Fanvue Provider",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "FanvueAccountRepository",
            "service": "FanvueOauthService",
            "dashboard": ("Fanvue Auth",),
            "columns": ("id", "username", "is_active"),
            "legacy": "provider-canonical",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "fanvue_chat_messages": {
            "owner": "Fanvue Provider",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "FanvueMessageRepository",
            "service": "FanvueMessageSyncService",
            "dashboard": ("Chat Console",),
            "columns": ("id", "fanvue_account_id", "fanvue_user_uuid", "fanvue_message_uuid"),
            "legacy": "provider-cache",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "fanvue_messages": {
            "owner": "Fanvue Provider",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "FanvueMessageSyncRepository",
            "service": "FanvueMessageSyncService",
            "dashboard": ("Chat Console",),
            "columns": ("fanvue_message_id", "fanvue_account_id"),
            "legacy": "provider-cache",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "fanvue_monetization_events": {
            "owner": "Fanvue Provider",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "MonetizationEventRepository",
            "service": "MonetizationEventNormalizerService",
            "dashboard": ("Customer Workspace",),
            "columns": ("id", "fanvue_account_id"),
            "legacy": "provider-cache",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "fanvue_threads": {
            "owner": "Fanvue Provider",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "FanvueMessageSyncRepository",
            "service": "FanvueMessageSyncService",
            "dashboard": ("Chat Console",),
            "columns": ("thread_id", "fanvue_account_id"),
            "legacy": "provider-cache",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "fanvue_users": {
            "owner": "Fanvue Provider",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "FanvueUserRepository",
            "service": "CustomerService / FanvueRelationshipSyncService",
            "dashboard": ("Customer Workspace",),
            "columns": ("id", "fanvue_account_id", "fanvue_user_uuid"),
            "legacy": "provider-canonical",
            "compatibility": "PROVIDER_SPECIFIC",
        },
        "mass_ppv_campaigns": {
            "owner": "Mass PPV",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "MassPpvCampaignRepository",
            "service": "MassPpvSchedulerService",
            "dashboard": ("Mass PPV Dashboard",),
            "columns": ("id", "fanvue_account_id", "status"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "mass_ppv_queue": {
            "owner": "Mass PPV",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "MassPpvCampaignRepository",
            "service": "MassPpvWorkerService",
            "dashboard": ("Mass PPV Dashboard",),
            "columns": ("id", "campaign_id", "fanvue_user_id", "status"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "offers_sent": {
            "owner": "Commerce Execution",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "OfferService",
            "service": "CommerceExecutionService",
            "dashboard": ("Creator HQ",),
            "columns": ("id", "fanvue_account_id", "fanvue_user_id", "sent_at"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "outreach_log": {
            "owner": "Outreach",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "OutreachLogRepository",
            "service": "OutreachService",
            "dashboard": ("Activity Feed",),
            "columns": ("id", "fanvue_account_id"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "outreach_queue": {
            "owner": "Outreach",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "OutreachQueueRepository",
            "service": "OutreachWorkerService",
            "dashboard": ("Activity Feed",),
            "columns": ("id", "fanvue_account_id", "queue_status", "scheduled_for"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "ppv_broadcast_log": {
            "owner": "PPV Broadcast",
            "migration": "20260707_003_reconcile_ppv_broadcast_logs.sql",
            "repository": "None",
            "service": "None",
            "dashboard": (),
            "columns": ("id", "fanvue_account_id", "fanvue_user_id"),
            "legacy": "legacy",
            "compatibility": "CANDIDATE_FOR_RETIREMENT",
        },
        "purchase_events": {
            "owner": "Commerce Intelligence",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "MonetizationEventRepository",
            "service": "CommerceIntelligenceService",
            "dashboard": ("Customer Workspace",),
            "columns": ("id", "fanvue_account_id", "fanvue_user_id"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "qualification_ppv_events": {
            "owner": "Qualification PPV",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "QualificationPpvRepository",
            "service": "QualificationPpvService",
            "dashboard": ("Creator HQ",),
            "columns": ("id", "fanvue_account_id", "fanvue_user_id"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "schema_migrations": {
            "owner": "Schema Manager",
            "migration": "SchemaManagerService.ensure_history_table",
            "repository": "SchemaManagerService",
            "service": "SchemaManagerService",
            "dashboard": (),
            "columns": ("id", "migration_name", "applied_at", "checksum"),
            "legacy": "infrastructure",
            "compatibility": "CANONICAL",
        },
        "send_log": {
            "owner": "Runtime Send Log",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "SendLogRepository",
            "service": "Runtime send services",
            "dashboard": ("Activity Feed",),
            "columns": ("id", "fanvue_account_id", "send_status"),
            "legacy": "compatibility",
            "compatibility": "COMPATIBILITY",
        },
        "user_memory": {
            "owner": "Customer Intelligence",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "MemoryRepository",
            "service": "MemoryService / CustomerIntelligenceService",
            "dashboard": ("Customer Workspace",),
            "columns": ("id", "fanvue_account_id", "fanvue_user_id"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "wall_post_history": {
            "owner": "Wall Scheduler",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "WallPostRepository",
            "service": "WallSchedulerService",
            "dashboard": ("Wall Scheduler",),
            "columns": ("id", "fanvue_account_id", "content_item_id"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "wall_post_queue": {
            "owner": "Wall Scheduler",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "WallPostRepository",
            "service": "WallWorkerService",
            "dashboard": ("Wall Scheduler",),
            "columns": ("id", "fanvue_account_id", "queue_status", "scheduled_for"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
        "webhook_events": {
            "owner": "Webhook Ingestion",
            "migration": "20260707_004_legacy_provider_schema_hardening.sql",
            "repository": "WebhookEventRepository",
            "service": "WebhookEventProcessorService",
            "dashboard": ("Developer Agent",),
            "columns": ("id", "internal_event_id", "status"),
            "legacy": "current",
            "compatibility": "CANONICAL",
        },
    }

    REQUIRED_INDEXES: Mapping[str, tuple[str, ...]] = {
        "hosted_asset_references": (
            "hosted_asset_reference_current_idx", "hosted_asset_reference_lookup_idx",
        ),
        "content_items": ("idx_content_items_creator_profile_status", "idx_content_items_local_vault_path"),
        "asset_lineage_relationships": (
            "idx_asset_lineage_source", "idx_asset_lineage_derived",
        ),
        "content_opportunity_records": ("idx_content_opportunity_records_type", "idx_content_opportunity_records_payload"),
        "customer_entitlements": ("idx_customer_entitlements_product", "idx_customer_entitlements_legacy_user"),
        "product_assets": ("idx_product_assets_asset_id",),
        "products": ("idx_products_catalog_creator_status",),
        "publishing_jobs": ("idx_publishing_jobs_provider_status", "idx_publishing_jobs_retry"),
        "runtime_control_records": ("idx_runtime_control_records_mode",),
        "telegram_identity_map": ("telegram_identity_map_active_telegram_lookup_idx",),
        "worker_heartbeats": (
            "idx_worker_heartbeats_worker_name", "idx_worker_heartbeats_instance",
            "idx_worker_heartbeats_creator_account", "idx_worker_heartbeats_last_heartbeat",
            "idx_worker_heartbeats_status",
        ),
        "outreach_queue": ("idx_outreach_queue_due", "idx_outreach_queue_active_lease"),
        "delayed_message_queue": ("idx_delayed_message_queue_due", "idx_delayed_message_queue_active_lease"),
        "mass_ppv_queue": ("idx_mass_ppv_queue_status_due", "idx_mass_ppv_queue_active_lease"),
        "wall_post_queue": ("idx_wall_post_queue_due", "idx_wall_post_queue_active_lease"),
        "webhook_events": ("idx_webhook_events_status_retry", "idx_webhook_events_active_lease"),
        "commerce_signal_reconciliations": (
            "idx_commerce_signal_reconciliation_due",
            "idx_commerce_signal_reconciliation_transaction",
        ),
        "developer_agent_events": (
            "developer_agent_events_execution_idx",
        ),
        "developer_agent_notifications": (
            "developer_agent_notifications_created_idx",
        ),
        "sales_sessions": (
            "uq_sales_sessions_active_customer",
            "idx_sales_sessions_creator_activity",
            "idx_sales_sessions_foundation",
        ),
        "sales_session_history": (
            "idx_sales_session_history_session",
        ),
    }

    CRITICAL_FOREIGN_KEYS: Mapping[str, tuple[str, ...]] = {
        "hosted_asset_references": ("hosted_asset_references_asset_id_fkey",),
        "asset_lineage_relationships": (
            "asset_lineage_relationships_source_asset_id_fkey",
            "asset_lineage_relationships_derived_asset_id_fkey",
        ),
        "products": ("products_creator_profile_id_fkey",),
        "product_assets": ("product_assets_product_id_fkey", "product_assets_asset_id_fkey"),
        "customer_entitlements": ("customer_entitlements_product_id_fkey",),
        "publishing_jobs": ("publishing_jobs_product_id_fkey", "publishing_jobs_asset_id_fkey"),
        "telegram_identity_map": ("telegram_identity_map_fanvue_account_id_fkey", "telegram_identity_map_local_fanvue_user_id_fkey"),
        "commerce_signal_reconciliations": (
            "commerce_signal_reconciliations_fanvue_account_id_fkey",
            "commerce_signal_reconciliations_creator_profile_id_fkey",
        ),
        "developer_agent_executions": (
            "developer_agent_executions_task_id_fkey",
        ),
        "developer_agent_events": (
            "developer_agent_events_execution_id_fkey",
        ),
        "developer_agent_reviews": (
            "developer_agent_reviews_execution_id_fkey",
        ),
        "sales_sessions": (
            "sales_sessions_creator_profile_id_fkey",
            "sales_sessions_fanvue_account_id_fkey",
            "sales_sessions_fanvue_user_id_fkey",
        ),
        "sales_session_purchase_intents": (
            "sales_session_purchase_intents_sales_session_id_fkey",
            "sales_session_purchase_intents_purchase_intent_id_fkey",
        ),
        "sales_session_history": (
            "sales_session_history_sales_session_id_fkey",
        ),
    }

    DOCUMENTED_FK_DEBT: Mapping[str, str] = {
        "creator_profiles.fanvue_account_id": "COMPATIBILITY_DEBT: stored as provider text identifier, not fanvue_accounts(id). Future migration should add a typed provider identity bridge.",
        "runtime_control_records.creator_profile_id": "COMPATIBILITY_DEBT: text profile key supports 'default' and test namespaces; FK to creator_profiles(id) would break runtime default mode.",
        "content_opportunity_records.creator_profile_id": "INTENTIONAL_PROVIDER_NEUTRAL: generic record table stores creator/profile context inside JSON payload until typed opportunity records are introduced.",
        "telegram_identity_map.creator_profile_id": "INTENTIONAL_PROVIDER_SPECIFIC: Telegram identity currently maps to Fanvue canonical user/account; creator profile inferred through account boundary.",
    }

    def __init__(
        self,
        *,
        connection_factory: Callable = get_db_connection,
        migration_dir: str | Path = FORWARD_MIGRATION_DIR,
    ) -> None:
        self._connection_factory = connection_factory
        self.migration_dir = Path(migration_dir)

    def discover_schema(self) -> Mapping[str, set[str]]:
        with self._connection_factory() as conn:
            self.ensure_history_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT table_name, column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                    """
                )
                rows = cursor.fetchall()
        schema: dict[str, set[str]] = {}
        for row in rows:
            schema.setdefault(row["table_name"], set()).add(row["column_name"])
        return schema

    def load_forward_migrations(self) -> tuple[MigrationFile, ...]:
        if not self.migration_dir.exists():
            return ()
        migrations: list[MigrationFile] = []
        for path in sorted(self.migration_dir.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            migrations.append(
                MigrationFile(
                    name=path.name,
                    path=path,
                    checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                    sql=sql,
                )
            )
        return tuple(migrations)

    def ensure_history_table(self, connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    id BIGSERIAL PRIMARY KEY,
                    migration_name TEXT NOT NULL UNIQUE,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    checksum TEXT NOT NULL
                )
                """
            )

    def applied_migrations(self, connection=None) -> Mapping[str, str]:
        if connection is not None:
            self.ensure_history_table(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT migration_name, checksum FROM public.schema_migrations"
                )
                return {
                    row["migration_name"]: row["checksum"]
                    for row in cursor.fetchall()
                }
        with self._connection_factory() as conn:
            return self.applied_migrations(conn)

    def reconcile(self) -> SchemaCertificationReport:
        migrations_applied: list[str] = []
        migrations_recorded: list[str] = []

        with self._connection_factory() as conn:
            self.ensure_history_table(conn)
            applied = dict(self.applied_migrations(conn))
            for migration in self.load_forward_migrations():
                if applied.get(migration.name) == migration.checksum:
                    continue

                if self._migration_schema_already_present(conn, migration.name):
                    self._record_migration(conn, migration)
                    migrations_recorded.append(migration.name)
                    continue

                with conn.cursor() as cursor:
                    cursor.execute(migration.sql)
                self._record_migration(conn, migration)
                migrations_applied.append(migration.name)

        return self.certify(
            migrations_applied=tuple(migrations_applied),
            migrations_recorded=tuple(migrations_recorded),
        )

    def reconcile_one(self, migration_name: str) -> SchemaCertificationReport:
        """Apply or record exactly one named forward migration."""
        migration = next((
            item for item in self.load_forward_migrations()
            if item.name == migration_name
        ), None)
        if migration is None:
            raise LookupError(f"Migration was not found: {migration_name}")
        applied_names: list[str] = []
        recorded_names: list[str] = []
        with self._connection_factory() as connection:
            self.ensure_history_table(connection)
            applied = self.applied_migrations(connection)
            prior_checksum = applied.get(migration.name)
            if prior_checksum is not None and prior_checksum != migration.checksum:
                raise ValueError(
                    f"Applied migration checksum differs: {migration.name}"
                )
            if prior_checksum == migration.checksum:
                return self.certify()
            if self._migration_schema_already_present(
                connection, migration.name
            ):
                self._record_migration(connection, migration)
                recorded_names.append(migration.name)
            else:
                with connection.cursor() as cursor:
                    cursor.execute(migration.sql)
                self._record_migration(connection, migration)
                applied_names.append(migration.name)
        return self.certify(
            migrations_applied=tuple(applied_names),
            migrations_recorded=tuple(recorded_names),
        )

    def certify(
        self,
        *,
        migrations_applied: tuple[str, ...] = (),
        migrations_recorded: tuple[str, ...] = (),
    ) -> SchemaCertificationReport:
        schema = self.discover_schema()
        migrations = self.load_forward_migrations()
        applied = self.applied_migrations()
        migration_names = tuple(migration.name for migration in migrations)
        missing_history = tuple(
            name for name in migration_names if name not in applied
        )
        drift = list(self.detect_schema_drift(schema))
        tables = tuple(self.audit_tables(schema))
        if missing_history:
            drift.append(
                "Migration history is incomplete: "
                + ", ".join(missing_history)
            )
        status = "PASS" if not drift else "FAIL"
        return SchemaCertificationReport(
            status=status,
            migrations_applied=migrations_applied,
            migrations_recorded=migrations_recorded,
            missing_migrations=missing_history,
            drift=tuple(drift),
            tables=tables,
            evidence={
                "forward_migration_dir": str(self.migration_dir),
                "forward_migration_count": len(migrations),
                "checked_at": datetime.now().astimezone().isoformat(),
                "content_opportunity_persistence": "PostgreSQL",
                "runtime_control_persistence": "PostgreSQL",
                "ppv_broadcast_canonical_table": "ppv_broadcast_logs",
            },
        )

    def detect_schema_drift(
        self,
        schema: Mapping[str, set[str]] | None = None,
    ) -> tuple[str, ...]:
        current = schema or self.discover_schema()
        drift: list[str] = []
        for table_name, metadata in self.REQUIRED_TABLES.items():
            columns = current.get(table_name)
            if columns is None:
                drift.append(f"Missing table: {table_name}")
                continue
            missing_columns = [
                column for column in metadata["columns"] if column not in columns
            ]
            if missing_columns:
                drift.append(
                    f"Missing columns on {table_name}: "
                    + ", ".join(missing_columns)
                )
        live_tables = set(current)
        unmanaged = sorted(table for table in live_tables if table not in self.TABLE_OWNERSHIP)
        if unmanaged:
            drift.append("Tables missing ownership matrix entries: " + ", ".join(unmanaged))
        for table_name, metadata in self.TABLE_OWNERSHIP.items():
            if table_name not in current:
                continue
            migration = str(metadata.get("migration") or "")
            if not migration:
                drift.append(f"Table has no migration origin: {table_name}")
        missing_indexes = self.detect_missing_indexes()
        if missing_indexes:
            drift.extend(f"Missing required index: {item}" for item in missing_indexes)
        missing_fks = self.detect_missing_foreign_keys()
        if missing_fks:
            drift.extend(f"Missing critical foreign key: {item}" for item in missing_fks)
        repository_ddl = self.detect_repository_schema_creation()
        if repository_ddl:
            drift.extend(f"Repository schema creation remains: {item}" for item in repository_ddl)
        root_sql_files = sorted(Path("migrations").glob("*.sql"))
        if root_sql_files:
            drift.append(
                "Forward/rollback migration separation incomplete: "
                + ", ".join(path.name for path in root_sql_files)
            )
        return tuple(drift)

    def audit_tables(
        self,
        schema: Mapping[str, set[str]] | None = None,
    ) -> tuple[SchemaTableAudit, ...]:
        current = schema or self.discover_schema()
        audits: list[SchemaTableAudit] = []
        for table_name, metadata in sorted(self.TABLE_OWNERSHIP.items()):
            if table_name not in current:
                continue
            columns = current.get(table_name, set())
            missing = tuple(
                column for column in metadata["columns"] if column not in columns
            )
            audits.append(
                SchemaTableAudit(
                    table_name=table_name,
                    owner=metadata["owner"],
                    migration=metadata["migration"],
                    repository=metadata["repository"],
                    service=metadata["service"],
                    dashboard_consumers=tuple(metadata.get("dashboard", ())),
                    legacy_status=metadata.get("legacy", "current"),
                    compatibility_status=metadata.get("compatibility", "canonical"),
                    exists=table_name in current,
                    missing_columns=missing,
                )
            )
        return tuple(audits)

    def detect_missing_indexes(self) -> tuple[str, ...]:
        missing: list[str] = []
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT tablename, indexname
                    FROM pg_indexes
                    WHERE schemaname = 'public'
                    """
                )
                indexes = {
                    (row["tablename"], row["indexname"])
                    for row in cursor.fetchall()
                }
        for table_name, expected_indexes in self.REQUIRED_INDEXES.items():
            for index_name in expected_indexes:
                if (table_name, index_name) not in indexes:
                    missing.append(f"{table_name}.{index_name}")
        return tuple(missing)

    def detect_missing_foreign_keys(self) -> tuple[str, ...]:
        missing: list[str] = []
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT t.relname AS table_name, c.conname
                    FROM pg_constraint c
                    JOIN pg_class t ON t.oid = c.conrelid
                    JOIN pg_namespace n ON n.oid = t.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.contype = 'f'
                    """
                )
                fks = {
                    (row["table_name"], row["conname"])
                    for row in cursor.fetchall()
                }
        for table_name, expected_fks in self.CRITICAL_FOREIGN_KEYS.items():
            for fk_name in expected_fks:
                if (table_name, fk_name) not in fks:
                    missing.append(f"{table_name}.{fk_name}")
        return tuple(missing)

    def detect_repository_schema_creation(self) -> tuple[str, ...]:
        offenders: list[str] = []
        for root in (Path("app/repositories"),):
            if not root.exists():
                continue
            for path in sorted(root.glob("*.py")):
                text = path.read_text(encoding="utf-8")
                if any(
                    marker in text.upper()
                    for marker in ("CREATE TABLE", "ALTER TABLE", "CREATE INDEX", "DROP TABLE")
                ):
                    offenders.append(str(path))
        return tuple(offenders)

    def _migration_schema_already_present(self, connection, migration_name: str) -> bool:
        expected = self.MIGRATION_SCHEMA_REQUIREMENTS.get(migration_name)
        if not expected:
            return False
        with connection.cursor() as cursor:
            for table_name, required_columns in expected.items():
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = %s
                    """,
                    (table_name,),
                )
                columns = {row["column_name"] for row in cursor.fetchall()}
                if not columns:
                    return False
                if not all(column in columns for column in required_columns):
                    return False
        return True

    def _record_migration(self, connection, migration: MigrationFile) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.schema_migrations (migration_name, checksum)
                VALUES (%s, %s)
                ON CONFLICT (migration_name)
                DO UPDATE SET
                    checksum = EXCLUDED.checksum,
                    applied_at = now()
                """,
                (migration.name, migration.checksum),
            )
