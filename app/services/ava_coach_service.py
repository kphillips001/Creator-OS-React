"""Deterministic, observational conversation coaching for operator review."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any
from uuid import UUID

from app.repositories.ava_coach_repository import AvaCoachRepository


class AvaCoachService:
    STOPWORDS = {
        "about", "after", "again", "also", "and", "are", "been", "but",
        "can", "did", "does", "for", "from", "have", "hello", "here", "hey",
        "how", "into", "just", "like", "more", "not", "really", "that",
        "the", "their", "them", "then", "there", "they", "this", "was",
        "what", "when", "where", "which", "with", "would", "you", "your",
    }

    def __init__(self, repository: Any | None = None) -> None:
        self.repository = repository or AvaCoachRepository()

    def analyze(self, account_id: int) -> dict:
        messages = self.repository.conversation_messages(account_id)
        overview, insights, recommendations = self._analyze(messages)
        timestamps = [item.get("sent_at") for item in messages if item.get("sent_at")]
        snapshot = self.repository.create_snapshot(
            account_id=account_id, overview=overview,
            evidence_metadata={
                "source": "chat_messages",
                "messageIds": [item["id"] for item in messages],
                "method": "deterministic_phase_1",
                "behaviorMutation": False,
            },
            period_start=min(timestamps) if timestamps else None,
            period_end=max(timestamps) if timestamps else None,
        )
        for insight in insights:
            self.repository.add_insight(
                snapshot_id=snapshot["snapshot_id"], account_id=account_id,
                insight=insight,
            )
        target = self.repository.target_version()
        for recommendation in recommendations:
            self.repository.upsert_recommendation(
                account_id=account_id, target_version_id=target["version_id"],
                recommendation=recommendation,
            )
        return self.dashboard(account_id)

    def dashboard(self, account_id: int) -> dict:
        snapshot = self.repository.latest_snapshot(account_id)
        return {
            "overview": snapshot.get("overview") if snapshot else self._empty_overview(),
            "snapshot": snapshot,
            "insights": (
                self.repository.insights(snapshot["snapshot_id"]) if snapshot else []
            ),
            "recommendations": self.repository.recommendations(account_id),
            "appliedImprovements": self.repository.improvements(account_id),
            "versions": self.repository.versions(),
            "observationalOnly": True,
        }

    def transition(self, recommendation_id: UUID, action: str) -> dict:
        normalized = action.upper()
        if normalized == "APPROVE":
            return self.repository.approve_and_apply(recommendation_id)
        if normalized not in {"REJECT", "DISMISS"}:
            raise ValueError("Unsupported coaching recommendation action.")
        return self.repository.transition(
            recommendation_id,
            "REJECTED" if normalized == "REJECT" else "DISMISSED",
        )

    def edit_recommendation(
        self, recommendation_id: UUID, *, title: str, description: str,
    ) -> dict:
        clean_title = title.strip()
        clean_description = description.strip()
        if not clean_title or not clean_description:
            raise ValueError("Recommendation title and text are required.")
        return self.repository.edit_recommendation(
            recommendation_id, title=clean_title,
            description=clean_description,
        )

    @classmethod
    def _analyze(cls, messages: list[dict]) -> tuple[dict, list[dict], list[dict]]:
        by_thread: dict[Any, list[dict]] = defaultdict(list)
        for message in messages:
            by_thread[message["thread_id"]].append(message)
        outbound = [item for item in messages if item.get("direction") == "outbound"]
        inbound = [item for item in messages if item.get("direction") == "inbound"]
        topic_counts: Counter[str] = Counter()
        topic_message_ids: dict[str, list[int]] = defaultdict(list)
        topic_threads: dict[str, set[Any]] = defaultdict(set)
        for message in messages:
            words = {
                word.lower() for word in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", message.get("text") or "")
                if word.lower() not in cls.STOPWORDS
            }
            for word in words:
                topic_counts[word] += 1
                topic_threads[word].add(message["thread_id"])
                if len(topic_message_ids[word]) < 10:
                    topic_message_ids[word].append(message["id"])

        consecutive_questions: list[list[int]] = []
        callback_ids: list[int] = []
        repeated_greeting_threads: list[Any] = []
        openings: list[dict] = []
        continued = 0
        opportunities = 0
        returning = 0
        endings = {"ava": 0, "visitor": 0, "unknown": 0}
        for thread_id, thread in by_thread.items():
            days = {item["sent_at"].date() for item in thread if item.get("sent_at")}
            returning += int(len(days) > 1)
            greeting_count = 0
            first_outbound = next((item for item in thread if item.get("direction") == "outbound"), None)
            if first_outbound:
                openings.append(first_outbound)
            for index, item in enumerate(thread):
                text = (item.get("text") or "").strip()
                lowered = text.lower()
                if item.get("direction") == "outbound":
                    if any(token in lowered for token in ("last time", "you mentioned", "remember when")):
                        callback_ids.append(item["id"])
                    if re.match(r"^(hi|hey|hello)\b", lowered):
                        greeting_count += 1
                    if index + 1 < len(thread):
                        opportunities += 1
                        if thread[index + 1].get("direction") == "inbound":
                            continued += 1
                    if (
                        index + 1 < len(thread)
                        and thread[index + 1].get("direction") == "outbound"
                        and "?" in text and "?" in (thread[index + 1].get("text") or "")
                    ):
                        consecutive_questions.append([item["id"], thread[index + 1]["id"]])
            if greeting_count > 1:
                repeated_greeting_threads.append(thread_id)
            if thread:
                endings[
                    "ava" if thread[-1].get("direction") == "outbound"
                    else "visitor" if thread[-1].get("direction") == "inbound"
                    else "unknown"
                ] += 1

        top_topics = [
            {
                "topic": topic, "mentions": count, "messageCount": count,
                "conversationCount": len(topic_threads[topic]),
                "messageIds": topic_message_ids[topic],
                "trend": None,
            }
            for topic, count in topic_counts.most_common(8)
        ]
        overview = {
            "totalConversationsReviewed": len(by_thread),
            "totalMessagesReviewed": len(messages),
            "averageConversationLength": round(len(messages) / len(by_thread), 1) if by_thread else 0,
            "returningVisitors": returning,
            "topicsDiscussed": top_topics,
            "conversationEndings": endings,
            "questionsAsked": sum((item.get("text") or "").count("?") for item in outbound),
            "conversationContinuationRate": round(continued / opportunities * 100, 1) if opportunities else 0,
            "inboundMessages": len(inbound),
            "outboundMessages": len(outbound),
        }
        insights: list[dict] = []
        recommendations: list[dict] = []
        if top_topics:
            insights.append(cls._insight(
                "TOPICS", "Recurring conversation topics",
                "These topics appeared most often in the reviewed message evidence.",
                {"topics": top_topics, "sampleSize": len(messages)},
                cls._confidence(len(messages), 40),
            ))
        if opportunities >= 5 and continued / opportunities >= 0.6:
            insights.append(cls._insight(
                "POSITIVE_STRENGTH", "Ava kept conversations moving",
                "Visitors replied after a majority of Ava's eligible messages in the reviewed evidence.",
                {
                    "continuedMessages": continued,
                    "eligibleMessages": opportunities,
                    "continuationRate": overview["conversationContinuationRate"],
                    "sampleSize": opportunities,
                },
                cls._confidence(opportunities, 20),
            ))
        if callback_ids:
            insights.append(cls._insight(
                "POSITIVE_STRENGTH", "Ava referenced prior context",
                "Ava used explicit callbacks to earlier conversation context.",
                {"messageIds": callback_ids, "sampleSize": len(callback_ids)},
                cls._confidence(len(callback_ids), 5),
            ))
        if returning:
            insights.append(cls._insight(
                "POSITIVE_STRENGTH", "Returning visitors stayed engaged",
                "Conversation history contains visitors active on more than one day.",
                {
                    "returningConversationCount": returning,
                    "sampleSize": len(by_thread),
                },
                cls._confidence(returning, 5),
            ))
        if consecutive_questions:
            evidence = {
                "occurrences": len(consecutive_questions),
                "messageIdPairs": consecutive_questions[:20],
                "sampleSize": len(consecutive_questions),
            }
            insights.append(cls._insight(
                "QUESTION_PATTERN", "Consecutive questions observed",
                "Ava sent question-bearing replies consecutively in the same conversation.",
                evidence, cls._confidence(len(consecutive_questions), 3),
            ))
            recommendations.append(cls._recommendation(
                "reduce_consecutive_questions", "Reduce consecutive questions",
                "Prefer one clear question at a time when the conversation evidence shows consecutive prompts.",
                evidence, cls._confidence(len(consecutive_questions), 3),
                "Make replies feel less interrogative and leave clearer room for a response.",
            ))
        if returning and not callback_ids:
            evidence = {
                "returningConversationCount": returning,
                "priorConversationCallbackMessageIds": callback_ids,
                "sampleSize": returning,
            }
            recommendations.append(cls._recommendation(
                "increase_prior_callbacks", "Use more callbacks to prior conversations",
                "No explicit prior-conversation callback was observed in conversations active on multiple days.",
                evidence, cls._confidence(returning, 3),
                "Improve continuity for returning visitors without changing Ava's personality.",
            ))
        long_openings = [item for item in openings if len(item.get("text") or "") > 240]
        if long_openings:
            evidence = {
                "openingMessageIds": [item["id"] for item in long_openings],
                "lengths": [len(item.get("text") or "") for item in long_openings],
                "thresholdCharacters": 240,
                "sampleSize": len(openings),
            }
            recommendations.append(cls._recommendation(
                "shorten_opening_replies", "Shorten opening replies",
                "Observed opening replies exceeded the evidence threshold.",
                evidence, cls._confidence(len(long_openings), 3),
                "Create a lighter opening that is easier to continue.",
            ))
        if repeated_greeting_threads:
            evidence = {
                "threadIds": repeated_greeting_threads,
                "threadCount": len(repeated_greeting_threads),
                "sampleSize": len(by_thread),
            }
            recommendations.append(cls._recommendation(
                "avoid_repeated_greetings", "Avoid repeating greetings",
                "Multiple greeting openings were observed inside the same conversation.",
                evidence, cls._confidence(len(repeated_greeting_threads), 2),
                "Make ongoing conversations feel more continuous.",
            ))
        return overview, insights, recommendations

    @staticmethod
    def _confidence(observations: int, high_at: int) -> float:
        return round(min(0.95, max(0.35, observations / max(1, high_at))), 3)

    @staticmethod
    def _insight(kind: str, title: str, description: str, evidence: dict, confidence: float) -> dict:
        return {
            "insight_type": kind, "title": title, "description": description,
            "evidence": evidence, "confidence": confidence,
        }

    @staticmethod
    def _recommendation(
        key: str, title: str, description: str, evidence: dict,
        confidence: float, expected_impact: str,
    ) -> dict:
        return {
            "recommendation_key": key, "title": title,
            "description": description, "evidence": evidence,
            "confidence": confidence, "expected_impact": expected_impact,
        }

    @staticmethod
    def _empty_overview() -> dict:
        return {
            "totalConversationsReviewed": 0, "totalMessagesReviewed": 0,
            "averageConversationLength": 0, "returningVisitors": 0,
            "topicsDiscussed": [], "conversationEndings": {
                "ava": 0, "visitor": 0, "unknown": 0,
            },
            "questionsAsked": 0, "conversationContinuationRate": 0,
            "inboundMessages": 0, "outboundMessages": 0,
        }
