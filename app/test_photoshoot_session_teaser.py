from app.services.photoshoot_session_teaser_service import PhotoshootSessionTeaserService


def context(**changes):
    value = {
        "is_archived": False, "is_active": True, "selling_mode": "SESSION",
        "registration_state": "IN_ASSET_LIBRARY", "strategy_count": 0,
        "offering_count": 0, "publication_count": 0, "intent_count": 0,
        "purchase_count": 0, "lifecycle_count": 0,
    }
    value.update(changes)
    return value


def test_unprepared_session_is_eligible_for_teaser_authoring():
    assert PhotoshootSessionTeaserService._eligibility(context()) == (True, None)


def test_bundle_and_archived_photoshoots_are_ineligible():
    assert PhotoshootSessionTeaserService._eligibility(context(selling_mode="BUNDLE"))[0] is False
    assert PhotoshootSessionTeaserService._eligibility(context(is_archived=True))[0] is False


def test_every_commercial_boundary_blocks_membership_mutation():
    for field in ("strategy_count", "offering_count", "publication_count", "intent_count",
                  "purchase_count", "lifecycle_count"):
        eligible, reason = PhotoshootSessionTeaserService._eligibility(context(**{field: 1}))
        assert eligible is False
        assert "commercial preparation or customer activity" in reason
