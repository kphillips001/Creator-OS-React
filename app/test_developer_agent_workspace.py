from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

from app.models.developer_agent import (
    DeveloperAgentEvidence,
    DeveloperAgentIntent,
    DeveloperAgentRecommendation,
    DeveloperAgentRequest,
    DeveloperAgentResponse,
    DeveloperAgentSource,
)


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict = {}
        self.records: list[tuple[str, object]] = []
        self.button_presses: dict[str, bool] = {}
        self.rerun_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def title(self, value):
        self.records.append(("title", value))

    def caption(self, value):
        self.records.append(("caption", value))

    def markdown(self, value, **kwargs):
        self.records.append(("markdown", value))

    def write(self, value):
        self.records.append(("write", value))

    def metric(self, label, value):
        self.records.append(("metric", (label, value)))

    def progress(self, value):
        self.records.append(("progress", value))

    def warning(self, value):
        self.records.append(("warning", value))

    def info(self, value):
        self.records.append(("info", value))

    def divider(self):
        self.records.append(("divider", None))

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [self for _ in range(count)]

    def button(self, label, **kwargs):
        key = kwargs.get("key") or label
        pressed = self.button_presses.get(key, False)
        self.records.append(("button", label))
        return pressed

    def chat_message(self, role):
        self.records.append(("chat_message", role))
        return _Context()

    def expander(self, label, **kwargs):
        self.records.append(("expander", label))
        return _Context()

    def form(self, key, **kwargs):
        self.records.append(("form", key))
        return _Context()

    def text_input(self, label, **kwargs):
        self.records.append(("text_input", label))
        return ""

    def form_submit_button(self, label, **kwargs):
        self.records.append(("form_submit_button", label))
        return False

    def spinner(self, label):
        self.records.append(("spinner", label))
        return _Context()

    def rerun(self):
        self.rerun_called = True


fake_streamlit_module = types.ModuleType("streamlit")
_fake_streamlit = FakeStreamlit()
for name in dir(_fake_streamlit):
    if not name.startswith("_"):
        setattr(fake_streamlit_module, name, getattr(_fake_streamlit, name))
sys.modules["streamlit"] = fake_streamlit_module

from app.dashboard.pages import developer_agent as developer_agent_page


class StubDeveloperAgentService:
    def __init__(self) -> None:
        self.requests: list[DeveloperAgentRequest] = []

    def answer(self, request: DeveloperAgentRequest) -> DeveloperAgentResponse:
        self.requests.append(request)
        return DeveloperAgentResponse(
            request=request,
            intent=DeveloperAgentIntent.ARCHITECTURE_AUDIT,
            answer_text="Review boundaries before implementation.",
            confidence=0.8,
            sources=(
                DeveloperAgentSource(
                    source_type="read_only_metadata",
                    name="Creator OS Architecture Metadata",
                    summary="Architecture metadata available.",
                    confidence=0.8,
                ),
            ),
            evidence=(
                DeveloperAgentEvidence(
                    source="Creator OS Architecture Metadata",
                    summary="Boundaries are preserved.",
                    confidence=0.8,
                ),
            ),
            recommendations=(
                DeveloperAgentRecommendation(
                    title="Validate ownership boundaries",
                    priority="HIGH",
                ),
            ),
            suggested_follow_up_questions=("What tests should I run?",),
            warnings=("Test warning",),
            limitations=("Test limitation",),
        )


class DeveloperAgentWorkspaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_st = FakeStreamlit()
        developer_agent_page.st = self.fake_st

    def test_developer_agent_page_renders(self) -> None:
        service = StubDeveloperAgentService()

        developer_agent_page.render_developer_agent(
            active_account={"id": 3},
            developer_agent_service=service,
        )

        self.assertIn(("title", "Developer Agent"), self.fake_st.records)
        self.assertIn(("markdown", "### Suggested Questions"), self.fake_st.records)
        self.assertIn(("markdown", "### Conversation"), self.fake_st.records)

    def test_suggested_question_routes_through_service(self) -> None:
        service = StubDeveloperAgentService()
        history: list[dict] = []
        self.fake_st.button_presses["developer_agent_suggestion_0"] = True

        developer_agent_page._render_suggestions(
            history=history,
            developer_agent_service=service,
        )

        self.assertTrue(self.fake_st.rerun_called)
        self.assertEqual(len(service.requests), 1)
        self.assertEqual(service.requests[0].question, "What should we build next?")
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")

    def test_conversation_history_persists(self) -> None:
        key = developer_agent_page._history_key({"id": 3})
        first = developer_agent_page._ensure_history(key)
        first.append({"role": "user", "content": "Hello"})
        second = developer_agent_page._ensure_history(key)

        self.assertIs(first, second)
        self.assertEqual(second[0]["content"], "Hello")

    def test_structured_response_displays_architecture_details(self) -> None:
        service = StubDeveloperAgentService()
        response = service.answer(DeveloperAgentRequest(question="Review."))

        developer_agent_page._render_response_details(response)

        record_values = [value for _, value in self.fake_st.records]
        self.assertIn("#### Architecture Sources", record_values)
        self.assertIn("#### Evidence", record_values)
        self.assertIn("#### Recommendations", record_values)
        self.assertIn("#### Suggested Follow-up Questions", record_values)
        self.assertIn("#### Warnings", record_values)
        self.assertIn("#### Limitations", record_values)

    def test_page_uses_developer_agent_service_only(self) -> None:
        source = Path("app/dashboard/pages/developer_agent.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("DeveloperAgentService", source)
        self.assertIn("developer_agent_service.answer", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("exec(", source)
        self.assertNotIn("Repository", source)
        self.assertNotIn("DecisionEngine", source)
        self.assertNotIn("TelegramDeliveryExecutor", source)
        self.assertNotIn("create_publishing_job", source)


if __name__ == "__main__":
    unittest.main()
