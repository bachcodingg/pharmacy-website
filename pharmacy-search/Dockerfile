# ---- frontend build ----
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---- backend + search index build ----
FROM python:3.12-slim AS backend
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./

# index/ is gitignored (a derived artifact, same pattern as app.db) - a
# fresh image has to rebuild the typo-correction index once from the
# committed product catalog before the app can serve corrections.
RUN python build/build_lexicon.py && python build/build_nearmiss.py

COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Overridden by the platform to point at a mounted volume in production -
# see app/db.py. Falls back to a path inside the image (fine for a quick
# local `docker run`, wiped on every rebuild).
ENV PHARMACY_SEARCH_DB=/data/app.db

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
