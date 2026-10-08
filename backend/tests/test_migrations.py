import os
import sqlite3
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run_alembic(database_path: Path, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["MARKETPLACE_DATABASE_URL"] = f"sqlite:///{database_path}"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "backend/alembic.ini",
            *arguments,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_sqlite_migrations_persist_and_can_run_again(tmp_path):
    database_path = tmp_path / "marketplace.db"
    run_alembic(database_path, "upgrade", "head")

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version")
        assert revision.fetchall() == [("20261008_0003",)]
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        table_names = {row[0] for row in tables}
        assert {
            "users",
            "categories",
            "listings",
            "listing_submissions",
            "listing_submission_photos",
            "moderation_decisions",
            "listing_photos",
        } <= table_names

    run_alembic(database_path, "upgrade", "head")
    run_alembic(database_path, "check")
    run_alembic(database_path, "downgrade", "base")
    run_alembic(database_path, "upgrade", "head")
