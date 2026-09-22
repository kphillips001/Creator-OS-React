"""Deterministic, durable question semantics shared by prompts and validators."""
import hashlib
import re

from app.services.foreground_relevance_contract import ForegroundRelevanceContract as Foreground


class QuestionObligationContract:
    VERSION = 'QUESTION_OBLIGATION_V1'

    @classmethod
    def resolve(cls, message, history=()):
        text = Foreground.normalize(message)
        prior = [str(m.get('content') or '') for m in history
                 if isinstance(m, dict) and m.get('role') in ('user', 'assistant')
                 and str(m.get('content') or '').strip() != text][-2:]
        kind, subject = 'EXISTING_DOMAIN', None
        continuation = re.search(r'(?:^|\b)(?:and\s+)?(?:then|what next|now what)\s*\?\s*$', text, re.I)
        preference = re.search(r'\b(?:do you (?:like|love|enjoy|prefer)|are you into)\s+(.+?)[?.!]*$', text, re.I)
        unresolved = bool(re.fullmatch(r'(?:what|why|how|huh|which|that|this|really|what do you want from me)\s*\?', text, re.I))
        if Foreground.location_question(text):
            kind, subject = 'LOCATION', 'public/coarse location'
        elif preference:
            kind, subject = 'PREFERENCE', preference.group(1).rstrip('?.!')
        elif continuation:
            subject = text[:continuation.start()].strip(' ,.!') or (prior[-1] if prior else '')
            kind = 'CONTINUATION' if subject else 'CLARIFICATION'
        elif (re.fullmatch(r'what do you want from me\s*\?', text, re.I)
              and prior and re.search(r'\b(?:need|want|ask|request)\b', prior[-1], re.I)):
            kind, subject = 'CONTEXTUAL_EXPECTATION', prior[-1]
        elif unresolved or ('?' in text and not re.search(
                r'\b(?:who|what|where|when|why|how|do|does|did|are|is|was|were|have|has|can|could|would|will)\b', text, re.I)):
            # No inferred intent/domain merely from a question mark or vague pronoun.
            kind, subject = 'CLARIFICATION', text
        meanings = {
            'LOCATION': ('ANSWER_LOCATION', 'Answer the location question with authorized coarse location or a truthful privacy boundary.'),
            'PREFERENCE': ('ANSWER_PREFERENCE', 'State a preference about the requested subject; do not invent biographical evidence.'),
            'CONTINUATION': ('RESPOND_TO_CONTINUATION', 'Respond to what follows from the immediately preceding context with a relevant stance, next conversational step, or truthful boundary. No explicit enactment or invented commitments are required.'),
            'CLARIFICATION': ('REQUEST_CLARIFICATION', 'The referent or intended question is unresolved. Ask one specific truthful clarification about that referent; do not pretend a domain is known.'),
            'CONTEXTUAL_EXPECTATION': ('EXPLAIN_EXISTING_EXPECTATION', 'Explain the expectation already expressed in relevantContext. Do not invent a new demand or commercial commitment.'),
            'EXISTING_DOMAIN': ('ANSWER_CURRENT_QUESTION', 'Answer the foreground question using the existing domain authority and factual/policy constraints; clarify only a genuinely missing referent.'),
        }
        act, criteria = meanings[kind]
        return {'version': cls.VERSION, 'obligation': 'ANSWER_DIRECT_QUESTION',
                'meaning': kind, 'subject': subject, 'requiredAct': act,
                'answerCriteria': criteria, 'clarificationRequired': kind == 'CLARIFICATION',
                'foreground': text, 'relevantContext': prior,
                'foregroundSha256': hashlib.sha256(text.encode()).hexdigest(),
                'source': 'DETERMINISTIC_CURRENT_QUESTION_AND_CONTEXT'}

    @classmethod
    def for_message(cls, message, saved=None, history=()):
        digest = hashlib.sha256(Foreground.normalize(message).encode()).hexdigest()
        if (isinstance(saved, dict) and saved.get('version') == cls.VERSION
                and saved.get('foregroundSha256') == digest):
            return dict(saved)
        return cls.resolve(message, history)

    @classmethod
    def accepts(cls, contract, candidate, *, existing_answer=False):
        text = Foreground.normalize(candidate)
        kind = contract['meaning']
        # A counter-question is not an answer. A necessary clarification is a
        # separate resolved act, never a blanket exception for engagement questions.
        statement = re.split(r'(?<=[.!])\s+|\?', text)[0]
        if '?' in text and not re.search(r'[.!]\s+', text):
            statement = ''
        if kind == 'CLARIFICATION':
            return bool(re.search(r'\b(?:what (?:do you mean|are you referring to)|which .{1,35}(?:mean|referring)|could you clarify|can you clarify|do you mean)\b', text, re.I)) and '?' in text
        if kind == 'LOCATION':
            return Foreground.location_answer(statement) or bool(existing_answer)
        if kind == 'PREFERENCE':
            stance = bool(re.search(r"\b(?:i (?:like|love|enjoy|prefer|don't|do not)|i'm (?:into|not)|yes|yeah|no|not really)\b", statement, re.I))
            tokens = re.findall(r'[a-z]{3,}', str(contract.get('subject') or '').lower())
            grounded = any(re.search(r'\b' + re.escape(t) + r'\b', statement, re.I) for t in tokens)
            return bool(stance and (grounded or re.match(r'^(?:yes|yeah|no|not really)\b', statement, re.I)))
        if kind == 'CONTINUATION':
            boundary = bool(re.search(r"\b(?:let's (?:keep|stay|slow)|i (?:prefer|want|would|don't|can't|won't)|i'd|we (?:can|could)|next|then)\b", statement, re.I))
            reflection = bool(re.search(r'\b(?:painting|painted|quite the picture|bold move|vivid image|your mind works)\b', statement, re.I))
            return bool(boundary and not reflection)
        if kind == 'CONTEXTUAL_EXPECTATION':
            tokens = set(re.findall(r'[a-z]{4,}', str(contract.get('subject') or '').lower())) - {'want', 'need', 'from', 'that', 'this', 'just'}
            return bool(re.search(r"\b(?:i (?:want|need|meant|was asking)|just|only)\b", statement, re.I)
                        and any(re.search(r'\b' + re.escape(t) + r'\b', statement, re.I) for t in tokens))
        return bool(existing_answer)
