"""Secret-safe, observational capture of the exact submitted provider payload."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from app.models.generation_recipe import GenerationRecipe, GenerationRecipeReference
from app.repositories.generation_recipe_repository import GenerationRecipeRepository


class GenerationRecipeCaptureService:
    SCHEMA_VERSION = "generation_recipe_v1"
    SECRET_KEYS = {"api_key","apikey","authorization","cookie","password","secret","token","access_token","refresh_token","signature","credentials"}

    def __init__(self, repository=None):
        self.repository = repository or GenerationRecipeRepository()

    def capture(self, *, request, provider, final_payload: Mapping[str, Any]) -> GenerationRecipe:
        payload_copy = copy.deepcopy(dict(final_payload))
        references = self._references(request, payload_copy)
        sanitized = self._sanitize_payload(payload_copy, references)
        prompt = str(final_payload.get("prompt") or "")
        metadata = dict(request.metadata or {})
        capabilities = getattr(provider, "capabilities", None)
        provider_metadata = dict(getattr(capabilities, "metadata", {}) or {})
        settings = self._settings(sanitized)
        seed = final_payload.get("seed")
        recipe_id = uuid4()
        recipe = GenerationRecipe(
            recipe_id=recipe_id,schema_version=self.SCHEMA_VERSION,
            generation_job_id=metadata.get("generation_job_id"),
            generation_request_id=request.request_id,prompt_plan_id=request.prompt_plan_id,
            submission_index=int(metadata.get("provider_submission_index") or 0),
            source_workflow=metadata.get("workflow_type") or metadata.get("source"),
            workflow_origin=metadata.get("workflow_origin"),provider_id=provider.provider_id,
            provider_family=getattr(provider,"provider_family",None),
            provider_adapter=f"{provider.__class__.__module__}.{provider.__class__.__qualname__}",
            provider_adapter_version=getattr(provider,"adapter_version",None),
            provider_endpoint=str(getattr(provider,"endpoint","") or "") or None,
            provider_model=provider_metadata.get("model"),
            provider_model_revision=provider_metadata.get("model_revision"),
            generation_type=request.generation_type,media_type=request.media_type,
            planned_prompt=str(request.prompt_text or ""),final_prompt=prompt,
            final_prompt_sha256=self._hash_text(prompt),creative_mode=metadata.get("creative_mode"),
            render_policy=metadata.get("render_policy"),
            render_policy_version=metadata.get("render_policy_version"),
            normalized_settings=settings,output_format=self._text(final_payload.get("output_format")),
            width=self._integer(final_payload.get("width")),height=self._integer(final_payload.get("height")),
            aspect_ratio=self._text(final_payload.get("aspect_ratio")),
            resolution=self._text(final_payload.get("resolution")),seed=self._text(seed),
            seed_policy="EXPLICIT" if seed is not None else "OMITTED_PROVIDER_RANDOM",
            sanitized_provider_payload=sanitized,
            sanitized_payload_sha256=self._hash_json(sanitized),references=tuple(
                GenerationRecipeReference(recipe_reference_id=uuid4(),recipe_id=recipe_id,**item)
                for item in references
            ),
            source_generated_image_id=metadata.get("source_generated_image_id"),
            source_recipe_id=metadata.get("source_recipe_id"),
            regeneration_operation_id=metadata.get("regeneration_operation_id"),
        )
        return self.repository.create(recipe)

    def submission_started(self, recipe_id):
        self.repository.transition_execution(recipe_id,"SUBMISSION_STARTED")

    def submitted(self, recipe_id, provider_request_id):
        self.repository.transition_execution(recipe_id,"SUBMITTED",provider_request_id=provider_request_id)

    def submission_failed(self, recipe_id, error, *, ambiguous=False):
        self.repository.transition_execution(recipe_id,"SUBMISSION_AMBIGUOUS" if ambiguous else "SUBMISSION_REJECTED",error_code=type(error).__name__,error_message=str(error))

    def terminal(self, recipe_id, status, *, error_message=None):
        terminal = "SUCCEEDED" if str(status).lower()=="succeeded" else "FAILED"
        self.repository.transition_execution(recipe_id,terminal,provider_terminal_status=str(status),error_code="ProviderFailure" if error_message else None,error_message=error_message)

    def associate_output(self, recipe_id, *, result_id, image_id, output_index, output_reference):
        self.repository.associate_output(recipe_id,generation_result_id=result_id,generated_image_id=image_id,output_index=output_index,output_reference_hash=self._hash_text(str(output_reference)))

    def _references(self, request, payload):
        values=[]; kind="images"
        if isinstance(payload.get("images"),list): values=list(payload["images"])
        else:
            for key in ("image","video","last_image"):
                if payload.get(key): values.append(payload[key]); kind=key
        metadata=dict(request.metadata or {}); policy=str(metadata.get("render_policy") or "")
        photoshoot=policy.startswith("PHOTOSHOOT_")
        workflow=str(metadata.get("workflow_type") or metadata.get("source") or "")
        result=[]
        for index,value in enumerate(values,1):
            role="OTHER"; source_type="PROVIDER_REFERENCE"; asset_id=None; generated_image_id=None; source_id=None
            if photoshoot and index==1:
                role="CANONICAL_IDENTITY"; source_type="CANONICAL_ASSET"; asset_id=request.reference_asset_id
            elif photoshoot and index==2:
                if metadata.get("original_photoshoot_seed_reference_image_url"):
                    role="ORIGINAL_PHOTOSHOOT_SEED"; source_type="GENERATED_IMAGE"; generated_image_id=metadata.get("original_photoshoot_seed_image_id"); source_id=generated_image_id
                else:
                    role="PHOTOSHOOT_CONTINUITY"; source_type="GENERATED_IMAGE"; generated_image_id=metadata.get("active_reference_image_id"); source_id=generated_image_id
            elif photoshoot and index==3:
                role="PREVIOUS_APPROVED_CONTINUITY"; source_type="GENERATED_IMAGE"; generated_image_id=metadata.get("previous_approved_continuity_reference_image_id") or metadata.get("active_reference_image_id"); source_id=generated_image_id
            elif workflow=="edit" and index==1:
                role="EDIT_SOURCE"; source_type="GENERATED_IMAGE"; generated_image_id=(metadata.get("source_image_ids") or [None])[0]; source_id=generated_image_id
            elif request.media_type=="video" and index==1:
                role="VIDEO_SOURCE"; source_type="GENERATION_SOURCE"; source_id=str(metadata.get("source_id") or "") or None
            elif index==1 and request.reference_asset_id:
                role="CANONICAL_IDENTITY"; source_type="CANONICAL_ASSET"; asset_id=request.reference_asset_id
            result.append(dict(position=index,role=role,source_type=source_type,source_id=source_id,asset_id=asset_id,generated_image_id=generated_image_id,media_type="video" if kind=="video" else "image",content_sha256=self._local_hash(value),provider_reference_kind=kind,diagnostic_metadata={"provider_host":urlsplit(str(value)).hostname if str(value).startswith(("http://","https://")) else None,"provider_url_sha256":self._hash_text(str(value))}))
        return result

    def _sanitize_payload(self,payload,references):
        def clean(value,key=""):
            if key.lower() in self.SECRET_KEYS or any(term in key.lower() for term in ("authorization","credential","signature")): return "[REDACTED]"
            if isinstance(value,Mapping): return {str(k):clean(v,str(k)) for k,v in value.items()}
            if isinstance(value,list): return [clean(v,key) for v in value]
            if isinstance(value,str) and value.startswith(("http://","https://")):
                parts=urlsplit(value); return urlunsplit((parts.scheme,parts.netloc,parts.path,"",""))
            return value
        sanitized=clean(payload)
        if references:
            if isinstance(sanitized.get("images"),list): sanitized["images"]=[f"recipe-reference://{i}" for i in range(1,len(references)+1)]
            else:
                for i,key in enumerate(k for k in ("image","video","last_image") if key in sanitized): sanitized[key]=f"recipe-reference://{i+1}"
        return sanitized

    @staticmethod
    def _settings(payload):
        excluded={"prompt","images","image","video","last_image"}
        return {str(k):copy.deepcopy(v) for k,v in payload.items() if k not in excluded}
    @staticmethod
    def _hash_text(value): return hashlib.sha256(value.encode("utf-8")).hexdigest()
    @classmethod
    def _hash_json(cls,value): return cls._hash_text(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False))
    @staticmethod
    def _text(value): return None if value is None else str(value)
    @staticmethod
    def _integer(value):
        try: return int(value) if value is not None else None
        except (TypeError,ValueError): return None
    @classmethod
    def _local_hash(cls,value):
        path=Path(str(value or ""))
        if not path.is_file(): return None
        digest=hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda:source.read(1024*1024),b""): digest.update(block)
        return digest.hexdigest()
