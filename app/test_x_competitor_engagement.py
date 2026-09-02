from datetime import datetime,timezone
from unittest.mock import Mock

from app.services.x_competitor_engagement_service import XCompetitorEngagementService,calculate_engagement


def post(tweet,*,likes=0,replies=0,retweets=0,quotes=0,views=100,day=16):
    return {"id":tweet,"x_tweet_id":tweet,"posted_at":datetime(2026,8,day,tzinfo=timezone.utc),"like_count":likes,"reply_count":replies,"retweet_count":retweets,"quote_count":quotes,"view_count":views,"text":tweet,"language":None,"conversation_id":None,"is_quote":False,"has_media":False,"media_metadata":[],"bookmark_count":None}


def test_primary_rates_medians_reach_mix_and_consistency_are_mathematically_correct():
    result=calculate_engagement([post("a",likes=10,views=50),post("b",likes=20,views=100),post("c",likes=30,views=300),post("d",likes=40,views=400)],100)
    assert result["median_follower_engagement_rate"]==25
    assert result["median_viewed_engagement_rate"]==15
    assert result["median_reach_ratio"]==200  # reach is intentionally not capped
    assert result["typical"]["like"]=={"median":25.0,"average":25.0}
    assert result["typical"]["interactions"]["median"]==25
    assert result["mix"]=={"like":100,"retweet":0,"quote":0,"comments":0}
    assert result["consistency"]=={"minimum":10,"q1":15,"median":25,"q3":35,"maximum":40}
    assert [item["x_tweet_id"] for item in result["top_posts"]]==["d","c","b","a"]


def test_unknown_metrics_and_invalid_denominators_are_not_fabricated():
    incomplete=post("unknown",likes=None);zero_views=post("zero",likes=5,views=0)
    result=calculate_engagement([incomplete,zero_views],0)
    assert result["sample_size"]==2 and result["median_follower_engagement_rate"] is None
    assert result["median_viewed_engagement_rate"] is None and result["median_reach_ratio"] is None
    assert result["typical"]["interactions"]["median"]==5
    assert calculate_engagement([],None)["sample_size"]==0


def test_odd_median_has_no_frequency_inflation_or_premature_rounding():
    result=calculate_engagement([post("a",likes=1),post("b",likes=2),post("c",likes=100)],3)
    assert result["median_follower_engagement_rate"]==2/3*100


def test_service_reads_only_persisted_repository_data_and_never_has_a_provider():
    repository=Mock();repository.get.return_value={"id":"1","username":"ava","display_name":"Ava","profile_image_url":None};repository.latest_followers.return_value=100;repository.posts_7d_established.return_value=True;repository.list_posts_7d.return_value=[post("a",likes=2)]
    service=XCompetitorEngagementService(repository=repository);_,result=service.analyze("1")
    assert result["median_follower_engagement_rate"]==2 and not hasattr(service,"provider")


def test_unestablished_posts_dataset_does_not_create_fake_engagement():
    repository=Mock();repository.get.return_value={"id":"1","username":"ava"};repository.latest_followers.return_value=100;repository.posts_7d_established.return_value=False
    _,result=XCompetitorEngagementService(repository=repository).analyze("1")
    assert result["sample_size"]==0 and result["median_follower_engagement_rate"] is None
    repository.list_posts_7d.assert_not_called()
