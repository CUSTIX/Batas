"""The retrieval quality gate: CI fails if keyword search gets worse on the fixed question set."""

import pytest

from evals.services import evaluate, load_cases
from laws import selectors

# Floors set from the measured scores, a little below them so wording changes don't flake.
MIN_RECALL_AT_5 = 0.95  # measured 100% (46 questions)
MIN_MRR = 0.80  # measured 0.88


@pytest.mark.django_db
def test_keyword_retrieval_meets_the_quality_floor():
    report = evaluate(selectors.keyword_search, k=5)
    misses = "\n".join(
        f"  {c.question} -> expected {c.expected}, got {c.got}" for c in report.misses
    )
    assert report.recall >= MIN_RECALL_AT_5, f"recall@5 {report.recall:.0%}. Misses:\n{misses}"
    assert report.mrr >= MIN_MRR, f"MRR {report.mrr:.2f}"


def test_question_set_is_well_formed():
    cases = load_cases()
    assert len(cases) >= 40
    assert all(c["q"].strip() and c["expect"] for c in cases)
    assert len({c["q"] for c in cases}) == len(cases), "duplicate questions"
