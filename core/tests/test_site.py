import re
from pathlib import Path

import pytest
from django.conf import settings


@pytest.mark.django_db
def test_livez_needs_no_database(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        response = client.get("/livez/")
    assert response.status_code == 200 and response.content == b"ok"
    assert "no-cache" in response["Cache-Control"]


@pytest.mark.django_db
def test_healthz_checks_the_database(client):
    assert client.get("/healthz/").status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("url", ["/", "/about/", "/laws/", "/laws/labor-code/95/"])
def test_pages_send_security_headers(client, url):
    response = client.get(url)
    assert response.status_code == 200
    csp = response["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp
    assert "frame-ancestors 'none'" in csp
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "camera=()" in response["Permissions-Policy"]


@pytest.mark.django_db
def test_unknown_page_is_404(client):
    assert client.get("/nope/").status_code == 404


def test_templates_have_no_inline_javascript_or_styles():
    """The CSP blocks inline script and style; this keeps templates from silently breaking."""
    root = Path(settings.BASE_DIR)
    for template in root.glob("*/templates/**/*.html"):
        html = template.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), template
        assert not re.search(r"\son[a-z]+=", html), template
        assert "style=" not in html, template
        assert "javascript:" not in html, template


def test_every_env_var_is_documented():
    root = Path(settings.BASE_DIR)
    used = set(
        re.findall(r'environ(?:\.get)?\(\s*"([A-Z_]+)"', (root / "config/settings.py").read_text())
    )
    used.update(
        re.findall(r'env_(?:bool|list)\("([A-Z_]+)"', (root / "config/settings.py").read_text())
    )
    documented = (root / ".env.example").read_text()
    missing = sorted(v for v in used if v not in documented and v != "RENDER_EXTERNAL_HOSTNAME")
    assert not missing, f"Document these in .env.example: {missing}"
