"""Objective rolling-seven-day engagement analytics from persisted X data only."""
from __future__ import annotations

from statistics import fmean, median
from typing import Any, Iterable, Mapping

from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository

INTERACTION_FIELDS=("like_count","reply_count","retweet_count","quote_count")
METRIC_FIELDS=("view_count",*INTERACTION_FIELDS)


def _median(values: Iterable[float | int]) -> float | None:
    items=list(values);return float(median(items)) if items else None


def _average(values: Iterable[float | int]) -> float | None:
    items=list(values);return float(fmean(items)) if items else None


def _quartiles(values: Iterable[float]) -> tuple[float | None,float | None]:
    """Tukey hinges: median of each half, excluding the median for odd samples."""
    items=sorted(values);size=len(items)
    if not items:return None,None
    if size==1:return items[0],items[0]
    midpoint=size//2;return float(median(items[:midpoint])),float(median(items[-midpoint:]))


def calculate_engagement(posts: Iterable[Mapping[str,Any]], followers: int | None) -> dict[str,Any]:
    rows=list(posts);valid_followers=isinstance(followers,int) and not isinstance(followers,bool) and followers>0
    enriched=[];metric_values={field:[] for field in METRIC_FIELDS};interaction_values=[];follower_rates=[];viewed_rates=[];reach_rates=[]
    totals={field:0 for field in INTERACTION_FIELDS}
    for post in rows:
        for field in METRIC_FIELDS:
            value=post.get(field)
            if isinstance(value,(int,float)) and not isinstance(value,bool) and value>=0:metric_values[field].append(value)
        interactions=None
        if all(isinstance(post.get(field),(int,float)) and not isinstance(post.get(field),bool) and post[field]>=0 for field in INTERACTION_FIELDS):
            interactions=sum(post[field] for field in INTERACTION_FIELDS);interaction_values.append(interactions)
            for field in INTERACTION_FIELDS:totals[field]+=post[field]
        follower_rate=(interactions/followers*100) if interactions is not None and valid_followers else None
        views=post.get("view_count");viewed_rate=(interactions/views*100) if interactions is not None and isinstance(views,(int,float)) and views>0 else None
        reach_rate=(views/followers*100) if valid_followers and isinstance(views,(int,float)) and views>=0 else None
        if follower_rate is not None:follower_rates.append(follower_rate)
        if viewed_rate is not None:viewed_rates.append(viewed_rate)
        if reach_rate is not None:reach_rates.append(reach_rate)
        enriched.append({**post,"interactions":interactions,"follower_engagement_rate":follower_rate,"viewed_engagement_rate":viewed_rate,"reach_ratio":reach_rate})
    q1,q3=_quartiles(follower_rates);interaction_total=sum(totals.values())
    typical={field.removesuffix("_count"):{"median":_median(values),"average":_average(values)} for field,values in metric_values.items()}
    typical["comments"]=typical.pop("reply");typical["interactions"]={"median":_median(interaction_values),"average":_average(interaction_values)}
    mix={field.removesuffix("_count"):(totals[field]/interaction_total*100 if interaction_total else None) for field in INTERACTION_FIELDS};mix["comments"]=mix.pop("reply")
    ranked=sorted((post for post in enriched if post["follower_engagement_rate"] is not None),key=lambda post:(-post["follower_engagement_rate"],-post["posted_at"].timestamp(),str(post["x_tweet_id"])))[:5]
    return {"sample_size":len(rows),"followers_count":followers,"median_follower_engagement_rate":_median(follower_rates),"median_viewed_engagement_rate":_median(viewed_rates),"median_reach_ratio":_median(reach_rates),"typical":typical,"mix":mix,"consistency":{"minimum":min(follower_rates) if follower_rates else None,"q1":q1,"median":_median(follower_rates),"q3":q3,"maximum":max(follower_rates) if follower_rates else None},"top_posts":ranked}


class XCompetitorEngagementService:
    def __init__(self,repository=None):self.repository=repository or XCompetitorIntelligenceRepository()

    def dashboard(self)->dict[str,Any]:
        data=self.repository.dashboard();posts_by_competitor=self.repository.list_all_posts_7d()
        for item in data["items"]:
            item["engagement_rate"]=calculate_engagement(posts_by_competitor.get(str(item["id"]),[]),item["followers_count"])["median_follower_engagement_rate"] if item["posts_7d"] is not None else None
        return data

    def analyze(self,competitor_id:str)->tuple[Mapping[str,Any],dict[str,Any]]:
        competitor=self.repository.get(competitor_id)
        if competitor is None:raise LookupError("Competitor not found.")
        followers=self.repository.latest_followers(competitor_id);posts=self.repository.list_posts_7d(competitor_id) if self.repository.posts_7d_established(competitor_id) else []
        return competitor,calculate_engagement(posts,followers)
