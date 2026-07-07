import json
from openai import OpenAI
from app.config import settings


class ObjectionClassifierService:
    """
    15.5 — GPT-based objection classification
    """

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def classify_objection(self, message: str, memory: dict = None) -> dict:
        memory = memory or {}

        if not message or not message.strip():
            return self._default_result()

        prompt = f"""
You are an objection classifier for a Fanvue chat sales assistant.

Analyze the user's latest message and determine if it contains a buying objection.

Classify into ONE:
- price
- uncertainty
- value
- delay
- none

Return ONLY valid JSON.

{{
  "has_objection": true or false,
  "objection_type": "price" | "uncertainty" | "value" | "delay" | "none",
  "confidence": 0.0 to 1.0,
  "reason": "short explanation"
}}

User message:
\"\"\"{message}\"\"\"

Memory:
{json.dumps(memory, default=str)}
"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )

            raw = response.choices[0].message.content.strip()

            # DEBUG (keep this — helps later)
            print(f"[OBJECTION RAW RESPONSE] {raw}")

            # Attempt safe JSON extraction
            try:
                # Handle cases where GPT wraps JSON in text
                start = raw.find("{")
                end = raw.rfind("}") + 1

                if start != -1 and end != -1:
                    json_str = raw[start:end]
                    result = json.loads(json_str)
                else:
                    raise ValueError("No JSON object found")

            except Exception as parse_error:
                print(f"[OBJECTION PARSE ERROR] {parse_error}")
                return self._default_result()

            return {
                "has_objection": bool(result.get("has_objection", False)),
                "objection_type": result.get("objection_type", "none"),
                "confidence": float(result.get("confidence", 0.0)),
                "reason": result.get("reason", ""),
            }

        except Exception as e:
            print(f"[OBJECTION CLASSIFIER ERROR] {e}")
            return self._default_result()

    def _default_result(self):
        return {
            "has_objection": False,
            "objection_type": "none",
            "confidence": 0.0,
            "reason": "",
        }