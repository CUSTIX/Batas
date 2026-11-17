"""Retrieval evaluation: does the right article come back, and how high?

Each case is a question and the article(s) that answer it. For each case we take the top k
retrieved passages, collapse them to articles (in order) and record the rank of the first
expected article. Reported: recall@k (share of cases with a right article in the top k) and MRR
(mean of 1/rank, 0 when missing).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings

CASES = Path(settings.BASE_DIR) / "evals" / "questions.json"
# Written after tuning and never tuned on: the honest estimate for new questions.
HELDOUT = Path(settings.BASE_DIR) / "evals" / "heldout.json"


@dataclass
class CaseResult:
    question: str
    expected: list[str]
    got: list[str]
    rank: int | None  # 1-based rank of the first expected article, None if missing


@dataclass
class Report:
    k: int
    cases: list[CaseResult] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return sum(c.rank is not None for c in self.cases) / max(1, len(self.cases))

    @property
    def mrr(self) -> float:
        return sum(1 / c.rank for c in self.cases if c.rank) / max(1, len(self.cases))

    @property
    def misses(self) -> list[CaseResult]:
        return [c for c in self.cases if c.rank is None]


def load_cases(path: Path = CASES) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate(retrieve, k: int = 5, cases: list[dict] | None = None) -> Report:
    """`retrieve(question, k) -> list of hits` (laws.selectors.Hit)."""
    report = Report(k=k)
    for case in cases if cases is not None else load_cases():
        articles: list[str] = []
        for hit in retrieve(case["q"], k * 2):
            label = hit.passage.article.label
            if label not in articles:
                articles.append(label)
        articles = articles[:k]
        rank = next((i for i, a in enumerate(articles, 1) if a in case["expect"]), None)
        report.cases.append(CaseResult(case["q"], case["expect"], articles, rank))
    return report
