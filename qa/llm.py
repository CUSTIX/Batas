"""Minimal Gemini client (REST, standard library only): text generation and embeddings.

No SDK on purpose: two endpoints, plain JSON, and the key travels in a header, never in a URL
(URLs end up in logs).
"""

import json
import re
import urllib.error
import urllib.request

from django.conf import settings

BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}"
MODEL_NAME = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,60}$")


class LLMError(Exception):
    """The AI service could not be used for this request (the caller falls back)."""


class Gemini:
    def __init__(self, api_key: str | None = None, timeout: int = 25):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.timeout = timeout
        if not self.api_key:
            raise LLMError("No GEMINI_API_KEY is set.")

    def _post(self, model: str, method: str, body: dict) -> dict:
        if not MODEL_NAME.match(model):
            raise LLMError("The model name in the settings is not valid.")
        request = urllib.request.Request(  # noqa: S310 - fixed https host, model name validated
            BASE.format(model=model, method=method),
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            reason = {
                400: "The AI service rejected the request.",
                403: "The AI service refused the API key.",
                404: "The AI model was not found.",
                429: "The AI service is busy or the free quota is used up.",
            }.get(exc.code, f"The AI service returned an error ({exc.code}).")
            raise LLMError(reason) from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise LLMError("The AI service could not be reached.") from exc

    def embed(self, texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        model = settings.GEMINI_EMBED_MODEL
        body = {
            "requests": [
                {
                    "model": f"models/{model}",
                    "content": {"parts": [{"text": t}]},
                    "taskType": task,
                    "outputDimensionality": settings.EMBEDDING_DIMENSIONS,
                }
                for t in texts
            ]
        }
        data = self._post(model, "batchEmbedContents", body)
        try:
            vectors = [e["values"] for e in data["embeddings"]]
        except (KeyError, TypeError) as exc:
            raise LLMError("The AI service sent an unexpected embedding reply.") from exc
        if len(vectors) != len(texts) or any(
            len(v) != settings.EMBEDDING_DIMENSIONS for v in vectors
        ):
            raise LLMError("The embeddings have the wrong size.")
        return vectors

    def generate(self, system: str, prompt: str) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 700},
        }
        data = self._post(settings.GEMINI_MODEL, "generateContent", body)
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("The AI service sent no answer.") from exc
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise LLMError("The AI service sent an empty answer.")
        return text
