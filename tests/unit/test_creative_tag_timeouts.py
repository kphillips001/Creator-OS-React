import asyncio
import json
from unittest.mock import patch

import pytest
import requests

from app.api.content_studio import _run_tag_action
from app.config import settings
from app.services.wavespeed_grok_service import generate_prompts_with_grok


def test_grok_timeout_is_shorter_than_creative_tag_api_deadline():
    assert settings.GROK_HTTP_TIMEOUT_SECONDS == 90
    assert settings.CREATIVE_TAG_API_DEADLINE_SECONDS == 100
    assert (
        settings.GROK_HTTP_TIMEOUT_SECONDS
        < settings.CREATIVE_TAG_API_DEADLINE_SECONDS
    )


def test_grok_network_timeout_returns_controlled_error_before_api_deadline():
    with patch(
        "app.services.wavespeed_grok_service.requests.post",
        side_effect=requests.exceptions.Timeout("transport detail"),
    ) as post:
        with pytest.raises(RuntimeError, match="Grok API request timed out"):
            generate_prompts_with_grok("safe test prompt", "test-key")

    assert post.call_args.kwargs["timeout"] == settings.GROK_HTTP_TIMEOUT_SECONDS


def test_creative_tag_api_timeout_is_logged_with_safe_diagnostics():
    async def timeout(awaitable, *, timeout):
        assert timeout == settings.CREATIVE_TAG_API_DEADLINE_SECONDS
        awaitable.close()
        raise asyncio.TimeoutError

    with (
        patch("app.api.content_studio.asyncio.wait_for", side_effect=timeout),
        patch("app.api.content_studio.logger.warning") as warning,
    ):
        response = asyncio.run(
            _run_tag_action(
                lambda: {"success": True},
                action_type="creative_tags.enhance",
                correlation_id="request-test",
            )
        )

    assert response.status_code == 503
    assert json.loads(response.body)["error"] == "Creative tag action timed out"
    logged = warning.call_args
    assert "action_type=%s" in logged.args[0]
    assert "creative_tags.enhance" in logged.args
    assert "request-test" in logged.args
    assert logged.kwargs["exc_info"] is True


def test_creative_tag_api_success_is_unchanged():
    response = asyncio.run(
        _run_tag_action(
            lambda: {"success": True, "error": None, "tags": "enhanced"},
            action_type="creative_tags.enhance",
        )
    )

    assert response.status_code == 200
    assert json.loads(response.body)["tags"] == "enhanced"


def test_creative_tag_generic_exception_uses_existing_error_path():
    def fail():
        raise RuntimeError("controlled failure")

    with patch("app.api.content_studio.logger.exception") as exception:
        response = asyncio.run(
            _run_tag_action(fail, action_type="creative_tags.enhance")
        )

    assert response.status_code == 503
    assert json.loads(response.body)["error"] == "controlled failure"
    exception.assert_called_once_with("Content Studio creative tag action failed")
