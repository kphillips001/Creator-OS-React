import sys
import tempfile
import types
import unittest
from pathlib import Path

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit

if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    rows = types.ModuleType("psycopg.rows")
    psycopg_types = types.ModuleType("psycopg.types")
    json_types = types.ModuleType("psycopg.types.json")
    errors = types.ModuleType("psycopg.errors")
    psycopg.connect = lambda *args, **kwargs: None
    rows.dict_row = object()
    json_types.Json = lambda value: value
    errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows
    sys.modules["psycopg.types"] = psycopg_types
    sys.modules["psycopg.types.json"] = json_types
    sys.modules["psycopg.errors"] = errors

from app.models.caption_studio import CaptionPlatform, CaptionStyle, CaptionTemplate
from app.models.generation_library import GeneratedImageRecord
from app.services.caption_studio_service import CaptionStudioService
from app.services.caption_prompt_guidance import NATURAL_EMOJI_INSTRUCTION
from app.services.generation_library_service import GenerationLibraryService
from app.services.social_publishing_service import SocialPublishingService


AVA_EMOJIS = (
    "😏", "😉", "🫣", "👀", "😂", "🤭", "😅", "🥹", "☺️", "💕",
    "👇", "🌊", "☀️", "🌅", "🚤", "☕", "🛋️", "🌙", "🌲", "🛻", "📸",
)


def emoji_count(text):
    return sum(text.count(emoji) for emoji in AVA_EMOJIS)


def generated_record(image_id="generated_image_caption_1"):
    return GeneratedImageRecord(
        image_id=image_id,
        generation_job_id="generation_job_caption",
        generation_request_id="generation_request_caption",
        generation_result_id="generation_result_caption",
        output_reference="https://cdn.test/caption.png",
        creator_profile_id=7,
        provider_id="seedream_4_5",
        prompt_plan_id="prompt_plan_caption",
        prompt_text="Coffee at home, warm window light, social-safe creator image",
        creative_mode="social_safe",
        reference_asset_id=55,
        prompt_metadata={"creative_tags": ("coffee", "window light")},
        generation_metadata={"request_metadata": {"source": "social_studio"}},
    )


def grok_vision_payload(**overrides):
    payload = {
        "image_analysis": {
            "location": "cozy kitchen",
            "wardrobe": "soft casual top",
            "expression": "warm smile",
            "body_language": "relaxed and inviting",
            "lighting": "morning window light",
            "mood": "affectionate and playful",
            "environment": "home",
            "activity": "making coffee",
        },
        "girlfriend_energy": [
        "I made coffee... would you rather spend the morning with me? 👇",
        "This morning would be better if you were here, right? 👀",
        "Home feels softer when I am thinking about you, agree? 😉",
        "I saved you the good seat next to me, taking it? 👇",
        "Morning light and one little wish you were here moment, yes? 👀",
        ],
        "teasing_naughty": [
        "You keep looking... I am not complaining, are you? 😏",
        "I know exactly what caught your attention, don't I? 👀",
        "You would probably get distracted if you were here, wouldn't you? 😉",
        "Careful, I might ask what you are thinking 👇",
        "This is me pretending I did not notice you paused, did you? 👀",
        ],
    }
    payload["girlfriend_energy"] = [
        "I made coffee... but I would rather spend the morning with you 👇",
        "This morning would be better if you were here with me 👀",
        "Home feels softer when I am thinking about you 😉",
        "I saved you the good seat next to me 👇",
        "Morning light and one little wish you were here moment 👀",
    ]
    payload["teasing_naughty"] = [
        "You keep looking... I am not complaining 😏",
        "I know exactly what caught your attention 👀",
        "You would probably get distracted if you were here 😉",
        "Careful, I might ask what you are thinking 👇",
        "This is me pretending I did not notice you paused 👀",
    ]
    payload.update(overrides)
    if "girlfriend_energy" not in overrides:
        payload["girlfriend_energy"] = [
            "I made coffee... would you rather spend the morning with me? 👇",
            "This morning would be better if you were here, right? 👀",
            "Home feels softer when I am thinking about you, agree? 😉",
            "I saved you the good seat next to me, taking it? 👇",
            "Morning light and one little wish you were here moment, yes? 👀",
        ]
    if "teasing_naughty" not in overrides:
        payload["teasing_naughty"] = [
            "You keep looking... I am not complaining, are you? 😏",
            "I know exactly what caught your attention, don't I? 👀",
            "You would probably get distracted if you were here, wouldn't you? 😉",
            "Careful, I might ask what you are thinking 👇",
            "This is me pretending I did not notice you paused, did you? 👀",
        ]
    return payload


def telegram_grok_vision_payload(**overrides):
    payload = {
        "image_analysis": {
            "location": "cozy bedroom",
            "wardrobe": "soft lounge set",
            "expression": "warm smile",
            "body_language": "relaxed and close",
            "lighting": "soft evening light",
            "mood": "intimate and playful",
            "environment": "home",
            "activity": "quiet evening moment",
        },
        "girlfriend_energy": [
            "I saved this quiet little moment for you",
            "This would feel better if you were here",
            "Soft lights and a little thought of you",
            "I like when it feels this close",
            "Come stay in this mood with me",
        ],
        "naughty": [
            "You noticed the look, didn't you",
            "I know exactly where your eyes went",
            "Careful, this mood gets distracting",
            "I was behaving until you showed up",
            "You would not be focused for long",
        ],
    }
    payload.update(overrides)
    return payload


class CaptionStudioTests(unittest.TestCase):
    def make_services(self, *, grok_vision_provider=None):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        caption_studio = CaptionStudioService(
            storage_dir=Path(temp_dir.name) / "captions",
            grok_vision_provider=grok_vision_provider,
        )
        generation_library = GenerationLibraryService(storage_dir=Path(temp_dir.name) / "library")
        social_publishing = SocialPublishingService(storage_dir=Path(temp_dir.name) / "social")
        generation_library._write_records([generated_record()])
        return caption_studio, generation_library, social_publishing

    def test_caption_request_session_result_and_history(self):
        caption_studio, _, _ = self.make_services()

        caption_item = caption_studio.create_caption_request(
            creator_profile_id=7,
            platform=CaptionPlatform.X.value,
            style=CaptionStyle.SOCIAL_SAFE.value,
            tone="playful",
            source_text="A cozy coffee post with warm morning light",
            variation_count=3,
        )
        result = caption_studio.generate_caption(caption_item)

        self.assertEqual(caption_item.platform, CaptionPlatform.X.value)
        self.assertEqual(len(result.variations), 3)
        self.assertLessEqual(len(result.variations[0]), 280)
        self.assertEqual(len(caption_studio.list_sessions()), 1)
        self.assertEqual(len(caption_studio.history()), 1)
        self.assertEqual(caption_studio.history()[0].caption_result_id, result.caption_result_id)

    def test_all_required_outputs_are_supported(self):
        caption_studio, _, _ = self.make_services()
        platforms = (
            CaptionPlatform.X.value,
            CaptionPlatform.TELEGRAM.value,
            CaptionPlatform.FANVUE.value,
            CaptionPlatform.PRODUCT.value,
            CaptionPlatform.STORY.value,
            CaptionPlatform.MARKETING.value,
        )

        outputs = {}
        for platform in platforms:
            caption_item = caption_studio.create_caption_request(
                creator_profile_id=7,
                platform=platform,
                style=CaptionStyle.DIRECT.value,
                tone="confident",
                source_text="Creator image with soft light and polished campaign direction",
                variation_count=1,
            )
            outputs[platform] = caption_studio.generate_caption(caption_item).variations[0]

        self.assertIn("Tone: confident", outputs[CaptionPlatform.TELEGRAM.value])
        self.assertIn("Crafted in a confident tone", outputs[CaptionPlatform.FANVUE.value])
        self.assertIn("product description", outputs[CaptionPlatform.PRODUCT.value])
        self.assertIn("story description", outputs[CaptionPlatform.STORY.value])
        self.assertIn("Marketing copy direction", outputs[CaptionPlatform.MARKETING.value])

    def test_templates_style_and_tone_are_preserved(self):
        caption_studio, _, _ = self.make_services()
        template = CaptionTemplate(
            template_id="custom_marketing",
            platform=CaptionPlatform.MARKETING.value,
            style=CaptionStyle.PLAYFUL.value,
            body="{hook} :: {detail} :: {tone} :: {style}",
        )
        caption_studio.save_template(template)

        caption_item = caption_studio.create_caption_request(
            creator_profile_id=7,
            platform=CaptionPlatform.MARKETING.value,
            style=CaptionStyle.PLAYFUL.value,
            tone="bright",
            source_text="Launch the weekend creative set",
            variation_count=1,
            template_id=template.template_id,
        )
        result = caption_studio.generate_caption(caption_item)

        self.assertIn("bright", result.variations[0])
        self.assertIn(CaptionStyle.PLAYFUL.value, result.variations[0])
        self.assertEqual(caption_studio.get_template("custom_marketing").body, template.body)

    def test_generation_library_source_can_generate_caption(self):
        caption_studio, generation_library, _ = self.make_services()

        result = caption_studio.generate_from_generation_library(
            generated_image_id="generated_image_caption_1",
            generation_library=generation_library,
            platform=CaptionPlatform.X.value,
            style=CaptionStyle.SOCIAL_SAFE.value,
            tone="warm",
            variation_count=2,
        )

        self.assertEqual(len(result.variations), 2)
        self.assertEqual(caption_studio.history()[0].metadata["source_generated_image_id"], "generated_image_caption_1")
        self.assertIn("Coffee at home", result.variations[0])

    def test_social_publishing_attachment(self):
        caption_studio, generation_library, social_publishing = self.make_services()
        queue_item = social_publishing.create_queue_item(
            generated_image_id="generated_image_caption_1",
            generation_library=generation_library,
            platform="x",
        )

        result = caption_studio.generate_for_social_queue(
            queue_item_id=queue_item.queue_item_id,
            social_publishing=social_publishing,
            style=CaptionStyle.SOCIAL_SAFE.value,
            tone="direct",
            variation_count=1,
        )
        updated = social_publishing.get_queue_item(queue_item.queue_item_id)

        self.assertEqual(updated.caption_id, result.caption_result_id)
        self.assertTrue(any(entry.status == "caption_attached" for entry in social_publishing.list_history()))
        self.assertEqual(caption_studio.history()[0].metadata["social_queue_item_id"], queue_item.queue_item_id)

    def test_caption_regeneration_and_selection(self):
        caption_studio, _, _ = self.make_services()
        caption_item = caption_studio.create_caption_request(
            creator_profile_id=7,
            platform=CaptionPlatform.X.value,
            style=CaptionStyle.SOCIAL_SAFE.value,
            tone="warm",
            source_text="Coffee at home with warm window light",
            variation_count=2,
        )
        result = caption_studio.generate_caption(caption_item)

        regenerated = caption_studio.regenerate_caption(result.caption_result_id)
        selected = caption_studio.select_caption(regenerated.caption_result_id, variation_index=2)

        self.assertNotEqual(regenerated.caption_result_id, result.caption_result_id)
        self.assertEqual(selected.selected_text, regenerated.variations[1])
        self.assertGreaterEqual(len(caption_studio.history()), 3)

    def test_x_engagement_themes_are_image_first_and_regenerable(self):
        calls = []

        def fake_grok(**kwargs):
            calls.append(kwargs)
            return grok_vision_payload()

        caption_studio, _, _ = self.make_services(grok_vision_provider=fake_grok)

        result = caption_studio.generate_x_engagement_themes(
            generated_image_id="generated_image_caption_1",
            image_reference="https://cdn.test/window-mirror-caption.png",
            creator_profile_id=7,
            creator_profile={"name": "Ava Blackthorne"},
            creative_mode="premium_teaser",
            prompt_text="Ribbed crop tank, window light, confident smile",
            prompt_metadata={"creative_tags": ("window light", "mirror")},
            generation_metadata={"workflow_type": "premium"},
            theme_count=4,
            captions_per_theme=3,
        )
        different = caption_studio.generate_x_engagement_themes(
            generated_image_id="generated_image_caption_1",
            image_reference="https://cdn.test/window-mirror-caption.png",
            creator_profile_id=7,
            creator_profile={"name": "Ava Blackthorne"},
            creative_mode="premium_teaser",
            prompt_text="Ribbed crop tank, window light, confident smile",
            idea_seed=1,
        )

        themes = result.formatter_metadata["themes"]
        self.assertTrue(result.formatter_metadata["vision_primary"])
        self.assertEqual(result.formatter_metadata["vision_provider"], "grok")
        self.assertEqual(calls[0]["image_reference"], "https://cdn.test/window-mirror-caption.png")
        self.assertIn("analyze the attached image", calls[0]["prompt"])
        self.assertEqual(len(themes), 2)
        self.assertEqual(themes[0]["theme"], "❤️ Girlfriend Energy")
        self.assertEqual(themes[1]["theme"], "😈 Teasing / Naughty")
        self.assertTrue(all(len(theme["captions"]) == 5 for theme in themes))
        self.assertEqual(len(result.variations), 10)
        self.assertLessEqual(max(len(caption) for caption in result.variations), 280)
        self.assertIn("grok_vision_image_analysis", caption_studio.get_caption_request(result.caption_request_id).metadata["context_priority"])
        self.assertEqual(
            themes[0]["theme"],
            different.formatter_metadata["themes"][0]["theme"],
        )

    def test_x_engagement_captions_use_context_aware_emojis_without_spam(self):
        caption_studio, _, _ = self.make_services(grok_vision_provider=lambda **kwargs: grok_vision_payload())

        result = caption_studio.generate_x_engagement_themes(
            generated_image_id="generated_image_caption_1",
            image_reference="https://cdn.test/mirror-outfit-opinion.png",
            creator_profile_id=7,
            creative_mode="premium_teaser",
            prompt_text="Mirror outfit opinion shot",
            prompt_metadata={"creative_tags": ("mirror", "outfit opinion")},
            theme_count=3,
            captions_per_theme=3,
        )

        captions = result.variations
        self.assertTrue(any("🫣" in caption or "👀" in caption for caption in captions))
        self.assertTrue(any(caption.endswith("👇") or "👇" in caption for caption in captions))
        self.assertTrue(all(1 <= emoji_count(caption) <= 3 for caption in captions))
        interactive_count = sum(
            1
            for caption in captions
            if "?" in caption
            or "Tell me" in caption
            or "Quote this" in caption
            or "First thought" in caption
            or "👇" in caption
        )
        self.assertGreaterEqual(interactive_count, len(captions) - 1)
        self.assertFalse(any("🔥🔥" in caption or "💯" in caption or "🚀" in caption for caption in captions))

    def test_x_engagement_emoji_context_changes_by_image_setting(self):
        def fake_setting_grok(**kwargs):
            image_reference = kwargs.get("image_reference", "")
            if "boat" in image_reference:
                return grok_vision_payload(girlfriend_energy=[
                    "Boat morning with you would be better 🚤",
                    "Lake light feels softer with you here 🌊",
                    "Saved you a spot by the water 🌊",
                    "This would be our quiet little escape 🚤",
                    "Wish you were here for this view 🌊",
                ])
                return grok_vision_payload(girlfriend_energy=[
                    "Boat morning with you would be better ðŸš¤",
                    "Lake light feels softer with you here ðŸŒŠ",
                    "Saved you a spot by the water ðŸŒŠ",
                    "This would be our quiet little escape ðŸš¤",
                    "Wish you were here for this view ðŸŒŠ",
                ])
            if "coffee" in image_reference:
                return grok_vision_payload(girlfriend_energy=[
                    "Coffee is ready and I saved you a seat ☕",
                    "Couch mornings are better with you 🛋️",
                    "I made coffee but wanted you here ☕",
                    "This corner feels made for two 🛋️",
                    "Morning softness and your missing spot ☕",
                ])
                return grok_vision_payload(girlfriend_energy=[
                    "Coffee is ready and I saved you a seat â˜•",
                    "Couch mornings are better with you ðŸ›‹ï¸",
                    "I made coffee but wanted you here â˜•",
                    "This corner feels made for two ðŸ›‹ï¸",
                    "Morning softness and your missing spot â˜•",
                ])
            return grok_vision_payload(girlfriend_energy=[
                "Okay photographer... tell me when to smile 📸",
                "This shot needed your opinion 📸",
                "Camera caught me thinking about you 📸",
                "You would probably ask for one more 📸",
                "I saved the good angle for you 📸",
            ])
            return grok_vision_payload(girlfriend_energy=[
                "Okay photographer... tell me when to smile ðŸ“¸",
                "This shot needed your opinion ðŸ“¸",
                "Camera caught me thinking about you ðŸ“¸",
                "You would probably ask for one more ðŸ“¸",
                "I saved the good angle for you ðŸ“¸",
            ])

        caption_studio, _, _ = self.make_services(grok_vision_provider=fake_setting_grok)

        boat = caption_studio.generate_x_engagement_themes(
            generated_image_id="generated_image_boat",
            image_reference="https://cdn.test/boat-lake-summer.png",
            creator_profile_id=7,
            prompt_text="Boat lake summer shot",
            theme_count=3,
            captions_per_theme=2,
        )
        coffee = caption_studio.generate_x_engagement_themes(
            generated_image_id="generated_image_coffee",
            image_reference="https://cdn.test/cozy-coffee-couch.png",
            creator_profile_id=7,
            prompt_text="Cozy coffee couch moment",
            theme_count=3,
            captions_per_theme=2,
        )
        camera = caption_studio.generate_x_engagement_themes(
            generated_image_id="generated_image_camera",
            image_reference="https://cdn.test/camera-photographer-shot.png",
            creator_profile_id=7,
            prompt_text="Photographer camera shot",
            theme_count=3,
            captions_per_theme=2,
        )

        self.assertTrue(any("🚤" in caption or "🌊" in caption for caption in boat.variations))
        self.assertTrue(any("☕" in caption or "🛋️" in caption for caption in coffee.variations))
        self.assertTrue(any("📸" in caption for caption in camera.variations))

    def test_generation_library_custom_caption_is_not_altered_by_emoji_logic(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")

        self.assertIn('selected_caption = str(st.session_state.get(custom_key) or "").strip()', source)
        self.assertIn("caption_text=selected_caption", source)
        self.assertNotIn("decorate_x", source)

    def test_telegram_uses_grok_vision_image_first_personas(self):
        calls = []

        def fake_grok(**kwargs):
            calls.append(kwargs)
            return telegram_grok_vision_payload()

        caption_studio, _, _ = self.make_services(grok_vision_provider=fake_grok)

        result = caption_studio.generate_telegram_vision_themes(
            generated_image_id="generated_image_caption_1",
            image_reference="https://cdn.test/telegram-bedroom-evening.png",
            creator_profile_id=7,
            creator_profile={"name": "Ava Blackthorne"},
            creative_mode="premium_teaser",
            prompt_text="Cozy evening lounge set",
            prompt_metadata={"creative_tags": ("bedroom", "soft light")},
            generation_metadata={"workflow_type": "premium"},
        )
        different = caption_studio.generate_telegram_vision_themes(
            generated_image_id="generated_image_caption_1",
            image_reference="https://cdn.test/telegram-bedroom-evening.png",
            creator_profile_id=7,
            creator_profile={"name": "Ava Blackthorne"},
            idea_seed=1,
        )

        themes = result.formatter_metadata["themes"]
        self.assertEqual(result.platform, CaptionPlatform.TELEGRAM.value)
        self.assertEqual(result.formatter_metadata["vision_provider"], "grok")
        self.assertEqual(calls[0]["image_reference"], "https://cdn.test/telegram-bedroom-evening.png")
        self.assertEqual(calls[0]["platform"], CaptionPlatform.TELEGRAM.value)
        self.assertIn("writing Telegram captions", calls[0]["prompt"])
        self.assertIn('"naughty"', calls[0]["prompt"])
        self.assertEqual(themes[0]["theme"], "❤️ Girlfriend Energy")
        self.assertEqual(themes[1]["theme"], "😈 Naughty")
        self.assertEqual(len(themes[0]["captions"]), 5)
        self.assertEqual(len(themes[1]["captions"]), 5)
        self.assertEqual(len(result.variations), 10)
        self.assertIn("grok_vision_image_analysis", caption_studio.get_caption_request(result.caption_request_id).metadata["context_priority"])
        self.assertNotEqual(result.caption_result_id, different.caption_result_id)

    def test_generation_library_telegram_caption_ui_uses_selected_or_custom_caption(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")

        self.assertIn("generate_telegram_vision_themes", source)
        self.assertIn("generation_library_telegram_selected_caption", source)
        self.assertIn("Generate Different Ideas", source)
        self.assertIn("Caption Editor", source)
        self.assertIn("Select a generated caption above or write your own.", source)
        self.assertIn('selected_caption = str(st.session_state.get(caption_key) or "").strip()', source)
        self.assertIn("caption_text=selected_caption", source)
        self.assertIn("social_publishing.assign_caption", source)

    def test_generation_library_caption_selection_syncs_with_textbox(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")

        self.assertIn("def _render_generated_caption_choices", source)
        self.assertIn("st.session_state[selected_key] = caption", source)
        self.assertIn("st.session_state[text_key] = caption", source)
        self.assertIn("Caption selected.", source)
        self.assertIn('type="primary" if selected else "secondary"', source)
        self.assertIn("Any changes made here will be published.", source)
        self.assertIn("↺ Restore Original", source)
        self.assertIn("caption_was_edited", source)
        self.assertIn('"caption_source": "edited_generated" if caption_was_edited else "generated" if selected_generated_caption else "custom"', source)
        self.assertIn("Custom caption will be published.", source)
        self.assertIn("Select a generated caption or write one before publishing.", source)
        self.assertIn("selected_generated_caption = str(st.session_state.get(selected_key) or \"\").strip()", source)
        self.assertIn("disabled=not selected_caption", source)
        self.assertIn('"selected_generated_caption": selected_generated_caption', source)

    def test_caption_prompts_include_natural_contextual_emoji_guidance(self):
        service_sources = {
            "caption_studio": Path("app/services/caption_studio_service.py").read_text(encoding="utf-8"),
            "grok_caption": Path("app/services/grok_caption_service.py").read_text(encoding="utf-8"),
            "content_caption": Path("app/services/content_caption_service.py").read_text(encoding="utf-8"),
            "ppv_caption": Path("app/services/ppv_caption_service.py").read_text(encoding="utf-8"),
        }

        guidance = Path("app/services/caption_prompt_guidance.py").read_text(encoding="utf-8")
        self.assertIn("contextually inside the caption", NATURAL_EMOJI_INSTRUCTION)
        self.assertIn("Sprinkle 1-4 appropriate emojis throughout the sentence", NATURAL_EMOJI_INSTRUCTION)
        self.assertIn("Do not simply append emojis to the beginning or end", NATURAL_EMOJI_INSTRUCTION)
        self.assertIn("Avoid generic emoji clusters", NATURAL_EMOJI_INSTRUCTION)
        self.assertIn("emotion, setting, object, action, or mood", guidance)

        for source in (
            service_sources["grok_caption"],
            service_sources["content_caption"],
            service_sources["ppv_caption"],
        ):
            self.assertIn("natural_emoji_instruction", source)
        self.assertIn("NATURAL_EMOJI_INSTRUCTION", service_sources["caption_studio"])
        self.assertNotIn("Do NOT stack all emojis at the end", service_sources["grok_caption"])
        self.assertNotIn("- no emojis", service_sources["content_caption"].lower())
        self.assertNotIn("0 or 1 emoji max", service_sources["content_caption"])
        self.assertNotIn("1 max if needed", service_sources["ppv_caption"])

    def test_caption_studio_ui_and_navigation_contract(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")
        navigation = Path("app/dashboard/navigation.py").read_text(encoding="utf-8")
        main = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("Caption Studio", source)
        self.assertIn("Caption Intake", source)
        self.assertIn("Caption Variations", source)
        self.assertIn("Prompt Template", source)
        self.assertIn("Tone", source)
        self.assertIn("Style", source)
        self.assertIn("Generate Text", source)
        self.assertIn("Regenerate Captions", source)
        self.assertIn("Select Caption", source)
        self.assertIn("Caption History", source)
        self.assertIn('"Caption Studio"', navigation)
        self.assertIn('"Caption Studio"', main)
        self.assertNotIn("publish_to_x", source)
        self.assertNotIn("publish_to_telegram", source)
        self.assertNotIn("caption_image_with_joycaption", source)
        self.assertNotIn("generate_social_captions", source)


if __name__ == "__main__":
    unittest.main()
