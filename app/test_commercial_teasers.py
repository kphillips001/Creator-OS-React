import base64
from io import BytesIO
from pathlib import Path
from PIL import Image
import pytest

from app.services.selective_blur_mask_validator import SelectiveBlurMaskValidator


def mask_data(painted=True):
    image = Image.new("RGBA", (8, 8), (255, 255, 255, 255 if painted else 0))
    value = BytesIO(); image.save(value, format="PNG")
    return "data:image/png;base64," + base64.b64encode(value.getvalue()).decode()


def test_generic_mask_validation_is_shared_and_rejects_empty_masks():
    validator = SelectiveBlurMaskValidator()
    assert validator.decode(mask_data(), 8, 8).startswith(b"\x89PNG")
    with pytest.raises(ValueError, match="painted blur region"):
        validator.decode(mask_data(False), 8, 8)


def test_commercial_teaser_migration_is_destination_neutral_and_reversible():
    forward = Path("migrations/forward/20260807_046_commercial_teasers.sql").read_text()
    rollback = Path("migrations/rollback/20260807_046_commercial_teasers.sql").read_text()
    assert "commercial_teasers" in forward
    assert "distribution_use IN ('CHAT','CONTENT_VAULT')" in forward
    assert "teaser_style IN ('FULL_BLUR','SELECTIVE_BLUR')" in forward
    assert "photoshoot" not in forward.lower()
    assert "DROP TABLE IF EXISTS public.commercial_teasers" in rollback


def test_content_vault_selective_teaser_constraint_is_explicit():
    forward = Path("migrations/forward/20260808_047_content_vault_selective_teasers.sql").read_text()
    assert "distribution_use = 'CONTENT_VAULT'" in forward
    assert "teaser_style = 'SELECTIVE_BLUR'" in forward
    assert "derived_asset_id IS NOT NULL" in forward
    assert "mask_path IS NOT NULL" in forward


def test_sales_inventory_prefers_chat_selective_teaser():
    source = Path("app/repositories/commercial_fulfillment_repository.py").read_text()
    assert "commercial_teaser.distribution_use='CHAT'" in source
    assert source.index("commercial_teaser.derivative_path") < source.index("NULLIF(hero.blurred_preview_path")
