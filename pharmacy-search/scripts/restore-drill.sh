#!/bin/sh
# Rehearse the restore. A backup you have never restored is not a backup.
#
#   scripts/restore-drill.sh local    round-trip against a file:// replica in a
#                                     temp dir. No credentials, no network -
#                                     this is the one CI and a laptop can run.
#   scripts/restore-drill.sh remote   restore the REAL production replica into a
#                                     scratch file and verify it. Read-only with
#                                     respect to the replica; safe to run against
#                                     production, and the only version that
#                                     proves the credentials and bucket path in
#                                     use actually work.
#
# Both modes end by running `PRAGMA integrity_check` and counting the rows that
# matter, because "litestream restore exited 0" only proves a file was written.
set -eu

MODE="${1:-local}"

if ! command -v litestream >/dev/null 2>&1; then
    echo "litestream is not installed. See https://litestream.io/install/" >&2
    echo "Or run it out of the image: docker run --rm -it pharmacy-search:local sh" >&2
    exit 127
fi
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if command -v python3 >/dev/null 2>&1; then PYTHON=python3; else PYTHON=python; fi
fi
if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "sqlite3 CLI is not installed; the drill verifies the restore with it." >&2
    exit 127
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

verify() {
    db="$1"
    echo "--- verifying $db"
    result="$(sqlite3 "$db" 'PRAGMA integrity_check;')"
    if [ "$result" != "ok" ]; then
        echo "integrity_check FAILED: $result" >&2
        exit 1
    fi
    echo "integrity_check ok"
    # Named explicitly rather than looping over sqlite_master: the point of the
    # drill is to confirm the tables a pharmacy cannot lose came back, and a
    # loop would happily report "0 tables verified" if the schema were missing.
    for table in users orders order_items reviews products admin_audit_log; do
        count="$(sqlite3 "$db" "SELECT COUNT(*) FROM $table;")"
        echo "  $table: $count rows"
    done
}

case "$MODE" in
local)
    SRC="$WORK/source.db"
    REPLICA="$WORK/replica"
    DEST="$WORK/restored.db"
    cat > "$WORK/litestream.yml" <<CONF
dbs:
  - path: $SRC
    replicas:
      - type: file
        path: $REPLICA
        sync-interval: 200ms
CONF

    echo "--- seeding a database with the real schema"
    # Uses the application's own init_db(), so the drill exercises the schema,
    # migrations and indexes that actually ship rather than a toy table.
    ( cd "$(dirname "$0")/../backend" \
      && PHARMACY_DATA_DIR="$WORK" PHARMACY_SEARCH_DB="$SRC" \
         PHARMACY_LOG_DIR="$WORK/logs" PHARMACY_LEARNING_DIR="$WORK/learning" \
         "$PYTHON" -c "from app.db import init_db; init_db()" )
    sqlite3 "$SRC" "INSERT INTO users (email, password_hash, salt, name, is_admin, created_at)
                    VALUES ('drill@example.com', 'x', 'y', 'Drill', 0, 0);"

    echo "--- replicating"
    litestream replicate -config "$WORK/litestream.yml" &
    LS_PID=$!
    # Give the initial snapshot time to land before writing the rows that the
    # restore has to recover from the WAL rather than from the snapshot.
    sleep 3
    i=0
    while [ "$i" -lt 50 ]; do
        sqlite3 "$SRC" "INSERT INTO click_counts (product_id, count) VALUES ($((i + 100000)), $i)
                        ON CONFLICT(product_id) DO UPDATE SET count = excluded.count;"
        i=$((i + 1))
    done
    expected="$(sqlite3 "$SRC" 'SELECT COUNT(*) FROM click_counts;')"
    sleep 3
    kill "$LS_PID" 2>/dev/null || true
    wait "$LS_PID" 2>/dev/null || true

    echo "--- restoring into a fresh file"
    litestream restore -config "$WORK/litestream.yml" -o "$DEST" "$SRC"
    verify "$DEST"

    got="$(sqlite3 "$DEST" 'SELECT COUNT(*) FROM click_counts;')"
    if [ "$got" != "$expected" ]; then
        echo "RESTORE LOST WRITES: expected $expected click_counts rows, got $got" >&2
        exit 1
    fi
    echo "--- drill passed: $got/$expected rows written after the snapshot survived the round trip"
    ;;
remote)
    : "${LITESTREAM_BUCKET:?set the replica environment first - see .env.example}"
    CONFIG="$(dirname "$0")/../litestream.yml"
    DEST="$WORK/restored.db"
    echo "--- restoring $LITESTREAM_BUCKET/${LITESTREAM_PATH:-} into a scratch file"
    # -o keeps this off the live database. Nothing here writes to the replica.
    PHARMACY_SEARCH_DB="${PHARMACY_SEARCH_DB:-/data/app.db}" \
        litestream restore -config "$CONFIG" -o "$DEST" "${PHARMACY_SEARCH_DB:-/data/app.db}"
    verify "$DEST"
    echo "--- drill passed: the production replica restores and passes integrity_check"
    ;;
*)
    echo "usage: $0 [local|remote]" >&2
    exit 2
    ;;
esac
