# Batas

Q&A over Philippine labor law with checked citations (RAG). Portfolio project: small, working end
to end, free to build and run. Same conventions as RestoCore and Abot.

## Stack

Django 5.2, PostgreSQL 17 + pgvector, Docker Compose, pytest + pytest-django, ruff, GitHub Actions.
Server-rendered templates; strict CSP (no inline script or style).

## Apps

- `core`: security headers, rate limit, base template, static files.
- `laws`: corpus (Source, Article, Passage), `build_corpus` / `load_corpus` / `embed_corpus`,
  retrieval in `selectors.py` (BM25 keywords, pgvector, fusion).
- `qa`: Gemini client (`llm.py`), answering with citation checks (`services.py`), pages.
- `evals`: question set (`questions.json`) and the retrieval quality gate.

## Commands

```
cp .env.example .env
docker compose up --build
docker compose run --rm web pytest
docker compose run --rm web ruff check .
docker compose run --rm web python manage.py eval_retrieval --verbose
docker compose run --rm web python manage.py embed_corpus      # needs GEMINI_API_KEY
docker compose run --rm --no-deps web python manage.py build_corpus   # refresh law text (internet)
```

## Rules

- Answers must cite only retrieved articles; keep the citation check and its tests.
- Any retrieval change: run `eval_retrieval`; the quality floors in
  `evals/tests/test_retrieval_quality.py` must hold. Add a question when you fix a miss.
- The app must work without `GEMINI_API_KEY`.
- Never commit `.env`, keys or real personal data. Questions are not stored.
- Stage explicit paths only. Never push without the owner confirming.
