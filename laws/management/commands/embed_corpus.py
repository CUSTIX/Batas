from django.core.management.base import BaseCommand, CommandError

from laws import services
from qa.llm import Gemini, LLMError


class Command(BaseCommand):
    help = "Embed passages that have no vector yet (needs GEMINI_API_KEY). Safe to re-run."

    def handle(self, *args, **options):
        try:
            client = Gemini()
            done = services.embed_missing(client.embed)
        except LLMError as exc:
            raise CommandError(
                f"Embedding stopped: {exc} Re-run later; finished passages are kept."
            ) from exc
        self.stdout.write(self.style.SUCCESS(f"Embedded {done} passages."))
