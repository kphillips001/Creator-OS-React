import os
from pathlib import Path
import psycopg
from dotenv import dotenv_values

root=Path(__file__).resolve().parents[1]
prod=str(dotenv_values(root/'.env').get('DATABASE_URL') or '')
name=str(dotenv_values(root/'.env.session5.local').get('CREATOR_OS_SCENARIO_LAB_DATABASE_NAME') or '')
if not prod or not name: raise SystemExit('isolated database configuration missing')
test=prod.rsplit('/',1)[0]+'/'+name
if test==prod or name in {'fanvue_chatbot','postgres'}: raise SystemExit('refusing production database')
os.environ['DATABASE_URL']=test
with psycopg.connect(test) as c, c.cursor() as q:
 q.execute('select version(),current_database()'); print(q.fetchone())
 q.execute("select to_regclass('public.purchase_intents'),to_regclass('public.ordinary_chat_reply_operations'),to_regclass('public.active_offer_follow_through_events')");print(q.fetchone())
 q.execute("select count(*) from purchase_intents");print('purchase_intents',q.fetchone()[0])
 q.execute("select migration_name from schema_migrations order by applied_at desc limit 8");print(q.fetchall())
