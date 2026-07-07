from app.database import get_db_connection
import json


ALLOWED_MEMORY_FIELDS = {
    "message_count",
    "inbound_message_count",
    "outbound_message_count",
    "price_questions_count",
    "exclusive_interest_count",
    "closing_questions_count",
    "offers_shown_count",
    "intent_score",
    "buyer_tier",
    "conversation_mode",
    "last_user_message",
    "last_bot_response",
    "last_offer_type",
    "last_offer_timestamp",
    "last_active_at",
    "last_inbound_at",
    "last_outbound_at",
    "message_score",
    "behavior_score",
    "intent_signals",
    "active_persona",
    "user_value_tier",
    "is_whale",
    "user_type",
    "value_score",
    "attention_tier",
    "effort_mode",
    "timewaster_flags",
    "current_route",
    "last_route",
    "last_route_confidence",
    "last_route_reason",
    "last_route_signals",
    "route_history",
    "last_offer_content_tag",
    "last_offer_price",
    "post_offer_nudge_count",
    "last_subscriber_send_at",
    "subscriber_send_count_24h",
    "last_subscriber_content_tag",
    "last_nudge_timestamp",
    "last_nudge_type",
    "offer_state",
    "messages_since_last_offer",
    "subscriber_status",
    "is_subscriber",
    "is_follower",
    "relationship_status",
    "subscriber_profile",
    "subscriber_profile_reason",
    "subscriber_reentry_count",
    "subscriber_fatigue_flag",
    "subscriber_rewarm_required",
    "engagement_depth_score",
    "conversation_streak",
    "engagement_tier",
    "subscriber_engagement_mode",
    "ppv_sent_count",
    "ppv_open_count",
    "ppv_purchase_count",
    "last_ppv_sent_at",
    "last_ppv_open_at",
    "last_ppv_purchase_at",
    "avg_ppv_spend",
    "silent_buyer_score",
    "silent_buyer_tier",
    "favorite_content_tags",
    "favorite_content_types",
    "last_outreach_at",
    "outreach_attempts",
    "outreach_response_count",
    "last_outreach_response_at",
    "outreach_ignore_count",
    "outreach_status",
    "content_send_count",
    "last_content_sent_at",
    "price_resistance_count",
    "discount_used_flag",
    "preferred_content_theme",
    "preferred_intensity_score",
    "last_selected_content_tag",
    "seen_content_tags",
    "content_success_count",
    "content_ignore_count",
    "last_content_outcome",
    "last_match_profile",
    "last_message_type",
    "purchases_in_session",
    "active_buyer_session",
    "buyer_session_active",
    "buyer_session_started_at",
    "buyer_session_last_action_at",
    "buyer_session_step",
    "buyer_session_ppv_count",
    "buyer_session_last_action",
    "buyer_session_last_ppv_at",
    "buyer_session_last_message_at",
    "buyer_session_cooldown_until",
    "buyer_session_ended_at",
    "buyer_session_wait_until",
    "last_engagement_at",
    "last_realtime_message_at",
}


def _memory_user_id(
    fanvue_user_id,
) -> str:
    return str(fanvue_user_id)


def _clean_memory_value(key, value):
    if key == "seen_content_tags":
        if value is None:
            return []

        if isinstance(value, str):
            return [value]

        if isinstance(value, list):
            return value

        return []

    if key == "preferred_intensity_score":
        try:
            return int(value)
        except Exception:
            return 0

    return value


def get_user_memory_row(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        SELECT *
        FROM user_memory
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def increment_message_count(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        UPDATE user_memory
        SET
            message_count = message_count + 1,
            inbound_message_count = inbound_message_count + 1,
            last_active_at = NOW(),
            last_inbound_at = NOW(),
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def increment_outbound_message_count(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        UPDATE user_memory
        SET
            outbound_message_count = outbound_message_count + 1,
            last_active_at = NOW(),
            last_outbound_at = NOW(),
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def update_conversation_mode(
    fanvue_account_id: int,
    fanvue_user_id: int,
    conversation_mode: str,
):
    query = """
        UPDATE user_memory
        SET
            conversation_mode = %s,
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    conversation_mode,
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def update_intent_fields(
    fanvue_account_id: int,
    fanvue_user_id: int,
    intent_score: float,
    buyer_tier: str,
):
    query = """
        UPDATE user_memory
        SET
            intent_score = %s,
            buyer_tier = %s,
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    intent_score,
                    buyer_tier,
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def set_memory_field(
    fanvue_account_id: int,
    fanvue_user_id: int,
    field_name: str,
    value,
):
    if field_name not in ALLOWED_MEMORY_FIELDS:
        raise ValueError(
            f"Unsupported memory field: {field_name}"
        )

    value = _clean_memory_value(field_name, value)

    query = f"""
        UPDATE user_memory
        SET
            {field_name} = %s,
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    value,
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def update_memory_fields(
    fanvue_account_id: int,
    fanvue_user_id: int,
    data: dict,
):
    if not data:
        return get_user_memory_row(
            fanvue_account_id,
            fanvue_user_id,
        )

    invalid_fields = [
        key
        for key in data.keys()
        if key not in ALLOWED_MEMORY_FIELDS
    ]

    if invalid_fields:
        raise ValueError(
            f"Unsupported memory fields: {invalid_fields}"
        )

    cleaned_data = {}

    for key, value in data.items():
        cleaned_data[key] = _clean_memory_value(
            key,
            value,
        )

    assignments = ", ".join(
        [
            f"{key} = %s"
            for key in cleaned_data.keys()
        ]
    )

    values = []

    for value in cleaned_data.values():
        if isinstance(value, (list, dict)):
            values.append(json.dumps(value))
        else:
            values.append(value)

    query = f"""
        UPDATE user_memory
        SET
            {assignments},
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        print(
            "[DB DEBUG] connected to DB:",
            conn.info.dbname,
        )

        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    *values,
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def reset_user_memory(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        UPDATE user_memory
        SET
            message_count = 0,
            inbound_message_count = 0,
            outbound_message_count = 0,
            price_questions_count = 0,
            exclusive_interest_count = 0,
            closing_questions_count = 0,
            offers_shown_count = 0,
            intent_score = 0,
            buyer_tier = 'low',
            conversation_mode = 'casual',
            last_user_message = NULL,
            last_bot_response = NULL,
            last_offer_type = NULL,
            last_offer_timestamp = NULL,
            last_active_at = NOW(),
            last_inbound_at = NULL,
            last_outbound_at = NULL,
            message_score = 0,
            behavior_score = 0,
            intent_signals = '[]'::jsonb,
            user_value_tier = 'cold',
            is_whale = FALSE,
            user_type = 'unknown',
            value_score = 50,
            attention_tier = 'medium',
            effort_mode = 'balanced',
            timewaster_flags = '[]'::jsonb,
            updated_at = NOW(),
            last_offer_content_tag = NULL,
            last_offer_price = NULL,
            post_offer_nudge_count = 0,
            last_subscriber_send_at = NULL,
            subscriber_send_count_24h = 0,
            last_subscriber_content_tag = NULL,
            last_nudge_timestamp = NULL,
            last_nudge_type = NULL,
            offer_state = 'none',
            messages_since_last_offer = 0,
            current_route = 'chat',
            last_route = 'chat',
            last_route_confidence = 0.50,
            last_route_reason = 'No route reason available.',
            last_route_signals = '[]'::jsonb,
            route_history = '[]'::jsonb,
            subscriber_status = 'none',
            is_subscriber = FALSE,
            is_follower = FALSE,
            relationship_status = 'unknown',
            subscriber_profile = 'none',
            subscriber_profile_reason = NULL,
            subscriber_reentry_count = 0,
            subscriber_fatigue_flag = FALSE,
            subscriber_rewarm_required = FALSE,
            ppv_sent_count = 0,
            ppv_open_count = 0,
            ppv_purchase_count = 0,
            last_ppv_sent_at = NULL,
            last_ppv_open_at = NULL,
            last_ppv_purchase_at = NULL,
            avg_ppv_spend = 0,
            silent_buyer_score = 0,
            silent_buyer_tier = 'none',
            favorite_content_tags = '[]'::jsonb,
            favorite_content_types = '[]'::jsonb,
            last_outreach_at = NULL,
            outreach_attempts = 0,
            outreach_response_count = 0,
            last_outreach_response_at = NULL,
            outreach_ignore_count = 0,
            outreach_status = 'eligible'
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def create_user_memory_row(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        INSERT INTO user_memory (
            fanvue_account_id,
            fanvue_user_id,
            ppv_sent_count,
            ppv_open_count,
            ppv_purchase_count,
            avg_ppv_spend,
            silent_buyer_score,
            silent_buyer_tier,
            last_subscriber_send_at,
            subscriber_send_count_24h,
            last_subscriber_content_tag,
            buyer_session_active,
            buyer_session_started_at,
            buyer_session_last_action_at,
            buyer_session_step,
            buyer_session_ppv_count,
            buyer_session_last_action,
            buyer_session_last_ppv_at,
            buyer_session_last_message_at,
            buyer_session_cooldown_until,
            buyer_session_ended_at,
            created_at,
            updated_at
        )
        VALUES (
            %s,
            %s::text,
            0,
            0,
            0,
            0,
            0,
            'none',
            NULL,
            0,
            NULL,
            FALSE,
            NULL,
            NULL,
            0,
            0,
            NULL,
            NULL,
            NULL,
            NULL,
            NULL,
            NOW(),
            NOW()
        )
        ON CONFLICT (fanvue_account_id, fanvue_user_id)
        DO NOTHING
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            row = cur.fetchone()

            return (
                row
                if row
                else get_user_memory_row(
                    fanvue_account_id,
                    fanvue_user_id,
                )
            )


def record_subscriber_send(
    fanvue_account_id: int,
    fanvue_user_id: int,
    content_tag: str,
):
    query = """
        UPDATE user_memory
        SET
            last_subscriber_send_at = NOW(),
            subscriber_send_count_24h = COALESCE(subscriber_send_count_24h, 0) + 1,
            last_subscriber_content_tag = %s,
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    content_tag,
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def mark_outreach_sent(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        UPDATE user_memory
        SET
            outreach_attempts = COALESCE(outreach_attempts, 0) + 1,
            last_outreach_at = NOW(),
            outreach_status = 'sent',
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def mark_outreach_ignored(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        UPDATE user_memory
        SET
            outreach_ignore_count = COALESCE(outreach_ignore_count, 0) + 1,
            outreach_status = CASE
                WHEN COALESCE(outreach_attempts, 0) >= 3 THEN 'exhausted'
                ELSE 'ignored'
            END,
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def mark_outreach_response(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        UPDATE user_memory
        SET
            outreach_response_count = COALESCE(outreach_response_count, 0) + 1,
            last_outreach_response_at = NOW(),
            outreach_status = 'responded',
            connection_score = COALESCE(connection_score, 0) + 5,
            attention_tier = CASE
                WHEN attention_tier = 'low' THEN 'medium'
                ELSE attention_tier
            END,
            last_active_at = NOW(),
            last_inbound_at = NOW(),
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
          AND outreach_status = 'sent'
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def force_reset_outreach_state(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        UPDATE user_memory
        SET
            last_outreach_at = NULL,
            outreach_attempts = 0,
            outreach_status = 'eligible',
            outreach_ignore_count = 0,
            outreach_response_count = 0,
            last_outreach_response_at = NULL,
            last_inbound_at = NULL,
            last_active_at = NULL,
            updated_at = NOW()
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()


def reset_exhausted_outreach_user(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        UPDATE user_memory
        SET
            outreach_status = 'eligible',
            outreach_attempts = 0,
            last_outreach_at = NULL,
            last_outreach_response_at = NULL,
            outreach_response_count = 0,
            outreach_ignore_count = 0
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s::text
          AND outreach_status = 'exhausted'
          AND last_outreach_at IS NOT NULL
          AND last_outreach_at <= NOW() - INTERVAL '168 hours'
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    _memory_user_id(fanvue_user_id),
                ),
            )
            return cur.fetchone()