from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models.business_optimization import (
    BusinessOptimizationHealth,
    BusinessOptimizationSnapshot,
)
from app.models.creator_agent import (
    CreatorAgentIntent,
    CreatorAgentRequest,
    CreatorAgentResponse,
    CreatorAgentToolRegistry,
)
from app.models.llm_provider import LLMResponse
from app.providers.llm.openai_provider import OpenAIProvider
from app.providers.llm.null_provider import NullLLMProvider
import app.services.creator_agent_service as creator_agent_module
from app.services.creator_agent_service import CreatorAgentService
from app.services.content_opportunity_service import ContentOpportunityService


class StubBusinessOptimizationService:
    def __init__(self) -> None:
        self.calls = 0

    def build_snapshot(self) -> BusinessOptimizationSnapshot:
        self.calls += 1
        return BusinessOptimizationSnapshot(
            health=BusinessOptimizationHealth.HEALTHY,
            revenue_readiness="ready",
            next_recommended_business_action="Publish Products awaiting Media Links",
            recommended_today_actions=(
                SimpleNamespace(
                    recommended_action="Publish Products awaiting Media Links",
                    priority="HIGH",
                    category="PUBLISHING",
                ),
            ),
            metadata={"provider_neutral": True},
        )


class StubWorkspaceService:
    def __init__(self) -> None:
        self.calls = 0

    def build_dashboard(self, *, creator_profile=None, active_account=None):
        self.calls += 1
        return SimpleNamespace(
            recommended_actions=(
                SimpleNamespace(
                    title="Review customer follow-ups",
                    detail="Workspace read model surfaced pending follow-ups.",
                    priority="MEDIUM",
                    target="Customer Workspace",
                ),
            )
        )


class StubReadModelService:
    def __init__(self, snapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0
        self.mutated = False

    def build_snapshot(self, **kwargs):
        self.calls += 1
        return self.snapshot

    def mutate_customer(self):
        self.mutated = True
        raise AssertionError("Creator Agent must not mutate customer state")

    def execute_telegram(self):
        raise AssertionError("Creator Agent must not execute Telegram")

    def write_to_database(self):
        raise AssertionError("Creator Agent must not perform database writes")


class StubStrategyService:
    def __init__(self, recommendation: str) -> None:
        self.recommendation = recommendation
        self.calls = 0

    def recommend(self):
        self.calls += 1
        return SimpleNamespace(
            recommendation=self.recommendation,
            next_recommended_action=self.recommendation,
        )


class StubPublishingService:
    def __init__(self) -> None:
        self.list_calls = 0
        self.mutation_calls = 0

    def list_publishing_queue_items(self):
        self.list_calls += 1
        return (
            SimpleNamespace(
                status="WAITING_MEDIA_LINK",
                product_id="product-1",
            ),
        )

    def build_publishing_queue_summary(self, items):
        return SimpleNamespace(
            waiting_media_link_count=len(items),
            next_recommended_action="Complete Media Links",
        )

    def create_publishing_job(self, **kwargs):
        self.mutation_calls += 1
        raise AssertionError("Creator Agent must not create publishing jobs")

    def upload_asset_media_item(self, **kwargs):
        self.mutation_calls += 1
        raise AssertionError("Creator Agent must not upload media")

    def record_publishing_job_media_link(self, *args, **kwargs):
        self.mutation_calls += 1
        raise AssertionError("Creator Agent must not record media links")


class StubContentOpportunityService:
    def __init__(self) -> None:
        self.calls = 0
        self.mutation_calls = 0
        self.service = ContentOpportunityService()
        self._seed()

    def _seed(self) -> None:
        self.service.resolve_content_request(
            customer_id="vip-customer",
            provider="telegram",
            provider_customer_id="telegram-vip",
            request_text="Do you have shower videos?",
            normalized_terms=("shower", "video"),
            requested_content_type="video",
            requested_format="video",
            is_vip=True,
        )
        self.service.resolve_content_request(
            customer_id="waiting-customer",
            provider="telegram",
            request_text="Any shower video content?",
            normalized_terms=("shower", "video"),
            requested_content_type="video",
            requested_format="video",
        )
        self.service.resolve_content_request(
            customer_id="matched-customer",
            provider="telegram",
            request_text="Do you have beach photos?",
            normalized_terms=("beach", "photos"),
            requested_content_type="photo",
            requested_format="photo",
            product_candidates=(
                {
                    "id": "product-beach",
                    "name": "Beach Photos",
                    "description": "Beach photo set",
                    "tags": ("beach", "photos"),
                    "published_active": True,
                },
            ),
        )
        for resolution in self.service.resolve_opportunities_for_product(
            {
                "id": "product-shower",
                "name": "Shower Videos",
                "description": "New shower video set",
                "tags": ("shower", "video"),
            }
        ):
            self.service.create_follow_up_opportunities(resolution)

    def build_snapshot(self):
        self.calls += 1
        return self.service.build_snapshot()

    def resolve_content_request(self, **kwargs):
        self.mutation_calls += 1
        raise AssertionError("Creator Agent must not record demand")

    def resolve_opportunities_for_product(self, *args, **kwargs):
        self.mutation_calls += 1
        raise AssertionError("Creator Agent must not resolve opportunities")

    def create_follow_up_opportunities(self, *args, **kwargs):
        self.mutation_calls += 1
        raise AssertionError("Creator Agent must not create follow-ups")


class CapturingLLMProvider:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            provider_name="capture",
            model_name="capture-model",
        )
        self.requests = []

    def generate_response(self, request):
        self.requests.append(request)
        return LLMResponse(
            response_text="Captured LLM answer.",
            provider_name="capture",
            model_name="capture-model",
            metadata={"external_api_called": False},
        )


def test_creator_agent_service_exists_and_request_can_be_created() -> None:
    request = CreatorAgentRequest(
        question="What should I focus on today?",
        creator_profile_id=123,
        account_id=456,
    )
    service = CreatorAgentService(enable_llm=False)

    response = service.answer(request)

    assert isinstance(response, CreatorAgentResponse)
    assert response.request == request
    assert response.intent == CreatorAgentIntent.DAILY_PRIORITIES
    assert response.compatibility["read_only"] is True
    assert response.compatibility["calls_external_llm"] is False
    assert response.compatibility["hardcodes_llm_provider"] is False


def test_daily_priority_questions_use_business_optimization_and_workspace_data() -> None:
    optimization = StubBusinessOptimizationService()
    workspace = StubWorkspaceService()
    service = CreatorAgentService(
        business_optimization_service=optimization,
        creator_workspace_service=workspace,
        enable_llm=False,
    )

    response = service.answer(CreatorAgentRequest(question="What are my priorities today?"))

    assert response.intent == CreatorAgentIntent.DAILY_PRIORITIES
    assert optimization.calls == 1
    assert workspace.calls == 1
    assert "Publish Products awaiting Media Links" in response.answer_text
    assert {source.name for source in response.sources} == {
        "BusinessOptimizationService",
        "CreatorWorkspaceService",
    }
    assert response.recommended_actions
    assert response.action_proposals
    assert all(proposal.requires_confirmation for proposal in response.action_proposals)


def test_creator_agent_works_with_null_llm_provider_after_tool_orchestration() -> None:
    optimization = StubBusinessOptimizationService()
    workspace = StubWorkspaceService()
    service = CreatorAgentService(
        business_optimization_service=optimization,
        creator_workspace_service=workspace,
        llm_provider=NullLLMProvider(),
    )

    response = service.answer(CreatorAgentRequest(question="What are my priorities today?"))

    assert optimization.calls == 1
    assert workspace.calls == 1
    assert response.answer_text.startswith("[null-llm] DAILY_PRIORITIES")
    assert response.metadata["llm_used"] is True
    assert response.metadata["llm_provider"] == "null"
    assert response.metadata["external_calls"] is False
    assert {source.name for source in response.sources} == {
        "BusinessOptimizationService",
        "CreatorWorkspaceService",
    }
    assert response.recommended_actions[0].title == "Publish Products awaiting Media Links"
    assert response.action_proposals[0].requires_confirmation is True


def test_creator_agent_defaults_to_openai_provider_when_configured() -> None:
    original_provider = creator_agent_module.OpenAIProvider
    try:
        creator_agent_module.OpenAIProvider = lambda: OpenAIProvider(
            client=SimpleNamespace(),
            api_key="test-key",
        )
        service = CreatorAgentService()

        assert isinstance(service.llm_provider, OpenAIProvider)
        assert service.llm_provider.is_configured is True
    finally:
        creator_agent_module.OpenAIProvider = original_provider


def test_creator_agent_default_provider_falls_back_to_null_when_openai_unavailable() -> None:
    original_provider = creator_agent_module.OpenAIProvider
    try:
        creator_agent_module.OpenAIProvider = lambda: OpenAIProvider(api_key="")
        service = CreatorAgentService()

        assert isinstance(service.llm_provider, NullLLMProvider)
    finally:
        creator_agent_module.OpenAIProvider = original_provider


def test_conversation_history_is_preserved_and_business_context_refreshes() -> None:
    optimization = StubBusinessOptimizationService()
    llm_provider = CapturingLLMProvider()
    service = CreatorAgentService(
        business_optimization_service=optimization,
        llm_provider=llm_provider,
    )
    request = CreatorAgentRequest(
        question="What should I do today?",
        metadata={
            "conversation_history": (
                {"role": "user", "content": "Earlier question"},
                {"role": "assistant", "content": "Earlier answer"},
            )
        },
    )

    service.answer(request)
    service.answer(request)

    assert optimization.calls == 2
    assert len(llm_provider.requests) == 2
    assert llm_provider.requests[0].conversation is not None
    assert llm_provider.requests[0].conversation.messages[0].content == "Earlier question"
    assert llm_provider.requests[0].structured_context["sources"] == (
        "BusinessOptimizationService",
    )
    assert "business_reasoning" in llm_provider.requests[0].structured_context
    assert "supporting_evidence" in llm_provider.requests[0].structured_context


def test_why_questions_build_source_backed_explanations() -> None:
    service = CreatorAgentService(
        business_optimization_service=StubBusinessOptimizationService(),
        product_business_service=StubReadModelService(
            SimpleNamespace(next_recommended_business_action="Review Product Business")
        ),
        business_learning_service=StubReadModelService(
            SimpleNamespace(next_recommended_action="Review learning evidence")
        ),
        product_strategy_service=StubStrategyService("Recommend premium Product"),
        commerce_strategy_service=StubStrategyService("Offer Bundle"),
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(
            question="Why was this Product recommended?",
            metadata={
                "conversation_history": (
                    {"role": "user", "content": "Recommend premium Product"},
                )
            },
        )
    )

    assert response.intent == CreatorAgentIntent.EXPLAIN_RECOMMENDATION
    assert response.business_reasoning
    assert response.supporting_evidence
    assert response.confidence_explanation
    assert response.recommendation_rationale
    assert "ProductStrategyService" in {source.name for source in response.sources}
    assert "Business Learning" in response.related_business_areas
    assert response.compatibility["explainability_only"] is True


def test_follow_up_questions_use_history_and_fresh_context() -> None:
    optimization = StubBusinessOptimizationService()
    service = CreatorAgentService(
        business_optimization_service=optimization,
        llm_provider=CapturingLLMProvider(),
    )
    request = CreatorAgentRequest(
        question="Tell me more.",
        metadata={
            "conversation_history": (
                {"role": "user", "content": "Why is business health low?"},
                {"role": "assistant", "content": "It is tied to publishing readiness."},
            )
        },
    )

    first = service.answer(request)
    second = service.answer(request)

    assert first.intent == CreatorAgentIntent.EXPLAIN_RECOMMENDATION
    assert optimization.calls == 2
    assert first.business_reasoning
    assert second.business_reasoning
    assert "Why is business health low?" in first.business_reasoning[0]


def test_comparison_questions_aggregate_multiple_business_sources() -> None:
    service = CreatorAgentService(
        product_business_service=StubReadModelService(
            SimpleNamespace(next_recommended_business_action="Prioritize Product A")
        ),
        business_learning_service=StubReadModelService(
            SimpleNamespace(next_recommended_action="Review conversion evidence")
        ),
        product_strategy_service=StubStrategyService("Bundle is stronger"),
        commerce_strategy_service=StubStrategyService("Cross-sell related Products"),
        business_optimization_service=StubBusinessOptimizationService(),
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(question="Compare these two Products. Which is better?")
    )

    assert response.intent == CreatorAgentIntent.COMPARE_BUSINESS_OPTIONS
    assert response.business_reasoning
    assert "comparison" in response.answer_text.lower()
    assert len(response.sources) >= 4
    assert response.recommended_actions
    assert "Which option has stronger evidence?" in response.suggested_follow_up_questions


def test_explainability_preserves_recommendations_and_sources() -> None:
    service = CreatorAgentService(
        customer_business_service=StubReadModelService(
            SimpleNamespace(next_recommended_action="Re-engage Customer")
        ),
        business_learning_service=StubReadModelService(
            SimpleNamespace(next_recommended_action="Review learning evidence")
        ),
        enable_llm=False,
    )

    response = service.answer(CreatorAgentRequest(question="Why is this customer at risk?"))

    assert response.intent == CreatorAgentIntent.EXPLAIN_RECOMMENDATION
    assert response.recommended_actions[0].title == "Re-engage Customer"
    assert response.recommended_actions[0].source == "CustomerBusinessService"
    assert {source.name for source in response.sources} >= {
        "CustomerBusinessService",
        "BusinessLearningService",
    }
    assert response.supporting_evidence


def test_creator_agent_preserves_warnings_and_limitations_after_llm_response() -> None:
    service = CreatorAgentService(llm_provider=NullLLMProvider())

    response = service.answer(CreatorAgentRequest(question="What is my business health?"))

    assert response.intent == CreatorAgentIntent.BUSINESS_HEALTH
    assert response.metadata["llm_used"] is True
    assert response.sources == ()
    assert "No upstream read models were available" in response.limitations[0]
    assert any("NullLLMProvider" in warning for warning in response.warnings)
    assert response.confidence == 0.2


def test_tool_registry_selects_correct_services_for_intents() -> None:
    service = CreatorAgentService(enable_llm=False)

    product_tools = service.selected_tools(CreatorAgentIntent.PRODUCT_ATTENTION)
    publishing_tools = service.selected_tools(CreatorAgentIntent.PUBLISHING_READINESS)
    telegram_tools = service.selected_tools(CreatorAgentIntent.TELEGRAM_FOLLOW_UP)
    content_tools = service.selected_tools(CreatorAgentIntent.CONTENT_OPPORTUNITY)

    assert isinstance(service.tool_registry, CreatorAgentToolRegistry)
    assert {tool.service_name for tool in product_tools} == {
        "product_business_service",
        "business_learning_service",
    }
    assert {tool.service_name for tool in publishing_tools} == {
        "publishing_service",
        "product_business_service",
    }
    assert {tool.service_name for tool in telegram_tools} == {
        "telegram_business_service",
    }
    assert {tool.service_name for tool in content_tools} == {
        "content_opportunity_service",
    }
    assert service.tool_registry.compatibility["avoids_runtime_execution"] is True
    assert service.tool_registry.compatibility["avoids_direct_repository_access"] is True


def test_multiple_services_can_be_aggregated_for_publishing_questions() -> None:
    publishing_service = StubPublishingService()
    product_service = StubReadModelService(
        SimpleNamespace(next_recommended_business_action="Review Product readiness")
    )
    service = CreatorAgentService(
        publishing_service=publishing_service,
        product_business_service=product_service,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(question="What publishing and media links need attention?")
    )

    assert response.intent == CreatorAgentIntent.PUBLISHING_READINESS
    assert product_service.calls == 1
    assert publishing_service.list_calls == 1
    assert {source.name for source in response.sources} == {
        "PublishingService",
        "ProductBusinessService",
    }
    assert response.context.tool_context is not None
    assert response.context.tool_context.metadata["tool_count"] == 2


def test_business_health_question_returns_sources_and_summary() -> None:
    service = CreatorAgentService(
        business_optimization_service=StubBusinessOptimizationService(),
        enable_llm=False,
    )

    response = service.answer(CreatorAgentRequest(question="How healthy is my business?"))

    assert response.intent == CreatorAgentIntent.BUSINESS_HEALTH
    assert "Business health is HEALTHY" in response.answer_text
    assert response.sources[0].name == "BusinessOptimizationService"
    assert response.confidence > 0


def test_product_question_uses_product_business_without_owning_product_logic() -> None:
    product_service = StubReadModelService(
        SimpleNamespace(
            product_health="NEEDS_ATTENTION",
            next_recommended_business_action="Review Product Business",
        )
    )
    service = CreatorAgentService(
        product_business_service=product_service,
        enable_llm=False,
    )

    response = service.answer(CreatorAgentRequest(question="Which products need attention?"))

    assert response.intent == CreatorAgentIntent.PRODUCT_ATTENTION
    assert product_service.calls == 1
    assert response.sources[0].name == "ProductBusinessService"
    assert response.recommended_actions[0].source == "ProductBusinessService"
    assert response.compatibility["modifies_products"] is False


def test_product_media_link_questions_do_not_execute_publishing_mutations() -> None:
    publishing_service = StubPublishingService()
    service = CreatorAgentService(
        publishing_service=publishing_service,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(question="What media links or publishing items are ready?")
    )

    assert response.intent == CreatorAgentIntent.PUBLISHING_READINESS
    assert publishing_service.list_calls == 1
    assert publishing_service.mutation_calls == 0
    assert response.sources[0].name == "PublishingService"
    assert response.compatibility["modifies_publishing"] is False


def test_business_learning_questions_route_to_business_learning_service() -> None:
    learning_service = StubReadModelService(
        SimpleNamespace(
            health="LEARNING_AVAILABLE",
            next_recommended_action="Review learning evidence",
        )
    )
    service = CreatorAgentService(
        business_learning_service=learning_service,
        enable_llm=False,
    )

    response = service.answer(CreatorAgentRequest(question="What learning evidence do we have?"))

    assert response.intent == CreatorAgentIntent.BUSINESS_LEARNING
    assert learning_service.calls == 1
    assert response.sources[0].name == "BusinessLearningService"
    assert response.compatibility["modifies_business_learning"] is False


def test_product_recommendation_questions_route_to_product_strategy_service() -> None:
    product_strategy_service = StubStrategyService("Recommend premium Product")
    service = CreatorAgentService(
        product_strategy_service=product_strategy_service,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(question="What product should I recommend next?")
    )

    assert response.intent == CreatorAgentIntent.PRODUCT_RECOMMENDATION
    assert product_strategy_service.calls == 1
    assert response.sources[0].name == "ProductStrategyService"
    assert response.compatibility["product_strategy_owner"] == "ProductStrategyService"


def test_commerce_recommendation_questions_route_to_commerce_strategy_service() -> None:
    commerce_strategy_service = StubStrategyService("Delay selling")
    service = CreatorAgentService(
        commerce_strategy_service=commerce_strategy_service,
        enable_llm=False,
    )

    response = service.answer(CreatorAgentRequest(question="What commerce strategy should I use?"))

    assert response.intent == CreatorAgentIntent.COMMERCE_RECOMMENDATION
    assert commerce_strategy_service.calls == 1
    assert response.sources[0].name == "CommerceStrategyService"
    assert response.compatibility["commerce_strategy_owner"] == "CommerceStrategyService"


def test_workspace_overview_routes_to_creator_workspace_service() -> None:
    workspace = StubWorkspaceService()
    service = CreatorAgentService(
        creator_workspace_service=workspace,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(
            question="Show me the workspace overview",
            creator_profile_id=1,
            account_id=2,
        )
    )

    assert response.intent == CreatorAgentIntent.WORKSPACE_OVERVIEW
    assert workspace.calls == 1
    assert response.sources[0].name == "CreatorWorkspaceService"


def test_customer_questions_do_not_mutate_customer_state() -> None:
    customer_service = StubReadModelService(
        SimpleNamespace(
            customer_health="AT_RISK",
            next_recommended_action="Re-engage Customer",
        )
    )
    service = CreatorAgentService(
        customer_business_service=customer_service,
        enable_llm=False,
    )

    response = service.answer(CreatorAgentRequest(question="Which customers need attention?"))

    assert response.intent == CreatorAgentIntent.CUSTOMER_ATTENTION
    assert customer_service.calls == 1
    assert customer_service.mutated is False
    assert response.sources[0].name == "CustomerBusinessService"
    assert response.compatibility["modifies_customers"] is False


def test_telegram_questions_do_not_call_runtime_execution() -> None:
    telegram_service = StubReadModelService(
        SimpleNamespace(
            business_health="HEALTHY",
            next_recommended_business_action="Follow Up",
        )
    )
    service = CreatorAgentService(
        telegram_business_service=telegram_service,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(question="Who needs Telegram follow-up?", provider="telegram")
    )

    assert response.intent == CreatorAgentIntent.TELEGRAM_FOLLOW_UP
    assert telegram_service.calls == 1
    assert response.sources[0].name == "TelegramBusinessService"
    assert response.compatibility["executes_telegram"] is False
    assert response.compatibility["avoids_direct_repository_access"] is True


def test_creator_agent_answers_content_demand_questions() -> None:
    content_service = StubContentOpportunityService()
    service = CreatorAgentService(
        content_opportunity_service=content_service,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(question="What content are customers asking for?")
    )

    assert response.intent == CreatorAgentIntent.CONTENT_OPPORTUNITY
    assert content_service.calls == 1
    assert content_service.mutation_calls == 0
    assert response.context.content_opportunity_snapshot is not None
    assert response.sources[0].name == "ContentOpportunityService"
    assert "3 demand request" in response.answer_text
    assert "shower video" in response.answer_text
    assert response.compatibility["content_opportunity_owner"] == (
        "ContentOpportunityService"
    )


def test_creator_agent_answers_content_follow_up_questions() -> None:
    content_service = StubContentOpportunityService()
    service = CreatorAgentService(
        content_opportunity_service=content_service,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(question="Which customers are waiting for content?")
    )

    assert response.intent == CreatorAgentIntent.CONTENT_OPPORTUNITY
    assert any(
        item.evidence_type == "content_follow_up"
        and "waiting-customer" in item.summary
        for item in response.supporting_evidence
    )
    assert any(
        "follow-up" in item.summary.lower()
        for item in response.supporting_evidence
    )
    assert content_service.mutation_calls == 0


def test_creator_agent_explains_content_recommendations() -> None:
    content_service = StubContentOpportunityService()
    service = CreatorAgentService(
        content_opportunity_service=content_service,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(
            question="Why does this shower video recommendation exist?"
        )
    )

    assert response.intent == CreatorAgentIntent.CONTENT_OPPORTUNITY
    assert response.business_reasoning
    assert any(
        item.evidence_type in {
            "content_demand_summary",
            "trending_content_topic",
        }
        and "VIP" in item.summary
        for item in response.supporting_evidence
    )
    assert any(
        action.source == "ContentOpportunityService"
        for action in response.recommended_actions
    )


def test_creator_agent_explains_matched_products() -> None:
    content_service = StubContentOpportunityService()
    service = CreatorAgentService(
        content_opportunity_service=content_service,
        enable_llm=False,
    )

    response = service.answer(
        CreatorAgentRequest(
            question="Which Products satisfy previous customer demand?"
        )
    )

    assert response.intent == CreatorAgentIntent.CONTENT_OPPORTUNITY
    assert any(
        item.evidence_type == "content_resolution"
        and "product-shower" in item.summary
        for item in response.supporting_evidence
    )
    assert any(
        "matched" in item.summary
        for item in response.supporting_evidence
    )


def test_unsupported_questions_return_safe_fallback() -> None:
    service = CreatorAgentService(enable_llm=False)

    response = service.answer(CreatorAgentRequest(question="Write a poem about the moon"))

    assert response.intent == CreatorAgentIntent.UNSUPPORTED
    assert "do not have a supported read model" in response.answer_text
    assert response.confidence == 0.0
    assert response.sources == ()
    assert response.action_proposals == ()
    assert response.limitations


def test_existing_services_remain_owners_of_business_logic() -> None:
    response = CreatorAgentService(
        business_optimization_service=StubBusinessOptimizationService(),
        product_business_service=StubReadModelService(
            SimpleNamespace(next_recommended_business_action="Review Product Business")
        ),
        customer_business_service=StubReadModelService(
            SimpleNamespace(next_recommended_action="Continue Relationship")
        ),
        enable_llm=False,
    ).answer(CreatorAgentRequest(question="What should I focus on today?"))

    assert response.compatibility["owns_business_logic"] is False
    assert response.compatibility["business_optimization_owner"] == (
        "BusinessOptimizationService"
    )
    assert response.compatibility["product_business_owner"] == "ProductBusinessService"
    assert response.compatibility["customer_business_owner"] == "CustomerBusinessService"
    assert response.compatibility["content_opportunity_owner"] == (
        "ContentOpportunityService"
    )
    assert all(action.metadata["read_only"] for action in response.recommended_actions)


def test_missing_upstream_services_return_limitations_not_errors() -> None:
    response = CreatorAgentService(enable_llm=False).answer(
        CreatorAgentRequest(question="What is my business health?")
    )

    assert response.intent == CreatorAgentIntent.BUSINESS_HEALTH
    assert response.sources == ()
    assert response.limitations
    assert response.confidence == 0.2


class CreatorAgentServiceTest(unittest.TestCase):
    def test_creator_agent_service_exists_and_request_can_be_created(self) -> None:
        test_creator_agent_service_exists_and_request_can_be_created()

    def test_daily_priority_questions_use_business_optimization_and_workspace_data(
        self,
    ) -> None:
        test_daily_priority_questions_use_business_optimization_and_workspace_data()

    def test_creator_agent_works_with_null_llm_provider_after_tool_orchestration(
        self,
    ) -> None:
        test_creator_agent_works_with_null_llm_provider_after_tool_orchestration()

    def test_creator_agent_defaults_to_openai_provider_when_configured(self) -> None:
        test_creator_agent_defaults_to_openai_provider_when_configured()

    def test_creator_agent_default_provider_falls_back_to_null_when_openai_unavailable(
        self,
    ) -> None:
        test_creator_agent_default_provider_falls_back_to_null_when_openai_unavailable()

    def test_conversation_history_is_preserved_and_business_context_refreshes(self) -> None:
        test_conversation_history_is_preserved_and_business_context_refreshes()

    def test_why_questions_build_source_backed_explanations(self) -> None:
        test_why_questions_build_source_backed_explanations()

    def test_follow_up_questions_use_history_and_fresh_context(self) -> None:
        test_follow_up_questions_use_history_and_fresh_context()

    def test_comparison_questions_aggregate_multiple_business_sources(self) -> None:
        test_comparison_questions_aggregate_multiple_business_sources()

    def test_explainability_preserves_recommendations_and_sources(self) -> None:
        test_explainability_preserves_recommendations_and_sources()

    def test_creator_agent_preserves_warnings_and_limitations_after_llm_response(
        self,
    ) -> None:
        test_creator_agent_preserves_warnings_and_limitations_after_llm_response()

    def test_tool_registry_selects_correct_services_for_intents(self) -> None:
        test_tool_registry_selects_correct_services_for_intents()

    def test_multiple_services_can_be_aggregated_for_publishing_questions(self) -> None:
        test_multiple_services_can_be_aggregated_for_publishing_questions()

    def test_business_health_question_returns_sources_and_summary(self) -> None:
        test_business_health_question_returns_sources_and_summary()

    def test_product_question_uses_product_business_without_owning_product_logic(
        self,
    ) -> None:
        test_product_question_uses_product_business_without_owning_product_logic()

    def test_product_media_link_questions_do_not_execute_publishing_mutations(
        self,
    ) -> None:
        test_product_media_link_questions_do_not_execute_publishing_mutations()

    def test_business_learning_questions_route_to_business_learning_service(self) -> None:
        test_business_learning_questions_route_to_business_learning_service()

    def test_product_recommendation_questions_route_to_product_strategy_service(
        self,
    ) -> None:
        test_product_recommendation_questions_route_to_product_strategy_service()

    def test_commerce_recommendation_questions_route_to_commerce_strategy_service(
        self,
    ) -> None:
        test_commerce_recommendation_questions_route_to_commerce_strategy_service()

    def test_workspace_overview_routes_to_creator_workspace_service(self) -> None:
        test_workspace_overview_routes_to_creator_workspace_service()

    def test_customer_questions_do_not_mutate_customer_state(self) -> None:
        test_customer_questions_do_not_mutate_customer_state()

    def test_telegram_questions_do_not_call_runtime_execution(self) -> None:
        test_telegram_questions_do_not_call_runtime_execution()

    def test_creator_agent_answers_content_demand_questions(self) -> None:
        test_creator_agent_answers_content_demand_questions()

    def test_creator_agent_answers_content_follow_up_questions(self) -> None:
        test_creator_agent_answers_content_follow_up_questions()

    def test_creator_agent_explains_content_recommendations(self) -> None:
        test_creator_agent_explains_content_recommendations()

    def test_creator_agent_explains_matched_products(self) -> None:
        test_creator_agent_explains_matched_products()

    def test_unsupported_questions_return_safe_fallback(self) -> None:
        test_unsupported_questions_return_safe_fallback()

    def test_existing_services_remain_owners_of_business_logic(self) -> None:
        test_existing_services_remain_owners_of_business_logic()

    def test_missing_upstream_services_return_limitations_not_errors(self) -> None:
        test_missing_upstream_services_return_limitations_not_errors()
