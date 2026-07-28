from app.services.editorial_quality_guidance import editorial_quality_guidance


def test_all_workflows_share_the_editorial_quality_contract():
    required = (
        "Prefer observed moments over static portraits",
        "natural movement or environmental interaction",
        "strong environmental interaction",
        "camera distance, crop, perspective, composition, and lighting",
        "scene-aware creative-director judgment",
        "confident premium fashion styling",
        "consistent creator identity",
        "realistic skin, hair and fabric texture",
    )

    for workflow in (
        "autonomous",
        "canonical_planner",
        "manual_creative_concept",
    ):
        guidance = editorial_quality_guidance(workflow=workflow)
        assert all(value in guidance for value in required)


def test_shared_quality_preserves_each_workflow_authority():
    autonomous = editorial_quality_guidance(workflow="autonomous")
    planner = editorial_quality_guidance(workflow="canonical_planner")
    manual = editorial_quality_guidance(workflow="manual_creative_concept")

    assert "review the complete collection" in autonomous
    assert "selected planner item is authoritative" in planner
    assert "operator's Creative Concept is authoritative" in manual
    assert "wardrobe, activity, requested setting" in manual
