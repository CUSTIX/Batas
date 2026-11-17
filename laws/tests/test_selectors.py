import pytest

from laws import selectors, services


def labels(hits):
    out = []
    for h in hits:
        if h.passage.article.label not in out:
            out.append(h.passage.article.label)
    return out


def test_expand_maps_filipino_and_plain_words():
    assert "wage deduction" in selectors.expand("Pwede bang kaltasan ang sahod ko?")
    assert "termination" in selectors.expand("I was fired")
    assert "thirteenth month pay" in selectors.expand("13th month")


def test_parse_tsvector_weights_heading_terms():
    tf = selectors._parse_tsvector("'leav':3A,9 'servic':1A 'year':12")
    assert tf == {"leav": 3.0 + 0.4, "servic": 3.0, "year": 0.4}


@pytest.mark.django_db
def test_keyword_search_finds_the_right_article():
    assert labels(selectors.keyword_search("service incentive leave", 6))[0] == "Art. 95"


@pytest.mark.django_db
def test_keyword_search_handles_filipino():
    assert (
        "Art. 113" in labels(selectors.keyword_search("Pwede bang kaltasan ang sahod ko?", 10))[:3]
    )


@pytest.mark.django_db
def test_rare_words_outrank_common_ones():
    """BM25: 'probationary' is rare, 'employee' is everywhere; the rare word must decide."""
    assert labels(selectors.keyword_search("employee probationary period", 6))[0] == "Art. 281"


@pytest.mark.django_db
def test_nonsense_and_stopwords_return_nothing():
    assert selectors.keyword_search("the and of", 5) == []
    assert selectors.keyword_search("xqzzv", 5) == []


@pytest.mark.django_db
def test_vector_search_and_fusion(fake_gemini):
    fake = fake_gemini()
    services.embed_missing(fake.embed, batch_size=200)
    assert selectors.has_embeddings()
    query = fake.vector("Right to service incentive leave yearly service incentive leave")
    vector_hits = selectors.vector_search(query, 5)
    assert vector_hits and vector_hits[0].found_by == ["meaning"]
    keyword_hits = selectors.keyword_search("service incentive leave", 5)
    fused = selectors.fuse(keyword_hits, vector_hits, k=5)
    assert labels(fused)[0] == "Art. 95"
    assert set(fused[0].found_by) == {"keywords", "meaning"}


def test_fuse_rewards_agreement():
    class P:
        def __init__(self, i):
            self.id = i

    a = [selectors.Hit(P(1), 0, ["keywords"]), selectors.Hit(P(2), 0, ["keywords"])]
    b = [selectors.Hit(P(2), 0, ["meaning"]), selectors.Hit(P(3), 0, ["meaning"])]
    fused = selectors.fuse(a, b, k=3)
    assert [h.passage.id for h in fused][0] == 2, "found by both lists ranks first"
