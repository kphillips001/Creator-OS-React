from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.conversation_gateway import (
    ConversationBrainContext,
    ConversationGatewayInput,
)
from app.services.conversation_gateway import ConversationGateway
from app.services.gpt_service import GPTService
from app.services.recent_creator_activity_context_service import (
    RecentCreatorActivityContextService,
)
from app.test_phone_texting_style import memory_none, user_memory


NOW = datetime(2026, 9, 16, 20, 14, tzinfo=UTC)


def queue_item(queue_id, *, creator=2, prompt="A peach bikini portrait"):
    return SimpleNamespace(
        queue_item_id=queue_id,
        creator_profile_id=creator,
        platform="telegram",
        generated_image_id=f"generation-{queue_id}",
        reference_asset_id=42,
        prompt_text=prompt,
        generation_metadata={},
    )


def publication(queue_id, *, minutes_ago=2, message_id=112, caption="caption",
                post_to="main", status="posted", description=None):
    metadata = {
        "telegram_post_to": post_to,
        "provider_post_id": str(message_id),
        "provider_metadata": {"response": {"result": {
            "message_id": message_id,
            "date": int((NOW - timedelta(minutes=minutes_ago)).timestamp()),
            "caption": caption,
        }}},
    }
    if description:
        metadata["description"] = description
    return SimpleNamespace(
        queue_item_id=queue_id, platform="telegram", status=status,
        created_at=(NOW - timedelta(minutes=minutes_ago)).isoformat(),
        metadata=metadata,
    )


class Publishing:
    def __init__(self, queues, publications):
        self.queues = queues
        self.publications = publications

    def list_queue_items(self, *, creator_profile_id=None, platform=None):
        return tuple(item for item in self.queues
                     if item.creator_profile_id == creator_profile_id
                     and item.platform == platform)

    def list_publish_items(self):
        return tuple(self.publications)


def test_exact_reference_projects_canonical_broadcast_and_generation_context():
    service = RecentCreatorActivityContextService(Publishing(
        [queue_item("dave")],
        [publication("dave", caption="You're staring again... aren't you? 😏🍑")],
    ))

    context = service.build(creator_profile_id=2, now=NOW)

    assert context["evidenceRole"] == "CONTEXTUAL_CANDIDATES_ONLY"
    assert context["windowHours"] == 12
    assert context["candidateLimit"] == 3
    assert context["candidates"] == [{
        "publishedAt": (NOW - timedelta(minutes=2)).replace(microsecond=0).isoformat(),
        "telegramMessageId": 112,
        "caption": "You're staring again... aren't you? 😏🍑",
        "generatedImageId": "generation-dave",
        "assetId": 42,
        "mediaDescription": "A peach bikini portrait",
    }]


def test_ambiguous_candidates_are_limited_ordered_and_not_resolved_to_one():
    queues = [queue_item(str(index)) for index in range(5)]
    posts = [publication(str(index), minutes_ago=index + 1,
                         message_id=200 + index, caption=f"post {index}")
             for index in range(5)]
    context = RecentCreatorActivityContextService(
        Publishing(queues, posts)
    ).build(creator_profile_id=2, now=NOW)

    assert [item["telegramMessageId"] for item in context["candidates"]] == [200, 201, 202]
    assert "selectedCandidate" not in context


def test_no_recent_posts_and_missing_metadata_degrade_without_provider_work():
    old = publication("old", minutes_ago=13 * 60)
    missing = publication("missing", minutes_ago=3, caption="")
    service = RecentCreatorActivityContextService(Publishing(
        [queue_item("old"), queue_item("missing", prompt="")], [old, missing]
    ))
    context = service.build(creator_profile_id=2, now=NOW)

    assert len(context["candidates"]) == 1
    assert context["candidates"][0]["caption"] is None
    assert context["candidates"][0]["mediaDescription"] is None


class Engine:
    def __init__(self):
        self.runtime = None

    def process_message(self, user_id, message, chat_history=None,
                        runtime_injection=None):
        self.runtime = runtime_injection
        return {"response": "natural reply", "send_offer": False,
                "offer": {"offer_type": "none", "content": None}}


class RecentActivity:
    def build(self, *, creator_profile_id):
        assert creator_profile_id == 2
        return {"schemaVersion": "recent_creator_activity_v1",
                "evidenceRole": "CONTEXTUAL_CANDIDATES_ONLY",
                "windowHours": 12, "candidateLimit": 3,
                "candidates": [{"telegramMessageId": 112}]}


def test_existing_customer_receives_context_without_deep_link_entry():
    engine = Engine()
    gateway = ConversationGateway(
        engine, allowed_fanvue_hostnames=["share.fanvue.com"],
        recent_creator_activity_service=RecentActivity(),
    )
    result = gateway.execute(ConversationGatewayInput(
        engine_user_id="telegram:existing-dave",
        message_text="What a beautiful view and sexy picture!",
        chat_history=[{"role": "assistant", "content": "earlier chat"}],
        correlation_id="dave-existing-conversation",
        brain_context=ConversationBrainContext(
            creator_profile_id=2,
            customer_identifier="existing-dave",
            conversation_identifier="existing-chat",
        ),
    ))

    assert result.response_text == "natural reply"
    assert engine.runtime["recent_creator_activity"]["candidates"] == [
        {"telegramMessageId": 112}
    ]


class Training:
    def runtime_prompt_block(self, **_):
        return ""


class Completions:
    def __init__(self):
        self.messages = []

    def create(self, **kwargs):
        self.messages.append(kwargs["messages"])
        message = SimpleNamespace(content="mm, that one definitely got your attention 😏")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_prompt_marks_recent_activity_as_optional_and_ambiguous():
    completions = Completions()
    service = GPTService(api_key="test", global_training_service=Training())
    service.openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    memory = user_memory(memory_none())
    memory["runtime_injection"]["recent_creator_activity"] = {
            "schemaVersion": "recent_creator_activity_v1",
            "evidenceRole": "CONTEXTUAL_CANDIDATES_ONLY",
            "windowHours": 12,
            "candidateLimit": 3,
            "candidates": [
                {"telegramMessageId": 112, "caption": "bikini post"},
                {"telegramMessageId": 111, "caption": "mirror post"},
            ],
        }
    memory["selected_provider"] = "OPENAI"

    service.generate_response(
        "default", "casual", "I saw what you posted", memory, False,
        chat_history=[],
    )

    prompt = completions.messages[0][0]["content"]
    assert "CONTEXTUAL_CANDIDATES_ONLY" in prompt
    assert "do not claim certainty" in prompt
    assert "If the message is unrelated, ignore this activity completely" in prompt
    assert "do not invent image details" in prompt
