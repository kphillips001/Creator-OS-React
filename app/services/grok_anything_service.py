import base64
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from app.config import GROK_VISION_MODEL


DEFAULT_GROK_TEXT_MODEL = "grok-3-mini"

IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def get_grok_client():
    load_dotenv()

    api_key = os.getenv("GROK_API_KEY")

    if not api_key:
        raise ValueError("Missing GROK_API_KEY in .env")

    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("GROK_BASE_URL") or "https://api.x.ai/v1",
    )


def get_uploaded_image_mime_type(uploaded_file):
    if getattr(uploaded_file, "type", None):
        return uploaded_file.type

    suffix = Path(getattr(uploaded_file, "name", "")).suffix.lower()

    return IMAGE_MIME_TYPES.get(suffix, "image/png")


def build_image_data_url(uploaded_file):
    image_bytes = uploaded_file.getvalue()

    if not image_bytes:
        raise ValueError("Uploaded image is empty.")

    mime_type = get_uploaded_image_mime_type(uploaded_file)
    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    return f"data:{mime_type};base64,{encoded_image}"


def ask_grok_anything(
    question,
    uploaded_image=None,
):
    question = str(question or "").strip()

    if not question:
        raise ValueError("Enter a question for Grok.")

    client = get_grok_client()
    has_image = uploaded_image is not None

    model = (
        GROK_VISION_MODEL
        if has_image
        else os.getenv("GROK_MODEL") or DEFAULT_GROK_TEXT_MODEL
    )

    if has_image:
        content = [
            {
                "type": "text",
                "text": question,
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": build_image_data_url(uploaded_image),
                },
            },
        ]
    else:
        content = question

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        temperature=0.8,
    )

    return response.choices[0].message.content.strip()
