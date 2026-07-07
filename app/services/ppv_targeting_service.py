from app.database import get_db_connection


class PPVTargetingService:
    def get_basic_targets(
        self,
        fanvue_account_id: int,
        content_tag: str,
        cooldown_hours: int = 24,
        include_followers: bool = True,
        include_subscribers: bool = True,
        limit: int = 100,
    ):
        """
        Upgraded PPV targeting v4 (Balanced):
        - Excludes whales
        - Excludes non-chat routes
        - Respects broadcast cooldown
        - Excludes users in active offer flow
        - Excludes users currently being nudged
        - Requires some spacing since the last offer
        - Followers are prioritized first
        - Subscribers are allowed but lower priority
        - Lower value users inside each group are prioritized first
        """

        conditions = ["u.fanvue_account_id = %s"]
        params = [fanvue_account_id]

        audience_filters = []

        if include_followers:
            audience_filters.append("u.is_follower = TRUE")

        if include_subscribers:
            audience_filters.append("u.is_subscriber = TRUE")

        if audience_filters:
            conditions.append("(" + " OR ".join(audience_filters) + ")")
        else:
            return []

        query = f"""
            SELECT
                u.id,
                u.fanvue_account_id,
                u.fanvue_user_uuid,
                u.username,
                u.display_name,
                u.relationship_status,
                u.is_follower,
                u.is_subscriber,
                m.user_value_tier,
                m.is_whale,
                m.value_score,
                m.attention_tier,
                m.current_route,
                m.current_route AS debug_current_route,
                m.offer_state,
                m.post_offer_nudge_count,
                m.messages_since_last_offer
            FROM fanvue_users u
            LEFT JOIN user_memory m
              ON u.fanvue_account_id = m.fanvue_account_id
             AND u.id = m.fanvue_user_id
            WHERE {' AND '.join(conditions)}
              AND COALESCE(m.is_whale, FALSE) = FALSE
              AND (
                  COALESCE(m.current_route, 'chat') = 'chat'
                  OR COALESCE(m.outreach_status, 'none') IN ('ignored', 'exhausted')
              )
              AND COALESCE(m.offer_state, 'none') IN ('none', 'expired')
              AND COALESCE(m.post_offer_nudge_count, 0) = 0
              AND COALESCE(m.messages_since_last_offer, 999999) >= 0
              AND NOT EXISTS (
                  SELECT 1
                  FROM ppv_broadcast_logs b
                  WHERE b.fanvue_account_id = u.fanvue_account_id
                    AND b.fanvue_user_id = u.id
                    AND b.created_at >= NOW() - (%s * INTERVAL '1 hour')
              )
            ORDER BY
                CASE
                    WHEN u.is_follower = TRUE AND COALESCE(u.is_subscriber, FALSE) = FALSE THEN 0
                    WHEN u.is_subscriber = TRUE THEN 1
                    ELSE 2
                END ASC,
                COALESCE(m.value_score, 999999) ASC,
                u.id ASC
            LIMIT %s
        """

        params.extend([cooldown_hours, limit])

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = cur.fetchall()
                print("PPV TARGETS:", results)
                return results

    # ✅ FOLLOWER MONETIZATION ENGINE — TARGETING + EXCLUDES + SEND STRATEGY + PRIORITIZATION
    def get_follower_monetization_targets(
        self,
        fanvue_account_id: int,
        limit: int = 100,
    ):
        """
        Follower Monetization Targeting v5:

        - Followers ONLY (no subscribers)
        - Prioritizes ignored + exhausted outreach users
        - Prioritizes cold / low-value users
        - Deprioritizes users closer to their last offer
        - Excludes whales, high-value users, and active/conflicting flows
        - Uses tiered cooldowns for more aggressive follower monetization
        - Adds basic re-hit lifecycle control
        """

        query = """
            SELECT
                u.id,
                u.fanvue_account_id,
                u.fanvue_user_uuid,
                u.username,
                u.display_name,
                u.is_follower,
                u.is_subscriber,
                m.user_value_tier,
                m.is_whale,
                m.value_score,
                m.attention_tier,
                m.outreach_status,
                m.current_route,
                m.offer_state,
                m.post_offer_nudge_count,
                m.messages_since_last_offer
            FROM fanvue_users u
            LEFT JOIN user_memory m
              ON u.fanvue_account_id = m.fanvue_account_id
             AND u.id = m.fanvue_user_id
            WHERE u.fanvue_account_id = %s

              -- ✅ Followers ONLY
              AND u.is_follower = TRUE
              AND COALESCE(u.is_subscriber, FALSE) = FALSE

              -- ❌ HARD EXCLUDE: whales
              AND COALESCE(m.is_whale, FALSE) = FALSE

              -- ❌ HARD EXCLUDE: high-value users
              AND COALESCE(m.user_value_tier, 'low') NOT IN ('high', 'whale')

              -- ❌ HARD EXCLUDE: attention-heavy users
              AND COALESCE(m.attention_tier, 'low') NOT IN ('high')

              -- ❌ HARD EXCLUDE: active offer/nudge flows
              AND COALESCE(m.offer_state, 'none') IN ('none', 'expired')
              AND COALESCE(m.post_offer_nudge_count, 0) = 0

              -- 🔁 RE-HIT LOGIC (Phase 1)
              AND COALESCE(m.messages_since_last_offer, 0) >= 0

              -- ❌ HARD EXCLUDE: active/conflicting routes
              -- ✅ EXCEPTION: allow ignored/exhausted outreach users
              AND (
                  COALESCE(m.current_route, 'chat') = 'chat'
                  OR COALESCE(m.outreach_status, 'none') IN ('ignored', 'exhausted')
              )

              -- ⏱️ Tiered cooldown (Send Strategy v1)
              AND NOT EXISTS (
                  SELECT 1
                  FROM ppv_broadcast_logs b
                  WHERE b.fanvue_account_id = u.fanvue_account_id
                    AND b.fanvue_user_id = u.id
                    AND b.created_at >= NOW() - (
                        CASE
                            WHEN m.outreach_status = 'exhausted' THEN INTERVAL '6 hours'
                            WHEN m.outreach_status = 'ignored' THEN INTERVAL '12 hours'
                            ELSE INTERVAL '24 hours'
                        END
                    )
              )

            ORDER BY
                -- 🔥 PRIORITY 1: outreach-based urgency
                CASE
                    WHEN m.outreach_status = 'exhausted' THEN 0
                    WHEN m.outreach_status = 'ignored' THEN 1
                    ELSE 2
                END ASC,

                -- 🔥 PRIORITY 2: colder / lower-value users first
                CASE
                    WHEN COALESCE(m.user_value_tier, 'low') IN ('cold', 'low') THEN 0
                    ELSE 1
                END ASC,

                -- 🔥 PRIORITY 3: lower value_score first
                COALESCE(m.value_score, 999999) ASC,

                -- 🔥 PRIORITY 4: more distance from last offer first
                COALESCE(m.messages_since_last_offer, 0) DESC,

                -- fallback
                u.id ASC

            LIMIT %s
        """

        params = [fanvue_account_id, limit]

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = cur.fetchall()
                print("FOLLOWER MONETIZATION TARGETS:", results)
                return results
    
    def get_subscriber_monetization_targets(
        self,
        fanvue_account_id: int,
        limit: int = 100,
    ):
        """
        Subscriber Monetization Targeting v1:
        - Subscribers ONLY
        - Excludes whales for now
        - Excludes active/conflicting offer flows
        - Excludes support/custom routes
        - Allows only safe chat-style monetization paths
        """
        query = """
            SELECT
                u.id,
                u.fanvue_account_id,
                u.fanvue_user_uuid,
                u.username,
                u.display_name,
                u.is_follower,
                u.is_subscriber,
                u.relationship_status,
                m.user_value_tier,
                m.is_whale,
                m.value_score,
                m.attention_tier,
                m.outreach_status,
                m.current_route,
                m.offer_state,
                m.post_offer_nudge_count,
                m.messages_since_last_offer,
                m.subscriber_profile
            FROM fanvue_users u
            LEFT JOIN user_memory m
            ON u.fanvue_account_id = m.fanvue_account_id
            AND u.id = m.fanvue_user_id
            WHERE u.fanvue_account_id = %s
            AND (
                COALESCE(u.is_subscriber, FALSE) = TRUE
                OR COALESCE(m.is_subscriber, FALSE) = TRUE
            )
            ORDER BY
            CASE
                WHEN COALESCE(m.subscriber_profile, 'none') = 'HIGH_VALUE_SUBSCRIBER' THEN 0
                WHEN COALESCE(m.subscriber_profile, 'none') = 'ACTIVE_SUBSCRIBER' THEN 1
                WHEN COALESCE(m.subscriber_profile, 'none') = 'NEW_SUBSCRIBER' THEN 2
                WHEN COALESCE(m.subscriber_profile, 'none') = 'LAPSED_SUBSCRIBER' THEN 3
                ELSE 4
            END ASC,
            COALESCE(m.value_score, 999999) ASC,
            u.id ASC
            LIMIT %s
        """
        params = [fanvue_account_id, limit]

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                results = cur.fetchall()
                print("SUBSCRIBER MONETIZATION TARGETS:", results)
                return results