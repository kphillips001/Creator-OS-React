from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)


class Settings:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    FANVUE_API_KEY = os.getenv("FANVUE_API_KEY", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    DEFAULT_PERSONA = os.getenv("DEFAULT_PERSONA", "ava")
    CMS_ROOT = os.getenv("CMS_ROOT", r"D:\Ava_CMS")
    REQUIRE_CREATOR_PROFILE = (
        os.getenv("REQUIRE_CREATOR_PROFILE", "true").lower() == "true"
    )

    # STEP 11.5 — Fanvue webhook signature verification
    FANVUE_WEBHOOK_SECRET = os.getenv(
        "FANVUE_WEBHOOK_SECRET",
        "test_webhook_secret"
    )


settings = Settings()


# Backward-compatible direct config export
FANVUE_WEBHOOK_SECRET = settings.FANVUE_WEBHOOK_SECRET

FANVUE_WEBHOOK_SIGNING_SECRET = os.getenv(
    "FANVUE_WEBHOOK_SIGNING_SECRET",
    FANVUE_WEBHOOK_SECRET,
)

ENABLE_REALTIME_FANVUE_SEND = (
    os.getenv("ENABLE_REALTIME_FANVUE_SEND", "false").lower() == "true"
)
