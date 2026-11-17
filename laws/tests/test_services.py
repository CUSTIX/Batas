import json

import pytest

from laws import services
from laws.models import Article, Passage


def test_short_text_is_one_passage():
    assert services.split_passages("One short article.") == ["One short article."]


def test_long_text_splits_on_paragraphs_then_sentences():
    para = "Sentence number one is here. " * 60  # ~1,700 characters, one paragraph
    pieces = services.split_passages(para.strip() + "\nA second paragraph.", limit=500)
    assert len(pieces) >= 3
    assert all(len(p) <= 520 for p in pieces)
    assert pieces[-1].endswith("A second paragraph.")


@pytest.mark.django_db
def test_real_corpus_is_loaded_with_search_vectors():
    assert Article.objects.filter(source__slug="labor-code").count() > 300
    assert not Passage.objects.filter(search__isnull=True).exists()
    sil = Article.objects.get(source__slug="labor-code", number="95")
    assert sil.label == "Art. 95" and "service incentive leave" in sil.heading.lower()
    assert "Book Three" in sil.path


@pytest.mark.django_db
def test_loading_again_changes_nothing():
    result = services.load_corpus()
    assert result.created == result.updated == 0 and result.unchanged > 300


def _corpus(tmp_path, text):
    data = {
        "sources": [
            {
                "slug": "test-law",
                "title": "Test Law",
                "citation": "Test Act",
                "short_label": "T.",
                "url": "https://example.com",
                "articles": [
                    {
                        "number": "1",
                        "sort_key": 1,
                        "heading": "Rest",
                        "path": "",
                        "text": text,
                        "url": "https://example.com",
                    }
                ],
            }
        ]
    }
    path = tmp_path / "c.json"
    path.write_text(json.dumps(data))
    return path


@pytest.mark.django_db
def test_changed_article_gets_new_passages_and_loses_old_embeddings(tmp_path):
    services.load_corpus(_corpus(tmp_path, "Workers rest on Sunday."))
    article = Article.objects.get(source__slug="test-law")
    Passage.objects.filter(article=article).update(embedding=[0.1] * 768)
    result = services.load_corpus(_corpus(tmp_path, "Workers rest one day a week."))
    assert result.updated == 1
    passage = article.passages.get()
    assert passage.text == "Workers rest one day a week."
    assert passage.embedding is None, "changed text must be re-embedded"
    assert passage.search is not None


@pytest.mark.django_db
def test_embed_missing_fills_only_empty_vectors(fake_gemini):
    fake = fake_gemini()
    total = Passage.objects.count()
    assert services.embed_missing(fake.embed, batch_size=200) == total
    assert not Passage.objects.filter(embedding__isnull=True).exists()
    assert services.embed_missing(fake.embed) == 0, "a second run has nothing to do"


@pytest.mark.django_db
def test_embedding_text_carries_the_citation():
    passage = Passage.objects.select_related("article__source").filter(article__number="95").first()
    assert services.embedding_text(passage).startswith("Art. 95. Right to service incentive leave")
