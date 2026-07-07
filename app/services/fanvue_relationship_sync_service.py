import requests


class FanvueRelationshipSyncService:
    BASE_URL = "https://api.fanvue.com"
    API_VERSION = "2025-06-26"

    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Fanvue access token is required.")

        self.access_token = access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "X-Fanvue-API-Version": self.API_VERSION,
            "Accept": "application/json",
        }

    def _get_paginated_users(self, endpoint: str, size: int = 50) -> list[dict]:
        users: list[dict] = []
        page = 1

        print(f"[FANVUE {endpoint.upper()} FETCH START]")

        while True:
            print(f"[FANVUE FETCH PAGE] endpoint={endpoint} page={page} size={size}")

            response = requests.get(
                f"{self.BASE_URL}{endpoint}",
                headers=self._headers(),
                params={"page": page, "size": size},
                timeout=30,
            )

            print(f"[FANVUE FETCH STATUS] endpoint={endpoint} status={response.status_code}")

            response.raise_for_status()

            payload = response.json()
            data = payload.get("data", [])
            pagination = payload.get("pagination", {})

            users.extend(data)

            print(
                f"[FANVUE FETCH PAGE COMPLETE] "
                f"endpoint={endpoint} page={page} returned={len(data)} total_so_far={len(users)}"
            )

            if not pagination.get("hasMore", False):
                break

            page += 1

        print(f"[FANVUE {endpoint.upper()} FETCH COMPLETE] total={len(users)}")
        return users

    def fetch_followers(self) -> list[dict]:
        print("[FANVUE FOLLOWERS FETCH START]")
        return self._get_paginated_users("/followers")

    def fetch_subscribers(self) -> list[dict]:
        print("[FANVUE SUBSCRIBERS FETCH START]")
        return self._get_paginated_users("/subscribers")

    def build_relationship_map(self) -> dict[str, dict]:
        """
        Builds the current Fanvue relationship snapshot.

        Returns:
            {
                "<fanvue_user_uuid>": {
                    "fanvue_user_uuid": str,
                    "username": str | None,
                    "display_name": str | None,
                    "relationship_status": "follower" | "subscriber",
                    "is_follower": bool,
                    "is_subscriber": bool,
                    "is_top_spender": bool,
                }
            }

        Notes:
            - Subscribers override relationship_status.
            - If a user appears in both followers and subscribers, both booleans stay true.
            - No DB writes happen here.
        """
        print("[FANVUE RELATIONSHIP MAP BUILD START]")

        relationship_map: dict[str, dict] = {}

        followers = self.fetch_followers()

        for user in followers:
            user_uuid = user.get("uuid")

            if not user_uuid:
                print("[FANVUE UUID SKIPPED] missing uuid in follower record")
                continue

            relationship_map[user_uuid] = {
                "fanvue_user_uuid": user_uuid,
                "username": user.get("handle"),
                "display_name": user.get("displayName"),
                "relationship_status": "follower",
                "is_follower": True,
                "is_subscriber": False,
                "is_top_spender": user.get("isTopSpender", False),
            }

            print(f"[FANVUE UUID FOUND] source=follower uuid={user_uuid} handle={user.get('handle')}")

        subscribers = self.fetch_subscribers()

        for user in subscribers:
            user_uuid = user.get("uuid")

            if not user_uuid:
                print("[FANVUE UUID SKIPPED] missing uuid in subscriber record")
                continue

            existing = relationship_map.get(user_uuid, {})

            relationship_map[user_uuid] = {
                "fanvue_user_uuid": user_uuid,
                "username": user.get("handle") or existing.get("username"),
                "display_name": user.get("displayName") or existing.get("display_name"),
                "relationship_status": "subscriber",
                "is_follower": existing.get("is_follower", False),
                "is_subscriber": True,
                "is_top_spender": user.get("isTopSpender", existing.get("is_top_spender", False)),
            }

            print(f"[FANVUE UUID FOUND] source=subscriber uuid={user_uuid} handle={user.get('handle')}")

        print(f"[FANVUE RELATIONSHIP MAP BUILD COMPLETE] total_unique_users={len(relationship_map)}")

        return relationship_map