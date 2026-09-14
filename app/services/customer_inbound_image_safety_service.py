"""Local NudeNet classification and non-generative customer-image policy."""
from __future__ import annotations

import asyncio
import os
from importlib.metadata import PackageNotFoundError, version
from datetime import datetime, timezone
from pathlib import Path

from app.models.customer_inbound_image_safety import (
    BoundedSafetyLabel, CustomerImagePolicyResult, CustomerImageResponsePolicy,
    CustomerImageSafetyResult, CustomerImageSafetyState, ImageSolicitationState,
    clear_ava_explicit_solicitation,
)
from app.repositories.customer_inbound_image_safety_repository import CustomerInboundImageSafetyRepository


class CustomerInboundImageSafetyService:
    CLASSIFIER="nudenet"
    try:
        CLASSIFIER_VERSION=version("nudenet")
    except PackageNotFoundError:
        CLASSIFIER_VERSION="unknown"
    EXPLICIT_LABELS=frozenset({'MALE_GENITALIA_EXPOSED','FEMALE_GENITALIA_EXPOSED','ANUS_EXPOSED'})
    NUDITY_LABELS=frozenset({'FEMALE_BREAST_EXPOSED','BUTTOCKS_EXPOSED'})
    SUGGESTIVE_LABELS=frozenset({'MALE_GENITALIA_COVERED','FEMALE_GENITALIA_COVERED','BUTTOCKS_COVERED','FEMALE_BREAST_COVERED'})

    def __init__(self, *, repository=None, runner=None,
                 exposed_genital_threshold=None,
                 nudity_threshold=None, suggestive_threshold=None, ambiguity_margin=None,
                 album_window_ms=None, safety_lease_seconds=None):
        self.repository=repository or CustomerInboundImageSafetyRepository()
        self.runner=runner or self._run_nudenet
        self.exposed_genital_threshold=float(
            exposed_genital_threshold
            if exposed_genital_threshold is not None
            else os.getenv('CUSTOMER_IMAGE_EXPOSED_GENITAL_THRESHOLD',.35))
        if not 0 <= self.exposed_genital_threshold <= 1:
            raise ValueError(
                'CUSTOMER_IMAGE_EXPOSED_GENITAL_THRESHOLD must be between 0 and 1')
        self.nudity_threshold=float(nudity_threshold or os.getenv('CUSTOMER_IMAGE_NUDITY_THRESHOLD',.60))
        self.suggestive_threshold=float(suggestive_threshold or os.getenv('CUSTOMER_IMAGE_SUGGESTIVE_THRESHOLD',.45))
        self.ambiguity_margin=float(ambiguity_margin or os.getenv('CUSTOMER_IMAGE_AMBIGUITY_MARGIN',.15))
        self.album_window_ms=int(album_window_ms or os.getenv('TELEGRAM_MEDIA_ALBUM_FINALIZE_MS',750))
        self.safety_lease_seconds=int(safety_lease_seconds or os.getenv('CUSTOMER_IMAGE_SAFETY_LEASE_SECONDS',300))

    @staticmethod
    def _run_nudenet(path):
        from app.services.content_classification_service import run_nudenet
        return run_nudenet(Path(path))

    def classify(self, attachment_id, path) -> CustomerImageSafetyResult:
        now=datetime.now(timezone.utc)
        try: raw=self.runner(Path(path))
        except Exception: raw=None
        if raw is None or any(isinstance(x,dict) and x.get('error') for x in raw):
            return CustomerImageSafetyResult(str(attachment_id),CustomerImageSafetyState.UNCLASSIFIABLE,self.CLASSIFIER,self.CLASSIFIER_VERSION,(),now)
        relevant=[]
        for item in raw:
            if not isinstance(item,dict):continue
            label=str(item.get('class') or '').upper();score=float(item.get('score') or 0)
            threshold=(self.exposed_genital_threshold if label in self.EXPLICIT_LABELS else self.nudity_threshold if label in self.NUDITY_LABELS else self.suggestive_threshold)
            if label in self.EXPLICIT_LABELS|self.NUDITY_LABELS|self.SUGGESTIVE_LABELS:
                relevant.append(BoundedSafetyLabel(label,score,threshold))
        def hit(labels,threshold):return any(x.label in labels and x.confidence>=threshold for x in relevant)
        if hit(self.EXPLICIT_LABELS,self.exposed_genital_threshold):state=CustomerImageSafetyState.EXPLICIT_GENITAL
        elif hit(self.NUDITY_LABELS,self.nudity_threshold):state=CustomerImageSafetyState.NUDITY_NON_GENITAL
        elif any(x.label in self.NUDITY_LABELS and x.confidence>=self.nudity_threshold-self.ambiguity_margin for x in relevant):state=CustomerImageSafetyState.AMBIGUOUS_REVIEW_REQUIRED
        elif hit(self.SUGGESTIVE_LABELS,self.suggestive_threshold):state=CustomerImageSafetyState.SUGGESTIVE_NON_EXPLICIT
        else:state=CustomerImageSafetyState.NORMAL_NON_EXPLICIT
        return CustomerImageSafetyResult(str(attachment_id),state,self.CLASSIFIER,self.CLASSIFIER_VERSION,tuple(relevant),now)

    @staticmethod
    def aggregate(states):
        precedence=(CustomerImageSafetyState.EXPLICIT_GENITAL,CustomerImageSafetyState.AMBIGUOUS_REVIEW_REQUIRED,
          CustomerImageSafetyState.UNCLASSIFIABLE,CustomerImageSafetyState.NUDITY_NON_GENITAL,
          CustomerImageSafetyState.SUGGESTIVE_NON_EXPLICIT,CustomerImageSafetyState.NORMAL_NON_EXPLICIT)
        values=set(states)
        return next((x for x in precedence if x in values),CustomerImageSafetyState.UNCLASSIFIABLE)

    @staticmethod
    def policy(state, *, clearly_solicited=False, prior_boundaries=0):
        solicitation=ImageSolicitationState.CLEARLY_SOLICITED if clearly_solicited else ImageSolicitationState.UNSOLICITED
        mapping={
          CustomerImageSafetyState.NORMAL_NON_EXPLICIT:CustomerImageResponsePolicy.SELFIE_COMPLIMENT_ELIGIBLE,
          CustomerImageSafetyState.SUGGESTIVE_NON_EXPLICIT:CustomerImageResponsePolicy.SUGGESTIVE_VISUAL_RESPONSE,
          CustomerImageSafetyState.NUDITY_NON_GENITAL:CustomerImageResponsePolicy.NUDITY_RESPONSE_REQUIRED,
          CustomerImageSafetyState.AMBIGUOUS_REVIEW_REQUIRED:CustomerImageResponsePolicy.AMBIGUOUS_SAFE_RESPONSE,
          CustomerImageSafetyState.UNCLASSIFIABLE:CustomerImageResponsePolicy.UNCLASSIFIABLE_SAFE_RESPONSE}
        if state is CustomerImageSafetyState.EXPLICIT_GENITAL:
            selected=(CustomerImageResponsePolicy.SOLICITED_EXPLICIT_MEDIA if clearly_solicited else
              CustomerImageResponsePolicy.FIRM_EXPLICIT_BOUNDARY if prior_boundaries else CustomerImageResponsePolicy.POLITE_EXPLICIT_BOUNDARY)
        else:selected=mapping[state]
        return CustomerImagePolicyResult(state,solicitation,selected,
          selected is CustomerImageResponsePolicy.SELFIE_COMPLIMENT_ELIGIBLE,
          prior_boundaries+1 if 'BOUNDARY' in selected.value else 0,False,'')

    async def process_operation(self, operation, *, immediate_messages=()):
        operation,claimed=await asyncio.to_thread(self.repository.schedule_and_claim,operation['operation_id'],grouped=bool(operation.get('grouped_id')),window_ms=self.album_window_ms,safety_lease_seconds=self.safety_lease_seconds)
        if not claimed and operation and operation.get('state')=='SAFETY_CLASSIFIED':
            return self.policy(
                CustomerImageSafetyState(operation['safety_state']),
                clearly_solicited=operation.get('solicitation_state')=='CLEARLY_SOLICITED',
                prior_boundaries=(1 if operation.get('response_policy')=='FIRM_EXPLICIT_BOUNDARY' else 0),
            )
        if not claimed:
            delay=max(0,(operation['album_finalize_after']-datetime.now(timezone.utc)).total_seconds())
            if delay:await asyncio.sleep(min(delay,self.album_window_ms/1000))
            operation,claimed=await asyncio.to_thread(self.repository.schedule_and_claim,operation['operation_id'],grouped=bool(operation.get('grouped_id')),window_ms=self.album_window_ms,safety_lease_seconds=self.safety_lease_seconds)
        if not claimed:return None
        rows=await asyncio.to_thread(self.repository.ready_attachments,operation['operation_id'])
        attachment_states=await asyncio.to_thread(self.repository.attachment_states,operation['operation_id'])
        existing=await asyncio.to_thread(self.repository.existing_results,operation['operation_id'])
        by_attachment={str(row['attachment_id']):row for row in existing}
        results=[]
        try:
            for row in rows:
                prior=by_attachment.get(str(row['attachment_id']))
                if prior:
                    result=CustomerImageSafetyResult(str(row['attachment_id']),CustomerImageSafetyState(prior['safety_state']),prior['classifier'],prior['classifier_version'],(),prior['classified_at'])
                else:
                    result=await asyncio.to_thread(self.classify,row['attachment_id'],row['normalized_path'])
                    await asyncio.to_thread(self.repository.save_result,operation_id=operation['operation_id'],position=row['position'],result=result)
                results.append(result)
            state=self.aggregate(x.state for x in results)
            solicited=clear_ava_explicit_solicitation(immediate_messages)
            count=await asyncio.to_thread(self.repository.boundary_count,creator_profile_id=operation['creator_profile_id'],fanvue_account_id=operation['fanvue_account_id'],telegram_user_id=operation['telegram_user_id'])
            policy=self.policy(state,clearly_solicited=solicited,prior_boundaries=count)
            partial_failure=any(value!='READY_FOR_ANALYSIS' for value in attachment_states)
            await asyncio.to_thread(self.repository.finish,operation['operation_id'],state=state.value,solicitation=policy.solicitation_state.value,policy=policy.policy.value,partial_failure=partial_failure)
            return policy
        except Exception:
            await asyncio.to_thread(self.repository.fail,operation['operation_id'],'SAFETY_CLASSIFIER_FAILED');raise

    async def response_context(self, operation, policy):
        rows=await asyncio.to_thread(
            self.repository.ready_attachments,operation['operation_id'])
        return {
            'operation_id':str(operation['operation_id']),
            'safety_state':policy.safety_state.value,
            'response_policy':policy.policy.value,
            'solicitation_state':policy.solicitation_state.value,
            'attachment_ids':[str(row['attachment_id']) for row in rows],
            'attachment_paths':[str(row['normalized_path']) for row in rows],
            'partial_failure':bool(operation.get('partial_failure',False)),
            'creator_profile_id':operation.get('creator_profile_id'),
            'fanvue_account_id':operation.get('fanvue_account_id'),
            'telegram_user_id':operation.get('telegram_user_id'),
            'visual_evidence_scope':'EPHEMERAL_CURRENT_TURN',
            'customer_identity_authority':False,
            'ocr_trust':'UNTRUSTED_CONTENT',
        }

    async def recovery_payloads(self, *, account_scope='AVA_TELETHON_PRIVATE',limit=25):
        from app.models.telegram_inbound import TelegramInboundAttachment,TelegramInboundPayload
        operations=await asyncio.to_thread(
            self.repository.response_recovery_candidates,
            account_scope=account_scope,limit=limit)
        payloads=[]
        for operation in operations:
            rows=await asyncio.to_thread(
                self.repository.ready_attachments,operation['operation_id'])
            policy=self.policy(CustomerImageSafetyState(operation['safety_state']),
                clearly_solicited=operation.get('solicitation_state')=='CLEARLY_SOLICITED',
                prior_boundaries=(1 if operation.get('response_policy')=='FIRM_EXPLICIT_BOUNDARY' else 0))
            visual=await self.response_context(operation,policy)
            attachments=tuple(TelegramInboundAttachment(
                attachment_id=str(row['attachment_id']),
                telegram_message_id=int(operation['canonical_message_id']),
                telegram_chat_id=int(operation['telegram_chat_id']),
                telegram_user_id=int(operation['telegram_user_id']),
                media_kind='PHOTO',telegram_media_id=str(row['attachment_id']),
                grouped_id=operation.get('grouped_id')) for row in rows)
            payloads.append(TelegramInboundPayload(
                telegram_user_id=int(operation['telegram_user_id']),
                telegram_chat_id=int(operation['telegram_chat_id']),
                message_text=str(operation.get('caption_text') or ''),
                message_id=int(operation['canonical_message_id']),
                received_at=operation.get('received_at'),attachments=attachments,
                current_turn_visual_context=visual))
        return tuple(payloads)
