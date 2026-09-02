from pathlib import Path
import re


MIGRATION = Path(
    "migrations/forward/20260819_070_generation_recipe_photoshoot_reference_roles.sql"
)

HISTORICAL_ROLES = {
    "CANONICAL_IDENTITY",
    "PHOTOSHOOT_CONTINUITY",
    "EDIT_SOURCE",
    "EDIT_REFERENCE",
    "VIDEO_SOURCE",
    "OTHER",
}

PHASE_2_ROLES = {
    "ORIGINAL_PHOTOSHOOT_SEED",
    "PREVIOUS_APPROVED_CONTINUITY",
}


def test_reference_role_migration_preserves_historical_and_phase_2_roles():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "DROP CONSTRAINT generation_recipe_references_role_check" in sql
    assert "ADD CONSTRAINT generation_recipe_references_role_check" in sql
    for role in HISTORICAL_ROLES | PHASE_2_ROLES:
        assert f"'{role}'" in sql


def test_reference_role_constraint_remains_an_explicit_allowlist():
    sql = MIGRATION.read_text(encoding="utf-8")
    constraint = sql.split("CHECK (role IN (", 1)[1].split("));", 1)[0]
    roles = set(re.findall(r"'([A-Z_]+)'", constraint))

    assert "CHECK (role IN (" in sql
    assert roles == HISTORICAL_ROLES | PHASE_2_ROLES
