import unittest

from app.tools.inspect_creator_persona import build_creator_persona_report


class CreatorPersonaInspectorTests(unittest.TestCase):
    def test_report_displays_stored_fields_and_storage_keys(self):
        report = build_creator_persona_report(
            {
                "id": 7,
                "fanvue_account_id": "2",
                "persona_name": "Ava Blackthorne",
                "display_name": "Ava",
                "age": 25,
                "location": "Austin",
                "personality_description": "Warm, playful, confident.",
                "flirt_style": "teasing",
                "response_style": "short and conversational",
                "is_active": True,
            },
            fanvue_account_id=2,
        )

        self.assertIn("Creator Persona Inspection", report)
        self.assertIn("Display Name: Ava", report)
        self.assertIn("stored_as: display_name", report)
        self.assertIn("Character Name: Ava Blackthorne", report)
        self.assertIn("Raw Stored Fields", report)
        self.assertIn("persona_name: Ava Blackthorne", report)

    def test_report_flags_missing_expected_fields(self):
        report = build_creator_persona_report({"id": 7}, fanvue_account_id=2)

        self.assertIn("Missing Field Review", report)
        self.assertIn("- Biography / Bio: should become canonical", report)
        self.assertIn("- Metadata / Active Flag: canonical", report)


if __name__ == "__main__":
    unittest.main()
