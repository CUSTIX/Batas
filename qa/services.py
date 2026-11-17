"""Answer a question from the law corpus: retrieve, then answer with checked citations.

Two modes, chosen automatically:
- "ai": Gemini writes a short answer from the retrieved passages only. Every citation it makes is
  checked against those passages; a made-up citation is removed, and an answer left with no real
  citation is not shown (the passages are shown instead).
- "passages": no key, an AI error, or a failed check. The answer is the most relevant sentences of
  the retrieved articles, quoted word for word.
"""

import logging
import re
from dataclasses import dataclass, field

from django.conf import settings

from laws import selectors
from laws.models import Article
from qa.llm import Gemini, LLMError

log = logging.getLogger(__name__)

MAX_ARTICLES = 4
CITATION = re.compile(
    r"\[((?:Art\.|PD 851 Rules Sec\.|PD 851 Sec\.|MO|RA \d+ Sec\.)\s*[\dA-Z-]+)\]"
)
NOT_COVERED = "NOT_COVERED"

SYSTEM = """You answer questions about Philippine labor law for workers and small employers.
Rules:
- Use ONLY the numbered sources given. If they don't answer the question, reply exactly NOT_COVERED.
- Cite every claim with the source's label in square brackets, exactly as given, e.g. [Art. 95].
- When a Republic Act (RA) source and a Labor Code article disagree, the RA is the later law and
  wins: answer from the RA and say the Labor Code figure is outdated.
- Older amounts or rules in the sources may have been changed by later laws: say so briefly when a
  source shows a fixed peso amount or a rule known to be amended.
- Plain language, at most 5 short sentences or a short list. No preamble.
- Answer in the language of the question (English or Filipino/Taglish).
- You are not a lawyer; don't give advice about a specific case."""


@dataclass
class SourceCard:
    label: str
    heading: str
    path: str
    source_title: str
    url: str
    article_url: str
    anchor: str
    quote: str  # the sentences that matched best
    found_by: list[str] = field(default_factory=list)


@dataclass
class Segment:
    text: str
    cite: str | None = None
    anchor: str | None = None


@dataclass
class Answer:
    question: str
    mode: str  # "ai", "passages" or "none"
    segments: list[Segment] = field(default_factory=list)
    sources: list[SourceCard] = field(default_factory=list)
    notice: str = ""
    retrieval: str = "keywords"  # "keywords" or "hybrid"


def anchor_for(label: str) -> str:
    return "src-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def retrieve(question: str, k: int | None = None, client: Gemini | None = None):
    """Hybrid when embeddings exist and the AI is available, keywords otherwise."""
    k = k or settings.RETRIEVAL_TOP_K
    keyword = selectors.keyword_search(question, k * 2)
    if client is not None and selectors.has_embeddings():
        try:
            query_vec = client.embed([question], task="RETRIEVAL_QUERY")[0]
            return selectors.fuse(keyword, selectors.vector_search(query_vec, k * 2), k=k), "hybrid"
        except LLMError as exc:
            log.warning("vector retrieval skipped: %s", exc)
    return keyword[:k], "keywords"


def _best_sentences(text: str, question: str, limit: int = 2) -> str:
    words = {w[:5] for w in re.findall(r"[a-z0-9]{3,}", selectors.expand(question).lower())}
    sentences = [
        s.strip() for s in re.split(r"(?<=[.;:])\s+", text.replace("\n", " ")) if s.strip()
    ]
    scored = sorted(
        enumerate(sentences),
        key=lambda pair: (
            -len(words & {w[:5] for w in re.findall(r"[a-z0-9]{3,}", pair[1].lower())})
        ),
    )
    keep = sorted(i for i, _ in scored[:limit])
    quote = " ".join(sentences[i] for i in keep)
    return quote if len(quote) <= 700 else quote[:697].rsplit(" ", 1)[0] + "…"


FULL_TEXT_CHARS = 650  # short articles are quoted whole: exceptions often sit in the last clause
RELEVANCE_FLOOR = 0.6  # keyword hits under 60% of the best score are left out (measured on
# the eval set: no right article hidden, about 2.6 articles shown per answer)


def _quote(article: Article, question: str) -> str:
    if len(article.text) <= FULL_TEXT_CHARS:
        return " ".join(article.text.split())
    return _best_sentences(article.text, question)


def _cards(
    hits, question: str, how: str = "keywords"
) -> tuple[list[SourceCard], dict[str, Article]]:
    cards, articles = [], {}
    # BM25 scores are comparable within one question, so weak matches can be cut. Fused (hybrid)
    # scores are rank-based and too flat for a cut-off; there the count limit alone applies.
    floor = hits[0].score * RELEVANCE_FLOOR if hits and how == "keywords" else 0.0
    for hit in hits:
        if hit.score < floor:
            break
        article = hit.passage.article
        if article.label in articles:
            continue
        articles[article.label] = article
        cards.append(
            SourceCard(
                label=article.label,
                heading=article.heading,
                path=article.path,
                source_title=article.source.title,
                url=article.source.url,
                article_url=f"/laws/{article.source.slug}/{article.number}/",
                anchor=anchor_for(article.label),
                quote=_quote(article, question),
                found_by=hit.found_by,
            )
        )
        if len(cards) == MAX_ARTICLES:
            break
    return cards, articles


def _prompt(question: str, articles: dict[str, Article]) -> str:
    blocks = [
        f"[{label}] {a.heading} ({a.source.citation})\n{a.text[:2500]}"
        for label, a in articles.items()
    ]
    return "Sources:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def segment(text: str, allowed: set[str]) -> tuple[list[Segment], int, int]:
    """Split an answer into text and citation pieces. Citations not in `allowed` are dropped.
    Returns (segments, citations kept, citations dropped)."""
    segments, kept, dropped, pos = [], 0, 0, 0
    for match in CITATION.finditer(text):
        if match.start() > pos:
            segments.append(Segment(text[pos : match.start()]))
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        if label in allowed:
            segments.append(Segment("", cite=label, anchor=anchor_for(label)))
            kept += 1
        else:
            dropped += 1
        pos = match.end()
    if pos < len(text):
        segments.append(Segment(text[pos:]))
    return segments, kept, dropped


def answer(question: str, client: Gemini | None = None) -> Answer:
    question = " ".join(question.split())[: settings.QUESTION_MAX_LENGTH]
    if client is None and settings.GEMINI_API_KEY:
        client = Gemini()
    hits, how = retrieve(question, client=client)
    cards, articles = _cards(hits, question, how)
    result = Answer(question=question, mode="none", sources=cards, retrieval=how)
    if not cards:
        result.notice = 'Nothing in the Labor Code matched. Try other words, e.g. "overtime pay".'
        return result
    if client is not None:
        try:
            text = client.generate(SYSTEM, _prompt(question, articles))
            if text.strip() == NOT_COVERED:
                result.notice = (
                    "The AI found no direct answer in these articles. The closest ones are below."
                )
            else:
                segments, kept, dropped = segment(text, set(articles))
                if kept:
                    result.mode, result.segments = "ai", segments
                    if dropped:
                        result.notice = (
                            f"Removed {dropped} citation(s) that weren't in the sources."
                        )
                    return result
                result.notice = (
                    "The AI answer had no checkable citation, so the law text is shown instead."
                )
        except LLMError as exc:
            log.warning("answer generation skipped: %s", exc)
            result.notice = "The AI is unavailable right now, so the matching law text is shown."
    result.mode = "passages"
    return result
