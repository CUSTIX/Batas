"""Read side of the law corpus: find the passages that answer a question.

Keyword retrieval is BM25 over Postgres-stemmed terms: Postgres stems the words and indexes them,
Python scores the candidates with BM25, which weighs rare words (like "probationary") above
common ones (like "pay"). Postgres's own ts_rank has no notion of rarity.
Vector retrieval (optional) uses pgvector cosine distance. Hybrid mixes both rankings with
reciprocal rank fusion, which needs no score calibration between the two.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from django.db import connection
from pgvector.django import CosineDistance

from laws.models import Article, Passage, Source

# Plain-language and Filipino words people actually type, mapped to the words the law uses.
EXPANSIONS: dict[str, str] = {
    "13th": "thirteenth month pay",
    "thirteenth": "thirteenth month pay",
    "christmas bonus": "thirteenth month pay",
    "fired": "termination dismissal just cause",
    "dismiss": "termination dismissal just cause",
    "tanggal": "termination dismissal",
    "terminate": "termination just cause authorized cause",
    "resign": "termination by employee notice",
    "quit": "termination by employee notice",
    "overtime": "overtime work",
    "night shift": "night shift differential",
    "graveyard": "night shift differential",
    "night diff": "night shift differential",
    "vacation": "service incentive leave",
    "sick leave": "service incentive leave",
    "bakasyon": "service incentive leave",
    "pregnan": "maternity leave",
    "buntis": "maternity leave",
    "maternity": "maternity leave",
    "probation": "probationary employment",
    "regularization": "regular employment",
    "contractual": "regular casual employment contractor",
    "endo": "regular casual employment contractor labor-only contracting",
    "retire": "retirement",
    "separation pay": "separation pay closure retrenchment redundancy",
    "redundan": "redundancy separation pay",
    "holiday": "holiday pay",
    "rest day": "rest day premium",
    "day off": "rest day",
    "sunday": "rest day",
    "minimum wage": "minimum wage rates",
    "sahod": "wage",
    "sweldo": "wage",
    "salary": "wage",
    "kaltas": "wage deduction",
    "deduct": "wage deduction",
    "union": "labor organization self-organization",
    "welga": "strike",
    "complaint": "labor arbiter money claims",
    "deadline": "prescription",
    "prescri": "prescription money claims",
    "working hours": "normal hours of work",
    "oras": "hours of work",
    "lunch": "meal periods",
    "break": "meal periods",
    "tip": "service charges",
    "service charge": "service charges",
    "minor": "minimum employable age",
    "child": "minimum employable age",
    "foreigner": "employment permit non-resident aliens",
    "agency": "recruitment placement",
    "manpower": "contractor subcontractor",
    "payday": "time of payment wages",
    "how often": "time of payment",
    "illegal dismissal": "labor arbiters jurisdiction termination disputes",
    "file a case": "labor arbiters jurisdiction",
    "where do i file": "labor arbiters jurisdiction",
    "magsampa": "labor arbiters jurisdiction",
    "sexual": "sexual harassment",
}

BM25_K1, BM25_B = 1.2, 0.75
WEIGHT = {"A": 3.0, "B": 1.5, "C": 1.0, "D": 0.4}  # heading counts 3x the body text
LEXEME = re.compile(r"'((?:[^']|'')+)':([\d,A-D]+)")
POSITION = re.compile(r"\d+([A-D]?)")


def expand(question: str) -> str:
    text = question.lower()
    extra = [v for k, v in EXPANSIONS.items() if k in text]
    return " ".join([question, *extra])


def _parse_tsvector(value: str) -> dict[str, float]:
    """ "'leav':3A,9 'servic':1A" -> {"leav": 4.0, "servic": 3.0} (weighted term frequency)."""
    tf: dict[str, float] = {}
    for word, positions in LEXEME.findall(value or ""):
        # a position without a letter has Postgres's default weight, D
        tf[word.replace("''", "'")] = sum(WEIGHT[w or "D"] for w in POSITION.findall(positions))
    return tf


@lru_cache(maxsize=1)
def _stats(version: int) -> tuple[int, float, dict[str, int]]:
    """Corpus statistics for BM25: passage count, average weighted length, document frequency.
    Cached per corpus version (the passage count), so it is computed once per process."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT search::text FROM laws_passage WHERE search IS NOT NULL")
        docs = [_parse_tsvector(row[0]) for row in cursor.fetchall()]
    df: Counter[str] = Counter()
    for tf in docs:
        df.update(tf.keys())
    avg = sum(sum(tf.values()) for tf in docs) / max(1, len(docs))
    return len(docs), avg, dict(df)


def _query_lexemes(text: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_tsvector('english', %s)::text", [text])
        return [w.replace("''", "'") for w, _ in LEXEME.findall(cursor.fetchone()[0])]


@dataclass
class Hit:
    passage: Passage
    score: float
    found_by: list[str] = field(default_factory=list)  # "keywords", "meaning"


def keyword_search(question: str, k: int) -> list[Hit]:
    lexemes = _query_lexemes(expand(question))
    if not lexemes:
        return []
    n, avgdl, df = _stats(Passage.objects.count())
    query = " | ".join(f"'{w.replace(chr(39), chr(39) * 2)}'" for w in set(lexemes))
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, search::text FROM laws_passage WHERE search @@ to_tsquery('simple', %s)",
            [query],
        )
        rows = cursor.fetchall()
    counts = Counter(lexemes)
    scored = []
    for pid, vector in rows:
        tf = _parse_tsvector(vector)
        dl = sum(tf.values())
        score = 0.0
        for word, q_count in counts.items():
            f = tf.get(word, 0.0)
            if not f:
                continue
            idf = math.log(1 + (n - df.get(word, 0) + 0.5) / (df.get(word, 0) + 0.5))
            score += (
                q_count
                * idf
                * f
                * (BM25_K1 + 1)
                / (f + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
            )
        scored.append((score, pid))
    scored.sort(reverse=True)
    top = scored[:k]
    by_id = Passage.objects.select_related("article__source").in_bulk([pid for _, pid in top])
    return [Hit(by_id[pid], score, ["keywords"]) for score, pid in top]


def vector_search(query_embedding: list[float], k: int) -> list[Hit]:
    rows = (
        Passage.objects.exclude(embedding__isnull=True)
        .select_related("article__source")
        .annotate(distance=CosineDistance("embedding", query_embedding))
        .order_by("distance")[:k]
    )
    return [Hit(p, 1 - p.distance, ["meaning"]) for p in rows]


def has_embeddings() -> bool:
    return Passage.objects.exclude(embedding__isnull=True).exists()


def fuse(*rankings: list[Hit], k: int, c: int = 60) -> list[Hit]:
    """Reciprocal rank fusion: each list votes 1/(c + rank) for its passages."""
    merged: dict[int, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            entry = merged.setdefault(hit.passage.id, Hit(hit.passage, 0.0, []))
            entry.score += 1 / (c + rank)
            entry.found_by += [f for f in hit.found_by if f not in entry.found_by]
    return sorted(merged.values(), key=lambda h: h.score, reverse=True)[:k]


def article(source_slug: str, number: str) -> Article | None:
    return (
        Article.objects.select_related("source")
        .prefetch_related("passages")
        .filter(source__slug=source_slug, number=number)
        .first()
    )


def sources_with_articles():
    return Source.objects.prefetch_related("articles").order_by("id")
