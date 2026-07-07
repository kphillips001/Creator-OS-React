import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class ReactionLLMGenerationService:
    """
    3D.19.13 — Live GPT/Grok Generation Integration

    Generates terminal-preview reaction text from prompt-builder output.

    IMPORTANT:
    This service DOES NOT send Fanvue messages.
    This service DOES NOT write queues.
    This service DOES NOT enable outbound automation.
    """

    def generate_reaction_preview(
        self,
        prompt_payload: dict,
    ) -> dict:
        if not prompt_payload:
            return self._blocked(
                "missing_prompt_payload"
            )

        if not prompt_payload.get("success"):
            return self._blocked(
                "invalid_prompt_payload"
            )

        provider = prompt_payload.get(
            "provider",
            "openai",
        )

        if provider == "grok":
            return self._generate_with_grok(
                prompt_payload
            )

        return self._generate_with_openai(
            prompt_payload
        )

    def _generate_with_openai(
        self,
        prompt_payload: dict,
    ) -> dict:
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            return self._blocked(
                "missing_openai_api_key"
            )

        model = os.getenv(
            "OPENAI_MODEL",
            "gpt-4o-mini",
        )

        client = OpenAI(
            api_key=api_key,
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        prompt_payload[
                            "system_prompt"
                        ]
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        prompt_payload[
                            "user_prompt"
                        ]
                    ),
                },
            ],
            temperature=prompt_payload.get(
                "temperature",
                0.7,
            ),
            max_tokens=160,
        )

        text = response.choices[0].message.content

        return {
            "success": True,
            "provider": "openai",
            "model": model,
            "generated_text": text,
            "send_allowed": False,
            "queue_write_allowed": False,
            "preview_only": True,
        }

    def _generate_with_grok(
        self,
        prompt_payload: dict,
    ) -> dict:
        api_key = (
            os.getenv("GROK_API_KEY")
            or os.getenv("XAI_API_KEY")
        )

        if not api_key:
            return self._blocked(
                "missing_grok_api_key"
            )

        base_url = os.getenv(
            "GROK_BASE_URL",
            "https://api.x.ai/v1",
        )

        model = os.getenv(
            "GROK_MODEL",
            "grok-4.3",
        )

        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        prompt_payload[
                            "system_prompt"
                        ]
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        prompt_payload[
                            "user_prompt"
                        ]
                    ),
                },
            ],
            temperature=prompt_payload.get(
                "temperature",
                0.9,
            ),
            max_tokens=180,
        )

        text = response.choices[0].message.content

        return {
            "success": True,
            "provider": "grok",
            "model": model,
            "generated_text": text,
            "send_allowed": False,
            "queue_write_allowed": False,
            "preview_only": True,
        }

    def _blocked(
        self,
        reason: str,
    ) -> dict:
        return {
            "success": False,
            "blocked": True,
            "reason": reason,
            "send_allowed": False,
            "queue_write_allowed": False,
            "preview_only": True,
        }