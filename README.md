# Batas

**Ask the Philippine Labor Code a question, get an answer that cites the article it comes from.**
*Batas* is Filipino for "law".

Retrieval-augmented generation (RAG) over the Labor Code of the Philippines (PD 442, as amended),
the 13th Month Pay Law (PD 851) and its rules, and Memorandum Order No. 28. Questions in English,
Filipino or Taglish.

Portfolio project. Django 5.2, PostgreSQL 17 with pgvector, Docker Compose, GitHub Actions. Free to
build and run. **Not legal advice.**

## What makes it trustworthy

- **Every answer shows its sources.** Each claim cites an article (for example `Art. 95`), and the
  article text is right below it, so you can check.
- **Citations are verified.** An AI answer may only cite articles it was given. Made-up citations
  are removed; if none is left, the answer is not shown and the law text is shown instead.
- **It works without AI.** No API key: keyword retrieval (BM25) and the matching sentences of the
  law, quoted word for word. With a key: hybrid retrieval and a short plain-language answer.
- **Retrieval quality is measured in CI.** 46 real questions (English and Filipino) with the
  article that answers each. The build fails if recall@5 drops below 95% or MRR below 0.80.

Current scores (keyword retrieval only, no AI):

| Question set | Questions | recall@5 | MRR |
|---|---|---|---|
| Tuning set (`evals/questions.json`) | 46 | 100% | 0.89 |
| Held-out set (`evals/heldout.json`) | 20 | 75% | 0.68 |

recall@5: share of questions whose right article is in the top 5. MRR: average of 1 / rank of
the right article. The plain-language word map (for example *sahod* → wage, *tanggal* →
dismissal, *endo* → labor-only contracting) was developed against the tuning set, so its score is
a regression gate. The held-out set was written afterwards and is never tuned on; it is the honest
estimate for new questions. Its misses ("managers" vs "managerial employees", *sakit* vs
"disease") are what the optional meaning search is for.

## Quickstart

Prerequisites: Docker Desktop and Git.

```bash
git clone https://github.com/CUSTIX/Batas.git batas
cd batas
cp .env.example .env                 # Windows cmd: copy .env.example .env
docker compose up --build            # migrates and loads the law text, then serves the app
```

Open <http://127.0.0.1:8000/> and ask, for example, "Ilang araw ang service incentive leave?".

Optional AI answers: put a free Google AI Studio key in `.env` as `GEMINI_API_KEY`, restart, and
embed the passages once:

```bash
docker compose run --rm web python manage.py embed_corpus
```

## Commands

```bash
docker compose run --rm web pytest                          # tests, including the quality gate
docker compose run --rm web ruff check .
docker compose run --rm web python manage.py eval_retrieval --verbose   # per-question ranks
docker compose run --rm web python manage.py eval_retrieval --set heldout
docker compose run --rm web python manage.py load_corpus    # idempotent; runs on every start
docker compose run --rm web python manage.py embed_corpus   # needs GEMINI_API_KEY; resumable
docker compose run --rm web python manage.py build_corpus   # re-download and re-parse the laws
```

## How it works

```
question ──► expand plain/Filipino words ──► BM25 over Postgres-stemmed passages ─┐
         └─► (with a key) Gemini embedding ──► pgvector cosine search ────────────┤
                                                    reciprocal rank fusion ◄───────┘
                                                              │
                         top articles ──► Gemini, "use only these, cite [Art. N]"
                                                              │
                         answer ──► citation check ──► page with answer + sources
```

- **Corpus** (`laws/`): `build_corpus` downloads the published text, strips page chrome (and a
  hidden watermark the source inserts inside paragraphs), splits it into articles with their
  Book/Title/Chapter path, and writes `data/corpus.json`, which is committed and reviewed like
  code. `load_corpus` loads it into Postgres and splits long articles into ~900-character passages.
- **Keyword retrieval**: Postgres stems and indexes the words (weighted: heading > text > path);
  Python scores candidates with BM25, which favors rare legal terms over common words. Postgres's
  own `ts_rank` has no notion of how rare a word is.
- **Meaning retrieval** (optional): Gemini embeddings (768 dimensions) in pgvector with an HNSW
  index; merged with keyword results by reciprocal rank fusion.
- **Answering** (`qa/`): the model gets only the top articles and strict rules; its citations
  are checked against them. Without a key, or on any AI error, the matching sentences are shown.
- **Evaluation** (`evals/`): `evals/questions.json` plus a test that enforces the floors above.

## Decisions

- **Postgres for everything** (text search, vectors, rate-limit counters). One free Neon database,
  no separate vector store or search service.
- **BM25 in Python** over Postgres lexemes: the corpus is about 600 passages, so scoring in Python
  is fast, and it gives far better ranking than `ts_rank`.
- **Graceful without AI.** The demo stays useful when the free AI quota runs out.
- **Questions are GET requests**, so an answer has a shareable link. Rate-limited per visitor IP.
- **Server-rendered pages**, strict Content Security Policy (no inline script or style; a test
  enforces it).

## Limits

- The Labor Code text is the amended version with the original article numbers (still the most
  cited). Later separate laws (for example the Expanded Maternity Leave Law, the Kasambahay Law,
  current minimum wages) are not included yet.
- Articles 136 and 295 are missing from the source pages.

## Sources and licenses

- Labor Code text via [ChanRobles](https://chanrobles.com/legal4labor.htm); PD 851, its rules and
  MO 28 via [The LawPhil Project](https://lawphil.net) (Arellano Law Foundation).
- Philippine statutes are not subject to copyright (RA 8293, Sec. 176). Only the law text is
  stored, with a link to the page it came from.
- Code: MIT License, see [LICENSE](LICENSE).

## Deploy

Free: Render web service (Docker) + Neon Postgres (pgvector). See [docs/deploy.md](docs/deploy.md).
