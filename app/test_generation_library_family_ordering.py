from datetime import datetime, timezone

from app.repositories.generation_library_projection_repository import GenerationLibraryProjectionRepository
from app.models.generation_library import GenerationLibraryFilter


def test_content_filters_use_manual_priority_and_only_approved_workflow_provenance():
    sfw_clauses, sfw_params = GenerationLibraryProjectionRepository._filters(
        GenerationLibraryFilter(content_origin="SFW", creator_profile_id=7)
    )
    nsfw_clauses, nsfw_params = GenerationLibraryProjectionRepository._filters(
        GenerationLibraryFilter(content_origin="NSFW", creator_profile_id=7, search="portrait")
    )

    assert any("generation_library_content_classifications" in clause for clause in sfw_clauses)
    assert sfw_params[-1] == "SFW"
    assert nsfw_params[-7:] == ["%portrait%"] * 7
    assert nsfw_params[2] == "NSFW"
    joined = " ".join(sfw_clauses + nsfw_clauses)
    assert "autonomous_inspiration" in joined
    assert "explicit_tags" in joined and "explicit_inspiration" in joined
    assert "canonical_planner" not in joined
    assert "manual_creative_concept" not in joined
    assert "recreate_with_ava" not in joined


def test_all_content_adds_no_origin_clause_so_unknown_legacy_records_remain_visible():
    clauses, _params = GenerationLibraryProjectionRepository._filters(
        GenerationLibraryFilter(creator_profile_id=7)
    )
    assert not any("workflow_origin" in clause for clause in clauses)


def test_unclassified_is_null_effective_classification():
    clauses, params = GenerationLibraryProjectionRepository._filters(
        GenerationLibraryFilter(content_origin="UNCLASSIFIED", creator_profile_id=7, search="legacy")
    )

    origin_clause = next(clause for clause in clauses if "workflow_origin" in clause)
    assert "IS NULL" in origin_clause
    assert "generation_library_content_classifications" in origin_clause
    assert params[-7:] == ["%legacy%"] * 7


def row(image_id, day, *, provider="seedream", status="active", staged_at=None):
    return {"image_id": image_id, "generation_date": datetime(2026, 8, day, tzinfo=timezone.utc),
            "created_at": datetime(2026, 8, day, tzinfo=timezone.utc),
            "provider_id": provider, "status": status,
            "is_staged": staged_at is not None, "staged_at": staged_at}


def edge(parent, child, day, variation=1):
    stamp = datetime(2026, 8, day, tzinfo=timezone.utc)
    return {"parent_image_id": parent, "child_image_id": child, "variation_index": variation,
            "run_created_at": stamp, "result_created_at": stamp}


def ids(families):
    return [[item["image_id"] for item in members] for _root, members in families]


def test_newest_groups_root_and_variations_by_latest_family_activity():
    rows = [row("unrelated", 9), row("root", 1), row("a1", 10), row("a2", 10)]
    edges = [edge("root", "a1", 10, 1), edge("root", "a2", 10, 2)]
    assert ids(GenerationLibraryProjectionRepository._family_order(rows, edges, sort="newest")) == [
        ["root", "a1", "a2"], ["unrelated"]]


def test_recursive_and_multiple_runs_share_original_root_deterministically():
    rows = [row("root", 1), row("a1", 3), row("a11", 5), row("b1", 4)]
    edges = [edge("root", "a1", 3), edge("a1", "a11", 5), edge("root", "b1", 4)]
    assert ids(GenerationLibraryProjectionRepository._family_order(rows, edges, sort="newest")) == [
        ["root", "a1", "b1", "a11"]]


def test_eligible_subset_does_not_inject_filtered_or_dispositioned_siblings():
    # The absent root still provides lineage, but is not added to the result.
    rows = [row("child-a", 4), row("child-b", 5)]
    edges = [edge("hidden-root", "child-a", 4, 1), edge("hidden-root", "child-b", 5, 2)]
    assert ids(GenerationLibraryProjectionRepository._family_order(rows, edges, sort="newest")) == [
        ["child-a", "child-b"]]


def test_oldest_positions_family_by_earliest_visible_member():
    rows = [row("new-root", 5), row("old-root", 1), row("old-child", 10)]
    edges = [edge("old-root", "old-child", 10)]
    assert ids(GenerationLibraryProjectionRepository._family_order(rows, edges, sort="oldest")) == [
        ["old-root", "old-child"], ["new-root"]]


def test_cycle_is_bounded_and_deterministic():
    rows = [row("a", 1), row("b", 2)]
    edges = [edge("b", "a", 1), edge("a", "b", 2)]
    assert ids(GenerationLibraryProjectionRepository._family_order(rows, edges, sort="newest")) == [["a", "b"]]


def test_lineage_order_is_preserved_while_intermediate_pages_stay_full():
    families = [("one", [row(f"one-{i}", 1) for i in range(4)]),
                ("two", [row(f"two-{i}", 2) for i in range(3)])]
    pages = GenerationLibraryProjectionRepository._family_pages(families, page_size=5)
    assert [[item["image_id"] for item in page] for page in pages] == [
        ["one-0", "one-1", "one-2", "one-3", "two-0"], ["two-1", "two-2"]]


def test_family_larger_than_page_splits_deterministically():
    family = [("root", [row(f"member-{i}", 1) for i in range(7)])]
    pages = GenerationLibraryProjectionRepository._family_pages(family, page_size=5)
    assert [len(page) for page in pages] == [5, 2]
    assert [item["image_id"] for page in pages for item in page] == [f"member-{i}" for i in range(7)]


def test_every_non_final_page_is_full_and_records_are_unique():
    families = [
        (f"family-{family}", [row(f"{family}-{member}", family + 1)
                              for member in range(size)])
        for family, size in enumerate((3, 4, 2, 6, 7))
    ]
    pages = GenerationLibraryProjectionRepository._family_pages(families, page_size=5)
    flattened = [item["image_id"] for page in pages for item in page]
    assert [len(page) for page in pages] == [5, 5, 5, 5, 2]
    assert len(flattened) == len(set(flattened)) == 22


def test_canonical_twenty_four_image_page_boundaries():
    for total, expected_sizes in ((21, [21]), (24, [24]), (25, [24, 1]),
                                  (48, [24, 24]), (50, [24, 24, 2])):
        families = [("family", [row(f"image-{index}", (index % 28) + 1)
                                 for index in range(total)])]
        pages = GenerationLibraryProjectionRepository._family_pages(families, page_size=24)
        assert [len(page) for page in pages] == expected_sizes
        flattened = [item["image_id"] for page in pages for item in page]
        assert flattened == [f"image-{index}" for index in range(total)]
        assert len(flattened) == len(set(flattened)) == total


def test_lineage_flattening_fills_twenty_four_without_duplicates_or_skips():
    families = [
        (f"family-{family}", [row(f"{family}-{member}", family + 1)
                              for member in range(size)])
        for family, size in enumerate((7, 11, 3, 14, 15))
    ]
    pages = GenerationLibraryProjectionRepository._family_pages(families, page_size=24)
    flattened = [item["image_id"] for page in pages for item in page]
    expected = [item["image_id"] for _root, members in families for item in members]

    assert [len(page) for page in pages] == [24, 24, 2]
    assert flattened == expected
    assert len(flattened) == len(set(flattened)) == 50


def test_removed_or_filtered_record_is_replaced_when_an_eligible_record_remains():
    population = [row(f"image-{index}", (index % 28) + 1) for index in range(25)]
    before = GenerationLibraryProjectionRepository._family_pages(
        [("family", population)], page_size=24,
    )
    eligible_after_disposition = [item for item in population if item["image_id"] != "image-5"]
    after = GenerationLibraryProjectionRepository._family_pages(
        [("family", eligible_after_disposition)], page_size=24,
    )

    assert [len(page) for page in before] == [24, 1]
    assert [len(page) for page in after] == [24]
    assert "image-24" in {item["image_id"] for item in after[0]}


def test_preselected_filter_population_still_fills_twenty_four():
    # browse_page applies SQL eligibility/search/classification before passing
    # rows into lineage ordering and this final page slicer.
    matching_rows = [row(f"sfw-{index}", (index % 28) + 1) for index in range(31)]
    ordered = GenerationLibraryProjectionRepository._family_order(
        matching_rows,
        [edge("sfw-0", "sfw-1", 2), edge("sfw-0", "sfw-2", 3)],
        sort="newest",
    )
    pages = GenerationLibraryProjectionRepository._family_pages(ordered, page_size=24)
    flattened = [item["image_id"] for page in pages for item in page]

    assert [len(page) for page in pages] == [24, 7]
    assert len(flattened) == len(set(flattened)) == 31


def test_staged_records_precede_normal_families_in_staged_timestamp_order():
    rows = [
        row("root", 1), row("child", 10), row("normal", 9),
        row("staged-old", 2, staged_at=datetime(2026, 8, 12, tzinfo=timezone.utc)),
        row("staged-new", 3, staged_at=datetime(2026, 8, 14, tzinfo=timezone.utc)),
    ]
    edges = [edge("root", "child", 10)]

    ordered = GenerationLibraryProjectionRepository._staged_first_order(rows, edges, sort="newest")

    assert ids(ordered) == [["staged-new"], ["staged-old"], ["root", "child"], ["normal"]]
    pages = GenerationLibraryProjectionRepository._family_pages(ordered, page_size=2)
    assert [item["image_id"] for item in pages[0]] == ["staged-new", "staged-old"]


def test_visibility_uses_current_disposition_not_historical_intake_membership():
    clause = GenerationLibraryProjectionRepository.DISPOSITION_CLAUSE
    assert "generation_image_dispositions" in clause
    assert "assembled_photoshoot_intake_members" not in clause
