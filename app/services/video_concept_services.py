"""Grok scene analysis and complete-video concept direction."""
from __future__ import annotations
import base64, hashlib, json, os
from pathlib import Path
from uuid import uuid4
from app.config import GROK_VISION_MODEL
from app.services.llm_json_parser import parse_llm_json


def _grok_json(prompt, image_path=None):
    from openai import OpenAI
    client=OpenAI(api_key=os.environ["GROK_API_KEY"],base_url=os.getenv("GROK_BASE_URL","https://api.x.ai/v1"))
    content=[{"type":"input_text","text":prompt}]
    if image_path:
        if str(image_path).startswith(("http://","https://")): image_url=str(image_path)
        else:
            path=Path(image_path); mime={".png":"image/png",".webp":"image/webp"}.get(path.suffix.lower(),"image/jpeg")
            image_url=f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
        content.append({"type":"input_image","image_url":image_url})
    response=client.responses.create(model=GROK_VISION_MODEL,input=[{"role":"user","content":content}])
    return parse_llm_json(response.output_text,model_name=GROK_VISION_MODEL,caller="VideoStudio")


class VisualSceneIntelligenceService:
    schema_version="visual_scene_intelligence_v1"; prompt_version="video_scene_analysis_v1"
    def __init__(self, runner=None): self.runner=runner or _grok_json
    def cache_key(self, source):
        model=GROK_VISION_MODEL
        return hashlib.sha256(f"{source['source_type']}:{source['source_id']}:{source['source_version']}:{self.schema_version}:{model}:{self.prompt_version}".encode()).hexdigest()
    def analyze(self, source):
        prompt="""Analyze this reference as a film creative director. Return JSON only with keys: subject_state, pose, body_orientation, face_orientation, expression, clothing_state, nudity_state, environment, lighting, framing, composition, objects, camera_angle, physical_movement_opportunities, motion_constraints, environmental_motion_opportunities, camera_movement_opportunities, identity_continuity, anatomy_concerns, scene_continuity, audio_opportunities, extension_ending_state. Values may be strings or arrays. No provider syntax."""
        visual_path=source.get("visual_reference_path") or source.get("physical_path")
        value=dict(self.runner(prompt,visual_path)); value.update({"intelligence_id":str(uuid4()),"schema_version":self.schema_version,"cache_key":self.cache_key(source)})
        return value


def validate_video_concept(concept, runtime):
    required=("title","overall_theme","experience_summary","tone","viewer_experience","pacing","narrative_arc","timeline","output_intent")
    missing=[key for key in required if not concept.get(key)]
    if missing: raise ValueError("VideoConcept missing: "+", ".join(missing))
    timeline=concept["timeline"]
    if not timeline or float(timeline[0]["start_second"])!=0 or float(timeline[-1]["end_second"])!=float(runtime): raise ValueError("VideoConcept timeline must cover the complete runtime.")
    cursor=0.0
    for beat in timeline:
        start,end=float(beat["start_second"]),float(beat["end_second"])
        if start!=cursor or end<=start: raise ValueError("VideoConcept timeline contains a gap, overlap, or invalid beat.")
        cursor=end
    return True


class VideoConceptDirectorService:
    schema_version="video_concept_v1"
    def __init__(self, runner=None): self.runner=runner or _grok_json
    def create(self, *, intelligence, settings, capability, operator_idea=None, prior_concepts=()):
        count=1 if operator_idea else 4; runtime=int(settings["desired_runtime"])
        prompt=f"""You are Creator_OS Video Creative Director. Create {count} COMPLETE cinematic video concept(s), not prompts or motion snippets. Runtime is exactly {runtime}s. Settings: {json.dumps(settings)}. Provider creative constraints: {json.dumps(capability)}. Scene intelligence: {json.dumps(intelligence)}. Operator idea: {operator_idea or 'inspire me'}. Avoid prior: {json.dumps(list(prior_concepts))}. Return JSON object {{"concepts":[...]}}. Every concept requires title, overall_theme, experience_summary, tone, viewer_experience, pacing, narrative_arc, output_intent and timeline. Timeline entries require start_second,end_second,phase,creative_beat,subject_direction,expression_direction,camera_direction,environment_direction,audio_direction,continuity_intent. Timeline begins 0, ends {runtime}, has no gaps/overlap, evolves coherently, and has an explicit ending state."""
        raw=self.runner(prompt,None); concepts=[]
        for item in raw.get("concepts",[]):
            concept=dict(item); concept.update({"concept_id":str(uuid4()),"requested_runtime":runtime,"provider_context":capability,"visual_scene_intelligence_id":intelligence["intelligence_id"],"settings_version":settings.get("settings_version",1),"origin":"operator_guided" if operator_idea else "grok_inspiration","status":"ACTIVE","schema_version":self.schema_version})
            validate_video_concept(concept,runtime); concepts.append(concept)
        if len(concepts)!=count: raise ValueError(f"Grok returned {len(concepts)} concepts; expected {count}.")
        return concepts
