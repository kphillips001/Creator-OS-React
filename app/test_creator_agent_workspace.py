from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

from app.models.creator_agent import (
    CreatorAgentEvidence,
    CreatorAgentIntent,
    CreatorAgentRecommendedAction,
    CreatorAgentRequest,
    CreatorAgentResponse,
    CreatorAgentSource,
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

from app.dashboard.pages import creator_agent as creator_agent_page


class StubCreatorAgentService:
    def __init__(self) -> None:
        self.requests: list[CreatorAgentRequest] = []

    def answer(self, request: CreatorAgentRequest) -> CreatorAgentResponse:
        self.requests.append(request)
        return CreatorAgentResponse(
            request=request,
            intent=CreatorAgentIntent.DAILY_PRIORITIES,
            answer_text="Work on publishing readiness.",
            confidence=0.8,
            sources=(
                CreatorAgentSource(
                    source_type="read_model",
                    name="BusinessOptimizationService",
                    summary="Publish Products awaiting Media Links",
                    confidence=0.8,
                ),
            ),
            recommended_actions=(
                CreatorAgentRecommendedAction(
                    title="Publish Products awaiting Media Links",
                    source="BusinessOptimizationService",
                    priority="HIGH",
                ),
            ),
            business_reasoning=("Business Optimization supports this action.",),
            supporting_evidence=(
                CreatorAgentEvidence(
                    source="BusinessOptimizationService",
                    summary="Media Link readiness is blocked.",
                    confidence=0.8,
                ),
            ),
            confidence_explanation="Confidence is based on source read models.",
            recommendation_rationale=(
                "Publish Products awaiting Media Links is surfaced by Business Optimization.",
            ),
            suggested_follow_up_questions=("Show evidence.",),
            related_business_areas=("Business Optimization",),
            warnings=("Test warning",),
            limitations=("Test limitation",),
        )


class CreatorAgentWorkspaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_st = FakeStreamlit()
        creator_agent_page.st = self.fake_st

    def test_creator_agent_page_renders(self) -> None:
        service = StubCreatorAgentService()

        creator_agent_page.render_creator_agent(
            creator_profile={"id": 7},
            active_account={"id": 3},
            creator_agent_service=service,
        )

        self.assertIn(("title", "Creator Agent"), self.fake_st.records)
        self.assertIn(("markdown", "### Suggested Questions"), self.fake_st.records)
        self.assertIn(("markdown", "### Conversation"), self.fake_st.records)
        self.assertIn(("markdown", "### Future Capabilities"), self.fake_st.records)

    def test_suggested_question_submits_through_creator_agent_service(self) -> None:
        service = StubCreatorAgentService()
        history: list[dict] = []
        self.fake_st.button_presses["creator_agent_suggestion_0"] = True

        creator_agent_page._render_suggestions(
            history=history,
            creator_profile={"id": 7},
            active_account={"id": 3},
            creator_agent_service=service,
        )

        self.assertTrue(self.fake_st.rerun_called)
        self.assertEqual(len(service.requests), 1)
        self.assertEqual(service.requests[0].question, "What should I work on today?")
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")

    def test_conversation_history_persists_in_session_state(self) -> None:
        key = creator_agent_page._history_key({"id": 3})
        first = creator_agent_page._ensure_history(key)
        first.append({"role": "user", "content": "Hello"})
        second = creator_agent_page._ensure_history(key)

        self.assertIs(first, second)
        self.assertEqual(second[0]["content"], "Hello")

    def test_submit_question_passes_conversation_history_to_creator_agent_service(self) -> None:
        service = StubCreatorAgentService()
        history = [
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
        ]

        creator_agent_page._submit_question(
            "What now?",
            history=history,
            creator_profile={"id": 7},
            active_account={"id": 3},
            creator_agent_service=service,
        )

        self.assertEqual(service.requests[0].question, "What now?")
        self.assertEqual(
            service.requests[0].metadata["conversation_history"][0]["content"],
            "Earlier question",
        )

    def test_structured_response_displays_sources_actions_warnings_and_limits(self) -> None:
        service = StubCreatorAgentService()
        response = service.answer(CreatorAgentRequest(question="What now?"))

        creator_agent_page._render_response_details(response)

        record_values = [value for _, value in self.fake_st.records]
        self.assertIn("#### Supporting Sources", record_values)
        self.assertIn("#### Business Reasoning", record_values)
        self.assertIn("#### Supporting Evidence", record_values)
        self.assertIn("#### Confidence Explanation", record_values)
        self.assertIn("#### Recommendation Rationale", record_values)
        self.assertIn("#### Recommended Actions", record_values)
        self.assertIn("#### Action Proposals", record_values)
        self.assertIn("#### Suggested Follow-up Questions", record_values)
        self.assertIn("#### Related Business Areas", record_values)
        self.assertIn("#### Warnings", record_values)
        self.assertIn("#### Limitations", record_values)
        self.assertIn(("warning", "Test warning"), self.fake_st.records)
        self.assertIn(("info", "Test limitation"), self.fake_st.records)

    def test_page_uses_creator_agent_service_and_not_repositories(self) -> None:
        source = Path("app/dashboard/pages/creator_agent.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("CreatorAgentService", source)
        self.assertIn("creator_agent_service.answer", source)
        self.assertNotIn("Repository", source)
        self.assertNotIn("DecisionEngine", source)
        self.assertNotIn("TelegramDeliveryExecutor", source)
        self.assertNotIn("create_publishing_job", source)
        self.assertNotIn("upload_asset_media_item", source)


if __name__ == "__main__":
    unittest.main()
