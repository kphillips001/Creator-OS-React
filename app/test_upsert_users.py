from app.services.fanvue_oauth_service import FanvueOAuthService
from app.services.fanvue_relationship_sync_service import FanvueRelationshipSyncService
from app.repositories.fanvue_user_repository import upsert_fanvue_user


def run_test():
    print("\n=== 14N-2 UPSERT TEST ===\n")

    fanvue_account_id = 1  # Amanda

    oauth = FanvueOAuthService()
    access_token = oauth.get_valid_access_token()

    service = FanvueRelationshipSyncService(access_token=access_token)
    relationship_map = service.build_relationship_map()

    print(f"\n[UPSERT START] total_users={len(relationship_map)}\n")

    for user in relationship_map.values():
        user["fanvue_account_id"] = fanvue_account_id
        upsert_fanvue_user(user)

    print("\n=== UPSERT TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()