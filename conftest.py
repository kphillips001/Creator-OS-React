"""Shared pytest collection prerequisites.

Import the installed database driver before test modules are collected.  A
small set of legacy UI tests provides a fallback psycopg double only when the
driver is unavailable from ``sys.modules``; without this preload, that
module-global fallback can leak into unrelated PostgreSQL tests during a
combined collection run.
"""

import psycopg  # noqa: F401
