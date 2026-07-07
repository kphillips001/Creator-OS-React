from app.services.fanvue_oauth_service import FanvueOAuthService
from app.services.fanvue_relationship_sync_service import FanvueRelationshipSyncService


def run_test():
    print("\n=== 14N RELATIONSHIP MAP TEST ===\n")

    oauth = FanvueOAuthService()
    access_token = oauth.get_valid_access_token()

    service = FanvueRelationshipSyncService(access_token=access_token)

    relationship_map = service.build_relationship_map()

    followers_count = sum(1 for user in relationship_map.values() if user.get("is_follower"))
    subscribers_count = sum(1 for user in relationship_map.values() if user.get("is_subscriber"))

    print("\n========== SUMMARY ==========")
    print(f"Unique Users: {len(relationship_map)}")
    print(f"Followers: {followers_count}")
    print(f"Subscribers: {subscribers_count}")

    print("\n========== FIRST 5 USERS ==========")
    for user in list(relationship_map.values())[:5]:
        print(user)

    print("\n=== TEST COMPLETE — NO DB WRITES PERFORMED ===\n")


if __name__ == "__main__":
    run_test()