"""Durable workflow authority for Ava-improvement requests; never runtime authority."""
from uuid import uuid4
from psycopg.types.json import Json
from app.database import get_db_connection


class AiTrainingWorkItemRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory=connection_factory

    def list(self, *, creator_profile_id, fanvue_account_id):
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""SELECT * FROM public.ai_training_work_items WHERE creator_profile_id=%s
                AND fanvue_account_id=%s ORDER BY updated_at DESC,work_item_id""",(creator_profile_id,fanvue_account_id))
            return q.fetchall()

    def get(self, work_item_id, *, creator_profile_id, fanvue_account_id):
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""SELECT * FROM public.ai_training_work_items WHERE work_item_id=%s
                AND creator_profile_id=%s AND fanvue_account_id=%s""",(work_item_id,creator_profile_id,fanvue_account_id))
            return q.fetchone()

    def create(self, *, creator_profile_id, fanvue_account_id, scope, customer_fanvue_user_id, text, analysis=None):
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""INSERT INTO public.ai_training_work_items(work_item_id,creator_profile_id,
                fanvue_account_id,scope,customer_fanvue_user_id,original_request_text,status,analysis)
                VALUES(%s,%s,%s,%s,%s,%s,'TODO',%s) RETURNING *""",
                (uuid4(),creator_profile_id,fanvue_account_id,scope,customer_fanvue_user_id,text,Json(analysis or {})))
            return q.fetchone()

    def update(self, work_item_id, *, creator_profile_id, fanvue_account_id, **values):
        allowed={"original_request_text","status","classification","classification_rationale","analysis","linked_instruction_id","linked_future_task_id"}
        pairs=[(key,value) for key,value in values.items() if key in allowed]
        if not pairs:return self.get(work_item_id,creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
        assignments=[];params=[]
        for key,value in pairs:
            assignments.append(f"{key}=%s")
            params.append(Json(value) if key=="analysis" else value)
        assignments.append("updated_at=NOW()")
        if "status" in values:
            assignments.append("completed_at=NOW()" if values["status"] in {"IMPLEMENTED","REJECTED","CLOSED","SUPERSEDED"} else "completed_at=NULL")
        params.extend([work_item_id,creator_profile_id,fanvue_account_id])
        with self.connection_factory() as c, c.cursor() as q:
            q.execute(f"""UPDATE public.ai_training_work_items SET {','.join(assignments)}
                WHERE work_item_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s RETURNING *""",params)
            return q.fetchone()
