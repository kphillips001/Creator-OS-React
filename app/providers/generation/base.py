"""Base interfaces and shared helpers for generation providers."""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse

import requests

from app.models.generation_engine import (
    GenerationRequest,
    GenerationResult,
    GenerationStatus,
    new_generation_id,
)


class GenerationProviderError(RuntimeError):
    """Raised when a provider cannot submit, poll, or parse a request."""


@dataclass(frozen=True)
class ProviderCapabilities:
    supported_generation_types: tuple[str, ...]
    supports_images: bool = True
    supports_video: bool = False
    supports_cancel: bool = False
    max_images: int = 1
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
    image_host_api_key_env = "IMGBB_API_KEY"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        http_client: HttpClient | None = None,
        poll_interval_seconds: float = 3.0,
        max_poll_attempts: int = 40,
    ):
        self.api_key = api_key
        self.http_client = http_client or requests
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_attempts = max(1, int(max_poll_attempts or 1))

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
                "reference_image_host_api_key_env": self.image_host_api_key_env,
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
        self.validate_request(request)
        submissions: list[ProviderSubmission] = []
        poll_results: list[ProviderPollResult] = []
        output_references: list[str] = []
        for _index in range(max(1, int(request.image_count or 1))):
            submission = self.submit_generation(request)
            submissions.append(submission)
            poll_result = self.poll_status(submission)
            poll_results.append(poll_result)
            if poll_result.status != GenerationStatus.SUCCEEDED.value:
                return self.retrieve_result(request, submission, poll_result)
            output_references.extend(poll_result.output_references)

        first_submission = submissions[0]
        merged_poll = ProviderPollResult(
            provider_request_id=first_submission.provider_request_id,
            status=GenerationStatus.SUCCEEDED.value,
            raw_response={
                "provider_request_ids": tuple(item.provider_request_id for item in submissions),
                "poll_responses": tuple(item.raw_response for item in poll_results),
            },
            output_references=tuple(output_references),
        )
        return self.retrieve_result(request, first_submission, merged_poll)

    def submit_generation(self, request: GenerationRequest) -> ProviderSubmission:
        response = self.http_client.post(
            self.endpoint,
            headers=self._headers(content_type=True),
            json=self.build_payload(request),
            timeout=120,
        )
        self._raise_for_status(response, "WaveSpeed submit failed")
        data = response.json()
        provider_request_id = (
            data.get("id")
            or data.get("request_id")
            or data.get("data", {}).get("id")
        )
        if not provider_request_id:
            raise GenerationProviderError(f"No provider request ID returned from WaveSpeed. Response: {data}")
        return ProviderSubmission(provider_request_id=str(provider_request_id), raw_response=data)

    def poll_status(self, submission: ProviderSubmission) -> ProviderPollResult:
        last_result: ProviderPollResult | None = None
        for attempt in range(self.max_poll_attempts):
            result = self.poll_status_once(submission)
            if result.status in {
                GenerationStatus.SUCCEEDED.value,
                GenerationStatus.FAILED.value,
                GenerationStatus.CANCELLED.value,
            }:
                return result
            last_result = result
            if attempt < self.max_poll_attempts - 1:
                time.sleep(self.poll_interval_seconds)
        return last_result or ProviderPollResult(
            provider_request_id=submission.provider_request_id,
            status=GenerationStatus.FAILED.value,
            raw_response=submission.raw_response,
            failure_reason="Provider polling exhausted without a terminal status.",
        )

    def poll_status_once(self, submission: ProviderSubmission) -> ProviderPollResult:
        result_url = self.result_url_template.format(request_id=submission.provider_request_id)
        response = self.http_client.get(
            result_url,
            headers=self._headers(),
            timeout=120,
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
        return {
            "prompt": request.prompt_text,
            "images": [self._provider_reference_image(request)],
            "output_format": str(request.metadata.get("output_format") or "png"),
        }

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

    def _upload_reference_image(self, path: Path) -> str:
        api_key = os.getenv(self.image_host_api_key_env)
        if not api_key:
            raise GenerationProviderError(
                f"{self.provider_id} needs a public reference image URL. "
                f"Set {self.image_host_api_key_env} to upload local Creator OS reference assets."
            )
        response = self.http_client.post(
            "https://api.imgbb.com/1/upload",
            data={"key": api_key, "image": base64.b64encode(path.read_bytes())},
            timeout=120,
        )
        self._raise_for_status(response, "Reference image upload failed")
        data = response.json()
        image_url = self._extract_hosted_image_url(data)
        if not image_url:
            raise GenerationProviderError(f"No hosted reference URL returned from image host. Response: {data}")
        return image_url

    @staticmethod
    def _extract_hosted_image_url(data: Mapping[str, Any]) -> str | None:
        data_section = data.get("data", {}) if isinstance(data.get("data"), Mapping) else {}
        candidates = (
            data_section.get("image", {}).get("url") if isinstance(data_section.get("image"), Mapping) else None,
            data_section.get("url"),
            data_section.get("display_url"),
            data_section.get("medium", {}).get("url") if isinstance(data_section.get("medium"), Mapping) else None,
            data_section.get("thumb", {}).get("url") if isinstance(data_section.get("thumb"), Mapping) else None,
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

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
            try:
                body = response.json()
            except Exception:
                body = getattr(response, "text", "")
            raise GenerationProviderError(
                f"{context}. HTTP {getattr(response, 'status_code', '?')}: {body}"
            ) from exc
