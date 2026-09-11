"""Shared pytest collection prerequisites.

Import the installed database driver before test modules are collected.  A
small set of legacy UI tests provides a fallback psycopg double only when the
driver is unavailable from ``sys.modules``; without this preload, that
module-global fallback can leak into unrelated PostgreSQL tests during a
combined collection run.
"""

import psycopg  # noqa: F401


# This is a manual data-seeding utility for the retired/non-launch Mass PPV
# surface, not an automated test module. Its historical repository API no
# longer exists, so importing it during pytest collection is intentionally
# excluded rather than restoring obsolete production behavior.
collect_ignore = ["app/test_seed_mass_ppv_content.py"]
