from datetime import datetime,timezone
from typing import Any,Callable
from app.providers.x_twitterapi_io import TwitterApiIoProvider
from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository
from app.services.x_competitor_post_policy import POSTS_VISIBLE_WINDOW

class XCompetitorArchivedPostService:
    def __init__(self,*,provider:Any|None=None,repository:Any|None=None,clock:Callable[[],datetime]|None=None):
        self.provider=provider or TwitterApiIoProvider();self.repository=repository or XCompetitorIntelligenceRepository();self.clock=clock or (lambda:datetime.now(timezone.utc))
    def refresh_metrics(self,post_id:str,*,idempotency_key:str):
        key=idempotency_key.strip()
        if not key or len(key)>128: raise ValueError("A valid idempotency key is required.")
        post=self.repository.get_post_with_competitor(post_id)
        if post is None: raise LookupError("Competitor post not found.")
        now=self.clock();posted=post["posted_at"] if post["posted_at"].tzinfo else post["posted_at"].replace(tzinfo=timezone.utc)
        if post["is_reply"] or post["is_retweet"]: raise ValueError("Only archived original or quote posts can be refreshed individually.")
        if posted>=now-POSTS_VISIBLE_WINDOW: raise ValueError("Only archived posts can be refreshed individually.")
        if self.repository.has_manual_snapshot(post_id,key): return post,True
        activity=self.provider.get_tweet(post["x_tweet_id"])
        return self.repository.persist_manual_metrics(post_id,activity,observed_at=now,key=key),False
