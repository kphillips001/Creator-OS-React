import hashlib
import json
from pathlib import Path

from app.models.reference_library import ReferenceLibraryActionResult
from app.services.canonical_reference_service import CanonicalReferenceService


class FakeReferenceService:
    def __init__(self, active=None):
        self.active = active
        self.restore_calls = []

    def get_active_reference(self, *, creator_profile_id):
        return self.active

    def restore_canonical_reference(self, **kwargs):
        self.restore_calls.append(kwargs)
        return ReferenceLibraryActionResult(
            success=True,
            message="restored",
            asset_id=91,
            reference="restored-reference",
        )


def profile():
    return {
        "id": 2,
        "display_name": "Ava Blackthorne",
        "persona_name": "ava",
        "fanvue_account_id": "2",
    }


def test_protect_copies_and_verifies_permanent_identity_media(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(b"canonical-image")
    expected = hashlib.sha256(source.read_bytes()).hexdigest().upper()
    service = CanonicalReferenceService(cms_root=tmp_path / "cms")

    metadata = service.protect(
        source_path=source,
        creator_profile=profile(),
        original_filename="original.png",
        expected_sha256=expected,
        historical_asset_id=84,
    )

    assert source.read_bytes() == b"canonical-image"
    assert service.image_path("Ava Blackthorne").read_bytes() == b"canonical-image"
    assert metadata["sha256"] == expected
    assert metadata["historical_asset_id"] == 84
    assert metadata["automatic_cleanup_allowed"] is False
    assert service.verify("Ava Blackthorne") == (True, expected)


def test_recovery_uses_reference_service_only_when_active_reference_is_missing(tmp_path):
    source = tmp_path / "source.png"
    source.write_bytes(b"canonical-image")
    service = CanonicalReferenceService(cms_root=tmp_path / "cms")
    service.protect(
        source_path=source,
        creator_profile=profile(),
        original_filename="original.png",
    )
    references = FakeReferenceService()

    recovered = service.recover_creator(profile(), reference_service=references)

    assert recovered == "restored-reference"
    assert len(references.restore_calls) == 1
    assert references.restore_calls[0]["creator_profile_id"] == 2
    assert references.restore_calls[0]["original_filename"] == "original.png"

    references.active = "already-active"
    assert service.recover_creator(profile(), reference_service=references) == "already-active"
    assert len(references.restore_calls) == 1


def test_missing_canonical_never_blocks_startup_recovery(tmp_path):
    service = CanonicalReferenceService(cms_root=tmp_path / "cms")
    references = FakeReferenceService()

    assert service.recover_creator(profile(), reference_service=references) is None
    assert references.restore_calls == []


def test_reference_service_requires_explicit_canonical_confirmation():
    source = Path("app/services/reference_library_service.py").read_text(encoding="utf-8")
    assert "confirm_canonical: bool = False" in source
    assert "confirm_replace_canonical: bool = False" in source
    assert "Canonical Reference removal requires explicit confirmation." in source
    assert "Replacing the Canonical Reference requires explicit confirmation." in source


def test_canonical_root_is_outside_normal_vault_cleanup_roots(tmp_path):
    service = CanonicalReferenceService(cms_root=tmp_path / "cms")
    assert service.root == (tmp_path / "cms" / "Canonical").resolve()
    assert service.root not in service.local_vault.canonical_paths().values()


def test_canonical_restore_registers_an_active_asset():
    source = Path("app/services/reference_library_service.py").read_text(
        encoding="utf-8"
    )
    assert '"is_active": True' in source
