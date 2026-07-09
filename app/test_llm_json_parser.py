import json
import tempfile
import unittest
from pathlib import Path

from app.services.llm_json_parser import extract_llm_json_text, parse_llm_json


class LLMJsonParserTests(unittest.TestCase):
    def test_accepts_plain_json(self):
        self.assertEqual(parse_llm_json('{"ok": true}', model_name="test", caller="test"), {"ok": True})

    def test_accepts_json_fence(self):
        raw = """```json
{
  "ok": true,
  "items": [1, 2]
}
```"""
        self.assertEqual(parse_llm_json(raw, model_name="test", caller="test")["items"], [1, 2])

    def test_accepts_plain_code_fence(self):
        raw = """```
{
  "ok": true
}
```"""
        self.assertTrue(parse_llm_json(raw, model_name="test", caller="test")["ok"])

    def test_accepts_whitespace_and_blank_lines(self):
        raw = """

        {
          "ok": true
        }

        """
        self.assertTrue(parse_llm_json(raw, model_name="test", caller="test")["ok"])

    def test_extracts_first_to_last_json_object(self):
        raw = 'Here is the payload:\n{"ok": true, "nested": {"value": 3}}\nDone.'
        self.assertEqual(json.loads(extract_llm_json_text(raw))["nested"]["value"], 3)

    def test_saves_debug_file_on_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError) as caught:
                parse_llm_json(
                    "not json",
                    model_name="grok-test",
                    caller="unit_test",
                    debug_dir=temp_dir,
                )

            debug_path = Path(temp_dir) / "grok_last_response.json"
            self.assertTrue(debug_path.exists())
            debug_payload = json.loads(debug_path.read_text(encoding="utf-8"))
            self.assertEqual(debug_payload["model_name"], "grok-test")
            self.assertEqual(debug_payload["caller"], "unit_test")
            self.assertEqual(debug_payload["raw_response"], "not json")
            self.assertIn(str(debug_path), str(caught.exception))


if __name__ == "__main__":
    unittest.main()
