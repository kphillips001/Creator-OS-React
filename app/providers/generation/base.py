"""Base interfaces and shared helpers for generation providers."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import urlparse

import requests

from app.models.render_policy import RenderPolicy
from app.prompts.prompt_builder import SOCIAL_CLOSE_FRAMING_RENDER_LOCK
from app.models.generation_engine import (
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    new_generation_id,
)
from app.services.seedream_premium_render_locks import (
    enforce_explicit_render_lock,
    enforce_premium_render_body_lock,
)
from app.services.photoshoot_render_locks import enforce_photoshoot_safe_render_lock
from app.services.hosted_asset_reference_service import HostedAssetReferenceService
from app.services.canonical_facial_naturalism import (
    ensure_canonical_facial_naturalism,
)


TRANSPORT_LOGGER = logging.getLogger("creator_os.transport")


class GenerationProviderError(RuntimeError):
    """Raised when a provider cannot submit, poll, or parse a request."""


class WaveSpeedSubmissionAmbiguousError(GenerationProviderError):
    stage = "wavespeed_submission"
    retryable = True
    may_have_been_accepted = True


class SafeTransportError(GenerationProviderError):
    retryable = True
    may_have_been_accepted = False

    def __init__(self, message: str, *, stage: str):
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True)
class ProviderCapabilities:
    supported_generation_types: tuple[str, ...]
    supports_images: bool = True
    supports_video: bool = False
    supports_cancel: bool = False
    max_images: int = 1
    max_reference_images: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderMetadata:
    provider_id: str
    display_name: str
    provider_family: str
    endpoint: str | None
    enabled: bool
    capabilities: ProviderCapabilities
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderSubmission:
    provider_request_id: str
    raw_response: Mapping[str, Any]
    generation_recipe_id: str | None = None


@dataclass(frozen=True)
class ProviderPollResult:
    provider_request_id: str
    status: str
    raw_response: Mapping[str, Any]
    output_references: tuple[str, ...] = ()
    failure_reason: str | None = None


class HttpClient(Protocol):
    def post(self, url: str, **kwargs): ...

    def get(self, url: str, **kwargs): ...


class GenerationProvider:
    provider_id: str
    display_name: str
    capabilities: ProviderCapabilities

    def metadata(self) -> ProviderMetadata:
        raise NotImplementedError

    def validate_request(self, request: GenerationRequest) -> None:
        raise NotImplementedError

    def submit_generation(self, request: GenerationRequest) -> ProviderSubmission:
        raise NotImplementedError

    def poll_status(self, submission: ProviderSubmission) -> ProviderPollResult:
        raise NotImplementedError

    def retrieve_result(
        self,
        request: GenerationRequest,
        submission: ProviderSubmission,
        poll_result: ProviderPollResult,
    ) -> GenerationResult:
        raise NotImplementedError

    def cancel_job(self, provider_request_id: str) -> Mapping[str, Any]:
        raise NotImplementedError

    def execute(self, request: GenerationRequest) -> GenerationResult:
        self.validate_request(request)
        submission = self.submit_generation(request)
        poll_result = self.poll_status(submission)
        return self.retrieve_result(request, submission, poll_result)

    def dispatch(self, request: GenerationRequest) -> GenerationResult:
        return self.execute(request)


class WaveSpeedProviderBase(GenerationProvider):
    provider_family = "wavespeed"
    result_url_template = "https://api.wavespeed.ai/api/v3/predictions/{request_id}/result"
    api_key_env = "WAVESPEED_API_KEY"
    media_upload_endpoint = "https://api.wavespeed.ai/api/v3/media/upload/binary"
    provider_reference_host = "wavespeed_media"
    lifecycle = "ACTIVE"
    PREMIUM_RENDER_BODY_LOCK = """
FINAL REFERENCE BODY LOCK - NON-NEGOTIABLE:
CANONICAL AVA FACE + BODY IDENTITY:
Use the reference image as the identity, face, hair, skin-tone, body-size, body-shape, and bust-size source of truth only.
Preserve the exact same woman, face, long dark loose hair, same natural sun-kissed skin tone as the reference image, body size, body weight, and recognizable silhouette.
Hair must be worn down with a soft center part or natural side part, smooth flat natural top, and loose flowing dark hair over her shoulders or down her back.
Keep the scalp area natural and low-profile, with no lifted tied hairstyle and no tall hair shape.
Do not create a bun, hairbun, topknot, ponytail, updo, tied-up hair, piled hair, messy crown, lifted hair knot, or any tall hair shape.
The top of her hair must remain smooth, flat, natural, and low-profile, with no raised tied silhouette.
Do NOT copy the reference setting, location, background, water, boat, dock, railings, trees, cabin, rocks, room, furniture, props, lighting, outfit, pose, or camera angle unless the written prompt explicitly asks for those exact elements.
The written prompt is the source of truth for generated scene, wardrobe, nudity state, shower/pool/bedroom/hotel/indoor/outdoor setting, pose, lighting, and background.
If the prompt asks for shower, bathroom, bedroom, hotel, couch, pool, or any non-boat scene, do not include boat, lake, dock, marina, railing, cabin, natural-water background, or outdoor boat-deck elements from the reference image.
If the written prompt asks for nude/topless/shower content, do not preserve clothing from the reference image.
Preserve visibly large natural D-cup breasts with full volume, upper and lower fullness, rounded natural shape, bust projection, and natural cleavage when clothing or framing allows it.
Do not reduce breast size, flatten the chest, hide bust volume, or make her appear smaller-busted.
Preserve feminine hourglass body, same waist-to-hip proportions, hip width, thigh proportions, shoulder width, and bust-to-waist ratio.
Preserve the reference skin tone exactly across face, chest, arms, waist, hips, and legs when visible; keep it natural, even, sun-kissed, and photorealistic.
Use medium-close creator framing: close-medium, waist-up, head-to-hips, head-to-upper-thigh, upper-thigh, or intimate seated portrait framing.
Keep her full face and full head inside frame with smooth natural hair top visible and clean headroom above hair.
If the composition cannot fit face, smooth hair top, bust, waist, and hips at the requested crop distance, pull the camera back slightly.
Reject wide bed shots, wide room shots, distant mattress compositions, distant full-body shots, scenery-dominant lake/pool/landscape shots, and any framing where environment dominates the creator.
Unless the prompt explicitly asks for a wide shot, do not create a wide shot.
Avoid cropped-off forehead, missing top of head, face pressed against the top edge, hair touching the border, tall hair shapes, and body cues cropped away.
Do not use side/rear all-fours angles that hide or minimize the bust; if using side/rear body orientation, keep the chest, bust, face, and upper torso still visible and prominent.
Preserve exact facial identity, facial structure, eyes, nose, lips, jawline, cheekbones, smile shape, and natural facial proportions.
Keep the face photorealistic, natural, anatomically correct, and consistent with the selected expression variation.
Allow subtle natural human asymmetry in expression while preserving facial geometry.
Avoid goofy, silly, cartoonish, distorted, uncanny, melted, deformed, cross-eyed, or over-exaggerated facial expressions.
""".strip()
    CLOTHED_PREMIUM_WARDROBE_LOCK = """
CLOTHED PREMIUM WARDROBE LOCK - NON-NEGOTIABLE:
This is a clothed premium teaser request, not a nude or topless request.
The written outfit, clothing, lingerie, or wardrobe in the prompt is the source of truth and must remain visibly worn on the body.
Do not remove the clothing. Do not replace the requested outfit with nudity, topless styling, bare breasts, visible nipples, robe-only styling, towel-only styling, sheets, censor objects, or a different garment category.
If the prompt asks for a crop tank, skirt, shirt, dress, shorts, pants, bikini, lingerie, robe, or any other garment, render that garment clearly and consistently.
Premium sensuality must come from pose, expression, camera distance, fabric fit, fabric texture, lighting, hand placement, and creator confidence while preserving the specified wardrobe.
Bust volume may be visible only through realistic clothing fit, neckline, fabric tension, or cleavage allowed by the requested garment. Do not expose breasts unless the written prompt explicitly asks for topless, nude, or bare breasts.
""".strip()
    TOPLESS_RENDER_LOCK = """
TOPLESS RENDER LOCK - NON-NEGOTIABLE:
The requested image is topless. Do not add a bikini top, bra, lingerie top, swimsuit top, crop top, shirt, robe, towel, dress, or any upper-body clothing.
Bare breasts and natural nipples must be clearly visible and unobstructed.
Do not cover breasts with hair, arms, hands, furniture, sheets, pillows, props, water surface, fabric, shadows, or camera crop.
Bust size and shape remain owned by the canonical Ava identity boundary.
""".strip()
    NUDE_GROOMING_RENDER_LOCK = """
NUDE GROOMING LOCK - NON-NEGOTIABLE:
If pubic area or lower nude body is visible, there must be no pubic hair.
The pubic area must be fully smooth, hairless, and clean-shaven.
Do not render a landing strip, stubble, trimmed pubic hair, shadow hair, peach fuzz, or visible pubic hair texture.
""".strip()
    EXPRESSION_PROFILES = (
        (22, "teasing naughty seductive sexually enticing appealing salacious locked eye contact, fully open alert eyes, soft intimate private PPV mood"),
        (18, "parted lips, intimate seductive expression, fully open bedroom-alert eyes, quiet close-camera wanting"),
        (15, "playful lower-lip bite, teasing eyes fully open, coy naughty creator energy"),
        (12, "teasing coy smirk, fully open seductive eyes, alluring private appeal"),
        (10, "soft salacious smile, locked intimate eye contact, fully open alert eyes, sensual confidence"),
        (8, "playful expression, teasing grin, amused smile, casual creator-photo energy"),
        (7, "confident seductive eye contact, slight smirk, relaxed self-assured presence"),
        (5, "relaxed natural smile, authentic creator smile, subtle warmth, natural eye contact"),
        (3, "looking away thoughtfully with a coy private smile, candid intimate moment"),
    )
    EXPLICIT_TERMS = ("explicit", "nude", "naked", "topless", "bare breasts", "visible nipples", "masturbation", "touching her vagina", "vulva", "clit", "pussy", "dildo", "toy", "insertion")
    TOPLESS_TERMS = ("topless", "bare breasts", "bare breast", "no bra", "no bikini top", "no upper-body clothing", "upper body uncovered")
    NUDE_LOWER_TERMS = ("nude", "naked", "fully nude", "completely nude", "bare body", "pubic area", "vulva", "clit", "pussy", "touching her vagina")

    def __init__(
        self,
        *,
        api_key: str | None = None,
        http_client: HttpClient | None = None,
        poll_interval_seconds: float = 3.0,
        max_poll_attempts: int = 100,
        max_poll_elapsed_seconds: float = 300.0,
        hosted_reference_service=None,
        recipe_capture_service=None,
        sleep=time.sleep,
    ):
        self.api_key = api_key
        self.http_client = http_client or requests
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_attempts = max(1, int(max_poll_attempts or 1))
        self.max_poll_elapsed_seconds = max(30.0, float(max_poll_elapsed_seconds or 300))
        self.sleep = sleep
        self.hosted_references = hosted_reference_service or HostedAssetReferenceService(
            http_client=self.http_client, sleep=sleep,
        )
        if recipe_capture_service is None:
            from app.services.generation_recipe_capture_service import GenerationRecipeCaptureService
            recipe_capture_service = GenerationRecipeCaptureService()
        self.recipe_capture = recipe_capture_service
        self.transport_timeout = max(1.0, float(os.getenv("WAVESPEED_TRANSPORT_TIMEOUT_SECONDS", "120")))
        self.transport_retry_delays = HostedAssetReferenceService._retry_delays()

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider_id=self.provider_id,
            display_name=self.display_name,
            provider_family=self.provider_family,
            endpoint=self.endpoint,
            enabled=bool(self.endpoint),
            capabilities=self.capabilities,
            metadata={
                "api_key_env": self.api_key_env,
                "reference_image_host": self.provider_reference_host,
                "lifecycle": self.lifecycle,
            },
        )

    def validate_request(self, request: GenerationRequest) -> None:
        if not self.endpoint:
            raise GenerationProviderError(f"{self.provider_id} does not have an endpoint configured.")
        if request.generation_type not in self.capabilities.supported_generation_types:
            raise GenerationProviderError(
                f"{self.provider_id} does not support generation type {request.generation_type}."
            )
        if not request.prompt_text.strip():
            raise GenerationProviderError("Generation request prompt text is required.")
        if not self._reference_image(request):
            raise GenerationProviderError(
                "WaveSpeed image-edit providers require a reference image URL or reference asset path."
            )
        self._api_key()

    def execute(self, request: GenerationRequest) -> GenerationResult:
        return self.execute_with_progress(request)

    def execute_with_progress(
        self,
        request: GenerationRequest,
        progress_callback: Callable[..., None] | None = None,
    ) -> GenerationResult:
        self.validate_request(request)
        submissions: list[ProviderSubmission] = []
        poll_results: list[ProviderPollResult] = []
        failures: list[Mapping[str, Any]] = []
        output_references: list[str] = []
        output_recipe_ids: list[str] = []
        total = max(1, int(request.image_count or 1))
        prompt_variations = self._prompt_variations(request)
        for index in range(total):
            request_for_image = replace(
                request,
                prompt_text=prompt_variations[index % len(prompt_variations)],
                image_count=1,
                metadata={**dict(request.metadata or {}), "provider_submission_index": index},
            )
            if progress_callback:
                progress_callback(
                    current=index,
                    total=total,
                    message=f"Submitting image {index + 1} of {total}",
                    output_references=tuple(output_references),
                    completed_count=len(output_references),
                    failed_count=len(failures),
                    processed_count=index,
                )
            try:
                submission = self.submit_generation(request_for_image)
            except Exception as exc:
                failures.append(
                    {
                        "index": index + 1,
                        "stage": getattr(exc, "stage", "submit"),
                        "reason": str(exc),
                        "provider_error": exc.__class__.__name__,
                        "may_have_been_accepted": bool(getattr(exc, "may_have_been_accepted", False)),
                    }
                )
                if progress_callback:
                    progress_callback(
                        current=len(output_references),
                        total=total,
                        message=f"Image {index + 1} of {total} failed",
                        output_references=tuple(output_references),
                        completed_count=len(output_references),
                        failed_count=len(failures),
                        processed_count=index + 1,
                        failed=True,
                    )
                continue
            submissions.append(submission)
            if progress_callback:
                progress_callback(
                    current=index,
                    total=total,
                    message=f"Waiting for image {index + 1} of {total}",
                    output_references=tuple(output_references),
                    completed_count=len(output_references),
                    failed_count=len(failures),
                    processed_count=index,
                )
            try:
                poll_result = self.poll_status(submission)
            except Exception as exc:
                if submission.generation_recipe_id:
                    self.recipe_capture.terminal(
                        submission.generation_recipe_id, "failed", error_message=str(exc),
                    )
                failures.append(
                    {
                        "index": index + 1,
                        "stage": "poll",
                        "reason": str(exc),
                        "provider_request_id": submission.provider_request_id,
                        "provider_error": exc.__class__.__name__,
                    }
                )
                if progress_callback:
                    progress_callback(
                        current=len(output_references),
                        total=total,
                        message=f"Image {index + 1} of {total} failed",
                        output_references=tuple(output_references),
                        completed_count=len(output_references),
                        failed_count=len(failures),
                        processed_count=index + 1,
                        failed=True,
                    )
                continue
            poll_results.append(poll_result)
            if poll_result.status == GenerationStatus.RUNNING.value:
                return GenerationResult(
                    result_id=new_generation_id("generation_result"), request_id=request.request_id,
                    job_id="provider_pending", provider_id=self.provider_id,
                    status=GenerationStatus.RUNNING.value,
                    generation_metadata={"provider_family": self.provider_family,
                                         "generation_recipe_ids": tuple(item.generation_recipe_id for item in submissions if item.generation_recipe_id)},
                    execution_metadata={"provider_pending": True,
                                        "provider_request_id": submission.provider_request_id,
                                        "polling": dict(poll_result.raw_response or {})},
                    image_metadata={"requested_image_count": total, "output_count": 0},
                )
            if poll_result.status != GenerationStatus.SUCCEEDED.value:
                if submission.generation_recipe_id:
                    self.recipe_capture.terminal(
                        submission.generation_recipe_id, poll_result.status,
                        error_message=poll_result.failure_reason,
                    )
                failures.append(
                    {
                        "index": index + 1,
                        "stage": "provider_result",
                        "reason": poll_result.failure_reason or f"Image {index + 1} failed",
                        "provider_request_id": submission.provider_request_id,
                        "status": poll_result.status,
                    }
                )
                if progress_callback:
                    progress_callback(
                        current=len(output_references),
                        total=total,
                        message=poll_result.failure_reason or f"Image {index + 1} failed",
                        output_references=tuple(output_references),
                        completed_count=len(output_references),
                        failed_count=len(failures),
                        processed_count=index + 1,
                        failed=True,
                    )
                continue
            if submission.generation_recipe_id:
                self.recipe_capture.terminal(submission.generation_recipe_id, "succeeded")
            output_references.extend(poll_result.output_references)
            output_recipe_ids.extend(
                [submission.generation_recipe_id] * len(poll_result.output_references)
            )
            if progress_callback:
                progress_callback(
                    current=len(output_references),
                    total=total,
                    message=f"Image {index + 1} of {total} completed",
                    output_references=tuple(output_references),
                    output_generation_recipe_ids=tuple(output_recipe_ids),
                    completed_count=len(output_references),
                    failed_count=len(failures),
                    processed_count=index + 1,
                )

        failure_reason = None
        if failures:
            failure_reason = "; ".join(str(item.get("reason") or "Generation failed") for item in failures)
        if not submissions:
            return GenerationResult(
                result_id=new_generation_id("generation_result"),
                request_id=request.request_id,
                job_id="provider_pending",
                provider_id=self.provider_id,
                status=GenerationStatus.FAILED.value,
                generation_metadata={
                    "provider_family": self.provider_family,
                    "endpoint": self.endpoint,
                    "partial_success": False,
                },
                execution_metadata={"failures": tuple(dict(item) for item in failures)},
                image_metadata={
                    "requested_image_count": total,
                    "output_count": 0,
                    "completed_count": 0,
                    "failed_count": len(failures),
                    "processed_count": total,
                    "reference_asset_id": request.reference_asset_id,
                },
                output_references=(),
                failure_reason=failure_reason or "Generation failed. No requested images completed.",
            )

        first_submission = submissions[0]
        merged_poll = ProviderPollResult(
            provider_request_id=first_submission.provider_request_id,
            status=GenerationStatus.SUCCEEDED.value if output_references else GenerationStatus.FAILED.value,
            raw_response={
                "provider_request_ids": tuple(item.provider_request_id for item in submissions),
                "poll_responses": tuple(item.raw_response for item in poll_results),
                "failures": tuple(dict(item) for item in failures),
            },
            output_references=tuple(output_references),
            failure_reason=None if output_references else failure_reason,
        )
        result = self.retrieve_result(request, first_submission, merged_poll)
        return replace(
            result,
            generation_metadata={
                **dict(result.generation_metadata or {}),
                "partial_success": bool(output_references and failures),
                "generation_recipe_ids": tuple(
                    item.generation_recipe_id for item in submissions
                    if item.generation_recipe_id
                ),
                "output_generation_recipe_ids": tuple(output_recipe_ids),
            },
            execution_metadata={
                **dict(result.execution_metadata or {}),
                "failures": tuple(dict(item) for item in failures),
            },
            image_metadata={
                **dict(result.image_metadata or {}),
                "requested_image_count": total,
                "output_count": len(output_references),
                "completed_count": len(output_references),
                "failed_count": len(failures),
                "processed_count": total,
            },
            failure_reason=failure_reason if output_references and failures else result.failure_reason,
        )

    def submit_generation(self, request: GenerationRequest) -> ProviderSubmission:
        payload = self.build_payload(request)
        recipe = self.recipe_capture.capture(
            request=request, provider=self, final_payload=payload,
        )
        self.recipe_capture.submission_started(recipe.recipe_id)
        started = time.perf_counter()
        try:
            response = self.http_client.post(
                self.endpoint, headers=self._headers(content_type=True), json=payload,
                timeout=self.transport_timeout,
            )
        except Exception as exc:
            self.recipe_capture.submission_failed(recipe.recipe_id, exc, ambiguous=True)
            self._transport_log("wavespeed_submission", self.endpoint, request, 1, started, "ambiguous", error=exc, retry=False)
            raise WaveSpeedSubmissionAmbiguousError(
                "The provider connection closed during submission. Creator_OS could not safely confirm whether "
                "the job was accepted. Retry only after checking provider history."
            ) from exc
        self._transport_log("wavespeed_submission", self.endpoint, request, 1, started, "response", status=response.status_code)
        try:
            self._raise_for_status(response, "WaveSpeed submit failed")
        except Exception as exc:
            self.recipe_capture.submission_failed(recipe.recipe_id, exc)
            raise
        try:
            data = response.json()
        except Exception as exc:
            self.recipe_capture.submission_failed(recipe.recipe_id, exc, ambiguous=True)
            raise GenerationProviderError(
                "WaveSpeed submission returned an unreadable acceptance response."
            ) from exc
        provider_request_id = (
            data.get("id")
            or data.get("request_id")
            or data.get("data", {}).get("id")
        )
        if not provider_request_id:
            error = GenerationProviderError(
                "WaveSpeed accepted no canonical provider request ID."
            )
            self.recipe_capture.submission_failed(recipe.recipe_id, error, ambiguous=True)
            raise error
        self.recipe_capture.submitted(recipe.recipe_id, str(provider_request_id))
        return ProviderSubmission(
            provider_request_id=str(provider_request_id), raw_response=data,
            generation_recipe_id=str(recipe.recipe_id),
        )

    def poll_status(self, submission: ProviderSubmission) -> ProviderPollResult:
        started = time.monotonic()
        last_result: ProviderPollResult | None = None
        transient_errors = 0
        attempts = 0
        for attempt in range(self.max_poll_attempts):
            attempts = attempt + 1
            try:
                result = self.poll_status_once(submission)
                transient_errors = 0
            except Exception as error:
                transient_errors += 1
                if transient_errors >= 3:
                    return ProviderPollResult(
                        provider_request_id=submission.provider_request_id,
                        status=GenerationStatus.RUNNING.value,
                        raw_response={"polling_deferred": True, "poll_attempts": attempt + 1,
                                      "poll_error": type(error).__name__},
                        failure_reason=None,
                    )
                self.sleep(self.poll_interval_seconds)
                continue
            if result.status in {
                GenerationStatus.SUCCEEDED.value,
                GenerationStatus.FAILED.value,
                GenerationStatus.CANCELLED.value,
            }:
                TRANSPORT_LOGGER.info(
                    "provider_poll_terminal provider_request_id=%s attempts=%s elapsed_seconds=%.2f status=%s",
                    submission.provider_request_id, attempts, time.monotonic() - started, result.status,
                )
                return result
            last_result = result
            elapsed = time.monotonic() - started
            if elapsed >= self.max_poll_elapsed_seconds:
                break
            if attempt < self.max_poll_attempts - 1:
                self.sleep(self.poll_interval_seconds if elapsed < 60 else min(6.0, self.poll_interval_seconds * 2))
        elapsed = time.monotonic() - started
        TRANSPORT_LOGGER.info(
            "provider_poll_deferred provider_request_id=%s attempts=%s elapsed_seconds=%.2f last_status=%s",
            submission.provider_request_id, attempts, elapsed,
            last_result.status if last_result else "unknown",
        )
        return ProviderPollResult(
            provider_request_id=submission.provider_request_id,
            status=GenerationStatus.RUNNING.value,
            raw_response={"polling_deferred": True, "poll_attempts": attempts,
                          "poll_elapsed_seconds": elapsed,
                          "last_response": last_result.raw_response if last_result else submission.raw_response},
            failure_reason=None,
        )

    def poll_status_once(self, submission: ProviderSubmission) -> ProviderPollResult:
        result_url = self.result_url_template.format(request_id=submission.provider_request_id)
        response = self._safe_request(
            "get", result_url, stage="wavespeed_poll", asset_id=None,
            request_id=submission.provider_request_id, headers=self._headers(), timeout=self.transport_timeout,
        )
        self._raise_for_status(response, "WaveSpeed result poll failed")
        data = response.json()
        status = self._normalize_status(data.get("status") or data.get("data", {}).get("status"))
        outputs = self._extract_outputs(data)
        failure_reason = self._extract_failure_reason(data) if status == GenerationStatus.FAILED.value else None
        return ProviderPollResult(
            provider_request_id=submission.provider_request_id,
            status=status,
            raw_response=data,
            output_references=outputs,
            failure_reason=failure_reason,
        )

    def retrieve_result(
        self,
        request: GenerationRequest,
        submission: ProviderSubmission,
        poll_result: ProviderPollResult,
    ) -> GenerationResult:
        return GenerationResult(
            result_id=new_generation_id("generation_result"),
            request_id=request.request_id,
            job_id="provider_pending",
            provider_id=self.provider_id,
            status=poll_result.status,
            generation_metadata={
                "provider_request_id": submission.provider_request_id,
                "provider_family": self.provider_family,
                "endpoint": self.endpoint,
            },
            execution_metadata={
                "submit_response": dict(submission.raw_response),
                "poll_response": dict(poll_result.raw_response),
            },
            image_metadata={
                "requested_image_count": request.image_count,
                "output_count": len(poll_result.output_references),
                "reference_asset_id": request.reference_asset_id,
            },
            output_references=poll_result.output_references,
            failure_reason=poll_result.failure_reason,
        )

    def cancel_job(self, provider_request_id: str) -> Mapping[str, Any]:
        return {
            "provider_request_id": provider_request_id,
            "cancel_supported": False,
            "message": "WaveSpeed cancel API is not configured for this provider adapter.",
        }

    def build_payload(self, request: GenerationRequest) -> Mapping[str, Any]:
        prompt = self._render_prompt_text(request)
        images = self._provider_reference_images(request)
        payload = {
            "prompt": prompt,
            "images": images,
            "output_format": str(request.metadata.get("output_format") or "png"),
        }
        from app.services.generation_request_diagnostic_service import GenerationRequestDiagnosticService
        diagnostic = GenerationRequestDiagnosticService()
        trace_id = request.metadata.get("diagnostic_trace_id")
        origin = request.metadata.get("workflow_origin")
        diagnostic.record(trace_id=trace_id, workflow_origin=origin,
                          stage="11_ordered_provider_reference_images", value=images)
        diagnostic.record(trace_id=trace_id, workflow_origin=origin,
                          stage="12_final_provider_prompt", value=prompt)
        diagnostic.record(trace_id=trace_id, workflow_origin=origin,
                          stage="13_final_seedream_payload", value=payload)
        return payload

    def _render_prompt_text(self, request: GenerationRequest) -> str:
        exact_prompt = str(request.prompt_text or "")
        if self._is_trusted_final_prompt(request, exact_prompt):
            return exact_prompt
        prompt = exact_prompt.strip()
        policy = self._render_policy(request)
        if policy == RenderPolicy.CONTENT_STANDARD:
            return f"{prompt}\n\n{SOCIAL_CLOSE_FRAMING_RENDER_LOCK}"
        if policy in {
            RenderPolicy.CONTENT_SPICY,
            RenderPolicy.PHOTOSHOOT_PREMIUM,
        }:
            rendered = enforce_premium_render_body_lock(prompt)
            return self._with_expression_directive(rendered, prompt)
        if policy in {
            RenderPolicy.CONTENT_EXPLICIT,
            RenderPolicy.PHOTOSHOOT_EXPLICIT,
        }:
            rendered = enforce_explicit_render_lock(prompt)
            return self._with_expression_directive(rendered, prompt)
        if policy == RenderPolicy.PHOTOSHOOT_SAFE:
            return enforce_photoshoot_safe_render_lock(prompt)
        if policy == RenderPolicy.EDIT:
            return prompt
        raise GenerationProviderError(f"Unhandled render policy: {policy.value}")

    @staticmethod
    def _is_trusted_final_prompt(request: GenerationRequest, prompt: str | None = None) -> bool:
        from app.models.generation_engine import ProviderPromptState
        value = str(prompt if prompt is not None else request.prompt_text or "")
        metadata = dict(request.metadata or {})
        expected = str(metadata.get("trusted_final_prompt_sha256") or "")
        return bool(
            request.prompt_state == ProviderPromptState.FINAL_PROVIDER_RENDERED.value
            and metadata.get("regeneration_operation_id")
            and metadata.get("source_recipe_id")
            and expected
            and hashlib.sha256(value.encode("utf-8")).hexdigest() == expected
        )

    @staticmethod
    def _render_policy(request: GenerationRequest) -> RenderPolicy:
        raw_policy = (request.metadata or {}).get("render_policy")
        if raw_policy is None:
            # Compatibility requests created before render-policy routing are
            # treated as standard content. Canonical engine requests always
            # persist an explicit policy.
            return RenderPolicy.CONTENT_STANDARD
        try:
            return RenderPolicy(str(raw_policy))
        except ValueError as error:
            raise GenerationProviderError(
                f"Unknown or missing render policy: {raw_policy!r}"
            ) from error

    @classmethod
    def _with_expression_directive(cls, rendered: str, identity: str) -> str:
        if (
            "EXPLICIT EXPRESSION VARIATION:" in rendered
            or "EXPLICIT EXPRESSION PROFILE" in rendered
        ):
            return ensure_canonical_facial_naturalism(rendered)
        return ensure_canonical_facial_naturalism(
            f"{rendered}\n\n{cls._explicit_expression_directive(identity)}"
        )

    @staticmethod
    def _prompt_variations(request: GenerationRequest) -> tuple[str, ...]:
        if WaveSpeedProviderBase._is_trusted_final_prompt(request):
            return (str(request.prompt_text or ""),)
        prompt_metadata = request.metadata.get("prompt_metadata") or {}
        candidates = (
            request.metadata.get("prompt_variations")
            or (prompt_metadata.get("prompt_variations") if isinstance(prompt_metadata, Mapping) else ())
            or ()
        )
        prompts = tuple(str(prompt).strip() for prompt in candidates if str(prompt).strip())
        return prompts or (request.prompt_text.strip(),)

    @classmethod
    def _contains_any(cls, prompt: str, terms: tuple[str, ...]) -> bool:
        text = str(prompt or "").lower()
        return any(term in text for term in terms)

    @classmethod
    def _references_explicit(cls, prompt: str) -> bool:
        text = str(prompt or "").lower()
        negated_phrases = (
            "not explicit",
            "non-explicit",
            "no explicit",
            "no nudity",
            "no nude",
            "no topless",
            "no bare breasts",
            "no visible nipples",
            "without nudity",
            "without topless",
            "unless nudity was explicitly requested",
            "unless they explicitly ask",
            "unless the creator explicitly asks",
            "unless the written prompt explicitly asks",
        )
        for phrase in negated_phrases:
            text = text.replace(phrase, " ")
        positive_patterns = (
            r"(?<!no )(?<!not )(?<!without )\bnude\b",
            r"(?<!no )(?<!not )(?<!without )\bnaked\b",
            r"(?<!no )(?<!not )(?<!without )\btopless\b",
            r"(?<!no )(?<!not )(?<!without )\bbare breasts?\b",
            r"(?<!no )(?<!not )(?<!without )\bvisible nipples?\b",
            r"\bmasturbation\b",
            r"\btouching her vagina\b",
            r"\bvulva\b",
            r"\bclit\b",
            r"\bpussy\b",
            r"\bdildo\b",
            r"\bsex toy\b",
            r"\binsertion\b",
        )
        return any(re.search(pattern, text) for pattern in positive_patterns)

    @classmethod
    def _references_topless(cls, prompt: str) -> bool:
        text = str(prompt or "").lower()
        for phrase in (
            "no topless",
            "not topless",
            "without topless",
            "no bare breasts",
            "no visible nipples",
            "do not generate nudity, topless styling, bare breasts",
            "unless the written prompt explicitly asks for topless",
        ):
            text = text.replace(phrase, " ")
        return any(
            re.search(pattern, text)
            for pattern in (
                r"(?<!no )(?<!not )(?<!without )\btopless\b",
                r"(?<!no )(?<!not )(?<!without )\bbare breasts?\b",
                r"(?<!no )(?<!not )(?<!without )\bvisible nipples?\b",
                r"\bno upper-body clothing\b",
                r"\bupper body uncovered\b",
            )
        )

    @classmethod
    def _references_nude_lower(cls, prompt: str) -> bool:
        text = str(prompt or "").lower()
        for phrase in (
            "no nudity",
            "no nude",
            "not nude",
            "without nudity",
            "unless nudity was explicitly requested",
            "unless they explicitly ask for nude",
            "unless the written prompt explicitly asks",
        ):
            text = text.replace(phrase, " ")
        return any(
            re.search(pattern, text)
            for pattern in (
                r"(?<!no )(?<!not )(?<!without )\bnude\b",
                r"(?<!no )(?<!not )(?<!without )\bnaked\b",
                r"\bfully nude\b",
                r"\bcompletely nude\b",
                r"\bbare body\b",
                r"\bpubic area\b",
                r"\bvulva\b",
                r"\bclit\b",
                r"\bpussy\b",
                r"\btouching her vagina\b",
            )
        )

    @classmethod
    def _explicit_expression_directive(cls, prompt: str) -> str:
        digest = hashlib.sha256(str(prompt or "").strip().encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") % 100
        running = 0
        selected = cls.EXPRESSION_PROFILES[-1][1]
        for weight, profile in cls.EXPRESSION_PROFILES:
            running += weight
            if bucket < running:
                selected = profile
                break
        return (
            "EXPLICIT EXPRESSION VARIATION:\n"
            f"Use this single selected expression profile only: {selected}.\n"
            "Let the selected expression control emotional intent without redefining Ava's facial geometry or identity.\n\n"
            "EXPLICIT HAIR SHAPE LOCK:\n"
            "Hair must be worn down naturally with a smooth flat natural top and loose dark hair flowing around her face, "
            "over her shoulders, or down her back. No bun, topknot, ponytail, updo, tied-up hair, messy crown, or tall hair shape."
        )

    def _api_key(self) -> str:
        api_key = self.api_key or os.getenv(self.api_key_env)
        if not api_key:
            raise GenerationProviderError(f"Missing {self.api_key_env}.")
        return api_key

    def _headers(self, *, content_type: bool = False) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self._api_key()}"}
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _provider_reference_image(self, request: GenerationRequest) -> str:
        reference = self._reference_image(request)
        if not reference:
            raise GenerationProviderError(
                "WaveSpeed image-edit providers require a reference image URL or reference asset path."
            )
        if self._is_remote_url(reference):
            return reference

        path = Path(reference).expanduser()
        if not path.exists():
            raise GenerationProviderError(f"Reference image was not found: {reference}")
        if request.reference_asset_id:
            return self.hosted_references.resolve(
                asset_id=int(request.reference_asset_id), source_path=str(path),
                host_name=self.provider_reference_host,
                uploader=lambda source: self._upload_reference_image(
                    source, asset_id=int(request.reference_asset_id), request_id=request.request_id,
                ),
            )
        return self._upload_reference_image(path, request_id=request.request_id)

    def _provider_reference_images(self, request: GenerationRequest) -> list[str]:
        continuity = str(request.metadata.get("photoshoot_continuity_reference_image_url") or "").strip()
        original_seed = str(request.metadata.get("original_photoshoot_seed_reference_image_url") or "").strip()
        frozen_identity_required = bool(request.metadata.get("require_frozen_photoshoot_identity"))
        photoshoot_policies = {
            RenderPolicy.PHOTOSHOOT_SAFE,
            RenderPolicy.PHOTOSHOOT_PREMIUM,
            RenderPolicy.PHOTOSHOOT_EXPLICIT,
        }
        canonical = str(
            request.metadata.get("canonical_reference_image_url")
            or request.reference_asset_path
            or ""
        ).strip()
        if frozen_identity_required:
            if self._render_policy(request) not in photoshoot_policies:
                raise GenerationProviderError("Frozen Photoshoot identity references require a Photoshoot render policy.")
            if self.capabilities.max_reference_images < 2:
                raise GenerationProviderError(
                    f"{self.provider_id} cannot enforce the Photoshoot identity lock because it supports fewer than two reference images."
                )
            if not canonical or not continuity:
                raise GenerationProviderError("The frozen identity and evolving continuity references are both required.")
            if "original_photoshoot_seed_reference_image_url" in request.metadata and not original_seed:
                raise GenerationProviderError("The immutable original Photoshoot seed reference is required.")
        if (
            self._render_policy(request) not in photoshoot_policies
            or self.capabilities.max_reference_images < 2
            or not continuity
        ):
            return [self._provider_reference_image(request)]
        seed_image_id = str(request.metadata.get("original_photoshoot_seed_image_id") or "").strip()
        previous_image_id = str(
            request.metadata.get("previous_approved_continuity_reference_image_id")
            or request.metadata.get("active_reference_image_id")
            or ""
        ).strip()
        ordered = []
        seen_references = set()
        seen_generated_images = set()
        for reference, generated_image_id in (
            (canonical, ""), (original_seed, seed_image_id), (continuity, previous_image_id),
        ):
            if not reference or reference in seen_references:
                continue
            if generated_image_id and generated_image_id in seen_generated_images:
                continue
            ordered.append(reference)
            seen_references.add(reference)
            if generated_image_id:
                seen_generated_images.add(generated_image_id)
        if len(ordered) < 2:
            if frozen_identity_required:
                raise GenerationProviderError("The identity and continuity references must be distinct Photoshoot images.")
            return [self._provider_reference_image(request)]
        if len(ordered) > self.capabilities.max_reference_images:
            raise GenerationProviderError(
                f"{self.provider_id} cannot preserve all mandatory Photoshoot reference anchors."
            )
        values = []
        for index, reference in enumerate(ordered):
            if index == 0 and not self._is_remote_url(reference) and request.reference_asset_id:
                values.append(self.hosted_references.resolve(
                    asset_id=int(request.reference_asset_id), source_path=reference,
                    host_name=self.provider_reference_host, uploader=lambda path: self._upload_reference_image(
                        path, asset_id=int(request.reference_asset_id), request_id=request.request_id,
                    ),
                ))
            else:
                values.append(self._provider_reference_value(reference))
        return values

    def _provider_reference_value(self, reference: str) -> str:
        if self._is_remote_url(reference):
            return reference
        path = Path(reference).expanduser()
        if not path.exists():
            raise GenerationProviderError(f"Reference image was not found: {reference}")
        return self._upload_reference_image(path)

    @staticmethod
    def _reference_image(request: GenerationRequest) -> str | None:
        value = (
            request.metadata.get("reference_image_url")
            or request.metadata.get("reference_url")
            or request.metadata.get("provider_reference_url")
            or request.reference_asset_path
        )
        return str(value).strip() if value else None

    @staticmethod
    def _is_remote_url(value: str) -> bool:
        return urlparse(value).scheme in {"http", "https"}

    def _upload_reference_image(self, path: Path, *, asset_id: int | None = None,
                                request_id: str | None = None) -> str:
        try:
            with path.open("rb") as source:
                response = self._safe_request(
                    "post", self.media_upload_endpoint, stage="canonical_reference_upload",
                    asset_id=asset_id, request_id=request_id or path.stem,
                    headers=self._headers(), files={"file": (path.name, source)},
                    timeout=self.transport_timeout,
                )
        except OSError as error:
            raise GenerationProviderError(
                f"Provider input preparation failed: canonical reference {path.name} could not be read."
            ) from error
        self._raise_for_status(response, "Provider reference upload failed")
        data = response.json()
        body = data.get("data") if isinstance(data, dict) else None
        image_url = str((body or {}).get("download_url") or (body or {}).get("url") or "").strip()
        if not image_url or not self._is_remote_url(image_url):
            raise GenerationProviderError(
                "Provider input preparation failed: WaveSpeed did not return a usable media URL."
            )
        return image_url
    def _safe_request(self, method: str, url: str, *, stage: str, asset_id, request_id: str, **kwargs):
        attempts = len(self.transport_retry_delays) + 1
        for attempt in range(1, attempts + 1):
            started = time.perf_counter()
            try:
                response = getattr(self.http_client, method)(url, **kwargs)
                status = int(response.status_code)
                retryable = HostedAssetReferenceService._retryable_status(status)
                if not retryable or attempt >= attempts:
                    self._transport_log(stage, url, None, attempt, started, "response", status=status,
                                        asset_id=asset_id, request_id=request_id, retry=False)
                    return response
                error = GenerationProviderError(f"HTTP {status}")
            except Exception as exc:
                if not HostedAssetReferenceService._retryable_exception(exc):
                    self._transport_log(stage, url, None, attempt, started, "failed", error=exc,
                                        asset_id=asset_id, request_id=request_id, retry=False)
                    raise
                error = exc
                if attempt >= attempts:
                    self._transport_log(stage, url, None, attempt, started, "failed", error=exc,
                                        asset_id=asset_id, request_id=request_id, retry=False)
                    message = (
                        "WaveSpeed status check was interrupted after 3 attempts. Retry this frame."
                        if stage == "wavespeed_poll"
                        else "Could not host the canonical reference after 3 attempts. Retry this frame."
                    )
                    raise SafeTransportError(message, stage=stage) from exc
            self._transport_log(stage, url, None, attempt, started, "retry", error=error,
                                asset_id=asset_id, request_id=request_id, retry=True)
            self.sleep(self.transport_retry_delays[attempt - 1])
        raise AssertionError("unreachable")

    @staticmethod
    def _transport_log(stage, url, request, attempt, started, outcome, *, status=None, error=None,
                       asset_id=None, request_id=None, retry=False):
        TRANSPORT_LOGGER.info(
            "transport stage=%s host=%s asset_id=%s request_id=%s attempt=%s elapsed_ms=%s "
            "outcome=%s http_status=%s error_code=%s retry=%s",
            stage, urlparse(url).netloc, asset_id or getattr(request, "reference_asset_id", None),
            request_id or getattr(request, "request_id", None), attempt,
            round((time.perf_counter() - started) * 1000, 2), outcome, status,
            error.__class__.__name__ if error else None, retry,
        )

    @staticmethod
    def _extract_outputs(data: Mapping[str, Any]) -> tuple[str, ...]:
        outputs = (
            data.get("outputs")
            or data.get("output")
            or data.get("data", {}).get("outputs")
            or data.get("data", {}).get("output")
            or ()
        )
        if isinstance(outputs, str):
            return (outputs,)
        if isinstance(outputs, Mapping):
            url = outputs.get("url")
            return (str(url),) if url else ()
        if isinstance(outputs, list):
            references = []
            for item in outputs:
                if isinstance(item, str) and item.strip():
                    references.append(item.strip())
                elif isinstance(item, Mapping) and item.get("url"):
                    references.append(str(item["url"]))
            return tuple(references)
        return ()

    @staticmethod
    def _extract_failure_reason(data: Mapping[str, Any]) -> str:
        result_data = data.get("data", {}) if isinstance(data.get("data"), Mapping) else {}
        return (
            result_data.get("error")
            or result_data.get("message")
            or data.get("message")
            or "Unknown provider error"
        )

    @staticmethod
    def _normalize_status(status: Any) -> str:
        value = str(status or "").strip().lower()
        if value in {"completed", "succeeded", "success"}:
            return GenerationStatus.SUCCEEDED.value
        if value in {"failed", "error"}:
            return GenerationStatus.FAILED.value
        if value in {"cancelled", "canceled"}:
            return GenerationStatus.CANCELLED.value
        if value in {"running", "processing", "queued", "pending", "created"}:
            return GenerationStatus.RUNNING.value
        return GenerationStatus.RUNNING.value

    @staticmethod
    def _raise_for_status(response, context: str) -> None:
        try:
            response.raise_for_status()
        except Exception as exc:
            raise GenerationProviderError(
                f"{context}. HTTP {getattr(response, 'status_code', '?')}."
            ) from exc
