# Abyss API v2

## What changed
- Main request/API server is now in `api.py`.
- Each extractor is isolated under `extractors/`.
- Fixed the `operator` NameError in the number extractor.
- Added the missing `v_info_extract_data` module.
- Added per-thread HTTP keep-alive sessions.
- Added shorter connect/read timeouts and better upstream error handling.
- Multiple upstream APIs race concurrently; the first successful result is returned.
- Gunicorn is configured with multiple workers + threads so requests from different keys do not wait behind one request.
- Usage counting is stored in `usage.sqlite3` locally, or in PostgreSQL when `DATABASE_URL` is set.
- Hour/day buckets use `Asia/Kolkata`.
- Added `/health` and IST timestamps in responses.

## Render persistence
Render web services have an ephemeral filesystem by default. For persistent usage counts, set `DATABASE_URL` to a Render Postgres database. A local SQLite file only persists when `DATA_DIR` points to a Render persistent disk.
