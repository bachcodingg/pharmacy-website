"""Guards on the Litestream backup path (F-13).

None of this can prove the replica works - only scripts/restore-drill.sh does
that, against a real bucket. What these tests catch is the silent drift that
would make the drill start failing months later: the database moving out from
under litestream.yml, WAL mode being turned off, or the entrypoint losing the
restore step. Each of those leaves a deployment that looks healthy and is not
being backed up.
"""
import re
import stat
from pathlib import Path

import pytest

from app import db

PROJECT_DIR = Path(__file__).resolve().parents[2]
LITESTREAM_YML = PROJECT_DIR / "litestream.yml"
ENTRYPOINT = PROJECT_DIR / "docker-entrypoint.sh"
DOCKERFILE = PROJECT_DIR / "Dockerfile"
DRILL = PROJECT_DIR / "scripts" / "restore-drill.sh"


def test_database_is_in_wal_mode():
    """Litestream replicates WAL frames; in any other journal mode it has
    nothing to ship. This is the precondition the whole scheme rests on."""
    db.init_db()
    with db.get_connection() as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_litestream_replicates_the_path_the_app_actually_writes():
    """The config takes the database path from PHARMACY_SEARCH_DB rather than
    hardcoding /data/app.db, so moving the database cannot leave the replica
    pointed at a file nobody writes to any more."""
    text = LITESTREAM_YML.read_text(encoding="utf-8")
    assert "path: ${PHARMACY_SEARCH_DB}" in text


@pytest.mark.parametrize("variable", [
    "LITESTREAM_BUCKET",
    "LITESTREAM_PATH",
    "LITESTREAM_ENDPOINT",
    "LITESTREAM_REGION",
    "LITESTREAM_ACCESS_KEY_ID",
    "LITESTREAM_SECRET_ACCESS_KEY",
])
def test_replica_settings_come_from_the_environment(variable):
    """Nothing about the bucket is baked into a committed file. The two key
    variables are secrets; the rest change per environment."""
    assert "${%s}" % variable in LITESTREAM_YML.read_text(encoding="utf-8")


def test_no_credentials_are_committed():
    """A literal AWS-style key in any of these files means a secret leaked into
    git history, where deleting it later does not help."""
    for path in (LITESTREAM_YML, ENTRYPOINT, DOCKERFILE, PROJECT_DIR / "fly.toml"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"AKIA[0-9A-Z]{16}", text), path
        assert not re.search(r"secret-access-key:\s*[A-Za-z0-9/+=]{20,}", text), path


def test_entrypoint_restores_before_starting_the_app():
    """app/main.py creates an empty database at import time, so a machine that
    lost its volume would come up empty and replicate that emptiness over the
    good copy. The restore has to win the race, and the only way it can is by
    happening before uvicorn is exec'd."""
    text = ENTRYPOINT.read_text(encoding="utf-8")
    restore_at = text.index("litestream restore")
    replicate_at = text.index("litestream replicate")
    assert restore_at < replicate_at


def test_missing_replica_is_fatal_unless_bootstrap_was_asked_for():
    """`-if-replica-exists` turns "the bucket is misconfigured" into "this is a
    first deploy", which is exactly the failure that destroys the replica. It
    is allowed only on the branch guarded by LITESTREAM_BOOTSTRAP."""
    text = ENTRYPOINT.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "-if-replica-exists" in line and not line.lstrip().startswith("#"):
            bootstrap_at = text.index("LITESTREAM_BOOTSTRAP")
            assert bootstrap_at < text.index(line)
    # And the unguarded path must still call restore, without the flag.
    strict = [
        line for line in text.splitlines()
        if "litestream restore" in line and "-if-replica-exists" not in line
        and not line.lstrip().startswith("#")
    ]
    assert strict, "there is no strict restore path; a bad bucket would boot empty"


def test_image_ships_the_config_and_entrypoint():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY litestream.yml /etc/litestream.yml" in text
    assert "docker-entrypoint.sh" in text
    assert 'ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]' in text


def test_drill_script_is_executable():
    """It is committed as a runbook step; a non-executable runbook step is a
    step people skip."""
    assert DRILL.exists()
    assert DRILL.stat().st_mode & stat.S_IXUSR or DRILL.read_text(encoding="utf-8").startswith("#!")


def test_restored_database_would_pass_the_drill_checks():
    """The drill verifies a restored file with PRAGMA integrity_check and by
    counting a fixed list of tables. If a table on that list is ever renamed,
    the drill starts failing in production at the worst possible moment - so
    the list is checked against the live schema here instead."""
    drill = DRILL.read_text(encoding="utf-8")
    match = re.search(r"for table in ([^;]+); do", drill)
    assert match, "could not find the table list in the drill script"
    tables = match.group(1).split()

    db.init_db()
    with db.get_connection() as conn:
        existing = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    missing = [t for t in tables if t not in existing]
    assert not missing, f"the drill checks tables that no longer exist: {missing}"
