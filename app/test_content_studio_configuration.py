import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.api.content_studio import (
    AutonomousInspirationRequest,
    PromptWorkshopRequest,
    PromptWorkshopUseRequest,
    PromptPreviewRequest,
    GenerationSubmissionRequest,
    TransformTagsRequest,
    _create_prompt_preview,
    _ask_prompt_planner,
    _execute_content_studio_generation,
    _execute_autonomous_inspiration,
    _generation_run_content,
    _generation_runs,
    ask_content_studio_prompt_planner,
    _enhance_tags,
    _generate_prompt_workshop_batch,
    _mark_prompt_workshop_used,
    _read_content_studio_configuration,
    _creative_director_context,
    _read_prompt_workshop_archive,
    _surprise_tags,
)


def test_creative_director_guard_uses_direct_creator_scoped_canonical_lookup():
    calls = []

    class ReferenceService:
        def get_active_canonical_asset_id(self, *, creator_profile_id):
            calls.append(creator_profile_id)
            return 84

        def get_active_reference(self, **_kwargs):
            raise AssertionError("Content Studio guard must not use full enrichment")

        def list_references(self, *_args, **_kwargs):
            raise AssertionError("Content Studio guard must not enumerate references")

    with (
        patch("app.api.content_studio._current_account_id", return_value=7),
        patch("app.api.content_studio.get_active_creator_profile", return_value={"id": 2}),
        patch("app.api.content_studio.ReferenceLibraryService", return_value=ReferenceService()),
    ):
        creator, _director = _creative_director_context()

    assert creator == {"id": 2}
    assert calls == [2]
from app.services.content_studio_configuration_service import (
    ContentStudioConfiguration,
    ContentStudioConfigurationService,
    PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
    PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
)


class _CreativeDirector:
    def __init__(self, *, mode: str, prompt_count: int) -> None:
        self.settings = SimpleNamespace(
            default_mode=mode,
            default_prompt_count=prompt_count,
        )

    def load_settings(self, creator_profile_id: int):
        self.creator_profile_id = creator_profile_id
        return self.settings


class _ProviderRegistry:
    def __init__(self, provider_ids: tuple[str, ...]) -> None:
        self._provider_ids = provider_ids

    def provider_ids(self) -> tuple[str, ...]:
        return self._provider_ids


class ContentStudioConfigurationServiceTests(unittest.TestCase):
    def _load(
        self,
        *,
        mode: str = "spicy",
        prompt_count: int = 5,
        provider_ids: tuple[str, ...] = (
            "nano_banana",
            "nano_banana_pro",
            "wan_2_7_image_edit",
            "seedream_5_0_pro",
            "seedream_4_5",
            "not_available_to_content_studio",
        ),
    ) -> ContentStudioConfiguration:
        return ContentStudioConfigurationService(
            creative_director=_CreativeDirector(
                mode=mode,
                prompt_count=prompt_count,
            ),
            generation_engine=SimpleNamespace(
                provider_registry=_ProviderRegistry(provider_ids),
            ),
        ).load(creator_profile_id=42)

    def test_load_preserves_backend_modes_provider_order_and_defaults(self):
        configuration = self._load()

        self.assertEqual(
            configuration.modes,
            (
                ("premium_teaser", "Premium Teaser"),
                ("spicy", "Spicy"),
                ("story_sequence", "Story Sequence"),
            ),
        )
        self.assertEqual(configuration.default_mode, "spicy")
        self.assertEqual(
            configuration.providers,
            (
                ("seedream_5_0_pro", "Seedream 5.0 Pro"),
            ),
        )
        self.assertEqual(configuration.default_provider, "seedream_5_0_pro")

    def test_load_validates_defaults_against_backend_configuration(self):
        below_minimum = self._load(mode="unknown", prompt_count=-1)
        above_maximum = self._load(prompt_count=999)

        self.assertEqual(below_minimum.default_mode, "premium_teaser")
        self.assertEqual(
            below_minimum.default_prompt_count,
            PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
        )
        self.assertEqual(
            above_maximum.default_prompt_count,
            PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
        )

    def test_load_continues_to_accept_historical_story_sequence_default(self):
        configuration = self._load(mode="story_sequence")

        self.assertEqual(configuration.default_mode, "story_sequence")
        self.assertIn(
            ("story_sequence", "Story Sequence"),
            configuration.modes,
        )

    def test_load_fails_closed_when_registry_has_no_supported_provider(self):
        with self.assertRaisesRegex(
            RuntimeError, "No active Content Studio generation provider is registered"
        ):
            self._load(provider_ids=("not_available_to_content_studio",))


class ContentStudioConfigurationApiTests(unittest.TestCase):
    def test_configuration_response_exposes_only_control_values(self):
        configuration = ContentStudioConfiguration(
            modes=(("premium_teaser", "Premium Teaser"),),
            prompt_count_minimum=1,
            prompt_count_maximum=20,
            default_mode="premium_teaser",
            default_prompt_count=5,
            providers=(("seedream_5_0_pro", "Seedream 5.0 Pro"),),
            default_provider="seedream_5_0_pro",
        )

        with (
            patch("app.api.content_studio._current_account_id", return_value=7),
            patch(
                "app.api.content_studio.get_active_creator_profile",
                return_value={"id": 42},
            ),
            patch(
                "app.services.content_studio_configuration_service."
                "ContentStudioConfigurationService.load",
                return_value=configuration,
            ),
        ):
            response = _read_content_studio_configuration()

        self.assertEqual(
            response,
            {
                "success": True,
                "error": None,
                "modes": [
                    {"value": "premium_teaser", "label": "Premium Teaser"},
                ],
                "promptCount": {"minimum": 1, "maximum": 20, "default": 5},
                "providers": [
                    {"value": "seedream_5_0_pro", "label": "Seedream 5.0 Pro"},
                ],
                "defaults": {
                    "mode": "premium_teaser",
                    "provider": "seedream_5_0_pro",
                },
            },
        )


class _CreativeTagDirector:
    def __init__(self) -> None:
        self.calls = []

    def premium_lucky_tags(self, **kwargs):
        self.calls.append(("lucky", kwargs))
        return "lucky explicit" if kwargs["explicit"] else "lucky premium"

    def enhance_premium_tags(self, **kwargs):
        self.calls.append(("enhance", kwargs))
        return "enhanced explicit" if kwargs["explicit"] else "enhanced premium"

    def surprise_premium_tags(self, **kwargs):
        self.calls.append(("surprise", kwargs))
        return "surprise premium"

    def ask_prompt_assistant(self, **kwargs):
        self.calls.append(("workshop", kwargs))
        return SimpleNamespace(
            batch_id="batch-new",
            creator_profile_id=42,
            request_text=kwargs["request_text"],
            lane=kwargs["lane"],
            prompts=("prompt one", "prompt two"),
            used_prompt_numbers=(),
            created_at="2026-07-17T12:00:00",
        )

    def prompt_assistant_history(self, **kwargs):
        self.calls.append(("history", kwargs))
        return (
            SimpleNamespace(
                batch_id="batch-archived",
                creator_profile_id=42,
                request_text="archived brief",
                lane="premium",
                prompts=("archived one", "archived two"),
                used_prompt_numbers=(2,),
                created_at="2026-07-16T12:00:00",
            ),
        )

    def mark_prompt_assistant_used(self, batch_id, prompt_number):
        self.calls.append(("mark", {"batch_id": batch_id, "prompt_number": prompt_number}))

    def create_prompt_plan(self, **kwargs):
        self.calls.append(("preview", kwargs))
        return SimpleNamespace(
            plan_id="plan-preview",
            prompt_text="fallback prompt",
            creative_mode=kwargs["creative_mode"],
            creative_rationale="Created by the current prompt planner.",
            prompt_metadata={
                "prompt_variations": ("preview one", "preview two"),
                "canonical_planner": "creator_os",
            },
        )

    def ask_anything(self, **kwargs):
        self.calls.append(("planner", kwargs))
        return f"planner answer: {kwargs['question']}"


class ContentStudioCreativeTagActionTests(unittest.TestCase):
    def setUp(self):
        self.director = _CreativeTagDirector()
        self.context = patch(
            "app.api.content_studio._creative_director_context",
            return_value=({"id": 42}, self.director),
        )
        self.context.start()
        self.creator_aware_planner = patch(
            "app.api.content_studio.CreatorAwareCanonicalPromptPlanner.build_question",
            side_effect=lambda *, fanvue_account_id, question: (
                f"creator-aware planner context\n{question}"
            ),
        )
        self.creator_aware_planner_mock = self.creator_aware_planner.start()

    def tearDown(self):
        self.creator_aware_planner.stop()
        self.context.stop()

    @patch("app.api.content_studio._execute_content_studio_generation")
    @patch("app.api.content_studio._current_account_id", return_value=2)
    @patch(
        "app.services.autonomous_inspiration_engine."
        "AutonomousInspirationEngine.create_directions",
        return_value=tuple(f"private direction {index}" for index in range(6)),
    )
    def test_autonomous_inspiration_privately_queues_six_images(
        self, create_directions, _account, execute_generation,
    ):
        _execute_autonomous_inspiration(
            "run-inspire",
            AutonomousInspirationRequest(provider="seedream_5_0_pro"),
        )

        create_directions.assert_called_once_with(fanvue_account_id=2)
        queued = execute_generation.call_args.args[1]
        self.assertEqual(queued.promptCount, 6)
        self.assertEqual(queued.provider, "seedream_5_0_pro")
        self.assertEqual(queued.promptBatch, [])
        self.assertIn("private direction 0", queued.promptSource)

    def test_transform_actions_delegate_to_existing_services(self):
        enhanced = _enhance_tags(TransformTagsRequest(tags="  hotel robe  "))
        explicit = _enhance_tags(
            TransformTagsRequest(tags="  explicit hotel  ", explicit=True)
        )
        surprised = _surprise_tags(TransformTagsRequest(tags="  lake house  "))

        self.assertEqual(enhanced["tags"], "enhanced premium")
        self.assertEqual(explicit["tags"], "enhanced explicit")
        self.assertEqual(surprised["tags"], "surprise premium")
        self.assertEqual(self.director.calls[0][1]["simple_tags"], "hotel robe")
        self.assertEqual(self.director.calls[1][1]["simple_tags"], "explicit hotel")
        self.assertEqual(self.director.calls[2][1]["simple_tags"], "lake house")

    def test_transform_actions_reject_empty_tags_before_service_execution(self):
        with self.assertRaisesRegex(ValueError, "Tags are required"):
            _enhance_tags(TransformTagsRequest(tags="  "))
        with self.assertRaisesRegex(ValueError, "Tags are required"):
            _surprise_tags(TransformTagsRequest(tags="\n"))

        self.assertEqual(self.director.calls, [])

    def test_prompt_workshop_generation_delegates_to_prompt_assistant(self):
        result = _generate_prompt_workshop_batch(
            PromptWorkshopRequest(
                lane="explicit",
                requestText="  hotel sequence  ",
                promptCount=5,
            )
        )

        self.assertEqual(result["batch"]["batchId"], "batch-new")
        self.assertEqual(result["batch"]["prompts"], ["prompt one", "prompt two"])
        call = self.director.calls[0]
        self.assertEqual(call[0], "workshop")
        self.assertEqual(call[1]["request_text"], "hotel sequence")
        self.assertEqual(call[1]["lane"], "explicit")
        self.assertEqual(call[1]["prompt_count"], 5)

    def test_prompt_workshop_archive_is_creator_scoped_and_marks_existing_prompt(self):
        archive = _read_prompt_workshop_archive()
        marked = _mark_prompt_workshop_used(
            "batch-archived",
            PromptWorkshopUseRequest(promptNumber=1),
        )

        self.assertEqual(archive["batches"][0]["usedPromptNumbers"], [2])
        self.assertTrue(marked["success"])
        history_calls = [call for call in self.director.calls if call[0] == "history"]
        self.assertEqual(history_calls[0][1], {"creator_profile_id": 42, "limit": 10})
        self.assertEqual(history_calls[1][1], {"creator_profile_id": 42, "limit": 10_000})
        self.assertIn(
            ("mark", {"batch_id": "batch-archived", "prompt_number": 1}),
            self.director.calls,
        )

    def test_prompt_workshop_rejects_invalid_lane_and_archive_number(self):
        with self.assertRaisesRegex(ValueError, "Prompt Mode"):
            _generate_prompt_workshop_batch(
                PromptWorkshopRequest(lane="legacy", requestText="brief", promptCount=5)
            )
        with self.assertRaisesRegex(ValueError, "outside the archived batch"):
            _mark_prompt_workshop_used(
                "batch-archived",
                PromptWorkshopUseRequest(promptNumber=3),
            )

    def test_prompt_preview_delegates_to_create_prompt_plan_and_returns_streamlit_details(self):
        result = _create_prompt_preview(
            PromptPreviewRequest(
                creativeMode="premium_teaser",
                creativeTags="  manual prompt  ",
                promptCount=2,
            )
        )

        preview = result["preview"]
        self.assertEqual(preview["planId"], "plan-preview")
        self.assertEqual(len(preview["prompts"]), 2)
        self.assertTrue(preview["prompts"][0].startswith("preview one"))
        self.assertTrue(preview["prompts"][1].startswith("preview two"))
        self.assertIn("FINAL REFERENCE BODY LOCK", preview["prompts"][0])
        self.assertTrue(preview["promptMetadata"]["provider_prompt_preview"])
        self.assertEqual(
            preview["promptMetadata"]["provider_target"],
            "seedream_5_0_pro",
        )
        self.assertEqual(preview["creativeRationale"], "Created by the current prompt planner.")
        self.assertEqual(
            preview["signature"],
            {
                "creativeMode": "premium_teaser",
                "promptCount": 2,
                "creativeTags": "manual prompt",
            },
        )
        call = next(call for call in self.director.calls if call[0] == "preview")
        self.assertEqual(call[1]["creative_tags"], "manual prompt")
        self.assertEqual(call[1]["creative_mode"], "premium_teaser")
        self.assertEqual(call[1]["prompt_count"], 2)

    def test_prompt_preview_rejects_empty_input_and_historical_invalid_mode(self):
        with self.assertRaisesRegex(ValueError, "Creative Tags are required"):
            _create_prompt_preview(
                PromptPreviewRequest(
                    creativeMode="premium_teaser",
                    creativeTags="  ",
                    promptCount=2,
                )
            )

    def test_prompt_preview_explicit_lane_selects_canonical_explicit_mode(self):
        result = _create_prompt_preview(
            PromptPreviewRequest(
                creativeMode="ignored-premium-mode",
                creativeTags="explicit source",
                promptCount=2,
                lane="explicit",
            )
        )

        self.assertEqual(result["preview"]["creativeMode"], "explicit")
        self.assertTrue(
            result["preview"]["promptMetadata"]["provider_prompt_preview"]
        )
        self.assertIn(
            "FINAL REFERENCE BODY LOCK - NON-NEGOTIABLE:",
            result["preview"]["prompts"][0],
        )
        call = next(call for call in self.director.calls if call[0] == "preview")
        self.assertEqual(call[1]["creative_mode"], "explicit")

    def test_prompt_preview_rejects_unsupported_lane(self):
        with self.assertRaisesRegex(ValueError, "lane must be social or explicit"):
            _create_prompt_preview(
                PromptPreviewRequest(
                    creativeMode="premium_teaser",
                    creativeTags="tags",
                    promptCount=2,
                    lane="legacy",
                )
            )
        with self.assertRaisesRegex(ValueError, "Premium creative mode"):
            _create_prompt_preview(
                PromptPreviewRequest(
                    creativeMode="legacy_mode",
                    creativeTags="tags",
                    promptCount=2,
                )
            )

    def test_prompt_planner_delegates_text_only_request_without_reference(self):
        result = _ask_prompt_planner(question="  critique this pose  ")

        self.assertEqual(
            result["answer"],
            "planner answer: creator-aware planner context\ncritique this pose",
        )
        self.creator_aware_planner_mock.assert_called_once_with(
            fanvue_account_id=2,
            question="critique this pose",
        )
        call = self.director.calls[-1]
        self.assertEqual(call[0], "planner")
        self.assertEqual(call[1], {
            "question": "creator-aware planner context\ncritique this pose",
            "image_bytes": None,
            "image_mime_type": None,
            "image_name": None,
        })

    def test_prompt_planner_delegates_supported_transient_image(self):
        _ask_prompt_planner(
            question="Analyze this image",
            image_bytes=b"image-data",
            image_mime_type="image/webp",
            image_name="pose.webp",
        )

        call = self.director.calls[-1][1]
        self.assertEqual(call["image_bytes"], b"image-data")
        self.assertEqual(call["image_mime_type"], "image/webp")
        self.assertEqual(call["image_name"], "pose.webp")

    def test_planner_origin_uses_isolated_creator_aware_enhancement(self):
        request = TransformTagsRequest(
            tags="Golden Hour Marina Walk — coral crop top while walking at sunset",
            origin="canonical_planner",
            plannerQuestion="Give me marina ideas",
            plannerItemId="planner-1",
            plannerItemTitle="Golden Hour Marina Walk",
        )
        with (
            patch("app.api.content_studio._current_account_id", return_value=2),
            patch(
                "app.services.canonical_planner_enhancement_service."
                "CanonicalPlannerEnhancementService.enhance",
                return_value="creator-aware enhanced marina scene",
            ) as enhance,
        ):
            result = _enhance_tags(request)

        self.assertEqual(result["tags"], "creator-aware enhanced marina scene")
        enhance.assert_called_once_with(
            fanvue_account_id=2,
            selected_item=request.tags,
        )
        self.assertFalse(any(call[0] == "enhance" for call in self.director.calls))

    def test_manual_origin_uses_creator_aware_editorial_enhancement(self):
        request = TransformTagsRequest(
            tags="tight booty daisy duke shorts, crop top, hiking",
            origin="manual_creative_concept",
        )
        with (
            patch("app.api.content_studio._current_account_id", return_value=2),
            patch(
                "app.services.manual_creative_concept_enhancement_service."
                "ManualCreativeConceptEnhancementService.enhance",
                return_value="creator-aware candid hiking direction",
            ) as enhance,
        ):
            result = _enhance_tags(request)

        self.assertEqual(result["tags"], "creator-aware candid hiking direction")
        enhance.assert_called_once_with(
            fanvue_account_id=2,
            creative_concept=request.tags,
        )
        self.assertFalse(any(call[0] == "enhance" for call in self.director.calls))

    def test_prompt_planner_rejects_empty_question_and_unsupported_image(self):
        with self.assertRaisesRegex(ValueError, "Enter a question"):
            _ask_prompt_planner(question="  ")
        with self.assertRaisesRegex(ValueError, "PNG, JPG, JPEG, or WEBP"):
            _ask_prompt_planner(
                question="Analyze",
                image_bytes=b"gif",
                image_mime_type="image/gif",
                image_name="pose.gif",
            )

    def test_prompt_planner_provider_value_error_is_structured(self):
        with patch(
            "app.api.content_studio._ask_prompt_planner",
            side_effect=ValueError("GROK_API_KEY is required"),
        ):
            response = asyncio.run(ask_content_studio_prompt_planner(question="Question", image=None))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body)["error"], "GROK_API_KEY is required")

    def test_prompt_planner_service_exception_is_controlled(self):
        with patch(
            "app.api.content_studio._ask_prompt_planner",
            side_effect=RuntimeError("secret provider payload"),
        ):
            response = asyncio.run(ask_content_studio_prompt_planner(question="Question", image=None))

        body = json.loads(response.body)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(body["error"], "Canonical Prompt Planner request failed. Please try again.")
        self.assertNotIn("secret provider payload", body["error"])

    def test_generation_delegates_queue_dispatch_progress_and_library_sync(self):
        request = GenerationSubmissionRequest(
            provider="seedream_5_0_pro",
            promptSource="manual generation prompt",
            promptSourceLabel="Manual Prompt",
            promptBatch=["edited one", "edited two"],
            creativeMode="premium_teaser",
            promptCount=2,
            creatorContext={"status": "ready", "activeReferenceAssetId": 42},
        )
        plan = SimpleNamespace(plan_id="plan-live")
        director = SimpleNamespace(
            reference_library=SimpleNamespace(),
            create_prompt_plan=lambda **kwargs: plan,
        )
        job = SimpleNamespace(job_id="job-live")
        result = SimpleNamespace(image_metadata={"completed_count": 2, "failed_count": 0}, output_references=("one.png", "two.png"))
        executed = SimpleNamespace(status="succeeded", failure=None, result=result)
        records = (SimpleNamespace(output_reference="one.png"), SimpleNamespace(output_reference="two.png"))
        captured = {}

        def execute(_self, job_value, *, progress_callback):
            captured.update({"job": job_value, "progress_callback": progress_callback})
            progress_callback(
                completed_count=1, failed_count=0, processed_count=1,
                message="Rendered image 1 of 2", output_references=("one.png",),
            )
            return executed, records

        _generation_runs["run-test"] = {"runId": "run-test", "outputReferences": ()}
        with (
            patch("app.api.content_studio._creative_director_context", return_value=({"id": 42}, director)),
            patch("app.services.content_studio_configuration_service.ContentStudioConfigurationService.load", return_value=SimpleNamespace(providers=(("seedream_5_0_pro", "Seedream 5.0 Pro"),))),
            patch("app.services.content_studio_generation_service.ContentStudioGenerationService.queue", return_value=(plan, job)) as queue,
            patch("app.services.content_studio_generation_service.ContentStudioGenerationService.execute", autospec=True, side_effect=execute),
        ):
            _execute_content_studio_generation("run-test", request)

        self.assertEqual(queue.call_args.kwargs["provider_id"], "seedream_5_0_pro")
        self.assertEqual(queue.call_args.kwargs["prompt_batch"], ("edited one", "edited two"))
        self.assertEqual(captured["job"], job)
        state = _generation_run_content("run-test")["generation"]
        self.assertEqual(state["status"], "succeeded")
        self.assertEqual(state["completedCount"], 2)
        self.assertEqual(len(state["images"]), 2)


if __name__ == "__main__":
    unittest.main()
