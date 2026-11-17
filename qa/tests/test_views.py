import pytest


@pytest.mark.django_db
def test_home_shows_examples(client):
    html = client.get("/").content.decode()
    assert "Ask the Labor Code." in html and "?q=" in html


@pytest.mark.django_db
def test_question_shows_answer_and_sources(client):
    response = client.get("/", {"q": "How long is probationary employment?"})
    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="src-art-281"' in html and "Probationary employment" in html
    assert "/laws/labor-code/281/" in html


@pytest.mark.django_db
def test_question_text_is_escaped(client):
    html = client.get("/", {"q": "<script>alert(1)</script> overtime"}).content.decode()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


@pytest.mark.django_db
def test_too_short_question_is_refused(client):
    html = client.get("/", {"q": "a"}).content.decode()
    assert 'role="alert"' in html and "Most relevant articles" not in html


@pytest.mark.django_db
def test_questions_are_rate_limited_per_visitor(client, settings):
    settings.QUESTIONS_PER_HOUR = 2
    assert client.get("/", {"q": "overtime"}).status_code == 200
    assert client.get("/", {"q": "overtime"}).status_code == 200
    response = client.get("/", {"q": "overtime"})
    assert response.status_code == 429 and "a lot of questions" in response.content.decode()


@pytest.mark.django_db
def test_post_is_not_allowed(client):
    assert client.post("/", {"q": "overtime"}).status_code == 405


@pytest.mark.django_db
def test_article_page_and_browse(client):
    article = client.get("/laws/labor-code/95/")
    assert article.status_code == 200 and "five days with pay" in article.content.decode()
    assert client.get("/laws/labor-code/9999/").status_code == 404
    index = client.get("/laws/").content.decode()
    assert "Labor Code of the Philippines" in index and "/laws/pd-851/1/" in index


@pytest.mark.django_db
def test_about_explains_rag(client):
    assert "retrieval-augmented generation" in client.get("/about/").content.decode()
