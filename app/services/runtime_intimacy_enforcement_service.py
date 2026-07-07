class RuntimeIntimacyEnforcementService:
    """
    3D.10.15B — Runtime Intimacy Enforcement

    Builds GPT runtime rules from intimacy context.
    This does NOT replace GPTService.
    It injects strict escalation ceilings into GPTService.
    """

    def build_instruction(self, user_memory: dict) -> str:
        intimacy = user_memory.get("intimacy_context", {}) or {}

        intimacy_tier = intimacy.get("intimacy_tier", "cold")
        spender_confidence = intimacy.get("spender_confidence", "low")
        premium_sexting_allowed = bool(
            intimacy.get("premium_sexting_allowed", False)
        )
        explicit_allowed = bool(
            intimacy.get("explicit_allowed", False)
        )
        escalation_priority = intimacy.get(
            "escalation_priority", "low"
        )
        runtime_mode = intimacy.get("runtime_mode", "safe_chat")
        allowed_behaviors = intimacy.get("allowed_behaviors", [])
        blocked_behaviors = intimacy.get("blocked_behaviors", [])

        return f"""
--- RUNTIME INTIMACY ENFORCEMENT (3D.10.15B) ---

INTIMACY PROFILE:
- Intimacy tier: {intimacy_tier}
- Spender confidence: {spender_confidence}
- Premium sexting allowed: {premium_sexting_allowed}
- Explicit allowed: {explicit_allowed}
- Escalation priority: {escalation_priority}
- Runtime mode: {runtime_mode}
- Allowed behaviors: {allowed_behaviors}
- Blocked behaviors: {blocked_behaviors}

STRICT ESCALATION CEILING RULES:
- Runtime intimacy rules override persona, tone, mode, and offer behavior.
- Never exceed the intimacy tier.
- Never generate explicit or hardcore sexual wording unless explicit_allowed is True.
- If premium_sexting_allowed is False, do not move into paid sexting-style escalation.
- If spender_confidence is low, keep replies playful, warm, teasing, and non-explicit.
- If intimacy_tier is cold or warm, stay PG-13 / suggestive only.
- If intimacy_tier is hot but explicit_allowed is False, build tension without graphic wording.
- If runtime_mode is safe_chat, do not escalate sexually.
- If runtime_mode is tease_only, flirt lightly but do not intensify.
- If runtime_mode is premium_gate, imply exclusivity but do not provide explicit content in chat.
- If runtime_mode is explicit_allowed, explicit escalation is allowed only if explicit_allowed is True.

BLOCKED BEHAVIOR RULES:
- Do not perform any blocked behavior listed above.
- If user asks for blocked behavior, redirect with playful restraint.
- Do not say policy, rules, blocked behavior, or intimacy tier to the user.

FINAL VALIDATION:
Before sending the final response:
- Check if the response violates explicit_allowed.
- Check if it exceeds intimacy_tier.
- Check if it ignores blocked_behaviors.
- If it violates any runtime intimacy rule, rewrite it safer and lower intensity.
"""