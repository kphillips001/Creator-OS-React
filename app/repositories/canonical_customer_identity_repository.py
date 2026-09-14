"""Exact, creator-scoped canonical customer identity persistence."""
from uuid import UUID, uuid4
from app.database import get_db_connection


class CustomerIdentityConflictError(ValueError): pass


class CanonicalCustomerIdentityRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def missing_commerce_customers(self, *, creator_profile_id=None):
        scope = "AND p.creator_profile_id=%s" if creator_profile_id is not None else ""
        params = (creator_profile_id,) if creator_profile_id is not None else ()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""SELECT p.* FROM customer_commerce_profiles p
                LEFT JOIN fanvue_users u ON u.fanvue_account_id=p.fanvue_account_id
                 AND u.fanvue_user_uuid=p.external_fanvue_user_uuid
                WHERE u.id IS NULL {scope} ORDER BY p.customer_commerce_profile_id""", params)
            return cursor.fetchall()

    def materialize(self, *, profile_id, dry_run=True):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM customer_commerce_profiles WHERE customer_commerce_profile_id=%s FOR SHARE", (profile_id,))
            profile = cursor.fetchone()
            if not profile: raise LookupError("Commerce profile was not found")
            cursor.execute("SELECT * FROM fanvue_users WHERE fanvue_account_id=%s AND fanvue_user_uuid=%s", (profile["fanvue_account_id"],profile["external_fanvue_user_uuid"]))
            existing = cursor.fetchone()
            if existing or dry_run:
                return {"status":"EXISTS" if existing else "WOULD_CREATE","profile":profile,"customer":existing,"dry_run":dry_run}
            cursor.execute("""INSERT INTO fanvue_users(fanvue_account_id,fanvue_user_uuid,username,display_name,source)
                VALUES(%s,%s,%s,%s,'commerce_profile_reconciliation')
                ON CONFLICT(fanvue_account_id,fanvue_user_uuid) DO UPDATE SET
                  username=COALESCE(fanvue_users.username,EXCLUDED.username),
                  display_name=COALESCE(fanvue_users.display_name,EXCLUDED.display_name)
                RETURNING *""",(profile["fanvue_account_id"],profile["external_fanvue_user_uuid"],profile.get("handle"),profile.get("display_name")))
            customer=cursor.fetchone()
            cursor.execute("""INSERT INTO canonical_customer_materialization_audit(
                audit_id,customer_commerce_profile_id,fanvue_account_id,local_fanvue_user_id,
                external_fanvue_user_uuid,action,source) VALUES(%s,%s,%s,%s,%s,'CREATED',%s)""",
                (uuid4(),profile["customer_commerce_profile_id"],profile["fanvue_account_id"],
                 customer["id"],profile["external_fanvue_user_uuid"],"commerce_profile_reconciliation"))
            return {"status":"CREATED","profile":profile,"customer":customer,"dry_run":False}

    def metadata_enrichment_preview(self, *, fanvue_account_id, local_fanvue_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM fanvue_users WHERE fanvue_account_id=%s AND id=%s",
                           (fanvue_account_id,local_fanvue_user_id)); customer=cursor.fetchone()
            if not customer: raise LookupError("Canonical Fanvue customer was not found")
            cursor.execute("""SELECT earnings_record->'user' provider_user,verified_at
                FROM commerce_signal_reconciliations WHERE fanvue_account_id=%s
                AND external_fanvue_user_uuid=%s AND state='VERIFIED'
                AND earnings_record->'user'->>'uuid'=%s ORDER BY verified_at DESC LIMIT 1""",
                (fanvue_account_id,customer['fanvue_user_uuid'],str(customer['fanvue_user_uuid'])))
            evidence=cursor.fetchone(); provider=dict((evidence or {}).get('provider_user') or {})
            proposed={'username':provider.get('handle'),'display_name':provider.get('displayName'),
                      'source':'provider_verified_earnings'}
            conflicts={key:{'current':customer.get(key),'proposed':value} for key,value in proposed.items()
                       if customer.get(key) not in (None,'') and value not in (None,'') and customer.get(key)!=value}
            changes={key:value for key,value in proposed.items() if customer.get(key) in (None,'') and value not in (None,'')}
            return {'customer':customer,'changes':changes,'conflicts':conflicts,
                    'evidence':{'type':'PROVIDER_VERIFIED_EARNINGS','verified_at':(evidence or {}).get('verified_at')},
                    'canApply':bool(changes) and not conflicts}

    def apply_metadata_enrichment(self, *, fanvue_account_id, local_fanvue_user_id):
        preview=self.metadata_enrichment_preview(fanvue_account_id=fanvue_account_id,local_fanvue_user_id=local_fanvue_user_id)
        if preview['conflicts']: raise CustomerIdentityConflictError('Non-null canonical metadata conflicts with provider evidence')
        if not preview['changes']: return {**preview,'status':'NO_CHANGES','idempotent':True}
        before={key:preview['customer'].get(key) for key in ('username','display_name','source')}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE fanvue_users SET username=COALESCE(username,%s),
                display_name=COALESCE(display_name,%s),source=COALESCE(source,%s),updated_at=NOW()
                WHERE fanvue_account_id=%s AND id=%s AND fanvue_user_uuid=%s RETURNING *""",
                (preview['changes'].get('username'),preview['changes'].get('display_name'),
                 preview['changes'].get('source'),fanvue_account_id,local_fanvue_user_id,
                 preview['customer']['fanvue_user_uuid'])); after=cursor.fetchone()
            cursor.execute("""SELECT customer_commerce_profile_id FROM customer_commerce_profiles
                WHERE fanvue_account_id=%s AND external_fanvue_user_uuid=%s""",
                (fanvue_account_id,after['fanvue_user_uuid'])); profile=cursor.fetchone()
            cursor.execute("""INSERT INTO canonical_customer_materialization_audit(
                audit_id,customer_commerce_profile_id,fanvue_account_id,local_fanvue_user_id,
                external_fanvue_user_uuid,action,source) VALUES(%s,%s,%s,%s,%s,'METADATA_COMPLETED',%s)""",
                (uuid4(),profile['customer_commerce_profile_id'],fanvue_account_id,local_fanvue_user_id,
                 after['fanvue_user_uuid'],'operator_provider_evidence_enrichment'))
        return {'status':'APPLIED','before':before,'customer':after,'idempotent':False}

    def observed_external(self, *, creator_profile_id, platform="X"):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM external_customer_identity_observations
                WHERE creator_profile_id=%s AND platform=%s ORDER BY last_observed_at DESC""",
                (creator_profile_id,str(platform).upper()))
            return cursor.fetchall()

    def get_observed_external(self, *, creator_profile_id, platform, external_numeric_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM external_customer_identity_observations
                WHERE creator_profile_id=%s AND platform=%s AND external_numeric_id=%s""",
                (creator_profile_id,str(platform).upper(),str(external_numeric_id)))
            return cursor.fetchone()

    def observe_external(self, *, creator_profile_id, platform, external_numeric_id,
                         username=None, display_name=None, source):
        platform=str(platform).upper(); external=str(external_numeric_id).strip()
        if platform != "X" or not external.isdigit():
            raise ValueError("A stable numeric X identity is required")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO external_customer_identity_observations(
                observation_id,creator_profile_id,platform,external_numeric_id,
                observed_username,observed_display_name,observation_source)
                VALUES(%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(creator_profile_id,platform,external_numeric_id) DO UPDATE SET
                  observed_username=COALESCE(EXCLUDED.observed_username,external_customer_identity_observations.observed_username),
                  observed_display_name=COALESCE(EXCLUDED.observed_display_name,external_customer_identity_observations.observed_display_name),
                  observation_source=EXCLUDED.observation_source,last_observed_at=NOW()
                RETURNING *""",(uuid4(),creator_profile_id,platform,external,username,display_name,source))
            return cursor.fetchone()

    def verify_external(self, *, creator_profile_id, fanvue_account_id, local_fanvue_user_id,
                        platform, external_numeric_id, username=None, display_name=None,
                        evidence, operator_source):
        platform=str(platform).upper(); external=str(external_numeric_id).strip()
        if platform != "X" or not external.isdigit(): raise ValueError("A stable numeric X identity is required")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(f"external-identity:{creator_profile_id}:{platform}:{external}",))
            cursor.execute("""SELECT u.* FROM fanvue_users u JOIN creator_profiles cp
                ON cp.id=%s AND cp.fanvue_account_id::text=u.fanvue_account_id::text
                WHERE u.id=%s AND u.fanvue_account_id=%s""",
                (creator_profile_id,local_fanvue_user_id,fanvue_account_id)); customer=cursor.fetchone()
            if not customer: raise LookupError("Canonical Fanvue customer was not found")
            cursor.execute("""SELECT * FROM external_customer_identity_observations
                WHERE creator_profile_id=%s AND platform=%s AND external_numeric_id=%s""",
                (creator_profile_id,platform,external)); observation=cursor.fetchone()
            if not observation: raise LookupError("Observed stable X identity was not found")
            cursor.execute("SELECT * FROM verified_external_customer_identities WHERE creator_profile_id=%s AND platform=%s AND external_numeric_id=%s AND is_active",(creator_profile_id,platform,external)); current=cursor.fetchone()
            if current:
                if int(current["local_fanvue_user_id"]) != int(local_fanvue_user_id): raise CustomerIdentityConflictError("External identity is linked to another customer")
                return current, True
            cursor.execute("SELECT 1 FROM verified_external_customer_identities WHERE creator_profile_id=%s AND fanvue_account_id=%s AND local_fanvue_user_id=%s AND platform=%s AND is_active",(creator_profile_id,fanvue_account_id,local_fanvue_user_id,platform))
            if cursor.fetchone(): raise CustomerIdentityConflictError("Customer already has an active identity for this platform")
            link_id=uuid4(); cursor.execute("""INSERT INTO verified_external_customer_identities(
                external_identity_link_id,creator_profile_id,fanvue_account_id,local_fanvue_user_id,platform,
                external_numeric_id,observation_id,observed_username,observed_display_name,verification_method,
                verification_source,verification_evidence) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,
                %s,'OPERATOR_CONFIRMED_STABLE_PROVIDER_ID',%s,%s::jsonb) RETURNING *""",
                (link_id,creator_profile_id,fanvue_account_id,local_fanvue_user_id,platform,external,
                 observation["observation_id"],observation.get("observed_username"),
                 observation.get("observed_display_name"),operator_source,__import__('json').dumps(evidence)))
            row=cursor.fetchone(); cursor.execute("INSERT INTO verified_external_customer_identity_audit(audit_id,external_identity_link_id,action,operator_source,evidence) VALUES(%s,%s,'VERIFIED',%s,%s::jsonb)",(uuid4(),link_id,operator_source,__import__('json').dumps(evidence)))
            return row, False

    def active_for_customer(self, *, fanvue_account_id, local_fanvue_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.verified_external_customer_identities') AS table_name")
            if cursor.fetchone()["table_name"] is None:
                return []
            cursor.execute("""SELECT link.*,
                COALESCE(observation.observed_username,link.observed_username) AS observed_username,
                COALESCE(observation.observed_display_name,link.observed_display_name) AS observed_display_name
                FROM verified_external_customer_identities link
                JOIN external_customer_identity_observations observation ON observation.observation_id=link.observation_id
                WHERE link.fanvue_account_id=%s AND link.local_fanvue_user_id=%s AND link.is_active
                ORDER BY link.platform""",(fanvue_account_id,local_fanvue_user_id)); return cursor.fetchall()

    def deactivate(self, *, link_id, reason, operator_source):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE verified_external_customer_identities SET is_active=FALSE,deactivated_at=NOW(),deactivation_reason=%s,updated_at=NOW() WHERE external_identity_link_id=%s AND is_active RETURNING *",(reason,UUID(str(link_id)))); row=cursor.fetchone()
            if not row: raise LookupError("Active external identity link was not found")
            cursor.execute("INSERT INTO verified_external_customer_identity_audit(audit_id,external_identity_link_id,action,operator_source,evidence) VALUES(%s,%s,'DEACTIVATED',%s,%s::jsonb)",(uuid4(),row["external_identity_link_id"],operator_source,__import__('json').dumps({"reason":reason}))); return row
