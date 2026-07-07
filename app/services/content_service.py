import json
import random

from app.repositories.memory_repository import update_memory_fields
from app.repositories.content_repository import get_random_content_for_now
from app.services.media_processing_service import MediaProcessingService
from app.services.runtime_media_resolver import RuntimeMediaResolver

class ContentService:
    def __init__(
        self,
        media_processing_service: MediaProcessingService | None = None,
        runtime_media_resolver: RuntimeMediaResolver | None = None,
    ):
        self.content = self.load_content()
        self.media_processing = media_processing_service or MediaProcessingService()
        self.runtime_media_resolver = (
            runtime_media_resolver or RuntimeMediaResolver()
        )
        self.tier_order = ["low", "mid", "high", "premium"]

    def load_content(self):
        try:
            with open("data/content_catalog.json", "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as e:
            print(f"Error loading content catalog: {e}")
            return []

    def _tier_index(self, tier_name: str) -> int:
        try:
            return self.tier_order.index(tier_name)
        except ValueError:
            return 0

    def _normalize_offer_type_to_content_type(self, offer_type: str) -> str:
        mapping = {
            "teaser_offer": "tease",
            "tease_offer": "tease",
            "vip_offer": "vip",
            "premium_offer": "vip",
            "tease": "tease",
            "vip": "vip",
            "premium": "vip",
        }
        return mapping.get(offer_type, "tease")

    def determine_target_tier(self, offer_type: str, user_memory: dict = None) -> str:
        if offer_type in ["premium_offer", "premium"]:
            return "premium"
        if offer_type in ["vip_offer", "vip"]:
            return "high"
        if offer_type in ["teaser_offer", "tease_offer", "tease"]:
            return "low"
        return "low"

    def determine_offer_type(self, user_memory: dict = None) -> str:
        if not user_memory:
            return "teaser_offer"

        user_value_tier = (user_memory.get("user_value_tier") or "low").lower()
        outreach_status = (user_memory.get("outreach_status") or "none").lower()

        if outreach_status in ["exhausted", "ignored"]:
            return "teaser_offer"

        if user_value_tier in ["cold", "low"]:
            return "teaser_offer"

        if user_value_tier in ["mid", "high", "premium"]:
            return "vip_offer"

        return "teaser_offer"

    def _filter_pool(self, content_type: str, persona: str):
        return [
            c for c in self.content
            if c.get("type") == content_type and c.get("persona") == persona
        ]

    def _normalize_seen_tags(self, seen_tags):
        if seen_tags is None:
            return []

        if isinstance(seen_tags, list):
            return seen_tags

        if isinstance(seen_tags, str):
            try:
                parsed = json.loads(seen_tags)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []

        return []

    def _get_adaptive_intensity_target(self, user_memory: dict = None) -> int:
        if not user_memory:
            return 5

        preferred_intensity = int(user_memory.get("preferred_intensity_score") or 0)
        success_count = int(user_memory.get("content_success_count") or 0)
        ignore_count = int(user_memory.get("content_ignore_count") or 0)
        last_outcome = user_memory.get("last_content_outcome")

        target = preferred_intensity or 5

        # 7E.4 — Adaptive learning adjustment
        if success_count > ignore_count:
            target += 1

        if ignore_count > success_count:
            target -= 1

        if last_outcome == "success":
            target += 1

        if last_outcome == "ignored":
            target -= 1

        return max(1, min(target, 10))

    def _score_content(self, content: dict, user_memory: dict = None) -> int:
        if not user_memory:
            return random.randint(0, 5)

        score = 0

        intent_score = int(user_memory.get("intent_score") or 0)
        user_value_tier = (user_memory.get("user_value_tier") or "").lower()
        subscriber_profile = (user_memory.get("subscriber_profile") or "").upper()

        preferred_theme = user_memory.get("preferred_content_theme")
        adaptive_intensity_target = self._get_adaptive_intensity_target(user_memory)

        content_tier = content.get("tier", "low")
        content_price = int(content.get("price") or 0)

        intensity_score = int(content.get("intensity_score") or 0)
        content_theme = content.get("content_theme")
        buyer_stage = content.get("buyer_stage")
        recommended_for = content.get("recommended_for", []) or []

        # Tier / intent alignment
        if intent_score >= 90:
            if content_tier == "premium":
                score += 60
            elif content_tier == "high":
                score += 35
            elif content_tier == "mid":
                score += 15

        elif intent_score >= 60:
            if content_tier == "high":
                score += 40
            elif content_tier == "premium":
                score += 30
            elif content_tier == "mid":
                score += 20

        elif intent_score >= 30:
            if content_tier == "mid":
                score += 35
            elif content_tier == "high":
                score += 20
            elif content_tier == "low":
                score += 10

        else:
            if content_tier == "low":
                score += 35
            elif content_tier == "mid":
                score += 10

        # Subscriber/value alignment
        if subscriber_profile == "HIGH_VALUE_SUBSCRIBER":
            if content_tier == "premium":
                score += 35
            elif content_tier == "high":
                score += 20

        if user_value_tier in ["high", "premium", "whale"]:
            if content_tier == "premium":
                score += 25

        # Price alignment
        if intent_score >= 90 and content_price >= 50:
            score += 15
        elif intent_score < 60 and content_price >= 60:
            score -= 15

        # Metadata intelligence
        if intent_score >= 90:
            if intensity_score >= 8:
                score += 30
            if buyer_stage == "conversion":
                score += 25
            if "hot_buyer" in recommended_for:
                score += 25
            if "high_intent" in recommended_for:
                score += 20

        elif intent_score >= 60:
            if 4 <= intensity_score <= 7:
                score += 25
            if buyer_stage == "interest":
                score += 25
            if "medium_intent" in recommended_for:
                score += 20
            if content_theme == "vip_curiosity":
                score += 15

        else:
            if intensity_score <= 3:
                score += 25
            if buyer_stage == "warmup":
                score += 25
            if "low_intent" in recommended_for:
                score += 20
            if content_theme == "soft_tease":
                score += 15

        # High-value subscriber boost
        if subscriber_profile == "HIGH_VALUE_SUBSCRIBER":
            if "high_value_subscriber" in recommended_for:
                score += 30

        # 7E.3 — Theme preference matching
        if preferred_theme and preferred_theme == content_theme:
            score += 20

        # 7E.4 — Adaptive intensity matching
        intensity_gap = abs(adaptive_intensity_target - intensity_score)

        if intensity_gap == 0:
            score += 35
        elif intensity_gap == 1:
            score += 25
        elif intensity_gap == 2:
            score += 15
        elif intensity_gap >= 5:
            score -= 20

        # 7E.5 — Behavior Feedback Loop
        last_match_profile = user_memory.get("last_match_profile") or {}
        last_content_outcome = user_memory.get("last_content_outcome")

        success_count = int(user_memory.get("content_success_count") or 0)
        ignore_count = int(user_memory.get("content_ignore_count") or 0)

        last_success_theme = last_match_profile.get("content_theme")
        last_success_intensity = int(last_match_profile.get("content_intensity") or 0)
        last_success_tier = last_match_profile.get("content_tier")

        if last_content_outcome == "success":
            if last_success_theme and content_theme == last_success_theme:
                score += 25

            if last_success_tier and content_tier == last_success_tier:
                score += 15

            if last_success_intensity:
                last_intensity_gap = abs(intensity_score - last_success_intensity)

                if last_intensity_gap == 0:
                    score += 20
                elif last_intensity_gap == 1:
                    score += 12
                elif last_intensity_gap >= 4:
                    score -= 10

        if last_content_outcome == "ignored":
            if last_success_theme and content_theme == last_success_theme:
                score -= 20

            if last_success_tier and content_tier == last_success_tier:
                score -= 10

            if last_success_intensity:
                last_intensity_gap = abs(intensity_score - last_success_intensity)

                if last_intensity_gap == 0:
                    score -= 20
                elif last_intensity_gap == 1:
                    score -= 10

        # Global trend learning
        if success_count >= 3 and success_count > ignore_count:
            score += 10

        if ignore_count >= 2 and ignore_count >= success_count:
            if intensity_score >= adaptive_intensity_target:
                score -= 20
            else:
                score += 10

        # Avoid repeating same tier too much
        last_tier = user_memory.get("last_offer_tier")
        if last_tier and last_tier == content_tier:
            score -= 10

        score += random.randint(0, 5)

        return score
    
    def _build_match_profile(self, content: dict, user_memory: dict = None) -> dict:
        if not user_memory:
            return {}

        return {
            "intent_score": int(user_memory.get("intent_score") or 0),
            "user_value_tier": user_memory.get("user_value_tier"),
            "subscriber_profile": user_memory.get("subscriber_profile"),
            "preferred_theme": user_memory.get("preferred_content_theme"),
            "adaptive_intensity_target": self._get_adaptive_intensity_target(user_memory),

            "content_tag": content.get("tag"),
            "content_tier": content.get("tier"),
            "content_price": content.get("price"),
            "content_intensity": content.get("intensity_score"),
            "content_theme": content.get("content_theme"),
            "buyer_stage": content.get("buyer_stage"),
        }

    def _get_last_content_tag(self, user_memory: dict = None):
        if not user_memory:
            return None

        return (
            user_memory.get("last_selected_content_tag")
            or user_memory.get("last_offer_content_tag")
            or user_memory.get("last_content_tag")
        )

    def _choose_from_pool(self, pool: list, user_memory: dict = None):
        if not pool:
            return None

        if not user_memory:
            return random.choice(pool)

        seen_tags = self._normalize_seen_tags(
            user_memory.get("seen_content_tags")
        )

        last_content_tag = (
            user_memory.get("last_selected_content_tag")
            or user_memory.get("last_content_tag")
            or user_memory.get("last_content_sent_tag")
        )

        if last_content_tag and last_content_tag not in seen_tags:
            seen_tags.append(last_content_tag)

        user_memory["seen_content_tags"] = seen_tags

        print(f"DEBUG rotation last_content_tag: {last_content_tag}")
        print(f"DEBUG rotation seen_tags: {seen_tags}")

        unseen_non_repeat_pool = [
            c for c in pool
            if c.get("tag") not in seen_tags
            and c.get("tag") != last_content_tag
        ]

        if unseen_non_repeat_pool:
            choice = random.choice(unseen_non_repeat_pool)
            print(f"DEBUG rotation selected unseen non-repeat: {choice.get('tag')}")
            return choice

        non_repeat_pool = [
            c for c in pool
            if c.get("tag") != last_content_tag
        ]

        if non_repeat_pool:
            choice = random.choice(non_repeat_pool)
            print(f"DEBUG rotation selected non-repeat fallback: {choice.get('tag')}")
            return choice

        choice = random.choice(pool)
        print(f"DEBUG rotation final fallback selected: {choice.get('tag')}")
        return choice

    def _choose_best_scored(self, pool: list, user_memory: dict = None):
        rotated_choice = self._choose_from_pool(pool, user_memory)

        if not rotated_choice:
            return None

        seen_tags = self._normalize_seen_tags(user_memory.get("seen_content_tags")) if user_memory else []
        last_content_tag = self._get_last_content_tag(user_memory)

        eligible_pool = [
            c for c in pool
            if c.get("tag") != last_content_tag
        ]

        if user_memory:
            unseen_pool = [
                c for c in eligible_pool
                if c.get("tag") not in seen_tags
            ]
            if unseen_pool:
                eligible_pool = unseen_pool

        if not eligible_pool:
            eligible_pool = [rotated_choice]

        scored_pool = []
        adaptive_target = self._get_adaptive_intensity_target(user_memory)

        for item in eligible_pool:
            score = self._score_content(item, user_memory)
            scored_pool.append((item, score))

        scored_pool.sort(key=lambda x: x[1], reverse=True)

        print(f"DEBUG adaptive intensity target: {adaptive_target}")
        print("DEBUG content scoring:")
        for item, score in scored_pool[:5]:
            print(
                f"  tag={item.get('tag')} | "
                f"tier={item.get('tier')} | "
                f"price={item.get('price')} | "
                f"intensity={item.get('intensity_score')} | "
                f"stage={item.get('buyer_stage')} | "
                f"theme={item.get('content_theme')} | "
                f"score={score}"
            )

        choice = scored_pool[0][0]

        match_profile = self._build_match_profile(choice, user_memory)

        print(f"[MATCH PROFILE] {match_profile}")

        choice["_match_profile"] = match_profile

        print(f"DEBUG intelligence selected: {choice.get('tag')}")
        return choice

    def _build_fallback_indices(self, target_index: int):
        fallback_indices = []

        for distance in range(1, len(self.tier_order)):
            lower_index = target_index - distance
            upper_index = target_index + distance

            if lower_index >= 0:
                fallback_indices.append(lower_index)
            if upper_index < len(self.tier_order):
                fallback_indices.append(upper_index)

        return fallback_indices

    def _persist_content_personalization(self, selected_content: dict, user_memory: dict = None):
        if not selected_content or not user_memory:
            return

        fanvue_account_id = user_memory.get("fanvue_account_id")
        fanvue_user_id = user_memory.get("fanvue_user_id")

        tag = selected_content.get("tag")
        theme = selected_content.get("content_theme")
        intensity = int(selected_content.get("intensity_score") or 0)

        seen_tags = self._normalize_seen_tags(user_memory.get("seen_content_tags"))

        if tag and tag not in seen_tags:
            seen_tags.append(tag)

        match_profile = selected_content.get("_match_profile") or {
            "tag": tag,
            "theme": theme,
            "intensity": intensity,
            "success_count": user_memory.get("content_success_count", 0),
            "ignore_count": user_memory.get("content_ignore_count", 0),
        }

        # Always update working memory, even if DB IDs are missing
        user_memory["last_selected_content_tag"] = tag
        user_memory["last_content_tag"] = tag
        user_memory["last_content_sent_tag"] = tag
        user_memory["seen_content_tags"] = seen_tags
        user_memory["preferred_content_theme"] = theme
        user_memory["preferred_intensity_score"] = intensity
        user_memory["last_match_profile"] = match_profile

        if not fanvue_account_id or not fanvue_user_id:
            print(
                f"[PERSONALIZATION MEMORY ONLY] Missing DB IDs, updated working memory only → "
                f"tag={tag}, seen_tags={seen_tags}"
            )
            return

        update_memory_fields(
            fanvue_account_id,
            fanvue_user_id,
            {
                "last_selected_content_tag": tag,
                "seen_content_tags": seen_tags,
                "preferred_content_theme": theme,
                "preferred_intensity_score": intensity,
                "last_match_profile": match_profile,
            },
        )

        print(
            f"[PERSONALIZATION] Updated memory → "
            f"tag={tag}, theme={theme}, intensity={intensity}, seen_tags={seen_tags}"
        )

        print(f"[MATCH PROFILE SAVED] {match_profile}")

    def get_content(self, offer_type: str, persona: str = "ava", user_memory: dict = None):
        print(f"DEBUG offer_type BEFORE normalize: {offer_type}")

        normalized_offer_type = (offer_type or "").lower()

        if normalized_offer_type.endswith("_offer"):
            normalized_offer_type = normalized_offer_type.replace("_offer", "")

        classification_map = {
            "tease": "TEASE",
            "teaser": "TEASE",
            "vip": "VIP",
            "premium": "PREMIUM",
        }

        classification = classification_map.get(normalized_offer_type)

        print(f"[CMS CONTENT SERVICE] normalized_offer_type={normalized_offer_type}")
        print(f"[CMS CONTENT SERVICE] classification={classification}")

        if not classification:
            print(f"[CMS CONTENT SERVICE] Unsupported offer_type={offer_type}")
            return None

        fanvue_account_id = user_memory.get("fanvue_account_id") if user_memory else None
        fanvue_user_id = user_memory.get("fanvue_user_id") if user_memory else None

        if not fanvue_account_id or not fanvue_user_id:
            print("[CMS CONTENT SERVICE] Missing fanvue_account_id or fanvue_user_id")
            return None

        if classification == "TEASE":
            from app.repositories.content_repository import get_tease_content_for_user
            selected_content = get_tease_content_for_user(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )

        elif classification == "VIP":
            from app.repositories.content_repository import get_vip_content_for_user
            selected_content = get_vip_content_for_user(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )

        elif classification == "PREMIUM":
            from app.repositories.content_repository import get_premium_content_for_user
            selected_content = get_premium_content_for_user(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )

        else:
            selected_content = None

        if not selected_content:
            print(f"[CMS CONTENT SERVICE] No eligible CMS content for {classification}")
            return None

        blurred_preview_path = self.media_processing.resolve_derivative(
            selected_content,
            "blurred_preview",
        )
        runtime_file_path = self.runtime_media_resolver.resolve_original_path_string(
            selected_content,
            require_exists=True,
        )

        normalized_content = {
            "id": selected_content.get("id"),
            "content_item_id": selected_content.get("id"),
            "tag": f"cms_{classification.lower()}_{selected_content.get('id')}",
            "type": classification.lower(),
            "tier": (
                "low" if classification == "TEASE"
                else "high" if classification == "VIP"
                else "premium"
            ),
            "price": selected_content.get("last_fanvue_message_price") or 0,
            "caption": selected_content.get("caption") or selected_content.get("file_name"),
            "fanvue_link": selected_content.get("fanvue_link"),
            "persona": persona,

            # CMS metadata
            "classification": selected_content.get("classification"),
            "file_path": runtime_file_path or selected_content.get("file_path"),
            "file_name": selected_content.get("file_name"),
            "blurred_preview_path": blurred_preview_path,
            "fanvue_media_preview_uuid": selected_content.get("fanvue_media_preview_uuid"),
            "fanvue_media_full_uuid": selected_content.get("fanvue_media_full_uuid"),
            "fanvue_ptv_set_id": selected_content.get("fanvue_ptv_set_id"),
            "source": "cms",
        }

        print(
            "[CMS CONTENT SERVICE] Selected CMS content "
            f"id={normalized_content.get('id')} "
            f"type={normalized_content.get('type')} "
            f"tag={normalized_content.get('tag')}"
        )

        self._persist_content_personalization(normalized_content, user_memory)

        return normalized_content
    
    def get_cms_content_for_classification(self, classification: str):
        """
        Fetch one approved, blurred, rotation-ready CMS item by classification.

        This uses the new 14K DB content pipeline:
        approved -> blurred -> ready_for_rotation
        """

        print(f"[CONTENT SERVICE] CMS fetch requested classification={classification}")

        item = get_random_content_for_now(classification=classification)

        if not item:
            print(f"[CONTENT SERVICE] No CMS content found for classification={classification}")
            return None

        print(
            "[CONTENT SERVICE] CMS content returned "
            f"id={item.get('id')} "
            f"classification={item.get('classification')} "
            f"file={item.get('file_name')}"
        )

        return item

    def get_tease_cms_content(self):
        return self.get_cms_content_for_classification("TEASE")

    def get_vip_cms_content(self):
        return self.get_cms_content_for_classification("VIP")

    def get_premium_cms_content(self):
        return self.get_cms_content_for_classification("PREMIUM")
