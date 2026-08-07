"""Sequential, restart-safe Seedance execution for one logical video."""
from app.models.generation_engine import GenerationRequest,GenerationStatus
from app.providers.generation.base import WaveSpeedSubmissionAmbiguousError,ProviderSubmission
from app.providers.generation.provider_registry import create_default_registry
from app.repositories.video_studio_repository import VideoStudioRepository
from app.services.generated_media_service import GeneratedMediaService


class VideoStudioBackgroundExecutor:
    executor_key="video_studio_generation"
    def __init__(self,repository=None,registry=None,media=None): self.repository=repository or VideoStudioRepository(); self.registry=registry or create_default_registry(); self.media=media or GeneratedMediaService()
    def execute(self,operation,operations,worker_id=None):
        session=self.repository.get_session(operation.subject_id,operation.creator_profile_id); run_id=operation.metadata["run_id"]
        segments=self.repository.list_segments(session["session_id"],run_id); completed=0; prior=session["source_snapshot"].get("provider_reference_url") or session["source_snapshot"]["physical_path"]
        for row in segments:
            if row["status"]=="SUCCEEDED": completed+=int(row["planned_duration"]); prior=row["output_clip"]; continue
            provider=self.registry.require(row["provider_id"])
            if row["status"]=="WAITING_EXTERNAL" and row.get("provider_task_id"):
                submission=ProviderSubmission(provider_request_id=row["provider_task_id"],raw_response=row.get("provider_response") or {})
                poll=provider.poll_status(submission)
                if poll.status!=GenerationStatus.SUCCEEDED.value or not poll.output_references:
                    self.repository.update_segment(row["segment_id"],status="FAILED",failure_code="PROVIDER_FAILED",failure_message=poll.failure_reason or "Provider returned no video.",provider_response=poll.raw_response); raise RuntimeError(poll.failure_reason or "Seedance segment failed.")
                prior=poll.output_references[0]; completed+=int(row["planned_duration"])
                self.repository.update_segment(row["segment_id"],status="SUCCEEDED",output_clip=prior,actual_duration=row["planned_duration"],provider_response=poll.raw_response)
                continue
            locked=self.repository.lock_for_dispatch(row["segment_id"])
            if not locked.get("dispatch_claimed"): raise RuntimeError("Segment dispatch requires provider reconciliation; automatic resubmission is blocked.")
            metadata={**row["request_metadata"],"duration":row["planned_duration"],"resolution":session["settings"]["resolution"],"aspect_ratio":session["settings"]["aspect_ratio"],"generate_audio":session["settings"]["generate_audio"]}
            if row["generation_type"]=="video_extend": metadata["input_video_url"]=prior
            else: metadata["reference_image_url"]=prior
            request=GenerationRequest(request_id=row["idempotency_key"],creator_profile_id=session["creator_profile_id"],prompt_plan_id=str(run_id),prompt_text=row["prompt_snapshot"],reference_asset_id=session.get("source_asset_id"),reference_asset_path=prior,provider_id=row["provider_id"],generation_type=row["generation_type"],media_type="video",metadata=metadata)
            if row["generation_type"]=="video_extend" and not str(prior).startswith(("http://","https://")):
                raise RuntimeError("Video extension requires CREATOR_OS_PUBLIC_BASE_URL so WaveSpeed can fetch the owned source video.")
            try: submission=provider.submit_generation(request)
            except WaveSpeedSubmissionAmbiguousError as error:
                self.repository.update_segment(row["segment_id"],status="SUBMISSION_UNCERTAIN",failure_code="SUBMISSION_UNCERTAIN",failure_message=str(error)); raise
            self.repository.update_segment(row["segment_id"],status="WAITING_EXTERNAL",provider_task_id=submission.provider_request_id,provider_response=submission.raw_response)
            poll=provider.poll_status(submission)
            if poll.status!=GenerationStatus.SUCCEEDED.value or not poll.output_references:
                self.repository.update_segment(row["segment_id"],status="FAILED",failure_code="PROVIDER_FAILED",failure_message=poll.failure_reason or "Provider returned no video.",provider_response=poll.raw_response); raise RuntimeError(poll.failure_reason or "Seedance segment failed.")
            prior=poll.output_references[0]; completed+=int(row["planned_duration"])
            self.repository.update_segment(row["segment_id"],status="SUCCEEDED",output_clip=prior,actual_duration=row["planned_duration"],provider_response=poll.raw_response)
            total=int(session["execution_plan"]["requested_runtime"])
            operations.progress(operation.operation_id,current=completed,total=total,percent=(completed/total)*100,stage="WAITING_EXTERNAL",message=f"Creating your video... {completed} / {total} seconds complete",metadata={"completed_runtime":completed})
        operations.stage(operation.operation_id,"DOWNLOADING_VIDEO","Downloading and validating completed video")
        media=self.media.ingest_video(url=prior,creator_profile_id=session["creator_profile_id"],account_id=session.get("account_id"),provider_id=session["provider_id"],lineage={"session_id":str(session["session_id"]),"source":session["source_lineage"],"segments":[{"segment_id":str(row["segment_id"]),"provider_task_id":row.get("provider_task_id")} for row in self.repository.list_segments(session["session_id"],run_id)]},generation_metadata={"concept":session["selected_concept"],"execution_plan":session["execution_plan"]})
        self.repository.update_session(session["session_id"],session["creator_profile_id"],status="COMPLETE",final_generated_media_id=media["media_id"],final_asset_id=media["asset_id"])
        operations.succeed(operation.operation_id,result_reference=str(media["media_id"]),metadata={"completed_runtime":completed,"generated_media_id":str(media["media_id"])})
