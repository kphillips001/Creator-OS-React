from pathlib import Path
from types import SimpleNamespace
import sys
import asyncio

from PIL import Image
import pytest

sys.modules.setdefault("telethon", SimpleNamespace(
    Button=SimpleNamespace(url=lambda *args, **kwargs: object()),
    events=SimpleNamespace(NewMessage=lambda **_kwargs: object()),
))

from app.integrations.telegram.bot_api_sender import TelegramBotApiSender
from app.integrations.telegram.telethon_transport import TelethonUserTransport
from app.providers.social.telegram_provider import TelegramPublishingProvider
from app.services.telegram_image_normalization_service import TelegramImageNormalizationService


def make_image(path: Path, size, color=(40, 90, 150)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


def artifact_size(stream) -> tuple[int, int]:
    stream.seek(0)
    with Image.open(stream) as image:
        return image.size


@pytest.mark.parametrize("size", [(960, 1280), (832, 1248), (1600, 900), (1000, 1000)])
def test_every_supported_aspect_produces_canonical_artifact(tmp_path, size):
    source = make_image(tmp_path / f"source-{size[0]}-{size[1]}.png", size)
    before = source.read_bytes()
    result = TelegramImageNormalizationService().normalize(source)
    with Image.open(result.path) as image:
        assert image.size == (960, 1280)
        assert image.format == "JPEG"
    assert source.read_bytes() == before


class Response:
    status_code = 200
    text = "ok"
    def json(self):
        return {"ok": True, "result": {"message_id": 123}}
    def raise_for_status(self):
        return None


class RecordingHttp:
    def __init__(self): self.upload_sizes = []
    def post(self, _url, **kwargs):
        self.upload_sizes.append(artifact_size(kwargs["files"]["photo"]))
        return Response()


@pytest.mark.parametrize("post_to", ["main", "vault"])
def test_generation_library_broadcast_and_vault_upload_actual_960x1280_artifact(
    tmp_path, monkeypatch, post_to,
):
    source = make_image(tmp_path / "generation-library.png", (832, 1248))
    http = RecordingHttp()
    provider = TelegramPublishingProvider(http_client=http)
    monkeypatch.setattr(provider, "load_telegram_env", lambda: {
        "bot_token": "token", "main_chat_id": "main", "vault_chat_id": "vault",
    })
    result = provider.publish(image_reference=str(source), caption="Caption", post_to=post_to)
    assert result.success is True
    assert http.upload_sizes == [(960, 1280)]


class RecordingSession:
    def __init__(self): self.upload_sizes = []
    def post(self, _url, **kwargs):
        self.upload_sizes.append(artifact_size(kwargs["files"]["photo"][1]))
        return Response()


def test_asset_library_bot_api_uploads_actual_960x1280_artifact(tmp_path):
    source = make_image(tmp_path / "asset-library.png", (1000, 1000))
    session = RecordingSession()
    message_id = TelegramBotApiSender(bot_token="token", session=session).send_asset(
        chat_id=123, asset_path=str(source), message_text="Asset",
    )
    assert message_id == 123
    assert session.upload_sizes == [(960, 1280)]


class RecordingTelethonClient:
    def __init__(self): self.upload_sizes = []
    async def send_file(self, _chat_id, path, **_kwargs):
        with Image.open(path) as image:
            self.upload_sizes.append(image.size)
        return SimpleNamespace(id=456)


def test_photoshoot_telethon_uploads_actual_960x1280_artifact(tmp_path):
    source = make_image(tmp_path / "photoshoot.png", (1600, 900))
    client = RecordingTelethonClient()
    result = asyncio.run(TelethonUserTransport(client=client).send_asset(
        chat_id=123, asset_path=str(source), message_text="Photoshoot",
    ))
    assert result == 456
    assert client.upload_sizes == [(960, 1280)]
