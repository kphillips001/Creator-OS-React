from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)


class Settings:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    GROK_VISION_MODEL = os.getenv("GROK_VISION_MODEL", "grok-4.5")
    FANVUE_API_KEY = os.getenv("FANVUE_API_KEY", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    DEFAULT_PERSONA = os.getenv("DEFAULT_PERSONA", "ava")
    CMS_ROOT = os.getenv("CMS_ROOT", r"D:\Ava_CMS")
    CONTENT_ROOT = os.getenv("CONTENT_ROOT", str(Path(CMS_ROOT) / "Content"))
    TELEGRAM_BOT_TOKEN_AVA = os.getenv("TELEGRAM_BOT_TOKEN_AVA", "")
    TELEGRAM_CHAT_ID_AVA = os.getenv("TELEGRAM_CHAT_ID_AVA", "")
    TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "")
    TELEGRAM_VAULT_CHANNEL_ID = os.getenv("TELEGRAM_VAULT_CHANNEL_ID", "")
    TELEGRAM_CONTENT_VAULT_URL = os.getenv("TELEGRAM_CONTENT_VAULT_URL", "")
    TELEGRAM_MAIN_CHANNEL_URL = os.getenv("TELEGRAM_MAIN_CHANNEL_URL", "")
    TELEGRAM_AVA_CHAT_URL = os.getenv("TELEGRAM_AVA_CHAT_URL", "")
    DMGATE_URL_AVA = os.getenv("DMGATE_URL_AVA", "")
    AVA_FANVUE_URL = os.getenv("AVA_FANVUE_URL", "")
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
GROK_VISION_MODEL = settings.GROK_VISION_MODEL
FANVUE_WEBHOOK_SECRET = settings.FANVUE_WEBHOOK_SECRET

FANVUE_WEBHOOK_SIGNING_SECRET = os.getenv(
    "FANVUE_WEBHOOK_SIGNING_SECRET",
    FANVUE_WEBHOOK_SECRET,
)

ENABLE_REALTIME_FANVUE_SEND = (
    os.getenv("ENABLE_REALTIME_FANVUE_SEND", "false").lower() == "true"
)
