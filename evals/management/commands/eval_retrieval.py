import json

from django.core.management.base import BaseCommand

from evals.services import CASES, HELDOUT, evaluate
from laws import selectors


class Command(BaseCommand):
    help = "Score keyword retrieval (recall@k and MRR) on the tuning or the held-out question set."

    def add_arguments(self, parser):
        parser.add_argument("-k", type=int, default=5)
        parser.add_argument("--set", choices=["tuning", "heldout"], default="tuning")
        parser.add_argument("--verbose", action="store_true")

    def handle(self, *args, **options):
        path = HELDOUT if options["set"] == "heldout" else CASES
        cases = json.loads(path.read_text(encoding="utf-8"))
        report = evaluate(selectors.keyword_search, k=options["k"], cases=cases)
        for c in report.cases:
            if options["verbose"] or c.rank is None:
                mark = f"#{c.rank}" if c.rank else "MISS"
                self.stdout.write(f"{mark:>5}  {c.question}  expected {c.expected}, got {c.got}")
        summary = f"recall@{report.k} {report.recall:.0%}  MRR {report.mrr:.2f}"
        self.stdout.write(f"{options['set']}: {len(report.cases)} cases  {summary}")
