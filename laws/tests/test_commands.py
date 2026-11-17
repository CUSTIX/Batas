from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from laws.models import Passage


@pytest.mark.django_db
def test_embed_corpus_without_a_key_explains_itself():
    with pytest.raises(CommandError, match="GEMINI_API_KEY"):
        call_command("embed_corpus")


@pytest.mark.django_db
def test_embed_corpus_embeds_everything(monkeypatch, settings, fake_gemini):
    settings.GEMINI_API_KEY = "test-key"
    fake = fake_gemini()
    monkeypatch.setattr(
        "qa.llm.Gemini.embed", lambda self, texts, task="RETRIEVAL_DOCUMENT": fake.embed(texts)
    )
    out = StringIO()
    call_command("embed_corpus", stdout=out)
    assert "Embedded" in out.getvalue()
    assert not Passage.objects.filter(embedding__isnull=True).exists()


@pytest.mark.django_db
def test_eval_command_prints_the_scores():
    out = StringIO()
    call_command("eval_retrieval", "--verbose", stdout=out)
    text = out.getvalue()
    assert "recall@5" in text and "MRR" in text and "#1" in text


@pytest.mark.django_db
def test_load_corpus_command_reports_counts():
    out = StringIO()
    call_command("load_corpus", stdout=out)
    assert "unchanged articles" in out.getvalue()
