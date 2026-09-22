from types import SimpleNamespace
import unittest

from app.services.x_thread_cta_publisher import XThreadCtaPublisher


class Deliveries:
    def __init__(self): self.row=None
    def claim_once(self,**values):
        if self.row is None: self.row={**values,"delivery_id":"d-1","state":"DELIVERING","_claim_acquired":True}
        else: self.row["_claim_acquired"]=False
        return self.row
    def mark_posted(self,delivery_id,*,reply_id,output_url):
        self.row.update(state="POSTED",resulting_x_reply_id=reply_id,provider_output_url=output_url);return self.row
    def mark_uncertain(self,delivery_id,reason): self.row.update(state="SEND_UNCERTAIN",failure_reason=reason)
class Provider:
    def __init__(self): self.calls=[]
    def publish_reply(self,**values): self.calls.append(values);return SimpleNamespace(provider_post_id="reply-1",provider_output_url="https://x/reply-1")
class Attributions:
    def __init__(self): self.attached=[]
    def attach_cta_post(self,*values): self.attached.append(values)

class PublisherTests(unittest.TestCase):
    def arguments(self): return dict(creator_profile_id=1,fanvue_account_id=2,publish_operation_id="op",x_account_name="AvaBlackthorne",primary_x_post_id="parent-1",x_link_attribution_id="a-1",timing="ASAP",cta_text="Chat",cta_url="https://example.test")
    def test_asap_and_delayed_share_threaded_publisher_boundary(self):
        for timing in ("ASAP","DELAY_30_60"):
            provider=Provider();publisher=XThreadCtaPublisher(provider=provider,attributions=Attributions(),deliveries=Deliveries());args=self.arguments();args["timing"]=timing
            publisher.publish(**args)
            self.assertEqual(provider.calls,[{"caption":"Chat\nhttps://example.test","in_reply_to_tweet_id":"parent-1","account_name":"AvaBlackthorne"}])
    def test_missing_parent_fails_before_provider(self):
        provider=Provider();publisher=XThreadCtaPublisher(provider=provider,attributions=Attributions(),deliveries=Deliveries());args=self.arguments();args["primary_x_post_id"]=""
        with self.assertRaises(ValueError): publisher.publish(**args)
        self.assertEqual(provider.calls,[])
    def test_confirmed_replay_does_not_publish_twice(self):
        provider=Provider();publisher=XThreadCtaPublisher(provider=provider,attributions=Attributions(),deliveries=Deliveries());publisher.publish(**self.arguments());publisher.publish(**self.arguments())
        self.assertEqual(len(provider.calls),1)

if __name__=="__main__": unittest.main()
