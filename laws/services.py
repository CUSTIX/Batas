"""Write side of the law corpus: load it from data/corpus.json, split it into passages, embed it."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction

from laws.models import Article, Passage, Source

PASSAGE_CHARS = 900  # long articles are split near this size, on paragraph or sentence breaks
SENTENCE_END = re.compile(r"(?<=[.;:])\s+(?=[A-Z(])")


def default_corpus_path() -> Path:
    return Path(settings.BASE_DIR) / "data" / "corpus.json"


def split_passages(text: str, limit: int = PASSAGE_CHARS) -> list[str]:
    """Paragraphs packed into pieces of about `limit` characters; very long paragraphs are cut at
    sentence ends. Short articles stay one passage, so a citation usually maps to one piece."""
    pieces: list[str] = []
    for para in (p.strip() for p in text.split("\n") if p.strip()):
        parts = [para] if len(para) <= limit else SENTENCE_END.split(para)
        for i, part in enumerate(parts):
            joiner = "\n" if i == 0 else " "  # a new paragraph, or the next sentence of a long one
            if pieces and len(pieces[-1]) + len(part) + 1 <= limit:
                pieces[-1] = f"{pieces[-1]}{joiner}{part}"
            else:
                pieces.append(part)
    return pieces or [text.strip()]


@dataclass
class LoadResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


def _refresh_search_vectors(article_ids: list[int]) -> None:
    """Weighted full-text vectors: the article heading counts most, the passage text next, the
    book/chapter path a little (A > C > D)."""
    if not article_ids:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE laws_passage AS p
            SET search = setweight(to_tsvector('english', a.heading), 'A')
                      || setweight(to_tsvector('english', p.text), 'C')
                      || setweight(to_tsvector('english', coalesce(a.path, '')), 'D')
            FROM laws_article AS a
            WHERE p.article_id = a.id AND a.id = ANY(%s)
            """,
            [article_ids],
        )


@transaction.atomic
def load_corpus(path: Path | None = None) -> LoadResult:
    """Create or update every source and article from the JSON file. Idempotent: an unchanged
    article keeps its passages and embeddings; a changed one gets new passages (embedded later)."""
    data = json.loads((path or default_corpus_path()).read_text(encoding="utf-8"))
    result = LoadResult()
    touched: list[int] = []
    for src in data["sources"]:
        source, _ = Source.objects.update_or_create(
            slug=src["slug"],
            defaults={k: src[k] for k in ("title", "citation", "short_label", "url")},
        )
        for item in src["articles"]:
            fields = {k: item[k] for k in ("sort_key", "heading", "path", "text")}
            article = Article.objects.filter(source=source, number=item["number"]).first()
            if article and all(getattr(article, k) == v for k, v in fields.items()):
                result.unchanged += 1
                continue
            if article:
                for k, v in fields.items():
                    setattr(article, k, v)
                article.save()
                article.passages.all().delete()
                result.updated += 1
            else:
                article = Article.objects.create(source=source, number=item["number"], **fields)
                result.created += 1
            Passage.objects.bulk_create(
                Passage(article=article, ordinal=i, text=t)
                for i, t in enumerate(split_passages(article.text))
            )
            touched.append(article.id)
    _refresh_search_vectors(touched)
    return result


def embedding_text(passage: Passage) -> str:
    """What gets embedded: the citation and heading give the vector its context."""
    a = passage.article
    return f"{a.label}. {a.heading}. {a.path}\n{passage.text}"


def embed_missing(embedder, batch_size: int = 50) -> int:
    """Embed every passage that has no vector yet. `embedder(texts) -> list[list[float]]`.
    Safe to re-run: it only picks up what is missing, so a quota error mid-way loses nothing."""
    done = 0
    while True:
        batch = list(
            Passage.objects.filter(embedding__isnull=True)
            .select_related("article__source")
            .order_by("id")[:batch_size]
        )
        if not batch:
            return done
        vectors = embedder([embedding_text(p) for p in batch])
        for passage, vector in zip(batch, vectors, strict=True):
            passage.embedding = vector
        Passage.objects.bulk_update(batch, ["embedding"])
        done += len(batch)
