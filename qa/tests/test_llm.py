import io
import json
import urllib.error

import pytest

from qa import llm


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def capture(monkeypatch, payload=None, error=None):
    seen = {}

    def urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.data)
        if error:
            raise error
        return FakeResponse(json.dumps(payload).encode())

    monkeypatch.setattr(llm.urllib.request, "urlopen", urlopen)
    return seen


def test_needs_a_key():
    with pytest.raises(llm.LLMError):
        llm.Gemini(api_key="")


def test_generate_sends_key_in_header_not_url(monkeypatch):
    seen = capture(monkeypatch, {"candidates": [{"content": {"parts": [{"text": "Hi [Art. 1]"}]}}]})
    assert llm.Gemini(api_key="secret-key").generate("sys", "q") == "Hi [Art. 1]"
    assert "secret-key" not in seen["url"]
    assert seen["headers"]["X-goog-api-key"] == "secret-key"
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "sys"


def test_embed_checks_size(monkeypatch, settings):
    capture(monkeypatch, {"embeddings": [{"values": [0.0] * settings.EMBEDDING_DIMENSIONS}]})
    assert len(llm.Gemini(api_key="k").embed(["a"])[0]) == settings.EMBEDDING_DIMENSIONS
    capture(monkeypatch, {"embeddings": [{"values": [0.0] * 3}]})
    with pytest.raises(llm.LLMError, match="wrong size"):
        llm.Gemini(api_key="k").embed(["a"])


@pytest.mark.parametrize("code,text", [(429, "quota"), (403, "refused"), (500, "error \\(500\\)")])
def test_http_errors_become_plain_messages(monkeypatch, code, text):
    capture(monkeypatch, error=urllib.error.HTTPError("u", code, "x", {}, None))
    with pytest.raises(llm.LLMError, match=text):
        llm.Gemini(api_key="k").generate("s", "q")


def test_empty_replies_are_errors(monkeypatch):
    capture(monkeypatch, {"candidates": []})
    with pytest.raises(llm.LLMError):
        llm.Gemini(api_key="k").generate("s", "q")


def test_invalid_model_name_is_refused(settings):
    settings.GEMINI_MODEL = "../../evil"
    with pytest.raises(llm.LLMError, match="not valid"):
        llm.Gemini(api_key="k").generate("s", "q")
