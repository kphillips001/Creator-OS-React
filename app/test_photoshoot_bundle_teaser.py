import base64
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageChops
import pytest

from app.models.asset_lineage import DerivationKind
from app.services.photoshoot_bundle_teaser_service import PhotoshootBundleTeaserService
from app.services.selective_blur_service import SelectiveBlurService
from app.services.blur_service import render_full_blur


def png_data(image):
    output = BytesIO(); image.save(output, "PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


def test_selective_blur_changes_only_masked_region_and_preserves_original(tmp_path):
    source = tmp_path / "source.png"
    image = Image.new("RGB", (20, 10), "red")
    for x in range(10, 20):
        for y in range(10): image.putpixel((x, y), (0, 0, 255) if (x + y) % 2 else (255, 255, 255))
    image.save(source); before = source.read_bytes()
    mask = Image.new("L", image.size, 0)
    for x in range(10, 20):
        for y in range(10): mask.putpixel((x, y), 255)
    mask_path = tmp_path / "mask.png"; mask.save(mask_path)
    output = tmp_path / "teaser.png"
    SelectiveBlurService().render(source_path=source, mask_path=mask_path, output_path=output, blur_strength=3)
    result = Image.open(output).convert("RGB")
    assert all(result.getpixel((x, y)) == (255, 0, 0) for x in range(0, 9) for y in range(10))
    assert any(result.getpixel((x, y)) != image.getpixel((x, y)) for x in range(12, 19) for y in range(10))
    assert source.read_bytes() == before


class Repository:
    def __init__(self, assets): self.current = None; self.assets = assets; self.next_id = 100
    def get(self, _): return self.current
    def create_asset(self, *, creator_profile_id, path, metadata, **_):
        value = self.next_id; self.next_id += 1
        self.assets[value] = SimpleNamespace(id=value, creator_profile_id=creator_profile_id,
            file_path=str(path), local_vault_path=str(path), media_metadata=metadata)
        return value
    def update_asset(self, asset_id, *, path, metadata):
        self.assets[asset_id] = SimpleNamespace(id=asset_id, creator_profile_id=7,
            file_path=str(path), local_vault_path=str(path), media_metadata=metadata); return True
    def upsert(self, **values):
        self.current = {**values, "commercial_role": "BUNDLE_PROMOTIONAL_TEASER",
            "mask_version": "selective_blur_mask_v1", "created_at": None, "updated_at": None}
        return self.current
    def integrity_conflicts(self, **_):
        return {"photoshoot_member": False, "paid_bundle_member": False}


class Renderer:
    def render(self, *, source_path, output_path, **_):
        Image.open(source_path).save(output_path, "PNG"); return output_path


class Lineage:
    def __init__(self): self.calls = []
    def relate(self, **values): self.calls.append(values)
    def relationships_for_asset(self, asset_id):
        return tuple(SimpleNamespace(
            source_asset_ids=tuple(item["source_asset_ids"]),
            derived_asset_id=item["derived_asset_id"],
            derivation_kind=item["derivation_kind"],
        ) for item in self.calls if item["derived_asset_id"] == asset_id)


def setup(tmp_path, *, mode="BUNDLE", protected=False):
    source1, source2 = tmp_path / "one.png", tmp_path / "two.png"
    Image.new("RGB", (20, 20), "red").save(source1); Image.new("RGB", (20, 20), "blue").save(source2)
    assets = {1: SimpleNamespace(id=1, creator_profile_id=7, file_path=str(source1), local_vault_path=str(source1)),
              2: SimpleNamespace(id=2, creator_profile_id=7, file_path=str(source2), local_vault_path=str(source2)),
              9: SimpleNamespace(id=9, creator_profile_id=8, file_path=str(source1), local_vault_path=str(source1))}
    photoshoots = SimpleNamespace(
        get=lambda _: {"deliverable_id": "set-1", "photoshoot_session_id": "session-1",
            "creator_profile_id": 7, "selling_mode": mode},
        members=lambda _: ({"asset_id": 1, "shot_order": 1}, {"asset_id": 2, "shot_order": 2}),
        has_protected_commercial_evidence=lambda *_args: protected,
    )
    repository, lineage = Repository(assets), Lineage()
    service = PhotoshootBundleTeaserService(photoshoots=photoshoots, repository=repository,
        assets=SimpleNamespace(get_by_id=lambda asset_id: assets.get(asset_id)), lineage=lineage,
        renderer=Renderer(), vault=SimpleNamespace(path=lambda value: tmp_path / value.replace("/", "_")))
    return service, repository, lineage, photoshoots


def mask():
    value = Image.new("L", (20, 20), 0)
    for x in range(5, 15):
        for y in range(5, 15): value.putpixel((x, y), 255)
    return png_data(value)


def full_mask(): return png_data(Image.new("L", (20, 20), 255))


def test_final_mask_classifies_full_blur_and_uses_canonical_strength(tmp_path):
    service, _, _, _ = setup(tmp_path)
    result = service.save("set-1", creator_profile_id=7, source_asset_id=1,
        mask_data=full_mask(), mask_width=20, mask_height=20, blur_strength=12)
    assert result["teaserStyle"] == "FULL_BLUR"
    assert result["blurStrength"] == 40


def test_saved_full_blur_pixels_match_canonical_single_image_processing(tmp_path):
    service, repository, _, _ = setup(tmp_path)
    service.renderer = SelectiveBlurService()
    result = service.save("set-1", creator_profile_id=7, source_asset_id=1,
        mask_data=full_mask(), mask_width=20, mask_height=20, blur_strength=12)
    saved = Image.open(repository.assets[result["teaserAssetId"]].file_path).convert("RGB")
    canonical = render_full_blur(repository.assets[1], blur_strength=40)
    try:
        assert ImageChops.difference(saved, canonical).getbbox() is None
    finally:
        saved.close(); canonical.close()


def test_full_blur_with_restored_pixels_classifies_selective(tmp_path):
    value = Image.new("L", (20, 20), 255)
    value.putpixel((10, 10), 0)
    service, _, _, _ = setup(tmp_path)
    result = service.save("set-1", creator_profile_id=7, source_asset_id=1,
        mask_data=png_data(value), mask_width=20, mask_height=20, blur_strength=40)
    assert result["teaserStyle"] == "SELECTIVE_BLUR"
    assert result["blurStrength"] == 40


def test_any_member_creates_canonical_derivative_lineage_and_persisted_edit_state(tmp_path):
    service, repository, lineage, photoshoots = setup(tmp_path)
    before_members = photoshoots.members("session-1")
    result = service.save("set-1", creator_profile_id=7, source_asset_id=2,
        mask_data=mask(), mask_width=20, mask_height=20, blur_strength=30)
    assert result["sourceAssetId"] == 2 and result["teaserAssetId"] == 100
    assert result["blurStrength"] == 30 and result["maskWidth"] == 20
    assert lineage.calls[0]["source_asset_ids"] == (2,)
    assert lineage.calls[0]["derived_asset_id"] == 100
    assert lineage.calls[0]["derivation_kind"] is DerivationKind.SELECTIVE_BLUR
    assert photoshoots.members("session-1") == before_members
    assert 100 not in {item["asset_id"] for item in before_members}


def test_ready_teaser_is_reconstructed_after_service_reentry(tmp_path):
    service, repository, lineage, photoshoots = setup(tmp_path)
    saved = service.save("set-1", creator_profile_id=7, source_asset_id=2,
        mask_data=mask(), mask_width=20, mask_height=20, blur_strength=30)
    reopened = PhotoshootBundleTeaserService(
        photoshoots=photoshoots, repository=repository, assets=service.assets,
        lineage=lineage, renderer=Renderer(), vault=service.vault,
    ).inspect("set-1", creator_profile_id=7)
    assert reopened["status"] == "READY"
    assert reopened["sourceAssetId"] == saved["sourceAssetId"] == 2
    assert reopened["teaserAssetId"] == saved["teaserAssetId"] == 100
    assert reopened["previewUrl"] == "/api/v1/assets/100/media"


def test_historical_selective_blur_without_authoritative_teaser_row_is_not_configured(tmp_path):
    service, repository, lineage, _ = setup(tmp_path)
    lineage.calls.append({
        "source_asset_ids": (1,), "derived_asset_id": 100,
        "derivation_kind": DerivationKind.SELECTIVE_BLUR,
    })
    assert repository.current is None
    result = service.inspect("set-1", creator_profile_id=7)
    assert result["status"] == "NOT_CONFIGURED"
    assert result["teaserAssetId"] is None


def test_reedit_reuses_derivative_and_source_change_replaces_authoritative_teaser(tmp_path):
    service, repository, lineage, _ = setup(tmp_path)
    first = service.save("set-1", creator_profile_id=7, source_asset_id=1,
        mask_data=mask(), mask_width=20, mask_height=20, blur_strength=20)
    edited = service.save("set-1", creator_profile_id=7, source_asset_id=1,
        mask_data=mask(), mask_width=20, mask_height=20, blur_strength=40)
    replaced = service.save("set-1", creator_profile_id=7, source_asset_id=2,
        mask_data=mask(), mask_width=20, mask_height=20, blur_strength=25)
    assert first["teaserAssetId"] == edited["teaserAssetId"] == 100
    assert replaced["teaserAssetId"] == 101 and repository.current["teaser_asset_id"] == 101
    assert len(lineage.calls) == 2


def test_nonmember_session_invalid_mask_strength_and_locked_source_are_rejected(tmp_path):
    service, *_ = setup(tmp_path)
    with pytest.raises(ValueError, match="approved original"):
        service.save("set-1", creator_profile_id=7, source_asset_id=9,
            mask_data=mask(), mask_width=20, mask_height=20, blur_strength=20)
    with pytest.raises(ValueError, match="invalid or corrupt"):
        service.save("set-1", creator_profile_id=7, source_asset_id=1,
            mask_data="bad", mask_width=20, mask_height=20, blur_strength=20)
    with pytest.raises(ValueError, match="between 1 and 80"):
        service.save("set-1", creator_profile_id=7, source_asset_id=1,
            mask_data=mask(), mask_width=20, mask_height=20, blur_strength=81)
    with pytest.raises(ValueError, match="at least one painted blur region"):
        service.save("set-1", creator_profile_id=7, source_asset_id=1,
            mask_data=png_data(Image.new("L", (20, 20), 0)),
            mask_width=20, mask_height=20, blur_strength=20)
    session, *_ = setup(tmp_path, mode="SESSION")
    with pytest.raises(ValueError, match="requires BUNDLE"):
        session.inspect("set-1", creator_profile_id=7)
    locked, repository, *_ = setup(tmp_path, protected=True)
    locked.save("set-1", creator_profile_id=7, source_asset_id=1,
        mask_data=mask(), mask_width=20, mask_height=20, blur_strength=20)
    with pytest.raises(ValueError, match="cannot change"):
        locked.save("set-1", creator_profile_id=7, source_asset_id=2,
            mask_data=mask(), mask_width=20, mask_height=20, blur_strength=20)
