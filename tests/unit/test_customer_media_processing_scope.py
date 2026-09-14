import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services.customer_media_processing_scope_service import CustomerMediaProcessingScopeService


BASE = {
    "TELEGRAM_CUSTOMER_IMAGE_SCOPE_MODE": "ONLY_CONTROLLED_IDENTITY",
    "TELEGRAM_CUSTOMER_IMAGE_SAFETY_ENABLED": "true",
    "TELEGRAM_CUSTOMER_IMAGE_RESPONSE_ENABLED": "true",
    "CONTROLLED_AUTONOMY_TEST_ENABLED": "true",
    "CONTROLLED_AUTONOMY_TELEGRAM_USER_ID": "101",
    "CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID": "202",
}


def decide(user=101, chat=202, **changes):
    values = {**BASE, **changes}
    with patch.dict(os.environ, values, clear=False):
        return CustomerMediaProcessingScopeService().decide(
            telegram_user_id=user, telegram_chat_id=chat)


def test_matching_numeric_user_and_chat_are_allowed_only_in_controlled_mode():
    result = decide()
    assert result.allowed and result.reason == "CONTROLLED_SCOPE_AUTHORIZED"
    assert len(result.identity_fingerprint) == 12


@pytest.mark.parametrize("user,chat", [(999, 202), (101, 999), (999, 999), (None, 202), (101, None)])
def test_partial_wrong_or_missing_event_identity_is_blocked(user, chat):
    assert not decide(user, chat).allowed


@pytest.mark.parametrize("changes", [
    {"CONTROLLED_AUTONOMY_TELEGRAM_USER_ID": ""},
    {"CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID": ""},
    {"CONTROLLED_AUTONOMY_TELEGRAM_USER_ID": "bad"},
    {"CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID": "-2"},
])
def test_missing_or_malformed_controlled_configuration_blocks_everyone(changes):
    assert decide(**changes).reason == "CONTROLLED_IDENTITY_INVALID"


def test_flags_off_disable_feature_even_for_matching_identity():
    result = decide(TELEGRAM_CUSTOMER_IMAGE_SAFETY_ENABLED="false",
                    TELEGRAM_CUSTOMER_IMAGE_RESPONSE_ENABLED="false")
    assert not result.allowed and result.reason == "IMAGE_FEATURE_DISABLED"


def test_response_without_safety_is_invalid_and_fail_closed():
    result = decide(TELEGRAM_CUSTOMER_IMAGE_SAFETY_ENABLED="false")
    assert not result.allowed and result.reason == "IMAGE_FEATURE_CONFIGURATION_INVALID"


def test_controlled_test_disabled_blocks_controlled_certification_mode():
    result = decide(CONTROLLED_AUTONOMY_TEST_ENABLED="false")
    assert not result.allowed and result.reason == "CONTROLLED_TEST_DISABLED"


def test_normal_production_is_explicit_and_cannot_overlap_controlled_test():
    conflict = decide(TELEGRAM_CUSTOMER_IMAGE_SCOPE_MODE="NORMAL_PRODUCTION")
    allowed = decide(user=999, chat=888,
                     TELEGRAM_CUSTOMER_IMAGE_SCOPE_MODE="NORMAL_PRODUCTION",
                     CONTROLLED_AUTONOMY_TEST_ENABLED="false")
    assert not conflict.allowed and conflict.reason == "CONTROLLED_MODE_CONFLICT"
    assert allowed.allowed and allowed.reason == "NORMAL_PRODUCTION_AUTHORIZED"


def test_unknown_scope_mode_fails_closed():
    assert decide(TELEGRAM_CUSTOMER_IMAGE_SCOPE_MODE="maybe").reason == "IMAGE_SCOPE_MODE_INVALID"


def test_restart_equivalent_new_instances_revalidate_environment_each_time():
    service = CustomerMediaProcessingScopeService()
    with patch.dict(os.environ, BASE, clear=False):
        assert service.decide(telegram_user_id=101, telegram_chat_id=202).allowed
    invalid = {**BASE, "CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID": "bad"}
    with patch.dict(os.environ, invalid, clear=False):
        assert not CustomerMediaProcessingScopeService().decide(telegram_user_id=101, telegram_chat_id=202).allowed
