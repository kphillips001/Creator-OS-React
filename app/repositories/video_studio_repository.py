"""PostgreSQL authority for Video Studio sessions and paid segments."""
from __future__ import annotations
import json
from uuid import UUID, uuid4
from app.database import get_db_connection


class VideoStudioRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory = connection_factory

    def create_session(self, **value):
        session_id = value.get("session_id") or uuid4()
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO public.video_generation_sessions
              (session_id,creator_profile_id,account_id,source_type,source_id,source_asset_id,source_media_type,
               source_version,source_lineage,source_snapshot,settings,provider_id,provider_capability,parent_session_id,parent_video_id)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s,%s) RETURNING *""",
              (session_id,value["creator_profile_id"],value.get("account_id"),value["source_type"],str(value["source_id"]),
               value.get("source_asset_id"),value["source_media_type"],value["source_version"],json.dumps(value.get("source_lineage",{})),
               json.dumps(value.get("source_snapshot",{})),json.dumps(value["settings"]),value["provider_id"],
               json.dumps(value["provider_capability"]),value.get("parent_session_id"),value.get("parent_video_id")))
            return dict(cur.fetchone())

    def get_session(self, session_id, creator_profile_id):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.video_generation_sessions WHERE session_id=%s AND creator_profile_id=%s",(session_id,creator_profile_id)); row=cur.fetchone()
            return dict(row) if row else None

    def list_sessions(self, creator_profile_id, account_id=None):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.video_generation_sessions WHERE creator_profile_id=%s AND (%s IS NULL OR account_id=%s) ORDER BY created_at DESC",(creator_profile_id,account_id,account_id))
            return [dict(row) for row in cur.fetchall()]

    def list_gallery(self, creator_profile_id, *, page=1, page_size=24, sort="newest", provider_id=None, search=None):
        clauses=["s.creator_profile_id=%s", "s.status='COMPLETE'", "s.final_generated_media_id IS NOT NULL", "m.media_type='video'"]
        params=[creator_profile_id]
        if provider_id:
            clauses.append("s.provider_id=%s"); params.append(provider_id)
        if search:
            clauses.append("(COALESCE(s.selected_concept->>'title','') ILIKE %s OR COALESCE(s.selected_concept->>'experience_summary','') ILIKE %s OR COALESCE(s.provider_id,'') ILIKE %s OR COALESCE(s.source_snapshot->>'label',s.source_snapshot->>'file_name','') ILIKE %s)")
            term=f"%{search}%"; params.extend((term,term,term,term))
        where=" AND ".join(clauses); direction="ASC" if sort=="oldest" else "DESC"
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS total FROM public.video_generation_sessions s JOIN public.generated_media m ON m.media_id=s.final_generated_media_id WHERE {where}",tuple(params)); total=int(cur.fetchone()["total"])
            cur.execute(f"""SELECT s.*,m.media_path,m.poster_path,m.duration_seconds,m.width,m.height,
              m.provider_metadata,m.generation_metadata,m.source_lineage AS media_lineage,m.created_at AS media_created_at
              FROM public.video_generation_sessions s JOIN public.generated_media m ON m.media_id=s.final_generated_media_id
              WHERE {where} ORDER BY m.created_at {direction},m.media_id {direction} LIMIT %s OFFSET %s""",tuple([*params,page_size,(page-1)*page_size]))
            return [dict(row) for row in cur.fetchall()],total

    def get_gallery_item(self, media_id, creator_profile_id):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""SELECT s.*,m.media_path,m.poster_path,m.duration_seconds,m.width,m.height,
              m.provider_metadata,m.generation_metadata,m.source_lineage AS media_lineage,m.created_at AS media_created_at
              FROM public.video_generation_sessions s JOIN public.generated_media m ON m.media_id=s.final_generated_media_id
              WHERE m.media_id=%s AND s.creator_profile_id=%s AND s.status='COMPLETE' AND m.media_type='video'""",(media_id,creator_profile_id)); row=cur.fetchone()
            return dict(row) if row else None

    def update_session(self, session_id, creator_profile_id, **values):
        allowed={"status","settings","settings_version","provider_id","provider_capability","visual_intelligence","visual_intelligence_cache_key","concept_batches","selected_concept","custom_guidance","execution_plan","current_generation_run","final_generated_media_id","final_asset_id"}
        assignments=[]; params=[]
        for key,value in values.items():
            if key not in allowed: continue
            if key in {"settings","provider_capability","visual_intelligence","concept_batches","selected_concept","execution_plan"}:
                assignments.append(f"{key}=%s::jsonb"); value=json.dumps(value) if value is not None else None
            else: assignments.append(f"{key}=%s")
            params.append(value)
        if not assignments: return self.get_session(session_id,creator_profile_id)
        params.extend((session_id,creator_profile_id))
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE public.video_generation_sessions SET {','.join(assignments)},updated_at=NOW() WHERE session_id=%s AND creator_profile_id=%s RETURNING *",tuple(params)); row=cur.fetchone()
            return dict(row) if row else None

    def create_segments(self, session_id, run_id, provider_id, segments):
        rows=[]
        with self.connection_factory() as conn, conn.cursor() as cur:
            for segment in segments:
                cur.execute("""INSERT INTO public.video_generation_segments(segment_id,session_id,generation_run_id,ordinal,generation_type,planned_duration,provider_id,idempotency_key,prompt_snapshot,request_metadata)
                 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(generation_run_id,ordinal) DO UPDATE SET updated_at=NOW() RETURNING *""",
                 (uuid4(),session_id,run_id,segment["ordinal"],segment["generation_type"],segment["planned_duration"],provider_id,segment["dispatch_identity"],segment["prompt"],json.dumps(segment)))
                rows.append(dict(cur.fetchone()))
        return rows

    def list_segments(self, session_id, run_id):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.video_generation_segments WHERE session_id=%s AND generation_run_id=%s ORDER BY ordinal",(session_id,run_id)); return [dict(row) for row in cur.fetchall()]

    def lock_for_dispatch(self, segment_id):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.video_generation_segments WHERE segment_id=%s FOR UPDATE",(segment_id,)); row=cur.fetchone()
            if not row: return None
            if row["status"] in {"SUCCEEDED","SUBMITTING","WAITING_EXTERNAL","SUBMISSION_UNCERTAIN"}:
                value=dict(row); value["dispatch_claimed"]=False; return value
            cur.execute("UPDATE public.video_generation_segments SET status='SUBMITTING',dispatch_started_at=NOW(),attempt_count=attempt_count+1,updated_at=NOW() WHERE segment_id=%s RETURNING *",(segment_id,))
            value=dict(cur.fetchone()); value["dispatch_claimed"]=True; return value

    def update_segment(self, segment_id, **values):
        allowed={"status","provider_task_id","provider_response","output_clip","output_hash","actual_duration","failure_code","failure_message","input_source","generation_job_id"}; assignments=[]; params=[]
        for key,value in values.items():
            if key not in allowed: continue
            if key in {"provider_response","input_source"}: assignments.append(f"{key}=%s::jsonb"); value=json.dumps(value)
            else: assignments.append(f"{key}=%s")
            params.append(value)
        terminal_status=values.get("status")
        params.extend((terminal_status,segment_id))
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE public.video_generation_segments SET {','.join(assignments)},updated_at=NOW(),completed_at=CASE WHEN %s='SUCCEEDED' THEN NOW() ELSE completed_at END WHERE segment_id=%s RETURNING *",tuple(params))
            return dict(cur.fetchone())
