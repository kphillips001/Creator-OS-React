"""Rollback-safe Creator_OS scale harness. Never commits synthetic rows."""
from __future__ import annotations

import argparse
import json
import sys
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import get_database_pool


def stats(values):
    ordered = sorted(values)
    return {"p50Ms": round(statistics.median(ordered), 3),
            "p95Ms": round(ordered[max(0, int(len(ordered) * .95) - 1)], 3)}


def query(connection, sql, params=(), iterations=20):
    values=[]
    for _ in range(iterations):
        started=time.perf_counter()
        with connection.cursor() as cursor: cursor.execute(sql,params); cursor.fetchall()
        values.append((time.perf_counter()-started)*1000)
    return stats(values)


def run(scale: int, concurrency: int):
    pool=get_database_pool(); connection=pool.getconn()
    creator=9_000_000 + scale
    try:
        connection.execute("BEGIN"); connection.execute("SAVEPOINT scale_harness")
        with connection.cursor() as cursor:
            cursor.execute("""INSERT INTO generation_library_read_projection(
              image_id,generation_job_id,output_reference,creator_profile_id,provider_id,prompt_plan_id,prompt_text,
              creative_mode,generation_date,status,review_state,created_at,media_available)
              SELECT 'scale-'||%s||'-'||g,'job-'||g,'C:/synthetic',%s,
                CASE WHEN g%%2=0 THEN 'seedream' ELSE 'wavespeed' END,'plan','sunlit portrait concept',
                CASE WHEN g%%3=0 THEN 'explicit' ELSE 'premium' END,NOW()-(g||' seconds')::interval,
                'active','unreviewed',NOW(),TRUE FROM generate_series(1,%s) g""",(scale,creator,scale))
        results={"scale":scale}
        results["page1"]=query(connection,"SELECT image_id FROM generation_library_read_projection WHERE creator_profile_id=%s AND status='active' AND media_available=TRUE ORDER BY generation_date DESC,image_id DESC LIMIT 20",(creator,))
        results["middlePage"]=query(connection,"SELECT image_id FROM generation_library_read_projection WHERE creator_profile_id=%s AND status='active' AND media_available=TRUE ORDER BY generation_date DESC,image_id DESC LIMIT 20 OFFSET %s",(creator,max(0,scale//2)))
        results["deepPage"]=query(connection,"SELECT image_id FROM generation_library_read_projection WHERE creator_profile_id=%s AND status='active' AND media_available=TRUE ORDER BY generation_date DESC,image_id DESC LIMIT 20 OFFSET %s",(creator,max(0,scale-40)))
        results["filter"]=query(connection,"SELECT image_id FROM generation_library_read_projection WHERE creator_profile_id=%s AND status='active' AND provider_id='seedream' AND creative_mode='premium' ORDER BY generation_date DESC LIMIT 20",(creator,))
        results["search"]=query(connection,"SELECT image_id FROM generation_library_read_projection WHERE creator_profile_id=%s AND status='active' AND prompt_text ILIKE '%%sunlit%%' ORDER BY generation_date DESC LIMIT 20",(creator,))
        results["countFacets"]=query(connection,"SELECT COUNT(*),COUNT(DISTINCT provider_id),COUNT(DISTINCT creative_mode) FROM generation_library_read_projection WHERE creator_profile_id=%s AND status='active'",(creator,))
        connection.execute("ROLLBACK TO SAVEPOINT scale_harness"); connection.rollback()
    finally: pool.putconn(connection)

    def concurrent_read(_):
        started=time.perf_counter()
        with pool.connection() as conn,conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM generation_library_read_projection WHERE status='active'"); cursor.fetchone()
        return (time.perf_counter()-started)*1000
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results["concurrentPoolRead"] = stats(list(executor.map(concurrent_read,range(concurrency*4))))
    snapshot=pool.get_stats()
    results["pool"]={key:snapshot.get(key) for key in ("pool_size","pool_available","requests_waiting","requests_errors","requests_num")}
    return results


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--scales",default="1000,10000,50000"); parser.add_argument("--concurrency",type=int,default=8)
    args=parser.parse_args()
    print(json.dumps([run(int(value),args.concurrency) for value in args.scales.split(",")],indent=2))


if __name__ == "__main__": main()
