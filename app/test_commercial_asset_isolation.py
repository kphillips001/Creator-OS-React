from types import SimpleNamespace

import pytest

from app.services.reference_asset_protection import (
    commercial_asset_eligibility_sql,
    is_commercially_eligible_asset,
    require_commercially_eligible_asset,
)


def test_canonical_reference_is_never_commercially_eligible():
    asset = SimpleNamespace(
        classification="REFERENCE",
        suggested_tags=["canonical-reference", "identity"],
        media_metadata={
            "reference_library": {
                "is_reference": True, "canonical": True, "protected": True,
            },
            "canonical_reference": {"permanent_identity_asset": True},
        },
    )
    assert is_commercially_eligible_asset(asset) is False
    with pytest.raises(ValueError, match="identity-only"):
        require_commercially_eligible_asset(asset, asset_id=93)


def test_normal_canonical_asset_remains_commercially_eligible():
    asset = SimpleNamespace(
        classification="COMMERCIAL", suggested_tags=[],
        media_metadata={},
    )
    assert is_commercially_eligible_asset(asset) is True
    require_commercially_eligible_asset(asset)


def test_sql_policy_contains_all_durable_reference_markers():
    sql = commercial_asset_eligibility_sql("asset")
    assert "reference_library" in sql
    assert "canonical_reference" in sql
    assert "permanent_identity_asset" in sql
    assert "REFERENCE" in sql and "IDENTITY" in sql
    with pytest.raises(ValueError, match="safe SQL"):
        commercial_asset_eligibility_sql("asset; DROP TABLE assets")
