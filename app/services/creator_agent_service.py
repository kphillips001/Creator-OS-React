"""Creator Agent natural-language orchestration service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.creator_agent import (
    CreatorAgentActionProposal,
    CreatorAgentContext,
    CreatorAgentEvidence,
    CreatorAgentIntent,
    CreatorAgentRecommendedAction,
    CreatorAgentRequest,
    CreatorAgentResponse,
    CreatorAgentSource,
    CreatorAgentTool,
    CreatorAgentToolContext,
    CreatorAgentToolRegistry,
    CreatorAgentToolRequest,
    CreatorAgentToolResult,
)
from app.models.llm_provider import LLMConversation, LLMMessage, LLMRequest
from app.providers.llm.null_provider import NullLLMProvider
from app.providers.llm.openai_provider import OpenAIProvider

if TYPE_CHECKING:
    from app.providers.llm.base import BaseLLMProvider
    from app.services.business_learning_service import BusinessLearningService
    from app.services.business_optimization_service import BusinessOptimizationService
    from app.services.creator_workspace_service import CreatorWorkspaceService
    from app.services.customer_business_service import CustomerBusinessService
    from app.services.product_business_service import ProductBusinessService
    from app.services.product_strategy_service import ProductStrategyService
    from app.services.publishing_service import PublishingService
    from app.services.commerce_strategy_service import CommerceStrategyService
    from app.services.telegram_business_service import TelegramBusinessService
    from app.services.content_opportunity_service import ContentOpportunityService


class CreatorAgentService:
    """Answer creator questions by aggregating existing read models only.

    Creator Agent is a natural-language presentation/orchestration boundary. It
    does not execute Telegram, mutate Product/Customer/Publishing/Business
    Learning state, change DecisionEngine behavior, or call external LLMs.
    """

    def __init__(
        self,
        *,
        business_optimization_service: "BusinessOptimizationService | None" = None,
        creator_workspace_service: "CreatorWorkspaceService | None" = None,
        product_business_service: "ProductBusinessService | None" = None,
        telegram_business_service: "TelegramBusinessService | None" = None,
        customer_business_service: "CustomerBusinessService | None" = None,
        business_learning_service: "BusinessLearningService | None" = None,
        publishing_service: "PublishingService | None" = None,
        product_strategy_service: "ProductStrategyService | None" = None,
        commerce_strategy_service: "CommerceStrategyService | None" = None,
        content_opportunity_service: "ContentOpportunityService | None" = None,
        tool_registry: CreatorAgentToolRegistry | None = None,
        llm_provider: "BaseLLMProvider | None" = None,
        enable_llm: bool = True,
    ) -> None:
        self.business_optimization_service = business_optimization_service
        self.creator_workspace_service = creator_workspace_service
        self.product_business_service = product_business_service
        self.telegram_business_service = telegram_business_service
        self.customer_business_service = customer_business_service
        self.business_learning_service = business_learning_service
        self.publishing_service = publishing_service
        self.product_strategy_service = product_strategy_service
        self.commerce_strategy_service = commerce_strategy_service
        self.content_opportunity_service = content_opportunity_service
        self.tool_registry = tool_registry or self.default_tool_registry()
        self.llm_provider = llm_provider if llm_provider is not None else (
            self._default_llm_provider() if enable_llm else None
        )

    def answer(self, request: CreatorAgentRequest) -> CreatorAgentResponse:
        """Return a read-only Creator Agent response for a natural question."""

        intent = self.resolve_intent(request.question)
        warnings: list[str] = []
        limitations: list[str] = []
        tool_context = self._run_tools(request=request, intent=intent, warnings=warnings)
        snapshots = self._context_from_tool_results(tool_context)
        context = CreatorAgentContext(
            intent=intent,
            tool_context=tool_context,
            **snapshots,
        )
        sources = self._sources(context)
        actions = self._recommended_actions(context=context, intent=intent)
        proposals = self._action_proposals(intent=intent, actions=actions)
        evidence = self._supporting_evidence(
            context=context,
            sources=sources,
            actions=actions,
        )
        reasoning = self._business_reasoning(
            request=request,
            intent=intent,
            context=context,
            sources=sources,
            actions=actions,
            evidence=evidence,
        )
        rationale = self._recommendation_rationale(actions=actions, evidence=evidence)
        confidence_explanation = self._confidence_explanation(
            sources=sources,
            warnings=warnings,
            evidence=evidence,
        )
        follow_ups = self._suggested_follow_up_questions(
            intent=intent,
            sources=sources,
            actions=actions,
        )
        related_areas = self._related_business_areas(sources=sources)
        answer_text = self._answer_text(
            intent=intent,
            context=context,
            actions=actions,
            reasoning=reasoning,
            warnings=warnings,
            limitations=limitations,
        )

        if intent is CreatorAgentIntent.UNSUPPORTED:
            limitations.append(
                "Creator Agent can answer business read-model questions, but this "
                "request is outside the current foundation scope."
            )
        if not sources and intent is not CreatorAgentIntent.UNSUPPORTED:
            limitations.append("No upstream read models were available for this answer.")

        llm_response = None
        if self.llm_provider is not None:
            llm_response = self._generate_llm_response(
                request=request,
                intent=intent,
                context=context,
                sources=sources,
                actions=actions,
                proposals=proposals,
                reasoning=reasoning,
                evidence=evidence,
                confidence_explanation=confidence_explanation,
                rationale=rationale,
                follow_ups=follow_ups,
                related_areas=related_areas,
                warnings=tuple(warnings),
                limitations=tuple(limitations),
            )
            if llm_response is not None:
                answer_text = llm_response.response_text
                warnings.extend(llm_response.warnings)
                if llm_response.errors:
                    limitations.extend(llm_response.errors)

        return CreatorAgentResponse(
            request=request,
            intent=intent,
            answer_text=answer_text,
            context=context,
            sources=sources,
            confidence=self._confidence(intent=intent, sources=sources, warnings=warnings),
            recommended_actions=actions,
            action_proposals=proposals,
            business_reasoning=reasoning,
            supporting_evidence=evidence,
            confidence_explanation=confidence_explanation,
            recommendation_rationale=rationale,
            suggested_follow_up_questions=follow_ups,
            related_business_areas=related_areas,
            warnings=tuple(warnings),
            limitations=tuple(limitations),
            compatibility=self._compatibility(),
            metadata={
                "source": "creator_agent",
                "provider_neutral": True,
                "llm_used": llm_response is not None,
                "llm_provider": llm_response.provider_name if llm_response else None,
                "llm_model": llm_response.model_name if llm_response else None,
                "llm_fallback": bool(
                    llm_response
                    and llm_response.raw_provider_metadata.get("fallback_provider")
                ),
                "external_calls": bool(
                    self._attr(llm_response.metadata if llm_response else {}, "external_api_called", False)
                ),
            },
        )

    def handle(self, request: CreatorAgentRequest) -> CreatorAgentResponse:
        """Compatibility alias for callers that model Agent work as handling."""

        return self.answer(request)

    def _default_llm_provider(self):
        openai_provider = OpenAIProvider()
        if openai_provider.is_configured:
            return openai_provider
        return NullLLMProvider()

    def resolve_intent(self, question: str) -> CreatorAgentIntent:
        text = question.lower()
        if not text.strip():
            return CreatorAgentIntent.UNSUPPORTED
        if any(
            phrase in text
            for phrase in (
                "content opportunity",
                "customers asking for",
                "customer demand",
                "what content",
                "create next",
                "currently have",
                "do not currently have",
                "don't currently have",
                "requests are increasing",
                "topics are trending",
                "trending topics",
                "vip requests",
                "waiting for content",
                "waiting customers",
                "unresolved opportunities",
                "recently resolved",
                "previous customer demand",
                "previous requests",
                "follow-ups are ready",
                "follow ups are ready",
                "biggest content opportunities",
                "future content recommendations",
                "most requested content",
                "shower videos",
                "shower video",
            )
        ):
            return CreatorAgentIntent.CONTENT_OPPORTUNITY
        if any(
            phrase in text
            for phrase in (
                "why",
                "explain",
                "tell me more",
                "show evidence",
                "what changed",
                "what should happen next",
            )
        ):
            return CreatorAgentIntent.EXPLAIN_RECOMMENDATION
        if any(
            phrase in text
            for phrase in (
                "compare",
                "which is better",
                "which bundle is stronger",
                "which product should i prioritize",
                "which publishing opportunity is better",
                "which content opportunity is better",
            )
        ):
            return CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS
        if any(word in text for word in ("workspace", "dashboard", "overview")):
            return CreatorAgentIntent.WORKSPACE_OVERVIEW
        if any(word in text for word in ("today", "daily", "priority", "priorities")):
            return CreatorAgentIntent.DAILY_PRIORITIES
        if "business optimization" in text or "optimization" in text:
            return CreatorAgentIntent.BUSINESS_OPTIMIZATION_SUMMARY
        if any(word in text for word in ("learning", "evidence", "outcome", "outcomes")):
            return CreatorAgentIntent.BUSINESS_LEARNING
        if "commerce" in text or any(word in text for word in ("sell", "selling", "offer strategy", "sales strategy")):
            return CreatorAgentIntent.COMMERCE_RECOMMENDATION
        if any(word in text for word in ("recommend product", "product recommendation", "what product should")):
            return CreatorAgentIntent.PRODUCT_RECOMMENDATION
        if any(word in text for word in ("health", "healthy", "status", "overview")):
            return CreatorAgentIntent.BUSINESS_HEALTH
        if any(word in text for word in ("media link", "media links", "publishing", "publish")):
            return CreatorAgentIntent.PUBLISHING_READINESS
        if any(word in text for word in ("product", "products", "catalog")):
            return CreatorAgentIntent.PRODUCT_ATTENTION
        if any(word in text for word in ("telegram", "follow up", "follow-up", "conversation", "chat")):
            return CreatorAgentIntent.TELEGRAM_FOLLOW_UP
        if any(word in text for word in ("customer", "customers", "vip", "retention", "dormant")):
            return CreatorAgentIntent.CUSTOMER_ATTENTION
        return CreatorAgentIntent.UNSUPPORTED

    def selected_tools(
        self,
        intent: CreatorAgentIntent,
    ) -> tuple[CreatorAgentTool, ...]:
        """Return read-only tools selected for the resolved intent."""

        return self.tool_registry.tools_for_intent(intent)

    @classmethod
    def default_tool_registry(cls) -> CreatorAgentToolRegistry:
        """Return the provider-neutral registry of read-only Creator OS tools."""

        compatibility = {
            "read_only": True,
            "provider_neutral": True,
            "avoids_runtime_execution": True,
            "avoids_mutations": True,
            "avoids_direct_repository_access": True,
        }
        return CreatorAgentToolRegistry(
            tools=(
                CreatorAgentTool(
                    name="business_optimization_snapshot",
                    service_name="business_optimization_service",
                    method_name="build_snapshot",
                    context_field="business_optimization_snapshot",
                    intents=(
                        CreatorAgentIntent.DAILY_PRIORITIES,
                        CreatorAgentIntent.BUSINESS_HEALTH,
                        CreatorAgentIntent.BUSINESS_OPTIMIZATION_SUMMARY,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                        CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
                    ),
                    metadata={"owner": "BusinessOptimizationService"},
                ),
                CreatorAgentTool(
                    name="workspace_dashboard",
                    service_name="creator_workspace_service",
                    method_name="build_dashboard",
                    context_field="workspace_dashboard",
                    intents=(
                        CreatorAgentIntent.DAILY_PRIORITIES,
                        CreatorAgentIntent.WORKSPACE_OVERVIEW,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                    ),
                    metadata={"owner": "CreatorWorkspaceService"},
                ),
                CreatorAgentTool(
                    name="product_business_snapshot",
                    service_name="product_business_service",
                    method_name="build_snapshot",
                    context_field="product_business_snapshot",
                    intents=(
                        CreatorAgentIntent.PRODUCT_ATTENTION,
                        CreatorAgentIntent.PUBLISHING_READINESS,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                        CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
                    ),
                    metadata={"owner": "ProductBusinessService"},
                ),
                CreatorAgentTool(
                    name="publishing_summary",
                    service_name="publishing_service",
                    method_name="build_publishing_queue_summary",
                    context_field="publishing_summary",
                    intents=(
                        CreatorAgentIntent.PUBLISHING_READINESS,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                        CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
                    ),
                    metadata={"owner": "PublishingService", "read_methods_only": True},
                ),
                CreatorAgentTool(
                    name="customer_business_snapshot",
                    service_name="customer_business_service",
                    method_name="build_snapshot",
                    context_field="customer_business_snapshot",
                    intents=(
                        CreatorAgentIntent.CUSTOMER_ATTENTION,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                        CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
                    ),
                    metadata={"owner": "CustomerBusinessService"},
                ),
                CreatorAgentTool(
                    name="telegram_business_snapshot",
                    service_name="telegram_business_service",
                    method_name="build_snapshot",
                    context_field="telegram_business_snapshot",
                    intents=(
                        CreatorAgentIntent.TELEGRAM_FOLLOW_UP,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                    ),
                    metadata={"owner": "TelegramBusinessService"},
                ),
                CreatorAgentTool(
                    name="business_learning_snapshot",
                    service_name="business_learning_service",
                    method_name="build_snapshot",
                    context_field="business_learning_snapshot",
                    intents=(
                        CreatorAgentIntent.BUSINESS_LEARNING,
                        CreatorAgentIntent.CUSTOMER_ATTENTION,
                        CreatorAgentIntent.PRODUCT_ATTENTION,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                        CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
                    ),
                    metadata={"owner": "BusinessLearningService"},
                ),
                CreatorAgentTool(
                    name="product_strategy_result",
                    service_name="product_strategy_service",
                    method_name="recommend",
                    context_field="product_strategy_result",
                    intents=(
                        CreatorAgentIntent.PRODUCT_RECOMMENDATION,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                        CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
                    ),
                    metadata={"owner": "ProductStrategyService"},
                ),
                CreatorAgentTool(
                    name="commerce_strategy_result",
                    service_name="commerce_strategy_service",
                    method_name="recommend",
                    context_field="commerce_strategy_result",
                    intents=(
                        CreatorAgentIntent.COMMERCE_RECOMMENDATION,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                        CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
                    ),
                    metadata={"owner": "CommerceStrategyService"},
                ),
                CreatorAgentTool(
                    name="content_opportunity_snapshot",
                    service_name="content_opportunity_service",
                    method_name="build_snapshot",
                    context_field="content_opportunity_snapshot",
                    intents=(
                        CreatorAgentIntent.CONTENT_OPPORTUNITY,
                        CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
                        CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
                    ),
                    metadata={"owner": "ContentOpportunityService"},
                ),
            ),
            compatibility=compatibility,
        )

    def _run_tools(
        self,
        *,
        request: CreatorAgentRequest,
        intent: CreatorAgentIntent,
        warnings: list[str],
    ) -> CreatorAgentToolContext:
        tool_requests = tuple(
            CreatorAgentToolRequest(
                tool=tool,
                request=request,
                intent=intent,
                parameters=self._tool_parameters(tool=tool, request=request),
                metadata={"read_only": True},
            )
            for tool in self.selected_tools(intent)
        )
        results = tuple(
            self._run_tool(tool_request=tool_request, warnings=warnings)
            for tool_request in tool_requests
        )
        return CreatorAgentToolContext(
            intent=intent,
            requests=tool_requests,
            results=results,
            compatibility=self.tool_registry.compatibility,
            metadata={"tool_count": len(tool_requests), "result_count": len(results)},
        )

    def _run_tool(
        self,
        *,
        tool_request: CreatorAgentToolRequest,
        warnings: list[str],
    ) -> CreatorAgentToolResult:
        tool = tool_request.tool
        service = getattr(self, tool.service_name, None)
        if service is None:
            return CreatorAgentToolResult(
                tool=tool,
                success=False,
                warning=f"{tool.metadata.get('owner', tool.service_name)} unavailable",
                metadata={"read_only": True},
            )
        try:
            result = self._execute_tool_method(
                service=service,
                tool_request=tool_request,
            )
        except Exception as exc:
            warning = f"{tool.metadata.get('owner', tool.service_name)} unavailable: {exc}"
            warnings.append(warning)
            return CreatorAgentToolResult(
                tool=tool,
                success=False,
                warning=warning,
                metadata={"read_only": True},
            )
        return CreatorAgentToolResult(
            tool=tool,
            success=True,
            result=result,
            source=CreatorAgentSource(
                source_type="read_model",
                name=str(tool.metadata.get("owner", tool.service_name)),
                summary=self._source_summary(result),
                confidence=0.8,
                metadata={
                    "field": tool.context_field,
                    "tool": tool.name,
                    "read_only": True,
                },
            ),
            metadata={"read_only": True, "aggregation_only": True},
        )

    def _execute_tool_method(
        self,
        *,
        service: Any,
        tool_request: CreatorAgentToolRequest,
    ) -> Any:
        tool = tool_request.tool
        if tool.service_name == "creator_workspace_service":
            return self._build_workspace_dashboard_from_service(
                service=service,
                request=tool_request.request,
            )
        if tool.service_name == "publishing_service":
            items = service.list_publishing_queue_items()
            return service.build_publishing_queue_summary(items)
        method = getattr(service, tool.method_name)
        return method(**dict(tool_request.parameters))

    def _context_from_tool_results(
        self, tool_context: CreatorAgentToolContext
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        for result in tool_context.results:
            if result.success:
                context[result.tool.context_field] = result.result
        return context

    def _tool_parameters(
        self,
        *,
        tool: CreatorAgentTool,
        request: CreatorAgentRequest,
    ) -> Mapping[str, Any]:
        if tool.service_name == "telegram_business_service":
            return {
                key: value
                for key, value in {
                    "customer_id": request.customer_id,
                    "provider": request.provider,
                }.items()
                if value is not None
            }
        if tool.service_name == "customer_business_service":
            return {
                "customer_id": request.customer_id
            } if request.customer_id is not None else {}
        return {}

    def _build_workspace_dashboard(
        self,
        *,
        request: CreatorAgentRequest,
        warnings: list[str],
    ) -> Any | None:
        if self.creator_workspace_service is None:
            return None
        try:
            return self._build_workspace_dashboard_from_service(
                service=self.creator_workspace_service,
                request=request,
            )
        except Exception as exc:
            warnings.append(f"CreatorWorkspaceService unavailable: {exc}")
            return None

    def _build_workspace_dashboard_from_service(
        self,
        *,
        service: Any,
        request: CreatorAgentRequest,
    ) -> Any:
        creator_profile = (
            {"id": request.creator_profile_id}
            if request.creator_profile_id is not None
            else None
        )
        active_account = (
            {"id": request.account_id} if request.account_id is not None else None
        )
        return service.build_dashboard(
            creator_profile=creator_profile,
            active_account=active_account,
        )

    def _publishing_summary(self, warnings: list[str]) -> Any | None:
        if self.publishing_service is None:
            return None
        try:
            items = self.publishing_service.list_publishing_queue_items()
            if hasattr(self.publishing_service, "build_publishing_queue_summary"):
                return self.publishing_service.build_publishing_queue_summary(items)
            return {"queue_items": tuple(items)}
        except Exception as exc:
            warnings.append(f"PublishingService read summary unavailable: {exc}")
            return None

    def _call_optional(
        self,
        service: Any | None,
        method_name: str,
        warnings: list[str],
        source_name: str,
        **kwargs: Any,
    ) -> Any | None:
        if service is None:
            return None
        try:
            method = getattr(service, method_name)
            clean_kwargs = {key: value for key, value in kwargs.items() if value is not None}
            return method(**clean_kwargs)
        except Exception as exc:
            warnings.append(f"{source_name} unavailable: {exc}")
            return None

    def _sources(self, context: CreatorAgentContext) -> tuple[CreatorAgentSource, ...]:
        sources: list[CreatorAgentSource] = []
        source_fields = (
            ("business_optimization_snapshot", "BusinessOptimizationService"),
            ("workspace_dashboard", "CreatorWorkspaceService"),
            ("product_business_snapshot", "ProductBusinessService"),
            ("telegram_business_snapshot", "TelegramBusinessService"),
            ("customer_business_snapshot", "CustomerBusinessService"),
            ("business_learning_snapshot", "BusinessLearningService"),
            ("publishing_summary", "PublishingService"),
            ("product_strategy_result", "ProductStrategyService"),
            ("commerce_strategy_result", "CommerceStrategyService"),
            ("content_opportunity_snapshot", "ContentOpportunityService"),
        )
        if context.tool_context is not None:
            tool_sources = tuple(
                result.source
                for result in context.tool_context.results
                if result.source is not None
            )
            if tool_sources:
                return tool_sources
        for field_name, service_name in source_fields:
            value = getattr(context, field_name)
            if value is None:
                continue
            sources.append(
                CreatorAgentSource(
                    source_type="read_model",
                    name=service_name,
                    summary=self._source_summary(value),
                    confidence=0.8,
                    metadata={"field": field_name},
                )
            )
        return tuple(sources)

    def _recommended_actions(
        self,
        *,
        context: CreatorAgentContext,
        intent: CreatorAgentIntent,
    ) -> tuple[CreatorAgentRecommendedAction, ...]:
        actions: list[CreatorAgentRecommendedAction] = []
        optimization = context.business_optimization_snapshot
        workspace = context.workspace_dashboard
        content_opportunity = context.content_opportunity_snapshot

        for action in self._iter_attr(optimization, "recommended_today_actions"):
            actions.append(self._action_from_any(action, source="BusinessOptimizationService"))
        for action in self._iter_attr(optimization, "prioritized_recommendations"):
            actions.append(self._action_from_any(action, source="BusinessOptimizationService"))
        for action in self._iter_attr(workspace, "recommended_actions"):
            actions.append(self._action_from_any(action, source="CreatorWorkspaceService"))
        for action in self._iter_attr(content_opportunity, "creator_recommendations"):
            actions.append(self._action_from_any(action, source="ContentOpportunityService"))
        for action in tuple(self._attr(content_opportunity, "next_recommended_actions", ()) or ())[:3]:
            actions.append(
                CreatorAgentRecommendedAction(
                    title=str(action),
                    detail="Recommended by ContentOpportunityService demand intelligence.",
                    priority="NORMAL",
                    source="ContentOpportunityService",
                    target="Content Opportunity Center",
                    metadata={"read_only": True, "aggregation_only": True},
                )
            )

        if not actions:
            fallback = self._fallback_action(context=context, intent=intent)
            if fallback is not None:
                actions.append(fallback)

        return tuple(actions[:5])

    def _fallback_action(
        self,
        *,
        context: CreatorAgentContext,
        intent: CreatorAgentIntent,
    ) -> CreatorAgentRecommendedAction | None:
        if intent is CreatorAgentIntent.UNSUPPORTED:
            return None
        candidates = (
            (context.business_optimization_snapshot, "next_recommended_business_action", "BusinessOptimizationService"),
            (context.product_business_snapshot, "next_recommended_business_action", "ProductBusinessService"),
            (context.telegram_business_snapshot, "next_recommended_business_action", "TelegramBusinessService"),
            (context.customer_business_snapshot, "next_recommended_action", "CustomerBusinessService"),
            (context.product_strategy_result, "recommendation", "ProductStrategyService"),
            (context.commerce_strategy_result, "recommendation", "CommerceStrategyService"),
            (context.content_opportunity_snapshot, "next_recommended_actions", "ContentOpportunityService"),
        )
        for model, attr, source in candidates:
            value = self._attr(model, attr)
            if value and not isinstance(value, str):
                try:
                    value = tuple(value)[0]
                except (IndexError, TypeError):
                    value = None
            if value:
                return CreatorAgentRecommendedAction(
                    title=str(value),
                    detail="Recommended by an existing Creator OS read model.",
                    priority="NORMAL",
                    source=source,
                )
        return None

    def _action_proposals(
        self,
        *,
        intent: CreatorAgentIntent,
        actions: tuple[CreatorAgentRecommendedAction, ...],
    ) -> tuple[CreatorAgentActionProposal, ...]:
        if not actions or intent is CreatorAgentIntent.UNSUPPORTED:
            return ()
        return tuple(
            CreatorAgentActionProposal(
                action_type="review_recommendation",
                title=action.title,
                detail="Review only. Creator Agent foundation does not execute actions.",
                executable_by=action.source,
                metadata={"read_only": True, "executed": False},
            )
            for action in actions
        )

    def _supporting_evidence(
        self,
        *,
        context: CreatorAgentContext,
        sources: tuple[CreatorAgentSource, ...],
        actions: tuple[CreatorAgentRecommendedAction, ...],
    ) -> tuple[CreatorAgentEvidence, ...]:
        evidence: list[CreatorAgentEvidence] = []
        for source in sources:
            evidence.append(
                CreatorAgentEvidence(
                    source=source.name,
                    summary=source.summary,
                    evidence_type=str(source.metadata.get("field", "read_model")),
                    confidence=source.confidence,
                    metadata={"source_type": source.source_type},
                )
            )
        for action in actions:
            evidence.append(
                CreatorAgentEvidence(
                    source=action.source,
                    summary=action.title,
                    evidence_type="recommendation",
                    confidence=0.7,
                    metadata={
                        "priority": action.priority,
                        "target": action.target,
                    },
                )
            )
        if context.tool_context is not None:
            for result in context.tool_context.results:
                if not result.success and result.warning:
                    evidence.append(
                        CreatorAgentEvidence(
                            source=str(
                                result.tool.metadata.get(
                                    "owner",
                                    result.tool.service_name,
                                )
                            ),
                            summary=result.warning,
                            evidence_type="unavailable_source",
                            confidence=0.2,
                            metadata={"tool": result.tool.name},
                        )
                    )
        evidence.extend(self._content_opportunity_evidence(context.content_opportunity_snapshot))
        return tuple(evidence[:16])

    def _content_opportunity_evidence(
        self,
        snapshot: Any | None,
    ) -> tuple[CreatorAgentEvidence, ...]:
        if snapshot is None:
            return ()
        evidence: list[CreatorAgentEvidence] = []
        total = int(self._attr(snapshot, "total_requests", 0) or 0)
        matched = int(self._attr(snapshot, "matched_count", 0) or 0)
        unmatched = int(self._attr(snapshot, "unmatched_count", 0) or 0)
        vip = int(self._attr(snapshot, "vip_request_count", 0) or 0)
        repeat = int(self._attr(snapshot, "repeat_request_count", 0) or 0)
        evidence.append(
            CreatorAgentEvidence(
                source="ContentOpportunityService",
                summary=(
                    f"Demand summary: {total} request(s), {matched} matched, "
                    f"{unmatched} unmatched, {repeat} repeat demand signal(s), "
                    f"{vip} VIP demand signal(s)."
                ),
                evidence_type="content_demand_summary",
                confidence=0.85,
                metadata={
                    "total_requests": total,
                    "matched_requests": matched,
                    "unmatched_requests": unmatched,
                    "repeat_request_count": repeat,
                    "vip_request_count": vip,
                },
            )
        )
        for topic in tuple(self._attr(snapshot, "trending_topics", ()) or ())[:3]:
            terms = " ".join(tuple(self._attr(topic, "terms", ()) or ())) or str(
                self._attr(topic, "topic_key", "content demand")
            )
            evidence.append(
                CreatorAgentEvidence(
                    source="ContentOpportunityService",
                    summary=(
                        f"{terms} has {self._attr(topic, 'request_count', 0)} request(s), "
                        f"{self._attr(topic, 'unique_customers', 0)} unique customer(s), "
                        f"and {self._attr(topic, 'vip_request_count', 0)} VIP request(s)."
                    ),
                    evidence_type="trending_content_topic",
                    confidence=0.82,
                    metadata={"topic_key": self._attr(topic, "topic_key", "")},
                )
            )
        for opportunity in tuple(
            self._attr(snapshot, "highest_priority_opportunities", ()) or ()
        )[:2]:
            evidence.append(
                CreatorAgentEvidence(
                    source="ContentOpportunityService",
                    summary=(
                        f"Unresolved opportunity from request: "
                        f"{self._attr(opportunity, 'request_text', 'content request')}"
                    ),
                    evidence_type="unresolved_content_opportunity",
                    confidence=float(self._attr(opportunity, "match_confidence", 0.7) or 0.7),
                    metadata={
                        "opportunity_id": self._attr(opportunity, "opportunity_id", ""),
                        "status": self._display(self._attr(opportunity, "status", "")),
                    },
                )
            )
        for resolution in tuple(self._attr(snapshot, "resolution_records", ()) or ())[:2]:
            evidence.append(
                CreatorAgentEvidence(
                    source="ContentOpportunityService",
                    summary=(
                        f"Resolution ready for {self._attr(resolution, 'customer_count', 0)} "
                        "waiting customer(s) with matched Product(s): "
                        f"{', '.join(tuple(self._attr(resolution, 'matched_product_ids', ()) or ())) or 'none'}."
                    ),
                    evidence_type="content_resolution",
                    confidence=float(self._attr(resolution, "confidence", 0.75) or 0.75),
                    metadata={
                        "resolution_id": self._attr(resolution, "resolution_id", ""),
                        "waiting_customer_ids": tuple(
                            self._attr(resolution, "waiting_customer_ids", ()) or ()
                        ),
                    },
                )
            )
        for follow_up in tuple(self._attr(snapshot, "follow_up_opportunities", ()) or ())[:2]:
            evidence.append(
                CreatorAgentEvidence(
                    source="ContentOpportunityService",
                    summary=(
                        f"Follow-up ready for {self._attr(follow_up, 'customer_id', 'customer')} "
                        f"about {self._attr(follow_up, 'original_request_text', 'requested content')}."
                    ),
                    evidence_type="content_follow_up",
                    confidence=float(self._attr(follow_up, "confidence", 0.75) or 0.75),
                    metadata={
                        "follow_up_id": self._attr(follow_up, "follow_up_id", ""),
                        "status": self._display(self._attr(follow_up, "status", "")),
                    },
                )
            )
        return tuple(evidence)

    def _business_reasoning(
        self,
        *,
        request: CreatorAgentRequest,
        intent: CreatorAgentIntent,
        context: CreatorAgentContext,
        sources: tuple[CreatorAgentSource, ...],
        actions: tuple[CreatorAgentRecommendedAction, ...],
        evidence: tuple[CreatorAgentEvidence, ...],
    ) -> tuple[str, ...]:
        if not sources and not evidence:
            return (
                "I could not build a source-backed explanation because the relevant Creator OS read models were unavailable.",
            )

        source_names = ", ".join(source.name for source in sources) or "Creator OS"
        action_text = (
            f"The leading recommendation is '{actions[0].title}'. "
            if actions
            else ""
        )
        if intent is CreatorAgentIntent.CONTENT_OPPORTUNITY:
            snapshot = context.content_opportunity_snapshot
            return (
                (
                    f"Content Opportunity Intelligence reports {self._attr(snapshot, 'total_requests', 0)} "
                    f"customer content request(s), with {self._attr(snapshot, 'unmatched_count', 0)} "
                    f"unmatched and {self._attr(snapshot, 'matched_count', 0)} matched. "
                    f"{action_text}"
                    "ContentOpportunityService owns the demand, match, resolution, and follow-up intelligence."
                ),
                "Creator Agent is summarizing demand intelligence and does not create Products, promise future content, or contact customers.",
            )
        if intent is CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS:
            return (
                (
                    "The comparison is based on the available read models from "
                    f"{source_names}. {action_text}"
                    "Creator Agent can explain relative priority, but it does not create new Product, Customer, or Commerce scores."
                ),
                "Use the supporting evidence list to see which domain contributed each signal.",
            )
        if intent is CreatorAgentIntent.EXPLAIN_RECOMMENDATION:
            topic = self._conversation_topic(request) or "the current recommendation"
            return (
                (
                    f"The explanation for {topic} is assembled from {source_names}. "
                    f"{action_text}"
                    "The source domains remain responsible for the underlying recommendation logic."
                ),
                "The evidence below is traceable to Creator OS read models and recommendation outputs.",
            )
        return (
            (
                f"This answer uses current Creator OS read models from {source_names}. "
                f"{action_text}"
                "Creator Agent is summarizing and explaining, not changing business state."
            ),
        )

    def _recommendation_rationale(
        self,
        *,
        actions: tuple[CreatorAgentRecommendedAction, ...],
        evidence: tuple[CreatorAgentEvidence, ...],
    ) -> tuple[str, ...]:
        if not actions:
            return ()
        rationale: list[str] = []
        evidence_sources = tuple(dict.fromkeys(item.source for item in evidence))
        for action in actions[:3]:
            source_note = (
                f" Supported by: {', '.join(evidence_sources[:4])}."
                if evidence_sources
                else ""
            )
            rationale.append(
                f"{action.title} is surfaced by {action.source} with {action.priority} priority.{source_note}"
            )
        return tuple(rationale)

    def _confidence_explanation(
        self,
        *,
        sources: tuple[CreatorAgentSource, ...],
        warnings: list[str],
        evidence: tuple[CreatorAgentEvidence, ...],
    ) -> str:
        if not sources:
            return "Confidence is low because no upstream read models were available."
        if warnings:
            return (
                "Confidence is reduced because one or more selected read models were unavailable."
            )
        return (
            f"Confidence is based on {len(sources)} source read model(s) and "
            f"{len(evidence)} evidence item(s)."
        )

    def _suggested_follow_up_questions(
        self,
        *,
        intent: CreatorAgentIntent,
        sources: tuple[CreatorAgentSource, ...],
        actions: tuple[CreatorAgentRecommendedAction, ...],
    ) -> tuple[str, ...]:
        suggestions = ["Show evidence.", "What should happen next?"]
        if intent is CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS:
            suggestions.append("Which option has stronger evidence?")
        source_names = {source.name for source in sources}
        if "ProductBusinessService" in source_names or "ProductStrategyService" in source_names:
            suggestions.append("Why was this Product recommended?")
            suggestions.append("Which Product should I prioritize?")
        if "CustomerBusinessService" in source_names:
            suggestions.append("Why is this customer at risk?")
            suggestions.append("Which customer needs attention first?")
        if "PublishingService" in source_names:
            suggestions.append("Why should I publish this today?")
        if "BusinessLearningService" in source_names:
            suggestions.append("What evidence supports this?")
        if "ContentOpportunityService" in source_names:
            suggestions.append("Which topics are trending?")
            suggestions.append("Which customers are waiting for content?")
            suggestions.append("Why does this content recommendation exist?")
        if actions:
            suggestions.append(f"Explain '{actions[0].title}'.")
        return tuple(dict.fromkeys(suggestions))[:6]

    def _related_business_areas(
        self,
        *,
        sources: tuple[CreatorAgentSource, ...],
    ) -> tuple[str, ...]:
        source_to_area = {
            "ProductStrategyService": "Product Strategy",
            "CommerceStrategyService": "Commerce Strategy",
            "ProductBusinessService": "Product Business",
            "CustomerBusinessService": "Customer Business",
            "TelegramBusinessService": "Telegram Business",
            "PublishingService": "Publishing",
            "BusinessLearningService": "Business Learning",
            "BusinessOptimizationService": "Business Optimization",
            "CreatorWorkspaceService": "Creator Workspace",
            "ContentOpportunityService": "Content Opportunity Intelligence",
        }
        areas = [
            source_to_area.get(source.name, source.name)
            for source in sources
        ]
        return tuple(dict.fromkeys(areas))

    def _conversation_topic(self, request: CreatorAgentRequest) -> str:
        for item in reversed(tuple(request.metadata.get("conversation_history") or ())):
            if not isinstance(item, Mapping):
                continue
            if item.get("role") != "user":
                continue
            content = str(item.get("content") or "").strip()
            if content:
                return content[:120]
        return request.question.strip()[:120]

    def _answer_text(
        self,
        *,
        intent: CreatorAgentIntent,
        context: CreatorAgentContext,
        actions: tuple[CreatorAgentRecommendedAction, ...],
        reasoning: tuple[str, ...],
        warnings: list[str],
        limitations: list[str],
    ) -> str:
        if intent is CreatorAgentIntent.UNSUPPORTED:
            return (
                "I can answer Creator OS business questions about priorities, health, "
                "Products, publishing readiness, customers, Telegram follow-up, and "
                "Business Optimization. I do not have a supported read model for this "
                "question yet."
            )

        headline = self._headline(intent=intent, context=context)
        if intent is CreatorAgentIntent.CONTENT_OPPORTUNITY:
            summary = self._content_opportunity_answer_summary(
                context.content_opportunity_snapshot
            )
            if actions:
                action_text = "; ".join(action.title for action in actions[:3])
                return f"{headline} {summary} Recommended next action: {action_text}."
            return f"{headline} {summary}"
        if intent in {
            CreatorAgentIntent.EXPLAIN_RECOMMENDATION,
            CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS,
        } and reasoning:
            return f"{headline} {reasoning[0]}"
        if actions:
            action_text = "; ".join(action.title for action in actions[:3])
            return f"{headline} Recommended next action: {action_text}."
        if warnings or limitations:
            return f"{headline} Some source data was unavailable, so this answer is limited."
        return f"{headline} No urgent action is visible from the available read models."

    def _generate_llm_response(
        self,
        *,
        request: CreatorAgentRequest,
        intent: CreatorAgentIntent,
        context: CreatorAgentContext,
        sources: tuple[CreatorAgentSource, ...],
        actions: tuple[CreatorAgentRecommendedAction, ...],
        proposals: tuple[CreatorAgentActionProposal, ...],
        reasoning: tuple[str, ...],
        evidence: tuple[CreatorAgentEvidence, ...],
        confidence_explanation: str,
        rationale: tuple[str, ...],
        follow_ups: tuple[str, ...],
        related_areas: tuple[str, ...],
        warnings: tuple[str, ...],
        limitations: tuple[str, ...],
    ):
        llm_request = self._build_llm_request(
            request=request,
            intent=intent,
            context=context,
            sources=sources,
            actions=actions,
            proposals=proposals,
            reasoning=reasoning,
            evidence=evidence,
            confidence_explanation=confidence_explanation,
            rationale=rationale,
            follow_ups=follow_ups,
            related_areas=related_areas,
            warnings=warnings,
            limitations=limitations,
        )
        try:
            response = self.llm_provider.generate_response(llm_request)
        except Exception as exc:
            return None
        if response.response_text:
            return response
        fallback = NullLLMProvider().generate_response(llm_request)
        return type(fallback)(
            response_text=fallback.response_text,
            provider_name=fallback.provider_name,
            model_name=fallback.model_name,
            usage=fallback.usage,
            warnings=fallback.warnings + response.warnings,
            errors=response.errors,
            tool_calls=fallback.tool_calls,
            tool_results=fallback.tool_results,
            raw_provider_metadata={
                **fallback.raw_provider_metadata,
                "fallback_provider": fallback.provider_name,
                "primary_provider": response.provider_name,
            },
            metadata={
                **fallback.metadata,
                "fallback_from": response.provider_name,
            },
        )

    def _build_llm_request(
        self,
        *,
        request: CreatorAgentRequest,
        intent: CreatorAgentIntent,
        context: CreatorAgentContext,
        sources: tuple[CreatorAgentSource, ...],
        actions: tuple[CreatorAgentRecommendedAction, ...],
        proposals: tuple[CreatorAgentActionProposal, ...],
        reasoning: tuple[str, ...],
        evidence: tuple[CreatorAgentEvidence, ...],
        confidence_explanation: str,
        rationale: tuple[str, ...],
        follow_ups: tuple[str, ...],
        related_areas: tuple[str, ...],
        warnings: tuple[str, ...],
        limitations: tuple[str, ...],
    ) -> LLMRequest:
        structured_context = {
            "intent": intent.value,
            "sources": tuple(source.name for source in sources),
            "source_summaries": tuple(source.summary for source in sources),
            "tool_results": self._llm_tool_result_summary(context),
            "recommended_actions": tuple(action.title for action in actions),
            "action_proposals": tuple(proposal.title for proposal in proposals),
            "business_reasoning": reasoning,
            "supporting_evidence": tuple(
                {
                    "source": item.source,
                    "summary": item.summary,
                    "evidence_type": item.evidence_type,
                    "confidence": item.confidence,
                }
                for item in evidence
            ),
            "confidence_explanation": confidence_explanation,
            "recommendation_rationale": rationale,
            "suggested_follow_up_questions": follow_ups,
            "related_business_areas": related_areas,
            "warnings": warnings,
            "limitations": limitations,
            "read_only": True,
            "runtime_execution_allowed": False,
            "publishing_execution_allowed": False,
            "telegram_execution_allowed": False,
            "business_mutation_allowed": False,
        }
        conversation = self._llm_conversation(request)
        return LLMRequest(
            messages=(
                LLMMessage(
                    role="system",
                    content=(
                        "You are Creator Agent. Turn structured Creator OS "
                        "read-model context into a concise, source-backed business explanation. Do not execute "
                        "runtime actions, publish Products, mutate Customers, or "
                        "change DecisionEngine state."
                    ),
                ),
                LLMMessage(role="user", content=request.question),
            ),
            structured_context=structured_context,
            provider_name=getattr(self.llm_provider.config, "provider_name", None)
            if self.llm_provider is not None
            else None,
            model_name=getattr(self.llm_provider.config, "model_name", None)
            if self.llm_provider is not None
            else None,
            conversation=conversation,
            metadata={
                "source": "CreatorAgentService",
                "provider_neutral": True,
                "read_only": True,
            },
        )

    def _llm_conversation(self, request: CreatorAgentRequest) -> LLMConversation | None:
        raw_history = request.metadata.get("conversation_history")
        if not raw_history:
            return None
        messages: list[LLMMessage] = []
        for item in raw_history:
            if not isinstance(item, Mapping):
                continue
            role = str(item.get("role") or "")
            content = str(item.get("content") or "")
            if role in {"user", "assistant", "system"} and content:
                messages.append(LLMMessage(role=role, content=content))
        if not messages:
            return None
        return LLMConversation(
            messages=tuple(messages[-12:]),
            metadata={"source": "creator_agent_session_history"},
        )

    def _llm_tool_result_summary(
        self,
        context: CreatorAgentContext,
    ) -> tuple[Mapping[str, Any], ...]:
        if context.tool_context is None:
            return ()
        return tuple(
            {
                "tool": result.tool.name,
                "service": result.tool.metadata.get("owner", result.tool.service_name),
                "success": result.success,
                "warning": result.warning,
                "summary": result.source.summary if result.source else None,
            }
            for result in context.tool_context.results
        )

    def _content_opportunity_answer_summary(self, snapshot: Any | None) -> str:
        if snapshot is None:
            return "No Content Opportunity snapshot was available."
        top_topic = None
        topics = tuple(self._attr(snapshot, "trending_topics", ()) or ())
        if topics:
            top_topic = topics[0]
        topic_label = (
            " ".join(tuple(self._attr(top_topic, "terms", ()) or ()))
            if top_topic is not None
            else ""
        ) or (
            str(self._attr(top_topic, "topic_key", ""))
            if top_topic is not None
            else ""
        )
        summary = (
            f"There are {self._attr(snapshot, 'total_requests', 0)} demand request(s): "
            f"{self._attr(snapshot, 'matched_count', 0)} matched, "
            f"{self._attr(snapshot, 'unmatched_count', 0)} unresolved, "
            f"{self._attr(snapshot, 'repeat_request_count', 0)} repeat signal(s), "
            f"and {self._attr(snapshot, 'vip_request_count', 0)} VIP signal(s)."
        )
        if topic_label:
            summary += f" The leading topic is {topic_label}."
        resolution_ready = int(self._attr(snapshot, "resolution_ready_count", 0) or 0)
        ready_follow_ups = int(self._attr(snapshot, "ready_follow_up_count", 0) or 0)
        if resolution_ready or ready_follow_ups:
            summary += (
                f" {resolution_ready} resolution(s) and {ready_follow_ups} "
                "follow-up(s) are ready for review."
            )
        return summary

    def _headline(self, *, intent: CreatorAgentIntent, context: CreatorAgentContext) -> str:
        optimization = context.business_optimization_snapshot
        if intent is CreatorAgentIntent.DAILY_PRIORITIES:
            return "Daily priorities are based on Business Optimization and Workspace read models."
        if intent is CreatorAgentIntent.BUSINESS_HEALTH:
            health = self._attr(optimization, "health") or "UNKNOWN"
            readiness = self._attr(optimization, "revenue_readiness") or "unknown"
            return f"Business health is {self._display(health)} with revenue readiness {readiness}."
        if intent is CreatorAgentIntent.BUSINESS_OPTIMIZATION_SUMMARY:
            next_action = self._attr(optimization, "next_recommended_business_action")
            if next_action:
                return f"Business Optimization recommends: {next_action}."
            return "Business Optimization is available as the top-level business summary."
        if intent is CreatorAgentIntent.BUSINESS_LEARNING:
            return "Business Learning evidence is based on existing learning read models."
        if intent is CreatorAgentIntent.PRODUCT_RECOMMENDATION:
            return "Product recommendations are based on Product Strategy read models."
        if intent is CreatorAgentIntent.COMMERCE_RECOMMENDATION:
            return "Commerce recommendations are based on Commerce Strategy read models."
        if intent is CreatorAgentIntent.WORKSPACE_OVERVIEW:
            return "Workspace overview is based on Creator Workspace read models."
        if intent is CreatorAgentIntent.CONTENT_OPPORTUNITY:
            return "Content Opportunity answers are based on ContentOpportunityService demand intelligence."
        if intent is CreatorAgentIntent.EXPLAIN_RECOMMENDATION:
            return "This explanation is source-backed by current Creator OS read models."
        if intent is CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS:
            return "This comparison uses current Creator OS read models and evidence."
        if intent is CreatorAgentIntent.PRODUCT_ATTENTION:
            return "Product attention is based on Product Business read models."
        if intent is CreatorAgentIntent.PUBLISHING_READINESS:
            return "Publishing and media-link readiness are based on Publishing read models only."
        if intent is CreatorAgentIntent.CUSTOMER_ATTENTION:
            return "Customer attention is based on Customer Business and Business Learning read models."
        if intent is CreatorAgentIntent.TELEGRAM_FOLLOW_UP:
            return "Telegram follow-up is based on Telegram Business read models only."
        return "Creator Agent reviewed available Creator OS read models."

    def _confidence(
        self,
        *,
        intent: CreatorAgentIntent,
        sources: tuple[CreatorAgentSource, ...],
        warnings: list[str],
    ) -> float:
        if intent is CreatorAgentIntent.UNSUPPORTED:
            return 0.0
        if not sources:
            return 0.2
        confidence = min(0.95, 0.45 + (0.1 * len(sources)))
        if warnings:
            confidence -= 0.15
        return max(0.0, round(confidence, 2))

    def _action_from_any(self, action: Any, *, source: str) -> CreatorAgentRecommendedAction:
        title = (
            self._attr(action, "recommended_action")
            or self._attr(action, "recommended_next_action")
            or self._attr(action, "title")
            or self._attr(action, "action_type")
            or "Review recommendation"
        )
        detail = self._attr(action, "detail") or ""
        if not detail:
            detail = self._attr(action, "summary") or ""
        priority = self._attr(action, "priority") or "NORMAL"
        target = self._attr(action, "target")
        return CreatorAgentRecommendedAction(
            title=str(title),
            detail=str(detail),
            priority=self._display(priority),
            source=source,
            target=str(target) if target is not None else None,
            metadata={"read_only": True, "aggregation_only": True},
        )

    def _iter_attr(self, obj: Any, attr: str) -> Iterable[Any]:
        value = self._attr(obj, attr)
        if value is None:
            return ()
        if isinstance(value, (str, bytes, Mapping)):
            return ()
        try:
            return tuple(value)
        except TypeError:
            return ()

    def _source_summary(self, value: Any) -> str:
        total_requests = self._attr(value, "total_requests")
        if total_requests is not None:
            return (
                f"{total_requests} content request(s), "
                f"{self._attr(value, 'matched_count', 0)} matched, "
                f"{self._attr(value, 'unmatched_count', 0)} unmatched"
            )
        for attr in (
            "next_recommended_business_action",
            "next_recommended_action",
            "health",
            "title",
        ):
            attr_value = self._attr(value, attr)
            if attr_value:
                return self._display(attr_value)
        return value.__class__.__name__

    def _attr(self, obj: Any, attr: str, default: Any = None) -> Any:
        if obj is None:
            return default
        if isinstance(obj, Mapping):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    def _display(self, value: Any) -> str:
        if hasattr(value, "value"):
            return str(value.value)
        return str(value)

    def _compatibility(self) -> Mapping[str, Any]:
        return {
            "source": "creator_agent",
            "owner": "CreatorAgentService",
            "read_only": True,
            "provider_neutral": True,
            "presentation_orchestration_only": True,
            "owns_business_logic": False,
            "executes_telegram": False,
            "modifies_products": False,
            "modifies_customers": False,
            "modifies_publishing": False,
            "records_business_learning": False,
            "modifies_business_learning": False,
            "changes_decision_engine_behavior": False,
            "calls_external_llm": False,
            "llm_provider_optional": True,
            "default_llm_provider": "OpenAIProvider",
            "llm_fallback_provider": "NullLLMProvider",
            "hardcodes_llm_provider": False,
            "uses_tool_registry": True,
            "explainability_only": True,
            "avoids_direct_repository_access": True,
            "business_optimization_owner": "BusinessOptimizationService",
            "workspace_owner": "CreatorWorkspaceService",
            "product_business_owner": "ProductBusinessService",
            "telegram_business_owner": "TelegramBusinessService",
            "customer_business_owner": "CustomerBusinessService",
            "business_learning_owner": "BusinessLearningService",
            "publishing_owner": "PublishingService",
            "product_strategy_owner": "ProductStrategyService",
            "commerce_strategy_owner": "CommerceStrategyService",
            "content_opportunity_owner": "ContentOpportunityService",
        }
