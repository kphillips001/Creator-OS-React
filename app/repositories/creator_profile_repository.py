from app.database import get_db_connection


def get_active_creator_profile(fanvue_account_id: str) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM creator_profiles
                WHERE fanvue_account_id = %s
                  AND is_active = TRUE
                LIMIT 1;
                """,
                (str(fanvue_account_id),),
            )

            row = cur.fetchone()
            return dict(row) if row else {}


def update_creator_profile(
    creator_profile_id: int,
    fanvue_account_id: str,
    profile: dict,
) -> dict:
    """Update one existing account-scoped creator profile without inserting."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE creator_profiles
                SET persona_name = %(persona_name)s,
                    display_name = %(persona_name)s,
                    age = %(age)s,
                    gender = %(gender)s,
                    location = %(location)s,
                    is_active = %(is_active)s,
                    archetype = %(archetype)s,
                    personality_description = %(personality_description)s,
                    backstory = %(backstory)s,
                    lifestyle_context = %(lifestyle_context)s,
                    lifestyle_vibe = %(lifestyle_vibe)s,
                    daily_routine = %(daily_routine)s,
                    hobbies = %(hobbies)s,
                    likes = %(likes)s,
                    dislikes = %(dislikes)s,
                    ideal_user_type = %(ideal_user_type)s,
                    turn_ons = %(turn_ons)s,
                    turn_offs = %(turn_offs)s,
                    sexual_style = %(sexual_style)s,
                    sexual_likes = %(sexual_likes)s,
                    sexual_dislikes = %(sexual_dislikes)s,
                    kinks = %(kinks)s,
                    fantasy_style = %(fantasy_style)s,
                    tone_style = %(tone_style)s,
                    flirt_style = %(flirt_style)s,
                    tease_intensity = %(tease_intensity)s,
                    push_pull_style = %(push_pull_style)s,
                    mystery_level = %(mystery_level)s,
                    response_style = %(response_style)s,
                    pacing_style = %(pacing_style)s,
                    question_frequency = %(question_frequency)s,
                    emotional_depth = %(emotional_depth)s,
                    affection_style = %(affection_style)s,
                    jealousy_style = %(jealousy_style)s,
                    availability_style = %(availability_style)s,
                    conversation_hooks = %(conversation_hooks)s,
                    retention_hooks = %(retention_hooks)s,
                    escalation_style = %(escalation_style)s,
                    escalation_triggers = %(escalation_triggers)s,
                    self_value_style = %(self_value_style)s,
                    persona_intensity = %(persona_intensity)s,
                    boundaries = %(boundaries)s,
                    sexual_boundaries = %(sexual_boundaries)s,
                    hard_limits = %(hard_limits)s,
                    response_rules = %(response_rules)s,
                    updated_at = NOW()
                WHERE id = %(creator_profile_id)s
                  AND fanvue_account_id = %(fanvue_account_id)s
                RETURNING *;
                """,
                {
                    **profile,
                    "creator_profile_id": int(creator_profile_id),
                    "fanvue_account_id": str(fanvue_account_id),
                },
            )
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else {}


def upsert_creator_profile(profile: dict) -> dict:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO creator_profiles (
                    fanvue_account_id,
                    persona_name,
                    display_name,
                    age,
                    gender,
                    location,
                    is_active,

                    archetype,
                    personality_description,
                    backstory,
                    lifestyle_context,
                    lifestyle_vibe,
                    daily_routine,
                    hobbies,

                    likes,
                    dislikes,
                    ideal_user_type,
                    turn_ons,
                    turn_offs,

                    sexual_style,
                    sexual_likes,
                    sexual_dislikes,
                    kinks,
                    fantasy_style,

                    tone_style,
                    flirt_style,
                    tease_intensity,
                    push_pull_style,
                    mystery_level,

                    response_style,
                    pacing_style,
                    question_frequency,
                    emotional_depth,
                    affection_style,
                    jealousy_style,
                    availability_style,

                    conversation_hooks,
                    retention_hooks,
                    escalation_style,
                    escalation_triggers,
                    self_value_style,
                    persona_intensity,

                    boundaries,
                    sexual_boundaries,
                    hard_limits,
                    response_rules,
                    updated_at
                )
                VALUES (
                    %(fanvue_account_id)s,
                    %(persona_name)s,
                    %(display_name)s,
                    %(age)s,
                    %(gender)s,
                    %(location)s,
                    %(is_active)s,

                    %(archetype)s,
                    %(personality_description)s,
                    %(backstory)s,
                    %(lifestyle_context)s,
                    %(lifestyle_vibe)s,
                    %(daily_routine)s,
                    %(hobbies)s,

                    %(likes)s,
                    %(dislikes)s,
                    %(ideal_user_type)s,
                    %(turn_ons)s,
                    %(turn_offs)s,

                    %(sexual_style)s,
                    %(sexual_likes)s,
                    %(sexual_dislikes)s,
                    %(kinks)s,
                    %(fantasy_style)s,

                    %(tone_style)s,
                    %(flirt_style)s,
                    %(tease_intensity)s,
                    %(push_pull_style)s,
                    %(mystery_level)s,

                    %(response_style)s,
                    %(pacing_style)s,
                    %(question_frequency)s,
                    %(emotional_depth)s,
                    %(affection_style)s,
                    %(jealousy_style)s,
                    %(availability_style)s,

                    %(conversation_hooks)s,
                    %(retention_hooks)s,
                    %(escalation_style)s,
                    %(escalation_triggers)s,
                    %(self_value_style)s,
                    %(persona_intensity)s,

                    %(boundaries)s,
                    %(sexual_boundaries)s,
                    %(hard_limits)s,
                    %(response_rules)s,
                    NOW()
                )
                ON CONFLICT (fanvue_account_id)
                DO UPDATE SET
                    persona_name = EXCLUDED.persona_name,
                    display_name = EXCLUDED.display_name,
                    age = EXCLUDED.age,
                    gender = EXCLUDED.gender,
                    location = EXCLUDED.location,
                    is_active = EXCLUDED.is_active,

                    archetype = EXCLUDED.archetype,
                    personality_description = EXCLUDED.personality_description,
                    backstory = EXCLUDED.backstory,
                    lifestyle_context = EXCLUDED.lifestyle_context,
                    lifestyle_vibe = EXCLUDED.lifestyle_vibe,
                    daily_routine = EXCLUDED.daily_routine,
                    hobbies = EXCLUDED.hobbies,

                    likes = EXCLUDED.likes,
                    dislikes = EXCLUDED.dislikes,
                    ideal_user_type = EXCLUDED.ideal_user_type,
                    turn_ons = EXCLUDED.turn_ons,
                    turn_offs = EXCLUDED.turn_offs,

                    sexual_style = EXCLUDED.sexual_style,
                    sexual_likes = EXCLUDED.sexual_likes,
                    sexual_dislikes = EXCLUDED.sexual_dislikes,
                    kinks = EXCLUDED.kinks,
                    fantasy_style = EXCLUDED.fantasy_style,

                    tone_style = EXCLUDED.tone_style,
                    flirt_style = EXCLUDED.flirt_style,
                    tease_intensity = EXCLUDED.tease_intensity,
                    push_pull_style = EXCLUDED.push_pull_style,
                    mystery_level = EXCLUDED.mystery_level,

                    response_style = EXCLUDED.response_style,
                    pacing_style = EXCLUDED.pacing_style,
                    question_frequency = EXCLUDED.question_frequency,
                    emotional_depth = EXCLUDED.emotional_depth,
                    affection_style = EXCLUDED.affection_style,
                    jealousy_style = EXCLUDED.jealousy_style,
                    availability_style = EXCLUDED.availability_style,

                    conversation_hooks = EXCLUDED.conversation_hooks,
                    retention_hooks = EXCLUDED.retention_hooks,
                    escalation_style = EXCLUDED.escalation_style,
                    escalation_triggers = EXCLUDED.escalation_triggers,
                    self_value_style = EXCLUDED.self_value_style,
                    persona_intensity = EXCLUDED.persona_intensity,

                    boundaries = EXCLUDED.boundaries,
                    sexual_boundaries = EXCLUDED.sexual_boundaries,
                    hard_limits = EXCLUDED.hard_limits,
                    response_rules = EXCLUDED.response_rules,
                    updated_at = NOW()
                RETURNING *;
                """,
                profile,
            )

            row = cur.fetchone()
            conn.commit()

            return dict(row) if row else {}
