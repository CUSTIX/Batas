from pathlib import Path

from django.core.management.base import BaseCommand

from laws import services


class Command(BaseCommand):
    help = "Load data/corpus.json into the database (idempotent; run on every start)."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=None)

    def handle(self, *args, **options):
        path = Path(options["path"]) if options["path"] else None
        result = services.load_corpus(path)
        self.stdout.write(
            f"Corpus: {result.created} new, {result.updated} updated, "
            f"{result.unchanged} unchanged articles."
        )
