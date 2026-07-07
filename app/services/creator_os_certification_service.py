"""Read-only Creator OS v1.0 certification aggregator."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from app.models.creator_os_certification import (
    CreatorOSCertificationReport,
    CreatorOSCertificationStatus,
    CreatorOSValidationEvidence,
    CreatorOSValidationSection,
)


class CreatorOSCertificationService:
    """Validate Creator OS v1.0 by consuming existing read-model services."""

    REQUIRED_SECTIONS = (
        "Creator Workflow",
        "Product Business",
        "Telegram Business",
        "Customer Business",
        "Content Opportunity",
        "Business Learning",
        "Business Optimization",
        "Creator HQ",
        "Creator Agent",
        "Publishing",
        "DecisionEngine/runtime compatibility",
    )

    def __init__(
        self,
        *,
        creator_workflow_service: Any | None = None,
        product_business_service: Any | None = None,
        telegram_business_service: Any | None = None,
        customer_business_service: Any | None = None,
        content_opportunity_service: Any | None = None,
        business_learning_service: Any | None = None,
        business_optimization_service: Any | None = None,
        creator_workspace_service: Any | None = None,
        creator_agent_service: Any | None = None,
        publishing_service: Any | None = None,
        decision_engine_runtime_boundary: Any | None = None,
    ) -> None:
        self.creator_workflow_service = creator_workflow_service
        self.product_business_service = product_business_service
        self.telegram_business_service = telegram_business_service
        self.customer_business_service = customer_business_service
        self.content_opportunity_service = content_opportunity_service
        self.business_learning_service = business_learning_service
        self.business_optimization_service = business_optimization_service
        self.creator_workspace_service = creator_workspace_service
        self.creator_agent_service = creator_agent_service
        self.publishing_service = publishing_service
        self.decision_engine_runtime_boundary = decision_engine_runtime_boundary

    def certify(self, **context: Any) -> CreatorOSCertificationReport:
        sections = (
            self._validate_build_snapshot(
                "Creator Workflow",
                self.creator_workflow_service,
                owner="CreatorWorkflowService",
                context=context,
            ),
            self._validate_build_snapshot(
                "Product Business",
                self.product_business_service,
                owner="ProductBusinessService",
                context=context,
            ),
            self._validate_build_snapshot(
                "Telegram Business",
                self.telegram_business_service,
                owner="TelegramBusinessService",
                context=context,
            ),
            self._validate_build_snapshot(
                "Customer Business",
                self.customer_business_service,
                owner="CustomerBusinessService",
                context=context,
            ),
            self._validate_content_opportunity(),
            self._validate_business_learning(context),
            self._validate_build_snapshot(
                "Business Optimization",
                self.business_optimization_service,
                owner="BusinessOptimizationService",
                context=context,
            ),
            self._validate_creator_hq(context),
            self._validate_creator_agent(),
            self._validate_publishing(),
            self._validate_runtime_compatibility(),
        )
        missing = tuple(
            item
            for section in sections
            for item in section.missing_items
        )
        status = self._aggregate_status(sections)
        return CreatorOSCertificationReport(
            status=status,
            sections=sections,
            evidence=tuple(
                evidence
                for section in sections
                for evidence in section.evidence
            ),
            missing_items=missing,
            compatibility={
                "read_only": True,
                "provider_neutral": True,
                "executes_runtime": False,
                "mutates_business_state": False,
                "duplicates_domain_logic": False,
                "decision_engine_owner": "DecisionEngine",
                "telegram_runtime_owner": "Telegram",
                "publishing_owner": "Publishing/Fanvue",
            },
            metadata={
                "source": "CreatorOSCertificationService",
                "certification": "Creator OS v1.0",
            },
        )

    def _validate_build_snapshot(
        self,
        name: str,
        service: Any,
        *,
        owner: str,
        context: Mapping[str, Any],
    ) -> CreatorOSValidationSection:
        return self._validate_callable(
            name,
            service,
            method_names=("build_snapshot",),
            owner=owner,
            context=context,
        )

    def _validate_content_opportunity(self) -> CreatorOSValidationSection:
        service = self.content_opportunity_service
        section = self._validate_callable(
            "Content Opportunity",
            service,
            method_names=("build_snapshot",),
            owner="ContentOpportunityService",
            context={},
        )
        if section.status is CreatorOSCertificationStatus.FAIL:
            return section
        snapshot = self._safe_call(getattr(service, "build_snapshot", None))
        compatibility = self._mapping(getattr(snapshot, "compatibility", {}))
        missing = list(section.missing_items)
        evidence = list(section.evidence)
        if not compatibility.get("durable_persistence"):
            missing.append("Content Opportunity durable persistence is not enabled.")
        else:
            evidence.append(
                CreatorOSValidationEvidence(
                    source="ContentOpportunityService",
                    summary="Durable Content Opportunity repository is enabled.",
                    metadata={"durable_persistence": True},
                )
            )
        return self._section(
            "Content Opportunity",
            evidence=evidence,
            missing_items=missing,
        )

    def _validate_business_learning(
        self,
        context: Mapping[str, Any],
    ) -> CreatorOSValidationSection:
        service = self.business_learning_service
        return self._validate_callable(
            "Business Learning",
            service,
            method_names=("build_learning_snapshot", "build_snapshot"),
            owner="BusinessLearningService",
            context=context,
        )

    def _validate_creator_hq(
        self,
        context: Mapping[str, Any],
    ) -> CreatorOSValidationSection:
        service = self.creator_workspace_service
        build_dashboard = getattr(service, "build_dashboard", None)
        if not callable(build_dashboard):
            return self._section(
                "Creator HQ",
                missing_items=("CreatorWorkspaceService.build_dashboard is unavailable.",),
            )
        dashboard = self._call_with_context(build_dashboard, context)
        if dashboard is None:
            return self._section(
                "Creator HQ",
                missing_items=("CreatorWorkspaceService.build_dashboard did not return a dashboard.",),
            )
        evidence = [
            CreatorOSValidationEvidence(
                source="CreatorWorkspaceService",
                summary="Creator HQ dashboard read model is available.",
                metadata={"has_content_opportunity_card": bool(getattr(dashboard, "content_opportunity_card", None))},
            )
        ]
        missing = []
        if getattr(dashboard, "content_opportunity_card", None) is None:
            missing.append("Creator HQ Content Opportunity card is unavailable.")
        return self._section("Creator HQ", evidence=evidence, missing_items=missing)

    def _validate_creator_agent(self) -> CreatorOSValidationSection:
        service = self.creator_agent_service
        registry = getattr(service, "tool_registry", None)
        tools = tuple(getattr(registry, "tools", ()) or ())
        if service is None or not tools:
            return self._section(
                "Creator Agent",
                missing_items=("CreatorAgentService tool registry is unavailable.",),
            )
        has_content_opportunity = any(
            getattr(tool, "service_name", "") == "content_opportunity_service"
            for tool in tools
        )
        missing = ()
        if not has_content_opportunity:
            missing = ("Creator Agent does not expose ContentOpportunityService.",)
        return self._section(
            "Creator Agent",
            evidence=(
                CreatorOSValidationEvidence(
                    source="CreatorAgentService",
                    summary="Creator Agent read-only tool registry is available.",
                    metadata={"tool_count": len(tools)},
                ),
            ),
            missing_items=missing,
        )

    def _validate_publishing(self) -> CreatorOSValidationSection:
        return self._validate_callable(
            "Publishing",
            self.publishing_service,
            method_names=("build_publishing_queue_summary",),
            owner="PublishingService",
            context={},
        )

    def _validate_runtime_compatibility(self) -> CreatorOSValidationSection:
        service = self.decision_engine_runtime_boundary
        if service is None:
            return self._section(
                "DecisionEngine/runtime compatibility",
                missing_items=("DecisionEngine runtime compatibility boundary is unavailable.",),
            )
        metadata = {}
        compatibility = getattr(service, "compatibility", None)
        if callable(compatibility):
            metadata = self._mapping(self._safe_call(compatibility))
        return self._section(
            "DecisionEngine/runtime compatibility",
            evidence=(
                CreatorOSValidationEvidence(
                    source=type(service).__name__,
                    summary="DecisionEngine/runtime compatibility boundary is available.",
                    metadata=metadata,
                ),
            ),
        )

    def _validate_callable(
        self,
        name: str,
        service: Any,
        *,
        method_names: tuple[str, ...],
        owner: str,
        context: Mapping[str, Any],
    ) -> CreatorOSValidationSection:
        if service is None:
            return self._section(
                name,
                missing_items=(f"{owner} is unavailable.",),
            )
        for method_name in method_names:
            method = getattr(service, method_name, None)
            if not callable(method):
                continue
            result = self._call_with_context(method, context)
            if result is not None:
                return self._section(
                    name,
                    evidence=(
                        CreatorOSValidationEvidence(
                            source=owner,
                            summary=f"{owner}.{method_name} returned a read model.",
                            metadata={"method": method_name},
                        ),
                    ),
                )
        return self._section(
            name,
            missing_items=(f"{owner} has no working {method_names} method.",),
        )

    def _call_with_context(
        self,
        method: Callable[..., Any],
        context: Mapping[str, Any],
    ) -> Any:
        try:
            return method(**dict(context))
        except TypeError:
            try:
                return method()
            except Exception:
                return None
        except Exception:
            return None

    @staticmethod
    def _safe_call(method: Any) -> Any:
        if not callable(method):
            return None
        try:
            return method()
        except Exception:
            return None

    @staticmethod
    def _section(
        name: str,
        *,
        evidence: tuple[CreatorOSValidationEvidence, ...] | list[CreatorOSValidationEvidence] = (),
        missing_items: tuple[str, ...] | list[str] = (),
    ) -> CreatorOSValidationSection:
        missing = tuple(missing_items)
        status = (
            CreatorOSCertificationStatus.PASS
            if not missing
            else CreatorOSCertificationStatus.FAIL
            if not evidence
            else CreatorOSCertificationStatus.PARTIAL
        )
        return CreatorOSValidationSection(
            name=name,
            status=status,
            evidence=tuple(evidence),
            missing_items=missing,
            metadata={"read_only": True},
        )

    @staticmethod
    def _aggregate_status(
        sections: tuple[CreatorOSValidationSection, ...],
    ) -> CreatorOSCertificationStatus:
        statuses = {section.status for section in sections}
        if CreatorOSCertificationStatus.FAIL in statuses:
            return CreatorOSCertificationStatus.FAIL
        if CreatorOSCertificationStatus.PARTIAL in statuses:
            return CreatorOSCertificationStatus.PARTIAL
        return CreatorOSCertificationStatus.PASS

    @staticmethod
    def _mapping(value: Any) -> Mapping[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}
