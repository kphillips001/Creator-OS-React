"""Video Studio application service; keeps state invalidation in one place."""
from dataclasses import asdict
from uuid import uuid4
from app.models.video_studio import VideoProviderCapabilityService
from app.repositories.video_studio_repository import VideoStudioRepository
from app.services.video_source_resolver import VideoSourceResolver
from app.services.video_concept_services import VisualSceneIntelligenceService,VideoConceptDirectorService
from app.services.video_execution_planner import VideoExecutionPlanner
from app.services.background_operation_service import BackgroundOperationService


class VideoStudioService:
    def __init__(self, repository=None, sources=None, capabilities=None, intelligence=None, director=None, planner=None, operations=None):
        self.repository=repository or VideoStudioRepository(); self.sources=sources or VideoSourceResolver(); self.capabilities=capabilities or VideoProviderCapabilityService(); self.intelligence=intelligence or VisualSceneIntelligenceService(); self.director=director or VideoConceptDirectorService(); self.planner=planner or VideoExecutionPlanner(); self.operations=operations or BackgroundOperationService()

    def create(self, *, creator_profile_id, account_id, source_type, source_id, settings, parent_session_id=None, parent_video_id=None):
        source=self.sources.resolve(source_type=source_type,source_id=source_id,creator_profile_id=creator_profile_id,account_id=account_id)
        capability=self.capabilities.require(settings["video_provider"])
        normalized={"desired_runtime":int(settings["desired_runtime"]),"aspect_ratio":settings.get("aspect_ratio") or "9:16","resolution":settings.get("resolution","720p"),"generate_audio":bool(settings.get("generate_audio",True)),"video_provider":capability.provider_id,"settings_version":1}
        return self.repository.create_session(creator_profile_id=creator_profile_id,account_id=account_id,source_type=source_type,source_id=source_id,source_asset_id=source["source_asset_id"],source_media_type=source["source_media_type"],source_version=source["source_version"],source_lineage=source["lineage"],source_snapshot=source,settings=normalized,provider_id=capability.provider_id,provider_capability=asdict(capability),parent_session_id=parent_session_id,parent_video_id=parent_video_id)

    def update_settings(self, session, changes):
        settings={**session["settings"],**changes}; capability=self.capabilities.require(settings["video_provider"]); version=int(session["settings_version"])+1; settings["settings_version"]=version
        return self.repository.update_session(session["session_id"],session["creator_profile_id"],settings=settings,settings_version=version,provider_id=capability.provider_id,provider_capability=asdict(capability),concept_batches=[],selected_concept=None,execution_plan=None,status="DRAFT")

    def analyze(self, session):
        source=session["source_snapshot"]; key=self.intelligence.cache_key(source)
        if session.get("visual_intelligence") and session.get("visual_intelligence_cache_key")==key: return session["visual_intelligence"]
        value=self.intelligence.analyze(source); self.repository.update_session(session["session_id"],session["creator_profile_id"],visual_intelligence=value,visual_intelligence_cache_key=key,status="ANALYZED"); return value

    def concepts(self, session, operator_idea=None):
        if not session.get("visual_intelligence"): raise ValueError("Visual Scene Intelligence is required.")
        prior=[c for batch in session.get("concept_batches",[]) for c in batch.get("concepts",[])]
        concepts=self.director.create(intelligence=session["visual_intelligence"],settings=session["settings"],capability=session["provider_capability"],operator_idea=operator_idea,prior_concepts=prior)
        batches=[*session.get("concept_batches",[]),{"batch_id":str(uuid4()),"settings_version":session["settings_version"],"concepts":concepts}]
        self.repository.update_session(session["session_id"],session["creator_profile_id"],concept_batches=batches,custom_guidance=operator_idea,status="CONCEPTS_READY"); return concepts

    def select(self, session, concept_id):
        for batch in session.get("concept_batches",[]):
            for concept in batch.get("concepts",[]):
                if concept["concept_id"]==concept_id and int(concept["settings_version"])==int(session["settings_version"]):
                    return self.repository.update_session(session["session_id"],session["creator_profile_id"],selected_concept=concept,execution_plan=None,status="CONCEPT_SELECTED")
        raise ValueError("Current VideoConcept not found.")

    def plan(self, session):
        if not session.get("selected_concept"): raise ValueError("Select a current VideoConcept first.")
        run_id=str(uuid4()); plan=self.planner.plan(session["selected_concept"],session["provider_capability"],session_id=str(session["session_id"]),run_id=run_id,source_media_type=session["source_media_type"])
        self.repository.create_segments(session["session_id"],run_id,session["provider_id"],plan["segments"])
        self.repository.update_session(session["session_id"],session["creator_profile_id"],execution_plan=plan,current_generation_run=run_id,status="PLANNED"); return plan

    def start_generation(self, session):
        plan=session.get("execution_plan"); run_id=session.get("current_generation_run")
        if not plan or not run_id: raise ValueError("A current execution plan is required.")
        operation,_=self.operations.create(operation_type="VIDEO_GENERATION",originating_workspace="video_studio",creator_profile_id=session["creator_profile_id"],account_id=session.get("account_id"),subject_type="video_generation_session",subject_id=str(session["session_id"]),idempotency_key=f"video:{session['session_id']}:{run_id}",executor_key="video_studio_generation",progress_total=int(plan["requested_runtime"]),current_stage="VALIDATING_PLAN",stage_message="Creating your video",cancellation_supported=False,metadata={"session_id":str(session["session_id"]),"run_id":str(run_id),"requested_runtime":plan["requested_runtime"],"completed_runtime":0})
        return operation
