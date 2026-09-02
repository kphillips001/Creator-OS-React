from app.testing.session5_scenario_harness import normalize_provider_diagnostics


def test_provider_metadata_mapping_is_normalized():
    assert normalize_provider_diagnostics({"provider": {"selected": "OPENAI"}}) == {
        "selected": "OPENAI", "shape": "mapping",
    }


def test_provider_metadata_string_is_normalized():
    assert normalize_provider_diagnostics({"provider": "GROK"}) == {
        "selected": "GROK", "shape": "string",
    }


def test_provider_metadata_absent_is_safe():
    assert normalize_provider_diagnostics({}) == {
        "selected": "OPENAI_SAFE_CHAT_RUNTIME", "shape": "absent",
    }


def test_unexpected_provider_diagnostics_are_safe():
    assert normalize_provider_diagnostics({"provider": ["unexpected"]}) == {
        "selected": "OPENAI_SAFE_CHAT_RUNTIME", "shape": "unexpected",
    }
