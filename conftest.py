import pytest
from django.core.management import call_command


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Load the real law corpus once per test run: retrieval tests run on the actual text."""
    with django_db_blocker.unblock():
        call_command("load_corpus", verbosity=0)
        call_command("createcachetable", verbosity=0)


@pytest.fixture(autouse=True)
def no_api_key(settings):
    """Tests never call the real AI service; a test that needs the AI passes a fake client."""
    settings.GEMINI_API_KEY = ""


@pytest.fixture(autouse=True)
def fresh_cache(settings):
    """In-memory cache per test (rate-limit counters start at zero; no database needed)."""
    from django.core.cache import cache

    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    cache.clear()
    yield


class FakeGemini:
    """Stands in for qa.llm.Gemini: canned answers, deterministic embeddings, call log."""

    def __init__(self, answer="", error=None, dims=768):
        self.answer, self.error, self.dims, self.calls = answer, error, dims, []

    def generate(self, system, prompt):
        self.calls.append(("generate", prompt))
        if self.error:
            raise self.error
        return self.answer

    def embed(self, texts, task="RETRIEVAL_DOCUMENT"):
        self.calls.append(("embed", task, len(texts)))
        if self.error:
            raise self.error
        return [self.vector(t) for t in texts]

    def vector(self, text):
        """Bag of hashed words: texts sharing words get similar vectors (good enough for tests)."""
        import hashlib
        import re

        v = [0.0] * self.dims
        for word in re.findall(r"[a-z]{4,}", text.lower()):
            v[
                int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16) % self.dims
            ] += 1.0
        if not any(v):
            v[0] = 1.0
        return v


@pytest.fixture
def fake_gemini():
    return FakeGemini
