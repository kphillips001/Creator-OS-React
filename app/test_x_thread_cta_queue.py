from datetime import datetime,timezone
from types import SimpleNamespace
import unittest
from app.services.x_thread_cta_queue_service import XThreadCtaQueueService

class Jobs:
    def __init__(self): self.rows={}; self.create_calls=0
    def create_once(self,**values):
        key=values["publish_operation_id"]
        if key not in self.rows: self.create_calls+=1; self.rows[key]={**values,"job_id":f"job-{self.create_calls}","state":"SCHEDULED","attempt_count":0,"created_at":datetime.now(timezone.utc)}
        return self.rows[key]
    def find_by_operation(self,*,publish_operation_id,**scope): return self.rows.get(publish_operation_id)
    def claim(self,*,worker_id,job_id=None,force=False,now=None):
        row=next((r for r in self.rows.values() if (not job_id or r["job_id"]==job_id) and r["state"]=="SCHEDULED"),None)
        if row: row["state"]="CLAIMED";row["attempt_count"]+=1
        return row
    def mark_posted(self,job_id,*,reply_id,output_url,now=None):
        row=next(r for r in self.rows.values() if r["job_id"]==job_id);row.update(state="POSTED",resulting_x_reply_id=reply_id,provider_output_url=output_url);return row
    def mark_uncertain(self,job_id,reason): next(r for r in self.rows.values() if r["job_id"]==job_id).update(state="SEND_UNCERTAIN",failure_reason=reason)
    def expire_claims_to_uncertain(self): return 0
    def get(self,job_id,**scope): return next((r for r in self.rows.values() if r["job_id"]==job_id),None)
class Attributions:
    def __init__(self): self.attached=[]
    def get_or_create_attribution(self,**values): return {**values,"x_link_attribution_id":"a-1"}
    def attach_cta_post(self,a,p): self.attached.append((a,p))
class Provider:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def publish_reply(self,**values):
        self.calls.append(values)
        if self.fail: raise RuntimeError("timeout")
        return SimpleNamespace(provider_post_id="reply-1",provider_output_url="https://x/reply-1")
class Deliveries:
    def __init__(self): self.rows={}
    def claim_once(self,**values):
        key=values["publish_operation_id"]
        self.rows.setdefault(key,{**values,"delivery_id":f"delivery-{len(self.rows)+1}","state":"DELIVERING","_claim_acquired":True})
        return self.rows[key]
    def mark_posted(self,delivery_id,*,reply_id,output_url):
        row=next(r for r in self.rows.values() if r["delivery_id"]==delivery_id);row.update(state="POSTED",resulting_x_reply_id=reply_id,provider_output_url=output_url);return row
    def mark_uncertain(self,delivery_id,reason):
        next(r for r in self.rows.values() if r["delivery_id"]==delivery_id).update(state="SEND_UNCERTAIN",failure_reason=reason)
class XCTAQueueTests(unittest.TestCase):
    def data(self): return dict(attribution_token="opaque-token",creator_profile_id=1,fanvue_account_id=2,publish_operation_id="op-1",social_queue_item_id="q-1",generation_image_id="g-1",primary_x_post_id="p-1",x_account_name="AvaBlackthorne",primary_caption="primary",primary_published_at=datetime.now(timezone.utc),asset_reference="asset",thumbnail_reference="thumb",caption_preview="primary",cta_text="Chat")
    def test_schedule_is_once_and_delay_is_not_resampled(self):
        jobs=Jobs();samples=iter((1800,3600));service=XThreadCtaQueueService(jobs=jobs,attributions=Attributions(),provider=Provider(),delay_sampler=lambda:next(samples));first=service.schedule(**self.data());second=service.schedule(**self.data());self.assertEqual(first["sampled_delay_seconds"],1800);self.assertEqual(second["sampled_delay_seconds"],1800);self.assertEqual(jobs.create_calls,1)
    def test_due_delivery_is_one_reply_to_primary(self):
        jobs=Jobs();provider=Provider();service=XThreadCtaQueueService(jobs=jobs,attributions=Attributions(),provider=provider,deliveries=Deliveries(),delay_sampler=lambda:2400);service.schedule(**self.data());result=service.process_one("worker");self.assertEqual(result["state"],"POSTED");self.assertEqual(provider.calls[0]["in_reply_to_tweet_id"],"p-1");self.assertEqual(service.process_one("worker"),None)
    def test_provider_ambiguity_is_fail_closed(self):
        jobs=Jobs();service=XThreadCtaQueueService(jobs=jobs,attributions=Attributions(),provider=Provider(True),deliveries=Deliveries(),delay_sampler=lambda:2400);job=service.schedule(**self.data());
        with self.assertRaises(RuntimeError): service.process_one("worker")
        self.assertEqual(jobs.get(job["job_id"])["state"],"SEND_UNCERTAIN")
if __name__=="__main__": unittest.main()
