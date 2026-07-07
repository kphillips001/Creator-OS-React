from app.services.reaction_intelligence_expansion_service import (
    ReactionIntelligenceExpansionService,
)


def main():
    service = ReactionIntelligenceExpansionService()

    print(
        "\n=== 3D.19.1 REACTION INTELLIGENCE EXPANSION TEST ===\n"
    )

    missing = service.build_reaction_intelligence(
        monetization_event={},
    )

    assert missing["success"] is False
    assert missing["blocked"] is True
    assert missing["reason"] == "missing_monetization_event"

    whale = service.build_reaction_intelligence(
        monetization_event={
            "event_type": "purchase_received",
        },
        spend_profile={
            "buyer_tier": "WHALE",
        },
    )

    assert whale["success"] is True
    assert whale["buyer_tier"] == "WHALE"
    assert whale["reaction_tone"] == "exclusive_soft_retention"
    assert whale["whale_sensitive"] is True
    assert whale["should_hard_sell"] is False

    whale_profile = whale["reaction_profile"]

    assert (
        whale_profile["emotional_warmth"]
        == "exclusive"
    )

    assert (
        whale_profile["reward_depth"]
        == "premium"
    )

    assert (
        whale_profile["retention_priority"]
        == "critical"
    )

    assert (
        whale_profile["continuation_pressure"]
        == "minimal"
    )

    tip = service.build_reaction_intelligence(
        monetization_event={
            "event_type": "tip_received",
        },
        spend_profile={
            "buyer_tier": "LOW_SPENDER",
        },
    )

    assert tip["success"] is True
    assert tip["reaction_tone"] == "warm_grateful"

    assert (
        tip["timing_profile"]
        == "immediate_acknowledgement"
    )

    assert (
        tip["cta_strategy"]
        == "light_reward_tease"
    )

    tip_profile = tip["reaction_profile"]

    assert (
        tip_profile["reward_depth"]
        == "enhanced"
    )

    subscription = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": (
                    "subscription_created"
                ),
            },
            buyer_memory={
                "buyer_tier": "ACTIVE_BUYER",
            },
        )
    )

    assert subscription["success"] is True

    assert (
        subscription["buyer_tier"]
        == "ACTIVE_BUYER"
    )

    assert (
        subscription["premium_positioning"]
        is True
    )

    assert (
        subscription["cta_strategy"]
        == "subscriber_warmup_no_sell"
    )

    subscription_profile = (
        subscription["reaction_profile"]
    )

    assert (
        subscription_profile[
            "premium_positioning"
        ]
        is True
    )

    assert (
        subscription_profile[
            "exclusivity_level"
        ]
        == "medium"
    )

    escalation = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": (
                    "unlock_confirmation"
                ),
            },
            runtime_state={
                "heat_score": 85,
                "sexual_intensity": 75,
                "buyer_session_active": True,
                "close_mode_active": True,
            },
            buyer_memory={
                "buyer_tier": "HIGH_VALUE",
            },
        )
    )

    assert escalation["success"] is True

    escalation_profile = (
        escalation["reaction_profile"]
    )

    assert (
        escalation_profile[
            "emotional_intensity"
        ]
        == "very_high"
    )

    assert (
        escalation_profile[
            "intimacy_level"
        ]
        == "intimate"
    )

    assert (
        escalation_profile[
            "session_awareness"
        ]
        is True
    )

    assert (
        escalation_profile[
            "close_mode_protection"
        ]
        is True
    )

    assert (
        escalation_profile[
            "escalation_mode"
        ]
        == "emotionally_locked"
    )

    assert (
        escalation_profile[
            "continuation_pressure"
        ]
        == "minimal"
    )

    premium_routing = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": (
                    "purchase_received"
                ),
            },
            runtime_state={
                "premium_sexting_allowed": True,
                "explicit_allowed": True,
                "runtime_mode": (
                    "premium_gate"
                ),
                "intimacy_tier": "premium",
            },
            buyer_memory={
                "buyer_tier": "ACTIVE_BUYER",
            },
        )
    )

    assert premium_routing["success"] is True

    routing = premium_routing[
        "premium_intimacy_routing"
    ]

    assert (
        routing["route"]
        == "premium_eligible"
    )

    assert (
        routing["premium_sexting_allowed"]
        is True
    )

    assert (
        routing["explicit_allowed"]
        is True
    )

    assert (
        routing["adult_model_allowed"]
        is True
    )

    assert (
        routing["runtime_mode"]
        == "premium_gate"
    )

    assert (
        routing["intimacy_tier"]
        == "premium"
    )

    safe_routing = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": (
                    "purchase_received"
                ),
            },
            buyer_memory={
                "buyer_tier": "NON_BUYER",
            },
        )
    )

    assert safe_routing["success"] is True

    safe_route = safe_routing[
        "premium_intimacy_routing"
    ]

    assert (
        safe_route["route"]
        == "safe_chat_only"
    )

    assert (
        safe_route["adult_model_allowed"]
        is False
    )

    assert (
        safe_route["safe_fallback"]
        is True
    )

    whale_retention = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": (
                    "purchase_received"
                ),
            },
            runtime_state={
                "emotional_attachment_score": 85,
            },
            spend_profile={
                "buyer_tier": "WHALE",
                "total_spend": 4200,
                "purchase_count": 67,
            },
        )
    )

    assert whale_retention["success"] is True

    whale_retention_profile = (
        whale_retention[
            "whale_retention_profile"
        ]
    )

    assert (
        whale_retention_profile[
            "whale_mode"
        ]
        is True
    )

    assert (
        whale_retention_profile[
            "retention_mode"
        ]
        == "vip_retention"
    )

    assert (
        whale_retention_profile[
            "low_pressure_mode"
        ]
        is True
    )

    assert (
        whale_retention_profile[
            "premium_only_behavior"
        ]
        is True
    )

    assert (
        whale_retention_profile[
            "vip_treatment"
        ]
        is True
    )

    assert (
        whale_retention_profile[
            "relationship_priority"
        ]
        is True
    )

    assert (
        whale_retention_profile[
            "purchase_depth"
        ]
        == 67
    )

    assert (
        whale_retention_profile[
            "total_spend"
        ]
        == 4200
    )

    adaptive = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": (
                    "unlock_confirmation"
                ),
            },
            runtime_state={
                "heat_score": 95,
                "sexual_intensity": 85,
                "premium_sexting_allowed": True,
                "explicit_allowed": True,
            },
            buyer_memory={
                "buyer_tier": "ACTIVE_BUYER",
            },
        )
    )

    assert adaptive["success"] is True

    adaptive_tone = (
        adaptive["adaptive_reaction_tone"]
    )

    assert (
        adaptive_tone["tone_style"]
        == "emotionally_locked_attachment"
    )

    assert (
        adaptive_tone["emoji_intensity"]
        == "high"
    )

    assert (
        adaptive_tone["message_pacing"]
        == "seductive"
    )

    assert (
        adaptive_tone[
            "emotionally_adaptive"
        ]
        is True
    )

    assert (
        adaptive_tone["premium_tone"]
        is True
    )

    timing = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": (
                    "unlock_confirmation"
                ),
            },
            runtime_state={
                "heat_score": 95,
                "sexual_intensity": 85,
                "premium_sexting_allowed": True,
                "explicit_allowed": True,
            },
            buyer_memory={
                "buyer_tier": "ACTIVE_BUYER",
            },
        )
    )

    assert timing["success"] is True

    timing_profile = (
        timing[
            "reaction_timing_intelligence"
        ]
    )

    assert (
        timing_profile["delay_strategy"]
        == "emotionally_attached"
    )

    assert (
        timing_profile[
            "minimum_delay_seconds"
        ]
        == 90
    )

    assert (
        timing_profile[
            "maximum_delay_seconds"
        ]
        == 300
    )

    assert (
        timing_profile["emotionally_timed"]
        is True
    )

    assert (
        timing_profile["premium_timing"]
        is True
    )

    cta = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": "purchase_received",
            },
            runtime_state={
                "premium_sexting_allowed": True,
                "explicit_allowed": True,
            },
            buyer_memory={
                "buyer_tier": "ACTIVE_BUYER",
            },
        )
    )

    assert cta["success"] is True

    cta_profile = cta[
        "contextual_cta_injection"
    ]

    assert (
        cta_profile["cta_type"]
        == "premium_curiosity_hook"
    )

    assert (
        cta_profile["should_include_cta"]
        is True
    )

    assert (
        cta_profile["cta_pressure"]
        == "soft"
    )

    assert (
        cta_profile["cta_allowed"]
        is True
    )

    whale_cta = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": "purchase_received",
            },
            spend_profile={
                "buyer_tier": "WHALE",
            },
        )
    )

    assert whale_cta["success"] is True

    whale_cta_profile = whale_cta[
        "contextual_cta_injection"
    ]

    assert (
        whale_cta_profile["cta_type"]
        == "no_sell_emotional_continuation"
    )

    assert (
        whale_cta_profile["should_include_cta"]
        is False
    )

    assert (
        whale_cta_profile["cta_allowed"]
        is False
    )

    assert (
        whale_cta_profile["whale_safe"]
        is True
    )

    followup = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": "tip_received",
            },
            spend_profile={
                "buyer_tier": "LOW_SPENDER",
            },
        )
    )

    assert followup["success"] is True

    followup_logic = followup[
        "followup_chaining_logic"
    ]

    assert (
        followup_logic["chain_type"]
        == "tip_reward_followup"
    )

    assert (
        followup_logic["should_chain_followup"]
        is True
    )

    assert (
        followup_logic["followup_delay_minutes"]
        == 45
    )

    assert (
        followup_logic["queue_write_allowed"]
        is False
    )

    assert (
        followup_logic["send_allowed"]
        is False
    )

    whale_followup = (
        service.build_reaction_intelligence(
            monetization_event={
                "event_type": "purchase_received",
            },
            spend_profile={
                "buyer_tier": "WHALE",
            },
        )
    )

    assert whale_followup["success"] is True

    whale_followup_logic = whale_followup[
        "followup_chaining_logic"
    ]

    assert (
        whale_followup_logic["chain_type"]
        == "whale_retention_followup"
    )

    assert (
        whale_followup_logic[
            "followup_delay_minutes"
        ]
        == 180
    )

    assert (
        whale_followup_logic[
            "should_chain_followup"
        ]
        is True
    )
    
    print(
        "✅ 3D.19.1 reaction intelligence expansion passed"
    )


if __name__ == "__main__":
    main()