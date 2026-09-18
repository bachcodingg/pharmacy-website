# ---- frontend build ----
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
# npm ci, not npm install: the lockfile is committed, so the build should
# install exactly what it pins rather than re-resolving the range.
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- backend + search index build ----
FROM python:3.12-slim AS backend
WORKDIR /app/backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Litestream replicates the SQLite WAL to object storage (F-13). It is a
# single static binary and runs as the container's supervisor, so it is
# installed into the runtime image rather than pulled at boot.
ARG LITESTREAM_VERSION=0.3.13
RUN set -eux;     apt-get update;     apt-get install -y --no-install-recommends ca-certificates curl;     case "$(dpkg --print-architecture)" in         amd64) ls_arch=amd64 ;;         arm64) ls_arch=arm64 ;;         *) echo "unsupported architecture for litestream" >&2; exit 1 ;;     esac;     curl -fsSL -o /tmp/litestream.tar.gz         "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-${ls_arch}.tar.gz";     tar -C /usr/local/bin -xzf /tmp/litestream.tar.gz litestream;     rm /tmp/litestream.tar.gz;     apt-get purge -y --auto-remove curl;     rm -rf /var/lib/apt/lists/*;     litestream version

# Production dependencies only - pytest and httpx live in requirements-dev.txt
# and no longer ship in the runtime image.
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./

# index/ is gitignored (a derived artifact, same pattern as app.db) - a
# fresh image has to rebuild the typo-correction index once from the
# committed product catalog before the app can serve corrections.
RUN python build/build_lexicon.py && python build/build_nearmiss.py

COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Everything mutable lives under /data, which is the mounted volume in
# production: the database, the query and click logs, and the pharmacist's
# approved correction pairs. Before this, only the database was on the
# volume - the logs and approvals were written inside the image and were
# discarded on every restart and redeploy, so the learning loop could never
# accumulate anything.
ENV PHARMACY_DATA_DIR=/data \
    PHARMACY_SEARCH_DB=/data/app.db \
    PHARMACY_LOG_DIR=/data/logs \
    PHARMACY_LEARNING_DIR=/data/learning

COPY litestream.yml /etc/litestream.yml
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Runs unprivileged. /data is chowned at build time; Fly mounts the volume
# over it, so the entrypoint re-checks ownership at boot.
RUN useradd --create-home --uid 10001 app     && chmod +x /usr/local/bin/docker-entrypoint.sh     && mkdir -p /data && chown -R app:app /data /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"

# The entrypoint restores from the replica when the volume is empty and then
# execs uvicorn under `litestream replicate`, so CMD stays the plain server
# command and can still be overridden for a one-off shell.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
