from app.services.gpt_service import GPTService


def test_3d_20_7_3_gpt_stability_context_injection():
    service = GPTService(api_key="test_key")

    captured = {}

    class FakeMessage:
        content = "steady, warm reply 🙂"

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured["messages"] = kwargs.get("messages", [])
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    service.openai_client = FakeClient()

    result = service.generate_response(
        persona_name="default",
        mode="flirty",
        user_message="I missed you",
        user_memory={
            "selected_provider": "OPENAI",
            "behavior_context": {
                "response_strategy": "chat",
                "tone_mode": "flirty",
                "pressure_level": "low",
            },
            "stability_level": "active_stabilization",
            "long_term_emotional_stability_active": True,
            "relationship_rhythm_state": "developing_rhythm",
            "long_term_response_bias": "grounded_consistent",
        },
        send_offer=False,
        offer=None,
        chat_history=[],
    )

    system_prompt = captured["messages"][0]["content"]

    assert result == "steady, warm reply 🙂"

    assert "3D.20.7.3 — LONG-TERM EMOTIONAL STABILITY" in system_prompt
    assert "active_stabilization" in system_prompt
    assert "developing_rhythm" in system_prompt
    assert "grounded_consistent" in system_prompt
    assert "Do not abruptly spike intensity" in system_prompt

if __name__ == "__main__":
    test_3d_20_7_3_gpt_stability_context_injection()

    print("\n=== 3D.20.7.3 TEST COMPLETE ===")