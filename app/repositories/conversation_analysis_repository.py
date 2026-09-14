"""Account/relationship-scoped persistence for read-only conversation analyses."""
from __future__ import annotations

import json
from app.database import get_db_connection


class ConversationAnalysisRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory=connection_factory

    def create(self, **v):
        return self._one("""INSERT INTO conversation_analyses(
          analysis_id,creator_profile_id,fanvue_account_id,relationship_key,
          telegram_user_id,telegram_chat_id,target_type,target_message_reference,
          evidence_fingerprint,evidence_digest,structured_result,validated_scope,
          failure_signatures,similar_case_summary,global_repair_candidate,
          provider_metadata,schema_version)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s)
          RETURNING *""",(v["analysis_id"],v["creator_profile_id"],v["fanvue_account_id"],
          v["relationship_key"],v["telegram_user_id"],v["telegram_chat_id"],v["target_type"],
          v.get("target_message_reference"),v["evidence_fingerprint"],v["evidence_digest"],
          json.dumps(v["structured_result"],default=str),v["validated_scope"],
          json.dumps(v["failure_signatures"],default=str),json.dumps(v["similar_case_summary"],default=str),
          v["global_repair_candidate"],json.dumps(v["provider_metadata"],default=str),v["schema_version"]))

    def get(self, analysis_id, *, creator_profile_id, fanvue_account_id, relationship_key=None):
        suffix=" AND relationship_key=%s" if relationship_key else ""
        params=[analysis_id,creator_profile_id,fanvue_account_id]
        if relationship_key: params.append(relationship_key)
        return self._one("""SELECT * FROM conversation_analyses WHERE analysis_id=%s
          AND creator_profile_id=%s AND fanvue_account_id=%s"""+suffix,tuple(params))

    def similar(self, signatures, *, creator_profile_id, fanvue_account_id,
                exclude_relationship_key, limit=25):
        if not signatures:return []
        return self._all("""SELECT analysis_id,relationship_key,validated_scope,
          failure_signatures,analyzed_at FROM conversation_analyses
          WHERE creator_profile_id=%s AND fanvue_account_id=%s
            AND relationship_key<>%s AND failure_signatures ?| %s
          ORDER BY analyzed_at DESC LIMIT %s""",(creator_profile_id,fanvue_account_id,
          exclude_relationship_key,list(signatures),limit))

    def count_all(self):
        row=self._one("SELECT COUNT(*) AS value FROM conversation_analyses",())
        return int(row["value"] if row else 0)

    def structural_similar(self, signatures, *, creator_profile_id, fanvue_account_id,
                           exclude_telegram_user_id, limit=25):
        """Search only canonical operation diagnostics; never unrelated transcript text."""
        clauses=[];params=[]
        if "CUSTOMER_QUESTION_UNANSWERED" in signatures:
            clauses.append("COALESCE(o.last_error,'') LIKE %s");params.append("%CUSTOMER_QUESTION_UNANSWERED%")
        if "MEMORY_RELEVANCE_FAILURE" in signatures:
            clauses.append("o.response_payload::text ~* %s");params.append("MEMORY_IRRELEVANCE|IRRELEVANT_MEMORY")
        if "COMMERCIAL_AUTHORITY_CONTRADICTION" in signatures:
            clauses.append("(o.response_payload#>>'{diagnostic_metadata,pre_generation_commercial_decision,classification}' IN (%s,%s,%s) AND COALESCE(o.response_payload#>>'{diagnostic_metadata,customer_sales_brain,decision}','') IN (%s,%s))")
            params.extend(["ORDINARY_NONCOMMERCIAL","NONCOMMERCIAL","NO_COMMERCIAL_INTENT","SELL","PRESENT_OFFER"])
        if not clauses:return []
        query="""SELECT DISTINCT p.telegram_user_id FROM ordinary_chat_reply_operations o
          JOIN telegram_sales_prospects p ON p.telegram_user_id=o.inbound_sender_telegram_user_id
            AND p.telegram_chat_id=o.telegram_chat_id
          WHERE p.creator_profile_id=%s AND p.fanvue_account_id=%s
            AND p.telegram_user_id<>%s AND ("""+" OR ".join(clauses)+") LIMIT %s"
        rows=self._all(query,tuple([creator_profile_id,fanvue_account_id,
                                    exclude_telegram_user_id]+params+[limit]))
        return [{"relationship_key":f"telegram:{creator_profile_id}:{fanvue_account_id}:{row['telegram_user_id']}"}
                for row in rows]

    def _one(self,query,params):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute(query,params);row=cursor.fetchone()
        return dict(row) if row else None

    def _all(self,query,params):
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute(query,params);return [dict(row) for row in cursor.fetchall()]
