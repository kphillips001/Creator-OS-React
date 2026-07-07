from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from app.models.developer_agent import (
    DeveloperAgentIntent,
    DeveloperAgentRequest,
    DeveloperAgentResponse,
    DeveloperAgentToolRegistry,
)
from app.models.llm_provider import LLMResponse
from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.null_provider import NullLLMProvider
from app.repositories.runtime_control_repository import RuntimeControlRepository
from app.services.developer_agent_service import DeveloperAgentService
from app.services.runtime_control_service import RuntimeControlService


class CapturingLLMProvider(BaseLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.requests = []

    def generate_response(self, request):
        self.requests.append(request)
        return LLMResponse(
            response_text="Captured developer LLM answer.",
            provider_name="capturing",
            model_name="capturing-model",
            metadata={"external_api_called": False},
        )


class DeveloperAgentServiceTest(unittest.TestCase):
    def test_models_can_be_created(self) -> None:
        request = DeveloperAgentRequest(question="Review the architecture.")

        self.assertEqual(request.question, "Review the architecture.")
        self.assertIsNotNone(request.created_at)

    def test_service_returns_response(self) -> None:
        service = DeveloperAgentService(enable_llm=False)

        response = service.answer(
            DeveloperAgentRequest(question="Review the architecture.")
        )

        self.assertIsInstance(response, DeveloperAgentResponse)
        self.assertEqual(response.intent, DeveloperAgentIntent.ARCHITECTURE_AUDIT)
        self.assertTrue(response.sources)
        self.assertTrue(response.evidence)
        self.assertTrue(response.recommendations)
        self.assertTrue(response.compatibility["read_only"])
        self.assertFalse(response.compatibility["executes_commands"])
        self.assertFalse(response.compatibility["modifies_files"])

    def test_intent_classification(self) -> None:
        service = DeveloperAgentService(enable_llm=False)

        self.assertEqual(
            service.resolve_intent("What tests should I run?"),
            DeveloperAgentIntent.TEST_STRATEGY,
        )
        self.assertEqual(
            service.resolve_intent("What technical debt remains?"),
            DeveloperAgentIntent.RISK_ANALYSIS,
        )
        self.assertEqual(
            service.resolve_intent("Is this implementation ready?"),
            DeveloperAgentIntent.RELEASE_READINESS,
        )

    def test_tool_registry_is_read_only(self) -> None:
        service = DeveloperAgentService(enable_llm=False)

        self.assertIsInstance(service.tool_registry, DeveloperAgentToolRegistry)
        self.assertTrue(service.tool_registry.compatibility["read_only"])
        self.assertTrue(service.tool_registry.compatibility["avoids_command_execution"])
        self.assertTrue(service.tool_registry.compatibility["avoids_file_mutation"])
        self.assertTrue(service.tool_registry.compatibility["avoids_runtime_mutation"])

    def test_null_provider_fallback_works(self) -> None:
        service = DeveloperAgentService(llm_provider=NullLLMProvider())

        response = service.answer(
            DeveloperAgentRequest(question="What should we build next?")
        )

        self.assertTrue(response.answer_text.startswith("[null-llm]"))
        self.assertEqual(response.metadata["llm_provider"], "null")
        self.assertTrue(response.sources)

    def test_llm_infrastructure_reused_with_context(self) -> None:
        llm = CapturingLLMProvider()
        service = DeveloperAgentService(llm_provider=llm)

        response = service.answer(
            DeveloperAgentRequest(
                question="Review the architecture.",
                metadata={
                    "conversation_history": (
                        {"role": "user", "content": "Earlier question"},
                    )
                },
            )
        )

        self.assertEqual(response.answer_text, "Captured developer LLM answer.")
        self.assertEqual(len(llm.requests), 1)
        request = llm.requests[0]
        self.assertFalse(request.structured_context["command_execution_allowed"])
        self.assertFalse(request.structured_context["file_mutation_allowed"])
        self.assertIsNotNone(request.conversation)

    def test_unsupported_question_is_safe(self) -> None:
        service = DeveloperAgentService(enable_llm=False)

        response = service.answer(DeveloperAgentRequest(question=""))

        self.assertEqual(response.intent, DeveloperAgentIntent.UNSUPPORTED)
        self.assertFalse(response.sources)
        self.assertTrue(response.limitations)

    def test_runtime_control_requires_confirmation_for_changes(self) -> None:
        with TemporaryDirectory() as directory:
            runtime = RuntimeControlService(
                repository=RuntimeControlRepository(f"{directory}/runtime.json")
            )
            service = DeveloperAgentService(
                runtime_control_service=runtime,
                enable_llm=False,
            )

            unconfirmed = service.answer(
                DeveloperAgentRequest(question="Stop Creator OS.")
            )
            confirmed = service.answer(
                DeveloperAgentRequest(
                    question="Switch to Observe Mode.",
                    metadata={"confirm_runtime_change": True},
                )
            )

            self.assertEqual(unconfirmed.intent, DeveloperAgentIntent.RUNTIME_CONTROL)
            self.assertTrue(unconfirmed.limitations)
            self.assertIsNone(unconfirmed.metadata["runtime_change"])
            self.assertEqual(confirmed.metadata["runtime_change"], "observe")
            self.assertIn("OBSERVE", confirmed.answer_text)


if __name__ == "__main__":
    unittest.main()
