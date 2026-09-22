"""Consolidate existing obligation types; freshness outranks all old evidence."""


class OrdinaryResponseObligationService:
    VERSION = 'ORDINARY_OBLIGATION_V1'

    @classmethod
    def decide(cls, operation, diagnostics=None, *, fresh=True):
        from app.services.gpt_service import GPTService
        delivery = dict(getattr(operation, 'delivery_payload', None) or {})
        style = dict((diagnostics or {}).get('conversationStyle') or {})
        visual = (diagnostics or {}).get('current_turn_visual_context') or delivery.get('current_turn_visual_context') or {}
        sources = {
            'burst': list(getattr(operation, 'burst_obligations', None) or ()),
            'burstMember': list(getattr(operation, 'burst_member_obligations', None) or ()),
            'candidateTurn': list(style.get('turnObligations') or ()),
            'canonicalTurnAuthority': list(GPTService.authoritative_turn_obligations(
                str(getattr(operation, 'inbound_message_text', '') or ''), visual_context=visual)),
        }
        obligations = sorted({str(o) for values in sources.values() for o in values if o})
        from app.services.question_obligation_contract import QuestionObligationContract
        question_contract = QuestionObligationContract.for_message(
            getattr(operation, 'inbound_message_text', '') or '', style.get('questionObligation'))
        meaningful = dict(delivery.get('attentionInvestment') or {}).get('meaningfulObligation')
        return {'version': cls.VERSION, 'source': 'GPTService.authoritative_turn_obligations+durable_turn_evidence',
                'required': bool(fresh and (obligations or meaningful is True)),
                'obligations': obligations if fresh else [],
                'questionObligation': question_contract if fresh and 'ANSWER_DIRECT_QUESTION' in obligations else None, 'sources': sources,
                'fresh': fresh, 'meaningfulObligation': meaningful,
                'contradictionResolved': bool(obligations and meaningful is False),
                'precedence': 'FRESHNESS_THEN_EXPLICIT_OBLIGATIONS_THEN_POSITIVE_ATTENTION'}

    @staticmethod
    def validate_self_photo(style, response, obligation):
        """Add the canonical multimodal obligation to existing final quality evidence."""
        import re
        if 'ACKNOWLEDGE_SELF_PHOTO' not in obligation['obligations']:
            return style
        style = dict(style)
        required = list(dict.fromkeys([*(style.get('turnObligations') or []), 'ACKNOWLEDGE_SELF_PHOTO']))
        text = str(response or '').replace("’", "'")
        # Interpret each appearance adjective locally. A positive negation is
        # evidence of reassurance; another unnegated insult still rejects it.
        negative = r"ugly|hideous|disgusting|unattractive|bad[- ]looking"
        positive_negation = re.compile(
            rf"\b(?:not|never|hardly|anything but|far from|nothing)(?:\s+(?:at all|even|remotely|really|exactly))*(?:\s+an?)?\s+(?:{negative})\b", re.I)
        reassurance = bool(positive_negation.search(text))
        remainder = positive_negation.sub('', text)
        insult = bool(re.search(rf"\b(?:{negative})\b", remainder, re.I))
        denied_compliment = bool(re.search(
            r"\b(?:not|aren't|isn't|don't)(?:\s+(?:very|really|particularly|exactly))?\s+(?:look\s+)?(?:handsome|cute|good[- ]looking|good|great|nice)\b", text, re.I))
        # Negated cognition is not an actual compliment (e.g. "I won't say you're not ugly").
        negated_reassurance = bool(re.search(
            r"\b(?:can't|cannot|won't|wouldn't|don't|not going to)\s+(?:honestly\s+)?(?:say|call|think|pretend)\b[^.!?]{0,45}\bnot\s+(?:ugly|bad[- ]looking|unattractive)\b", text, re.I))
        accepted = bool(reassurance or re.search(r"\b(?:you(?:'re| are) (?:handsome|cute|good[- ]looking)|you look (?:good|great|nice|handsome|cute)|(?:nice|lovely|good|great) to (?:finally )?see you|face to (?:the|a) (?:name|chat|messages)|(?:your|that) (?:smile|face)|handsome|cutie|(?:glad|happy) you (?:shared|sent)|thanks for (?:the (?:photo|picture)|sharing))\b", text, re.I))
        if insult or denied_compliment or negated_reassurance:
            accepted = False
        satisfied = set(style.get('satisfiedTurnObligations') or [])
        missing = set(style.get('unsatisfiedTurnObligations') or [])
        satisfied.discard('ACKNOWLEDGE_SELF_PHOTO'); missing.discard('ACKNOWLEDGE_SELF_PHOTO')
        (satisfied if accepted else missing).add('ACKNOWLEDGE_SELF_PHOTO')
        style.update(turnObligations=required, satisfiedTurnObligations=sorted(satisfied),
                     unsatisfiedTurnObligations=sorted(missing), turnObligationsSatisfied=not missing)
        return style
