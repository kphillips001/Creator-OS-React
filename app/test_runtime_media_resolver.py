from types import SimpleNamespace

from app.services.runtime_media_resolver import RuntimeMediaResolver


def test_resolver_prefers_local_vault_path_inside_media_metadata(tmp_path):
    legacy_path = tmp_path / "legacy.jpg"
    vault_path = tmp_path / "vault.jpg"
    legacy_path.write_bytes(b"legacy")
    vault_path.write_bytes(b"vault")

    result = RuntimeMediaResolver().resolve_original(
        {
            "media_metadata": {"local_vault_path": str(vault_path)},
            "file_path": str(legacy_path),
        },
        require_exists=True,
    )

    assert result.path == vault_path
    assert result.source == "media_metadata.local_vault_path"
    assert result.exists is True


def test_resolver_falls_back_to_direct_local_vault_path(tmp_path):
    vault_path = tmp_path / "direct-vault.webp"
    legacy_path = tmp_path / "legacy.webp"
    vault_path.write_bytes(b"vault")
    legacy_path.write_bytes(b"legacy")

    result = RuntimeMediaResolver().resolve_original(
        SimpleNamespace(
            media_metadata={},
            local_vault_path=str(vault_path),
            file_path=str(legacy_path),
        ),
        require_exists=True,
    )

    assert result.path == vault_path
    assert result.source == "local_vault_path"
    assert result.exists is True


def test_resolver_falls_back_to_legacy_file_path(tmp_path):
    legacy_path = tmp_path / "legacy.mp4"
    legacy_path.write_bytes(b"legacy")

    result = RuntimeMediaResolver().resolve_original(
        {
            "media_metadata": {},
            "local_vault_path": "",
            "file_path": str(legacy_path),
        },
        require_exists=True,
    )

    assert result.path == legacy_path
    assert result.source == "file_path"
    assert result.exists is True


def test_resolver_returns_missing_when_no_path_exists():
    result = RuntimeMediaResolver().resolve_original({}, require_exists=True)

    assert result.path is None
    assert result.source is None
    assert result.exists is False
    assert result.candidates == ()


def test_resolver_can_report_first_nonexistent_candidate(tmp_path):
    missing_path = tmp_path / "missing.jpg"

    result = RuntimeMediaResolver().resolve_original(
        {"media_metadata": {"local_vault_path": str(missing_path)}}
    )

    assert result.path == missing_path
    assert result.source == "media_metadata.local_vault_path"
    assert result.exists is False


def test_resolver_skips_nonexistent_candidates_when_required(tmp_path):
    missing_vault_path = tmp_path / "missing-vault.jpg"
    legacy_path = tmp_path / "legacy.jpg"
    legacy_path.write_bytes(b"legacy")

    result = RuntimeMediaResolver().resolve_original(
        {
            "media_metadata": {"local_vault_path": str(missing_vault_path)},
            "file_path": str(legacy_path),
        },
        require_exists=True,
    )

    assert result.path == legacy_path
    assert result.source == "file_path"
    assert result.exists is True
