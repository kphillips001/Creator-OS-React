"""Developer Agent advisory architecture orchestration service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.developer_agent import (
    DeveloperAgentContext,
    DeveloperAgentEvidence,
    DeveloperAgentIntent,
    DeveloperAgentRecommendation,
    DeveloperAgentRequest,
    DeveloperAgentResponse,
    DeveloperAgentSource,
    DeveloperAgentTool,
    DeveloperAgentToolRegistry,
    DeveloperAgentToolRequest,
    DeveloperAgentToolResult,
)
from app.models.llm_provider import LLMConversation, LLMMessage, LLMRequest
from app.providers.llm.null_provider import NullLLMProvider
from app.providers.llm.openai_provider import OpenAIProvider

if TYPE_CHECKING:
    from app.providers.llm.base import BaseLLMProvider


class DeveloperAgentService:
    """Answer software architecture questions using read-only metadata only.

    Developer Agent is advisory. It does not execute commands, run tests, edit
    files, create commits, mutate business state, or call runtime services.
    """

    def __init__(
        self,
        *,
        tool_registry: DeveloperAgentToolRegistry | None = None,
        creator_os_certification_service: Any | None = None,
        runtime_control_service: Any | None = None,
        llm_provider: "BaseLLMProvider | None" = None,
        enable_llm: bool = True,
    ) -> None:
        self.tool_registry = tool_registry or self.default_tool_registry()
        self.creator_os_certification_service = creator_os_certification_service
        self.runtime_control_service = runtime_control_service
        self.llm_provider = llm_provider if llm_provider is not None else (
            self._default_llm_provider() if enable_llm else None
        )

    def answer(self, request: DeveloperAgentRequest) -> DeveloperAgentResponse:
        intent = self.resolve_intent(request.question)
        warnings: list[str] = []
        limitations: list[str] = []
        runtime_change = self._apply_runtime_change_if_confirmed(
            request=request,
            intent=intent,
            limitations=limitations,
        )
        tool_requests = tuple(
            DeveloperAgentToolRequest(
                tool=tool,
                request=request,
                intent=intent,
                metadata={"read_only": True},
            )
            for tool in self.tool_registry.tools_for_intent(intent)
        )
        tool_results = tuple(
            self._run_tool(tool_request=tool_request)
            for tool_request in tool_requests
        )
        context = self._context(intent=intent, tool_results=tool_results)
        sources = tuple(
            result.source for result in tool_results if result.source is not None
        )
        evidence = self._evidence(tool_results)
        recommendations = self._recommendations(intent=intent, context=context)
        if intent is DeveloperAgentIntent.UNSUPPORTED:
            limitations.append(
                "Developer Agent can advise on Creator OS architecture, roadmap, "
                "validation, testing, risk, and release readiness. This request is "
                "outside the current foundation scope."
            )
        if not sources and intent is not DeveloperAgentIntent.UNSUPPORTED:
            limitations.append("No read-only architecture sources were selected.")

        answer_text = self._answer_text(
            intent=intent,
            sources=sources,
            recommendations=recommendations,
            limitations=tuple(limitations),
        )
        llm_response = None
        if self.llm_provider is not None:
            llm_response = self._generate_llm_response(
                request=request,
                intent=intent,
                context=context,
                sources=sources,
                evidence=evidence,
                recommendations=recommendations,
                warnings=tuple(warnings),
                limitations=tuple(limitations),
            )
            if llm_response is not None and llm_response.response_text:
                answer_text = llm_response.response_text
                warnings.extend(llm_response.warnings)
                limitations.extend(llm_response.errors)

        return DeveloperAgentResponse(
            request=request,
            intent=intent,
            answer_text=answer_text,
            context=context,
            sources=sources,
            evidence=evidence,
            recommendations=recommendations,
            warnings=tuple(warnings),
            limitations=tuple(limitations),
            confidence=self._confidence(sources=sources, warnings=warnings),
            suggested_follow_up_questions=self._follow_ups(intent),
            compatibility=self._compatibility(),
            metadata={
                "source": "developer_agent",
                "provider_neutral": True,
                "llm_used": llm_response is not None,
                "llm_provider": llm_response.provider_name if llm_response else None,
                "llm_model": llm_response.model_name if llm_response else None,
                "executes_commands": False,
                "modifies_files": False,
                "runtime_change": runtime_change,
            },
        )

    def handle(self, request: DeveloperAgentRequest) -> DeveloperAgentResponse:
        return self.answer(request)

    def _default_llm_provider(self):
        provider = OpenAIProvider()
        if provider.is_configured:
            return provider
        return NullLLMProvider()

    def resolve_intent(self, question: str) -> DeveloperAgentIntent:
        text = question.lower()
        if not text.strip():
            return DeveloperAgentIntent.UNSUPPORTED
        if any(word in text for word in ("audit", "architecture", "review")):
            return DeveloperAgentIntent.ARCHITECTURE_AUDIT
        if any(word in text for word in ("roadmap", "next", "build")):
            return DeveloperAgentIntent.ROADMAP_GUIDANCE
        if any(word in text for word in ("compatibility", "boundary", "preserve")):
            return DeveloperAgentIntent.COMPATIBILITY_VALIDATION
        if "creator os" in text and any(
            word in text for word in ("certification", "certify", "v1.0", "v1")
        ):
            return DeveloperAgentIntent.CREATOR_OS_CERTIFICATION
        if "creator os" in text and any(
            phrase in text
            for phrase in (
                "running",
                "runtime",
                "start",
                "stop",
                "observe",
                "offline",
            )
        ):
            return DeveloperAgentIntent.RUNTIME_CONTROL
        if any(
            phrase in text
            for phrase in (
                "switch to observe",
                "observe mode",
                "stop creator",
                "start creator",
                "runtime control",
            )
        ):
            return DeveloperAgentIntent.RUNTIME_CONTROL
        if any(word in text for word in ("ready", "release", "ship")):
            return DeveloperAgentIntent.RELEASE_READINESS
        if any(word in text for word in ("implement", "plan", "codex command", "command")):
            return DeveloperAgentIntent.IMPLEMENTATION_PLANNING
        if any(word in text for word in ("test", "tests", "validation")):
            return DeveloperAgentIntent.TEST_STRATEGY
        if any(word in text for word in ("risk", "risks", "debt")):
            return DeveloperAgentIntent.RISK_ANALYSIS
        if any(word in text for word in ("explain", "how does", "codebase")):
            return DeveloperAgentIntent.CODEBASE_EXPLANATION
        return DeveloperAgentIntent.UNSUPPORTED

    @classmethod
    def default_tool_registry(cls) -> DeveloperAgentToolRegistry:
        compatibility = {
            "read_only": True,
            "provider_neutral": True,
            "avoids_command_execution": True,
            "avoids_file_mutation": True,
            "avoids_runtime_mutation": True,
            "avoids_business_mutation": True,
        }
        return DeveloperAgentToolRegistry(
            tools=(
                DeveloperAgentTool(
                    name="architecture_metadata",
                    source_name="Creator OS Architecture Metadata",
                    context_field="architecture_context",
                    intents=(
                        DeveloperAgentIntent.ARCHITECTURE_AUDIT,
                        DeveloperAgentIntent.CODEBASE_EXPLANATION,
                        DeveloperAgentIntent.IMPLEMENTATION_PLANNING,
                    ),
                ),
                DeveloperAgentTool(
                    name="roadmap_metadata",
                    source_name="Creator OS Phase Roadmap",
                    context_field="roadmap_context",
                    intents=(
                        DeveloperAgentIntent.ROADMAP_GUIDANCE,
                        DeveloperAgentIntent.IMPLEMENTATION_PLANNING,
                        DeveloperAgentIntent.RELEASE_READINESS,
                    ),
                ),
                DeveloperAgentTool(
                    name="compatibility_metadata",
                    source_name="Creator OS Compatibility Boundaries",
                    context_field="compatibility_context",
                    intents=(
                        DeveloperAgentIntent.COMPATIBILITY_VALIDATION,
                        DeveloperAgentIntent.RISK_ANALYSIS,
                        DeveloperAgentIntent.RELEASE_READINESS,
                    ),
                ),
                DeveloperAgentTool(
                    name="test_inventory_metadata",
                    source_name="Creator OS Test Inventory",
                    context_field="test_context",
                    intents=(
                        DeveloperAgentIntent.TEST_STRATEGY,
                        DeveloperAgentIntent.RELEASE_READINESS,
                    ),
                ),
                DeveloperAgentTool(
                    name="creator_os_certification_report",
                    source_name="Creator OS v1.0 Certification",
                    context_field="release_context",
                    intents=(DeveloperAgentIntent.CREATOR_OS_CERTIFICATION,),
                ),
                DeveloperAgentTool(
                    name="runtime_control_status",
                    source_name="Creator OS Runtime Control",
                    context_field="release_context",
                    intents=(DeveloperAgentIntent.RUNTIME_CONTROL,),
                ),
            ),
            compatibility=compatibility,
        )

    def _run_tool(
        self,
        *,
        tool_request: DeveloperAgentToolRequest,
    ) -> DeveloperAgentToolResult:
        tool = tool_request.tool
        result = self._tool_payload(tool.name)
        return DeveloperAgentToolResult(
            tool=tool,
            success=True,
            result=result,
            source=DeveloperAgentSource(
                source_type="read_only_metadata",
                name=tool.source_name,
                summary=str(result.get("summary", tool.source_name)),
                confidence=0.85,
                metadata={
                    "tool": tool.name,
                    "read_only": True,
                    "status": result.get("status"),
                    "mode": result.get("mode"),
                },
            ),
            metadata={"read_only": True},
        )

    def _tool_payload(self, tool_name: str) -> dict[str, Any]:
        payloads = {
            "architecture_metadata": {
                "summary": "Creator OS separates presentation, AI orchestration, business read models, runtime execution, and provider integrations.",
                "known_surfaces": (
                    "Creator HQ",
                    "Creator Agent",
                    "Business Optimization",
                    "Customer Business",
                    "Telegram Business",
                    "Product Business",
                    "Publishing",
                ),
            },
            "roadmap_metadata": {
                "summary": "Phase 3.7 is evolving Creator HQ and AI assistant surfaces while preserving runtime/business ownership.",
                "recent_phases": (
                    "Creator HQ shell",
                    "Business Overview dashboard",
                    "Developer Agent foundation",
                ),
            },
            "compatibility_metadata": {
                "summary": "DecisionEngine, Telegram runtime, Publishing execution, and business domains remain separate ownership boundaries.",
                "protected_boundaries": (
                    "DecisionEngine",
                    "Telegram runtime",
                    "Publishing execution",
                    "Product mutation",
                    "Customer mutation",
                    "Business Learning writes",
                ),
            },
            "test_inventory_metadata": {
                "summary": "Creator Agent, LLM provider, Creator HQ navigation, and Workspace integration tests cover the reusable AI/HQ surface.",
                "known_suites": (
                    "app.test_creator_agent_service",
                    "app.test_creator_agent_workspace",
                    "app.test_llm_provider",
                    "app.test_creator_workspace_navigation",
                    "app.test_creator_workspace_integration",
                ),
            },
        }
        if tool_name == "creator_os_certification_report":
            report = self._creator_os_certification_payload()
            if report:
                return report
        if tool_name == "runtime_control_status":
            return self._runtime_control_payload()
        return dict(payloads.get(tool_name, {"summary": "No metadata available."}))

    def _context(
        self,
        *,
        intent: DeveloperAgentIntent,
        tool_results: tuple[DeveloperAgentToolResult, ...],
    ) -> DeveloperAgentContext:
        context_by_field: dict[str, Mapping[str, Any]] = {}
        for result in tool_results:
            if isinstance(result.result, Mapping):
                context_by_field[result.tool.context_field] = result.result
        return DeveloperAgentContext(
            intent=intent,
            architecture_context=context_by_field.get("architecture_context", {}),
            roadmap_context=context_by_field.get("roadmap_context", {}),
            compatibility_context=context_by_field.get("compatibility_context", {}),
            test_context=context_by_field.get("test_context", {}),
            release_context={
                "summary": "Release readiness is advisory until tests are run by the user/Codex workflow outside Developer Agent."
            },
            tool_results=tool_results,
            metadata={"read_only": True},
        )

    def _evidence(
        self,
        tool_results: tuple[DeveloperAgentToolResult, ...],
    ) -> tuple[DeveloperAgentEvidence, ...]:
        return tuple(
            DeveloperAgentEvidence(
                source=result.tool.source_name,
                summary=str(self._read(result.result, "summary", "Read-only source available.")),
                confidence=0.85 if result.success else 0.25,
                metadata={"tool": result.tool.name},
            )
            for result in tool_results
        )

    def _recommendations(
        self,
        *,
        intent: DeveloperAgentIntent,
        context: DeveloperAgentContext,
    ) -> tuple[DeveloperAgentRecommendation, ...]:
        mapping = {
            DeveloperAgentIntent.ARCHITECTURE_AUDIT: "Validate ownership boundaries before implementation.",
            DeveloperAgentIntent.ROADMAP_GUIDANCE: "Implement the next phase as a narrow, reversible architecture step.",
            DeveloperAgentIntent.COMPATIBILITY_VALIDATION: "Preserve existing routes, models, and service contracts where possible.",
            DeveloperAgentIntent.IMPLEMENTATION_PLANNING: "Create models, service, page, tests, then run affected suites outside Developer Agent.",
            DeveloperAgentIntent.TEST_STRATEGY: "Run focused unit tests plus directly affected integration tests.",
            DeveloperAgentIntent.RISK_ANALYSIS: "Document compatibility debt and avoid runtime mutations.",
            DeveloperAgentIntent.CODEBASE_EXPLANATION: "Trace UI to service to model ownership boundaries.",
            DeveloperAgentIntent.RELEASE_READINESS: "Confirm tests and architecture validation before release.",
            DeveloperAgentIntent.CREATOR_OS_CERTIFICATION: "Review the Creator OS v1.0 certification report.",
            DeveloperAgentIntent.RUNTIME_CONTROL: "Review Creator OS Runtime Control state before changing mode.",
        }
        title = mapping.get(intent)
        if not title:
            return ()
        return (
            DeveloperAgentRecommendation(
                title=title,
                detail="Advisory only. Developer Agent does not execute commands or modify files.",
                priority="HIGH" if intent in {
                    DeveloperAgentIntent.COMPATIBILITY_VALIDATION,
                    DeveloperAgentIntent.RELEASE_READINESS,
                    DeveloperAgentIntent.RISK_ANALYSIS,
                } else "NORMAL",
                metadata={"read_only": True, "intent": intent.value},
            ),
        )

    def _answer_text(
        self,
        *,
        intent: DeveloperAgentIntent,
        sources: tuple[DeveloperAgentSource, ...],
        recommendations: tuple[DeveloperAgentRecommendation, ...],
        limitations: tuple[str, ...],
    ) -> str:
        if intent is DeveloperAgentIntent.UNSUPPORTED:
            return "Developer Agent can advise on Creator OS architecture and development, but this request is outside the current scope."
        if intent is DeveloperAgentIntent.CREATOR_OS_CERTIFICATION:
            status = "UNKNOWN"
            for source in sources:
                if source.name == "Creator OS v1.0 Certification":
                    status = str(source.metadata.get("status") or status)
            return f"Developer Agent reviewed Creator OS v1.0 Certification. Certification status: {status}."
        if intent is DeveloperAgentIntent.RUNTIME_CONTROL:
            status = "UNKNOWN"
            mode = "UNKNOWN"
            for source in sources:
                if source.name == "Creator OS Runtime Control":
                    status = str(source.metadata.get("status") or status)
                    mode = str(source.metadata.get("mode") or mode)
            if limitations:
                return f"Creator OS Runtime is {status} in {mode} mode. {limitations[0]}"
            return f"Creator OS Runtime is {status} in {mode} mode."
        source_text = ", ".join(source.name for source in sources) or "no sources"
        recommendation = recommendations[0].title if recommendations else "Review architecture context."
        if limitations:
            return f"Developer Agent reviewed {source_text}. {limitations[0]}"
        return f"Developer Agent reviewed {source_text}. Recommended next step: {recommendation}"

    def _apply_runtime_change_if_confirmed(
        self,
        *,
        request: DeveloperAgentRequest,
        intent: DeveloperAgentIntent,
        limitations: list[str],
    ) -> str | None:
        if intent is not DeveloperAgentIntent.RUNTIME_CONTROL:
            return None
        action = self._requested_runtime_action(request.question)
        if action is None:
            return None
        if not request.metadata.get("confirm_runtime_change"):
            limitations.append(
                "Runtime changes are read-only until the creator confirms the action."
            )
            return None
        service = self.runtime_control_service
        method = getattr(service, action, None)
        if not callable(method):
            limitations.append("RuntimeControlService is unavailable.")
            return None
        method(creator_profile_id=request.metadata.get("creator_profile_id"))
        return action

    @staticmethod
    def _requested_runtime_action(question: str) -> str | None:
        text = question.lower()
        if "observe" in text:
            return "observe"
        if "stop" in text or "offline" in text:
            return "stop"
        if "start" in text or "live" in text:
            return "start"
        return None

    def _runtime_control_payload(self) -> dict[str, Any]:
        service = self.runtime_control_service
        build_snapshot = getattr(service, "build_snapshot", None)
        if not callable(build_snapshot):
            return {
                "summary": "Creator OS Runtime Control service is unavailable.",
                "status": "UNKNOWN",
                "mode": "UNKNOWN",
            }
        snapshot = build_snapshot()
        status = getattr(getattr(snapshot, "runtime_status", None), "value", "UNKNOWN")
        mode = getattr(getattr(snapshot, "current_mode", None), "value", "UNKNOWN")
        return {
            "summary": f"Creator OS Runtime is {status} in {mode} mode.",
            "status": status,
            "mode": mode,
            "active_conversations": getattr(snapshot, "active_conversations", 0),
            "pending_deliveries": getattr(snapshot, "pending_deliveries", 0),
            "pending_offers": getattr(snapshot, "pending_offers", 0),
            "read_only": True,
        }

    def _creator_os_certification_payload(self) -> dict[str, Any]:
        service = self.creator_os_certification_service
        certify = getattr(service, "certify", None)
        if not callable(certify):
            return {
                "summary": "Creator OS v1.0 certification service is unavailable.",
                "status": "FAIL",
                "missing_items": ("CreatorOSCertificationService is unavailable.",),
            }
        report = certify()
        sections = tuple(getattr(report, "sections", ()) or ())
        return {
            "summary": "Creator OS v1.0 certification report is available.",
            "status": getattr(getattr(report, "status", None), "value", "UNKNOWN"),
            "sections": tuple(
                {
                    "name": section.name,
                    "status": section.status.value,
                    "missing_items": section.missing_items,
                }
                for section in sections
            ),
            "missing_items": tuple(getattr(report, "missing_items", ()) or ()),
            "read_only": True,
        }

    def _generate_llm_response(
        self,
        *,
        request: DeveloperAgentRequest,
        intent: DeveloperAgentIntent,
        context: DeveloperAgentContext,
        sources: tuple[DeveloperAgentSource, ...],
        evidence: tuple[DeveloperAgentEvidence, ...],
        recommendations: tuple[DeveloperAgentRecommendation, ...],
        warnings: tuple[str, ...],
        limitations: tuple[str, ...],
    ):
        llm_request = LLMRequest(
            messages=(
                LLMMessage(
                    role="system",
                    content=(
                        "You are Developer Agent, an advisory software architect for Creator OS. "
                        "Use only structured read-only context. Do not execute commands, modify files, "
                        "mutate business state, run tests, or imply that actions were performed."
                    ),
                ),
                LLMMessage(role="user", content=request.question),
            ),
            structured_context={
                "intent": intent.value,
                "sources": tuple(source.name for source in sources),
                "evidence": tuple(item.summary for item in evidence),
                "recommendations": tuple(item.title for item in recommendations),
                "warnings": warnings,
                "limitations": limitations,
                "read_only": True,
                "command_execution_allowed": False,
                "file_mutation_allowed": False,
                "runtime_mutation_allowed": False,
                "business_mutation_allowed": False,
                "context": {
                    "architecture": dict(context.architecture_context),
                    "roadmap": dict(context.roadmap_context),
                    "compatibility": dict(context.compatibility_context),
                    "tests": dict(context.test_context),
                    "release": dict(context.release_context),
                },
            },
            provider_name=getattr(self.llm_provider.config, "provider_name", None)
            if self.llm_provider is not None
            else None,
            model_name=getattr(self.llm_provider.config, "model_name", None)
            if self.llm_provider is not None
            else None,
            conversation=self._llm_conversation(request),
            metadata={"source": "DeveloperAgentService", "read_only": True},
        )
        try:
            response = self.llm_provider.generate_response(llm_request)
        except Exception:
            return None
        if response.response_text:
            return response
        return NullLLMProvider().generate_response(llm_request)

    def _llm_conversation(self, request: DeveloperAgentRequest) -> LLMConversation | None:
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
        return LLMConversation(messages=tuple(messages[-12:]))

    def _confidence(
        self,
        *,
        sources: tuple[DeveloperAgentSource, ...],
        warnings: list[str],
    ) -> float:
        if not sources:
            return 0.25
        confidence = min(0.95, 0.55 + (0.1 * len(sources)))
        if warnings:
            confidence -= 0.1
        return max(0.0, round(confidence, 2))

    def _follow_ups(
        self,
        intent: DeveloperAgentIntent,
    ) -> tuple[str, ...]:
        if intent is DeveloperAgentIntent.TEST_STRATEGY:
            return ("Which tests are highest risk?", "What should be mocked?")
        if intent is DeveloperAgentIntent.ROADMAP_GUIDANCE:
            return ("What should we build next?", "What compatibility debt remains?")
        if intent is DeveloperAgentIntent.UNSUPPORTED:
            return ("Review the architecture.", "What are the risks?")
        return (
            "What technical debt remains?",
            "Is this implementation ready?",
            "What tests should I run?",
        )

    @staticmethod
    def _read(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, Mapping):
            return value.get(name, default)
        return getattr(value, name, default)

    @staticmethod
    def _compatibility() -> Mapping[str, Any]:
        return {
            "source": "developer_agent",
            "owner": "DeveloperAgentService",
            "read_only": True,
            "advisory_only": True,
            "provider_neutral": True,
            "executes_commands": False,
            "runs_tests": False,
            "modifies_files": False,
            "creates_commits": False,
            "mutates_products": False,
            "mutates_customers": False,
            "mutates_publishing": False,
            "mutates_telegram": False,
            "mutates_business_learning": False,
            "changes_decision_engine_behavior": False,
            "uses_llm_provider_contract": True,
            "uses_read_only_tool_registry": True,
        }
