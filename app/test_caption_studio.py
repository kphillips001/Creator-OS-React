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
from app.services.generation_library_service import GenerationLibraryService
from app.services.social_publishing_service import SocialPublishingService


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


class CaptionStudioTests(unittest.TestCase):
    def make_services(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        caption_studio = CaptionStudioService(storage_dir=Path(temp_dir.name) / "captions")
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
