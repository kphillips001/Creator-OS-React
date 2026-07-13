"""Canonical Content Recommendation Engine for Chat Ready Business Assets."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from app.models.content_recommendation import (
    RecommendationCandidate,
    RecommendationEvidence,
    RecommendationReason,
    RecommendationRequest,
    RecommendationResult,
    RecommendationScore,
)


class ContentRecommendationService:
    """Rank Chat Ready Business Assets without owning delivery or timing."""

    def __init__(
        self,
        *,
        chat_commerce_inventory_service: Any | None = None,
        content_intelligence_service: Any | None = None,
        customer_intelligence_service: Any | None = None,
        business_learning_service: Any | None = None,
        product_strategy_service: Any | None = None,
        commerce_strategy_service: Any | None = None,
        content_commerce_learning_service: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        self.chat_commerce_inventory_service = (
            chat_commerce_inventory_service
            or self._default_chat_commerce_inventory_service()
        )
        self.content_intelligence_service = (
            content_intelligence_service
            or self._default_content_intelligence_service()
        )
        self.customer_intelligence_service = (
            customer_intelligence_service
            or self._default_customer_intelligence_service()
        )
        self.business_learning_service = business_learning_service
        self.product_strategy_service = product_strategy_service
        self.commerce_strategy_service = commerce_strategy_service
        self.content_commerce_learning_service = (
            content_commerce_learning_service
            or self._default_content_commerce_learning_service()
        )
        self.logger = logger

    def recommend(
        self,
        request: RecommendationRequest | None = None,
        **kwargs: Any,
    ) -> RecommendationResult:
        resolved_request = self._with_runtime_learning_context(
            request or RecommendationRequest(**kwargs)
        )
        candidates = self._load_chat_ready_candidates(resolved_request)
        ranked: list[RecommendationCandidate] = []
        rejected: list[RecommendationCandidate] = []

        for candidate in candidates:
            scored = self._score_candidate(candidate, resolved_request)
            if scored.suppressed:
                rejected.append(scored)
            else:
                ranked.append(scored)

        ranked.sort(
            key=lambda item: (
                item.score.total,
                item.confidence,
                -int(item.asset_id),
            ),
            reverse=True,
        )
        rejected.sort(
            key=lambda item: (
                item.score.total,
                item.confidence,
                -int(item.asset_id),
            ),
            reverse=True,
        )

        limited = self._attach_recommendation_ids(
            tuple(ranked[: max(0, int(resolved_request.limit or 0))]),
            resolved_request,
        )
        rejected_with_ids = self._attach_recommendation_ids(
            tuple(rejected),
            resolved_request,
        )
        evidence = tuple(
            item for candidate in limited for item in candidate.evidence
        )
        result = RecommendationResult(
            request=resolved_request,
            ranked_assets=limited,
            rejected_candidates=rejected_with_ids,
            confidence=self._average(item.confidence for item in limited),
            supporting_evidence=evidence,
            business_rationale=tuple(
                dict.fromkeys(
                    reason.rationale
                    for candidate in limited
                    for reason in candidate.reasons
                    if reason.category == "business"
                )
            ),
            customer_rationale=tuple(
                dict.fromkeys(
                    reason.rationale
                    for candidate in limited
                    for reason in candidate.reasons
                    if reason.category in {"customer", "conversation"}
                )
            ),
            content_rationale=tuple(
                dict.fromkeys(
                    reason.rationale
                    for candidate in limited
                    for reason in candidate.reasons
                    if reason.category == "content"
                )
            ),
            metadata={
                "source": "ContentRecommendationService",
                "owner": "ContentRecommendationService",
                "ranks_chat_ready_assets": True,
                "decides_whether_to_sell": False,
                "candidate_count": len(candidates),
                "ranked_count": len(limited),
                "rejected_count": len(rejected_with_ids),
                "learning_context_available": resolved_request.learning_context
                is not None,
                "learning_context_missing": resolved_request.learning_context
                is None,
            },
        )
        self._record_recommendation_result(result)
        return result

    def top_recommendation(
        self,
        request: RecommendationRequest | None = None,
        **kwargs: Any,
    ) -> RecommendationCandidate | None:
        return self.recommend(request, **kwargs).top_candidate

    def _load_chat_ready_candidates(
        self,
        request: RecommendationRequest,
    ) -> tuple[Any, ...]:
        service = self.chat_commerce_inventory_service
        getter = getattr(service, "get_recommendation_candidates", None)
        if not callable(getter):
            return ()
        try:
            return tuple(
                getter(
                    creator_profile_id=request.creator_profile_id,
                    limit=request.candidate_limit,
                )
            )
        except Exception as error:
            self._log("warning", f"[CONTENT RECOMMENDATION] load failed: {error}")
            return ()

    def _score_candidate(
        self,
        candidate: Any,
        request: RecommendationRequest,
    ) -> RecommendationCandidate:
        asset_id = int(getattr(candidate, "asset_id"))
        evidence: list[RecommendationEvidence] = []
        reasons: list[RecommendationReason] = []

        eligibility = self._eligibility(asset_id, request)
        suppression_reasons = list(getattr(eligibility, "block_reasons", ()) or ())
        suppression_reasons.extend(self._runtime_suppression_reasons(candidate, request))
        suppression_reasons = list(dict.fromkeys(suppression_reasons))

        customer_score = self._customer_fit(candidate, request, evidence, reasons)
        conversation_score = self._conversation_fit(candidate, request, evidence, reasons)
        content_score = self._content_fit(asset_id, request, evidence, reasons)
        business_score = self._business_fit(candidate, request, evidence, reasons)
        suppression_penalty = 100.0 if suppression_reasons else 0.0
        base_score = 50.0 if not suppression_reasons else 0.0
        total = (
            base_score
            + customer_score
            + conversation_score
            + content_score
            + business_score
            - suppression_penalty
        )
        confidence = self._confidence(evidence, suppressed=bool(suppression_reasons))
        score = RecommendationScore(
            total=total,
            customer_fit=customer_score,
            conversation_fit=conversation_score,
            content_fit=content_score,
            business_fit=business_score,
            suppression_penalty=suppression_penalty,
            confidence=confidence,
        )
        return RecommendationCandidate(
            asset_id=asset_id,
            source_candidate=candidate,
            score=score,
            confidence=confidence,
            evidence=tuple(evidence),
            reasons=tuple(reasons),
            suppressed=bool(suppression_reasons),
            suppression_reasons=tuple(suppression_reasons),
            product_ids=tuple(str(value) for value in getattr(candidate, "product_ids", ()) or ()),
            experience_ids=tuple(str(value) for value in getattr(candidate, "experience_ids", ()) or ()),
            media_link=getattr(candidate, "media_link", None),
            provider_media_id=getattr(candidate, "provider_media_id", None),
            metadata={
                "chat_registration_id": str(
                    getattr(candidate, "chat_registration_id", "")
                ),
                "source": "ContentRecommendationService",
            },
        )

    def _eligibility(self, asset_id: int, request: RecommendationRequest) -> Any:
        service = self.chat_commerce_inventory_service
        checker = getattr(service, "eligibility_for_asset", None)
        if not callable(checker):
            return None
        try:
            return checker(asset_id, customer_context=request.customer_context)
        except Exception as error:
            self._log(
                "warning",
                f"[CONTENT RECOMMENDATION] eligibility failed asset={asset_id}: {error}",
            )
            return None

    def _runtime_suppression_reasons(
        self,
        candidate: Any,
        request: RecommendationRequest,
    ) -> tuple[str, ...]:
        asset_id = str(getattr(candidate, "asset_id", ""))
        tag = f"chat_asset_{asset_id}"
        contexts = (
            request.customer_context,
            request.conversation_context,
            request.decision_context,
        )
        reasons: list[str] = []
        if self._contains_any(contexts, asset_id, "seen_asset_ids", "delivered_asset_ids"):
            reasons.append("customer_already_seen_asset")
        if self._contains_any(contexts, asset_id, "recently_delivered_asset_ids"):
            reasons.append("recently_delivered_asset")
        if self._contains_any(contexts, asset_id, "recently_recommended_asset_ids"):
            reasons.append("recently_recommended_asset")
        if self._contains_any(contexts, tag, "owned_content_tags", "owned_asset_tags"):
            reasons.append("customer_already_owns_asset")
        if self._contains_any(contexts, tag, "recently_seen_tags", "seen_content_tags"):
            reasons.append("customer_already_seen_asset")
        return tuple(reasons)

    def _customer_fit(
        self,
        candidate: Any,
        request: RecommendationRequest,
        evidence: list[RecommendationEvidence],
        reasons: list[RecommendationReason],
    ) -> float:
        score = 0.0
        context = self._merged_context(
            request.customer_context,
            request.decision_context,
        )
        relationship_stage = self._normalized(
            self._first_value(context, "relationship_stage", "customer_stage")
        )
        if relationship_stage in {"purchaser", "repeat_purchaser", "vip"}:
            score += self._add_evidence(
                evidence,
                "customer",
                "relationship_stage",
                8.0,
                relationship_stage,
                "Customer relationship supports stronger commerce fit.",
            )

        value_tier = self._normalized(
            self._first_value(context, "user_value_tier", "customer_value_tier")
        )
        if value_tier in {"high", "vip", "whale"}:
            score += self._add_evidence(
                evidence,
                "customer",
                "customer_value",
                7.0,
                value_tier,
                "Customer value tier supports stronger asset ranking.",
            )

        intent_score = self._float(self._first_value(context, "intent_score", "score"))
        if intent_score >= 70:
            score += self._add_evidence(
                evidence,
                "customer",
                "high_intent",
                6.0,
                intent_score,
                "Current customer intent is high.",
            )

        preferred_terms = self._terms(
            context.get("preferred_content_theme"),
            context.get("interests"),
            context.get("preferences"),
            context.get("customer_segments"),
        )
        product_ids = tuple(str(value) for value in getattr(candidate, "product_ids", ()) or ())
        experience_ids = tuple(str(value) for value in getattr(candidate, "experience_ids", ()) or ())
        current_product = self._text(
            self._first_value(context, "current_product_id", "product_id")
        )
        current_experience = self._text(
            self._first_value(context, "current_experience_id", "experience_id")
        )
        if current_product and current_product in product_ids:
            score += self._add_evidence(
                evidence,
                "customer",
                "current_product_match",
                8.0,
                current_product,
                "Asset belongs to the customer's current Product context.",
            )
        if current_experience and current_experience in experience_ids:
            score += self._add_evidence(
                evidence,
                "customer",
                "current_experience_match",
                8.0,
                current_experience,
                "Asset belongs to the customer's current Experience context.",
            )
        if preferred_terms:
            overlap = preferred_terms.intersection(
                self._candidate_terms(candidate, request)
            )
            if overlap:
                score += self._add_evidence(
                    evidence,
                    "customer",
                    "preference_match",
                    min(10.0, 4.0 + len(overlap) * 2.0),
                    tuple(sorted(overlap)),
                    "Customer preferences match asset intelligence.",
                )

        if score > 0:
            reasons.append(
                RecommendationReason(
                    "customer",
                    "Customer fit increased ranking.",
                    tuple(item.signal for item in evidence if item.category == "customer"),
                )
            )
        return score

    def _conversation_fit(
        self,
        candidate: Any,
        request: RecommendationRequest,
        evidence: list[RecommendationEvidence],
        reasons: list[RecommendationReason],
    ) -> float:
        terms = self._terms(
            request.conversation_context.get("message_text"),
            request.conversation_context.get("last_user_message"),
            request.decision_context.get("last_user_message"),
            request.decision_context.get("intent_signals"),
        )
        if not terms:
            return 0.0
        overlap = terms.intersection(self._candidate_terms(candidate, request))
        if not overlap:
            return 0.0
        score = self._add_evidence(
            evidence,
            "conversation",
            "conversation_term_match",
            min(12.0, 4.0 + len(overlap) * 2.0),
            tuple(sorted(overlap)),
            "Current conversation matches asset content signals.",
        )
        reasons.append(
            RecommendationReason(
                "conversation",
                "Conversation context matches asset.",
                ("conversation_term_match",),
            )
        )
        return score

    def _content_fit(
        self,
        asset_id: int,
        request: RecommendationRequest,
        evidence: list[RecommendationEvidence],
        reasons: list[RecommendationReason],
    ) -> float:
        intelligence = self._content_intelligence(asset_id)
        if intelligence is None:
            return 0.0
        score = 0.0
        confidence = self._float(getattr(intelligence, "confidence", None))
        if confidence:
            score += self._add_evidence(
                evidence,
                "content",
                "content_intelligence_confidence",
                min(8.0, confidence * 8.0),
                confidence,
                "Content Intelligence confidence is available.",
            )
        if self._terms(
            getattr(intelligence, "themes", ()),
            getattr(intelligence, "tags", ()),
            getattr(intelligence, "keywords", ()),
        ):
            score += self._add_evidence(
                evidence,
                "content",
                "content_descriptors_available",
                6.0,
                True,
                "Content descriptors are available for ranking.",
            )
        technical_quality = getattr(intelligence, "technical_quality", {}) or {}
        if technical_quality.get("has_runtime_media") or technical_quality.get(
            "runtime_exists"
        ):
            score += self._add_evidence(
                evidence,
                "content",
                "runtime_media_available",
                4.0,
                True,
                "Runtime media is available.",
            )
        if score > 0:
            reasons.append(
                RecommendationReason(
                    "content",
                    "Content Intelligence increased ranking.",
                    tuple(item.signal for item in evidence if item.category == "content"),
                )
            )
        return score

    def _business_fit(
        self,
        candidate: Any,
        request: RecommendationRequest,
        evidence: list[RecommendationEvidence],
        reasons: list[RecommendationReason],
    ) -> float:
        asset_id = str(getattr(candidate, "asset_id"))
        score = 0.0
        product_ids = tuple(str(value) for value in getattr(candidate, "product_ids", ()) or ())
        experience_ids = tuple(str(value) for value in getattr(candidate, "experience_ids", ()) or ())
        if product_ids:
            score += self._add_evidence(
                evidence,
                "business",
                "product_relationship",
                4.0,
                product_ids,
                "Asset has Product relationships.",
            )
        if experience_ids:
            score += self._add_evidence(
                evidence,
                "business",
                "experience_relationship",
                3.0,
                experience_ids,
                "Asset has Experience relationships.",
            )

        asset_scores = self._mapping(request.business_context.get("asset_scores"))
        learning_scores = self._mapping(
            self._read(request.learning_context, "asset_scores")
            or self._read(self._read(request.learning_context, "metadata"), "asset_scores")
        )
        asset_profiles = self._mapping(
            self._read(request.learning_context, "asset_profiles")
        )
        raw_business_score = self._first_value(asset_scores, asset_id, int(asset_id))
        if raw_business_score is None:
            raw_business_score = self._first_value(
                learning_scores,
                asset_id,
                int(asset_id),
            )
        if raw_business_score is not None:
            profile = self._mapping(self._first_value(asset_profiles, asset_id, int(asset_id)))
            confidence = self._float(profile.get("confidence"))
            if confidence <= 0:
                confidence = 0.5 if raw_business_score is not None else 0.0
            weight = max(-12.0, min(12.0, self._float(raw_business_score) * confidence))
            score += self._add_evidence(
                evidence,
                "business",
                "business_learning_asset_score",
                weight,
                {
                    "score": raw_business_score,
                    "confidence": confidence,
                    "sample_size": profile.get("sample_size"),
                    "evidence_freshness": profile.get("evidence_freshness"),
                },
                "Business learning changes asset ranking.",
            )

        priority_terms = self._terms(
            request.business_context.get("business_priorities"),
            request.product_strategy_context.get("recommended_objective"),
            request.commerce_strategy_context.get("recommended_objective"),
        )
        if priority_terms:
            overlap = priority_terms.intersection(self._candidate_terms(candidate, request))
            if overlap:
                score += self._add_evidence(
                    evidence,
                    "business",
                    "strategy_priority_match",
                    min(8.0, 3.0 + len(overlap) * 2.0),
                    tuple(sorted(overlap)),
                    "Business strategy priorities match asset signals.",
                )

        if score > 0:
            reasons.append(
                RecommendationReason(
                    "business",
                    "Business evidence increased ranking.",
                    tuple(item.signal for item in evidence if item.category == "business"),
                )
            )
        return score

    def _content_intelligence(self, asset_id: int) -> Any | None:
        service = self.content_intelligence_service
        getter = getattr(service, "get_asset_intelligence", None)
        if not callable(getter):
            return None
        try:
            return getter(asset_id)
        except Exception as error:
            self._log(
                "warning",
                f"[CONTENT RECOMMENDATION] content intelligence failed asset={asset_id}: {error}",
            )
            return None

    def _candidate_terms(
        self,
        candidate: Any,
        request: RecommendationRequest,
    ) -> set[str]:
        asset_id = int(getattr(candidate, "asset_id"))
        intelligence = self._content_intelligence(asset_id)
        values = [
            getattr(candidate, "product_ids", ()),
            getattr(candidate, "experience_ids", ()),
        ]
        if intelligence is not None:
            values.extend(
                [
                    getattr(intelligence, "themes", ()),
                    getattr(intelligence, "tags", ()),
                    getattr(intelligence, "keywords", ()),
                    getattr(intelligence, "mood", None),
                    getattr(intelligence, "setting", None),
                    getattr(intelligence, "activity", None),
                    getattr(intelligence, "outfit", None),
                    getattr(intelligence, "objects", ()),
                    getattr(intelligence, "environment", None),
                    getattr(intelligence, "activities", ()),
                    getattr(intelligence, "clothing", None),
                    getattr(intelligence, "classification", None),
                ]
            )
        values.extend(
            [
                request.business_context.get("asset_terms", {}).get(str(asset_id))
                if isinstance(request.business_context.get("asset_terms"), Mapping)
                else None
            ]
        )
        return self._terms(*values)

    def _confidence(
        self,
        evidence: Iterable[RecommendationEvidence],
        *,
        suppressed: bool,
    ) -> float:
        items = tuple(evidence)
        if suppressed:
            return 0.0
        if not items:
            return 0.35
        categories = {item.category for item in items}
        return min(0.95, 0.35 + len(categories) * 0.12 + len(items) * 0.03)

    @staticmethod
    def _average(values: Iterable[float]) -> float:
        items = tuple(float(value) for value in values)
        return sum(items) / len(items) if items else 0.0

    @staticmethod
    def _add_evidence(
        evidence: list[RecommendationEvidence],
        category: str,
        signal: str,
        weight: float,
        value: Any,
        rationale: str,
    ) -> float:
        evidence.append(
            RecommendationEvidence(
                category=category,
                signal=signal,
                weight=float(weight),
                value=value,
                rationale=rationale,
            )
        )
        return float(weight)

    @staticmethod
    def _contains_any(
        contexts: Iterable[Mapping[str, Any]],
        needle: str,
        *field_names: str,
    ) -> bool:
        for context in contexts:
            for name in field_names:
                values = context.get(name)
                if values is None:
                    continue
                if str(needle) in {str(value) for value in ContentRecommendationService._as_iterable(values)}:
                    return True
        return False

    @staticmethod
    def _terms(*values: Any) -> set[str]:
        terms: set[str] = set()
        for value in values:
            if value is None:
                continue
            if isinstance(value, Mapping):
                iterable = value.values()
            elif isinstance(value, str):
                iterable = value.replace(",", " ").replace(";", " ").split()
            else:
                iterable = ContentRecommendationService._as_iterable(value)
            for item in iterable:
                text = str(item).strip().lower()
                if not text:
                    continue
                for token in text.replace("_", " ").replace("-", " ").split():
                    token = token.strip()
                    if len(token) > 1:
                        terms.add(token)
                terms.add(text)
        return terms

    @staticmethod
    def _as_iterable(value: Any) -> tuple[Any, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        try:
            return tuple(value)
        except TypeError:
            return (value,)

    @staticmethod
    def _merged_context(*contexts: Mapping[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for context in contexts:
            merged.update(dict(context or {}))
        return merged

    @staticmethod
    def _first_value(values: Mapping[Any, Any], *names: Any) -> Any:
        for name in names:
            if name in values and values[name] is not None:
                return values[name]
            text_name = str(name)
            if text_name in values and values[text_name] is not None:
                return values[text_name]
        return None

    @staticmethod
    def _read(value: Any, name: str) -> Any:
        if isinstance(value, Mapping):
            return value.get(name)
        return getattr(value, name, None)

    @staticmethod
    def _mapping(value: Any) -> dict[Any, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _text(value: Any) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _normalized(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _default_chat_commerce_inventory_service(self) -> Any | None:
        try:
            from app.services.chat_commerce_registration_service import (
                ChatCommerceRegistrationService,
            )

            return ChatCommerceRegistrationService()
        except Exception:
            return None

    def _default_content_intelligence_service(self) -> Any | None:
        try:
            from app.services.content_intelligence_service import (
                ContentIntelligenceService,
            )

            return ContentIntelligenceService()
        except Exception:
            return None

    def _default_customer_intelligence_service(self) -> Any | None:
        try:
            from app.services.customer_intelligence_service import (
                CustomerIntelligenceService,
            )

            return CustomerIntelligenceService()
        except Exception:
            return None

    def _default_content_commerce_learning_service(self) -> Any | None:
        try:
            from app.services.content_commerce_learning_service import (
                ContentCommerceLearningService,
            )

            return ContentCommerceLearningService(
                business_learning_service=self.business_learning_service,
            )
        except Exception:
            return None

    def _with_runtime_learning_context(
        self,
        request: RecommendationRequest,
    ) -> RecommendationRequest:
        if request.learning_context is not None:
            return request
        context = None
        for service in (
            self.business_learning_service,
            self.content_commerce_learning_service,
        ):
            builder = getattr(service, "build_runtime_learning_context", None)
            if not callable(builder):
                continue
            try:
                context = builder(
                    request=request,
                    creator_profile_id=request.creator_profile_id,
                    customer_context=request.customer_context,
                    conversation_context=request.conversation_context,
                )
            except Exception as error:
                self._log(
                    "warning",
                    f"[CONTENT RECOMMENDATION] learning context failed: {error}",
                )
                context = None
            if context is not None:
                break
        if context is None:
            metadata = {
                **dict(request.metadata or {}),
                "learning_context_missing": True,
            }
            return replace(request, metadata=metadata)
        metadata = {
            **dict(request.metadata or {}),
            "learning_context_missing": False,
        }
        return replace(request, learning_context=context, metadata=metadata)

    def _attach_recommendation_ids(
        self,
        candidates: tuple[RecommendationCandidate, ...],
        request: RecommendationRequest,
    ) -> tuple[RecommendationCandidate, ...]:
        service = self.content_commerce_learning_service
        id_factory = getattr(service, "recommendation_id_for", None)
        updated: list[RecommendationCandidate] = []
        for candidate in candidates:
            recommendation_id = None
            if callable(id_factory):
                try:
                    recommendation_id = id_factory(
                        asset_id=candidate.asset_id,
                        request_context=request.to_context(),
                        explicit=candidate.metadata.get("recommendation_id"),
                    )
                except Exception:
                    recommendation_id = None
            metadata = {
                **dict(candidate.metadata or {}),
                "recommendation_id": recommendation_id,
            }
            updated.append(replace(candidate, metadata=metadata))
        return tuple(updated)

    def _record_recommendation_result(self, result: RecommendationResult) -> None:
        service = self.content_commerce_learning_service
        recorder = getattr(service, "record_recommendation_result", None)
        if not callable(recorder):
            return
        try:
            recorder(result)
        except Exception as error:
            self._log(
                "warning",
                f"[CONTENT RECOMMENDATION] recommendation recording failed: {error}",
            )

    def _log(self, level: str, message: str) -> None:
        logger = self.logger
        if logger is None:
            return
        writer = getattr(logger, level, None)
        if callable(writer):
            writer(message)
