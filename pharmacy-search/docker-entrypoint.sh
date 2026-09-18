#!/bin/sh
# Boot sequence for the container: restore the database from object storage if
# this machine does not already have one, then run the app under Litestream so
# every subsequent write is replicated.
#
# Ordering matters. app/main.py calls init_db() at import time, which creates
# an empty database if none exists - so the restore has to finish before
# uvicorn is allowed to start, or a machine that lost its volume would come up
# with an empty catalogue and immediately begin replicating that emptiness
# over the good replica.
set -eu

CONFIG=/etc/litestream.yml
DB="${PHARMACY_SEARCH_DB:-/data/app.db}"

log() {
    # Structured, because this goes to the Fly log drain alongside the app's
    # own JSON lines and should be filterable the same way.
    printf '{"ts":"%s","level":"%s","logger":"entrypoint","event":"%s"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2"
}

if [ -z "${LITESTREAM_BUCKET:-}" ]; then
    # No bucket configured: run unreplicated rather than refusing to boot.
    # Local development and CI have no object storage, and the alternative -
    # a hard failure - would make the image untestable without credentials.
    log warn "litestream_disabled_no_bucket"
    exec "$@"
fi

if [ -f "$DB" ]; then
    log info "database_present_skipping_restore"
elif [ "${LITESTREAM_BOOTSTRAP:-}" = "1" ]; then
    # First deploy against an empty bucket. Deliberately a one-shot flag: see
    # the comment below for why this is not the default.
    log info "bootstrap_restore_optional"
    litestream restore -if-replica-exists -config "$CONFIG" "$DB"
else
    # No local database and no bootstrap flag, so a replica MUST exist. If the
    # restore fails - wrong bucket, revoked key, typo'd path - this exits
    # non-zero and the machine crash-loops, which is the loud failure we want.
    #
    # Running `-if-replica-exists` unconditionally would be the quiet failure
    # instead: a misconfigured bucket looks exactly like a first deploy, so the
    # app would come up serving an empty database and start overwriting the
    # real replica with it. The flag exists, but you have to ask for it.
    log info "restore_required"
    litestream restore -config "$CONFIG" "$DB"
    log info "restore_complete"
fi

log info "starting_replication"
exec litestream replicate -config "$CONFIG" -exec "$*"
