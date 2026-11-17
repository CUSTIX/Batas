# Deploying Batas (free)

| Piece | Service | Notes |
|---|---|---|
| Web | Render free web service (Docker, Singapore) | `render.yaml`; sleeps after 15 min idle, the heartbeat keeps it awake |
| Database | Neon free Postgres | pgvector is available; the first migration enables it |
| AI (optional) | Google AI Studio free key | without it: keyword search and quoted law text |

Render's free plan gives 750 instance hours per workspace per month, enough for one always-on
service. Put Batas in its own workspace if another always-on demo already uses the hours.

## One-time setup

1. **Neon**: create a project (Singapore), copy the connection string. Use the direct host
   (without `-pooler`).
2. **Render**: New > Blueprint > pick this repo. Paste the Neon string as `DATABASE_URL`.
   Optionally add `GEMINI_API_KEY`. Both are set only in the dashboard, never in the repo.
3. The first deploy migrates, loads the law text and (with a key) embeds the passages in the
   background. Check `https://batas-ph.onrender.com/livez/` and `/healthz/`.

## What runs on start (`bin/start.sh`)

1. `migrate` (creates the pgvector extension on the first run)
2. `createcachetable` (rate-limit counters)
3. `load_corpus` (idempotent: unchanged articles keep their embeddings)
4. `embed_corpus` in the background when `GEMINI_API_KEY` is set (resumable)
5. gunicorn: 2 workers x 4 threads, no query strings in the access log

## Environment variables

Every variable is documented in `.env.example` (a test enforces it).

## Updating the law text

```bash
docker compose run --rm --no-deps web python manage.py build_corpus
git diff --stat data/corpus.json      # review what changed before committing
```

Changed articles get new passages; the next start re-embeds only those.

## Before every deploy

`pytest`, `ruff check .`, `ruff format --check .`, and
`python manage.py check --deploy` with production settings. CI runs all of them, and Render
deploys only after CI passes.
