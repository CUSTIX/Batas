import pytest

from laws import services as law_services
from qa import services
from qa.llm import LLMError


@pytest.mark.django_db
def test_without_ai_the_answer_is_the_law_text():
    result = services.answer("How many days of service incentive leave?")
    assert result.mode == "passages" and result.retrieval == "keywords"
    assert result.sources[0].label == "Art. 95"
    assert "five days with pay" in result.sources[0].quote
    assert result.sources[0].article_url == "/laws/labor-code/95/"


@pytest.mark.django_db
def test_ai_answer_keeps_real_citations(fake_gemini):
    fake = fake_gemini(answer="You get five days of paid leave a year [Art. 95].")
    result = services.answer("How many days of service incentive leave?", client=fake)
    assert result.mode == "ai"
    assert [s.cite for s in result.segments if s.cite] == ["Art. 95"]
    assert result.notice == ""
    prompt = fake.calls[0][1]
    assert "[Art. 95]" in prompt and "Question: How many days" in prompt


@pytest.mark.django_db
def test_made_up_citations_are_removed(fake_gemini):
    fake = fake_gemini(answer="Five days [Art. 95]. Also see [Art. 999].")
    result = services.answer("service incentive leave", client=fake)
    assert [s.cite for s in result.segments if s.cite] == ["Art. 95"]
    assert "Removed 1 citation" in result.notice


@pytest.mark.django_db
def test_answer_without_any_real_citation_is_not_shown(fake_gemini):
    fake = fake_gemini(answer="You get fifteen days off, trust me [Art. 999].")
    result = services.answer("service incentive leave", client=fake)
    assert result.mode == "passages" and not result.segments
    assert "no checkable citation" in result.notice


@pytest.mark.django_db
def test_not_covered_falls_back_to_passages(fake_gemini):
    result = services.answer("service incentive leave", client=fake_gemini(answer="NOT_COVERED"))
    assert result.mode == "passages" and "no direct answer" in result.notice


@pytest.mark.django_db
def test_ai_failure_falls_back_to_passages(fake_gemini):
    result = services.answer("overtime pay", client=fake_gemini(error=LLMError("quota")))
    assert result.mode == "passages" and "unavailable" in result.notice
    assert result.sources


@pytest.mark.django_db
def test_hybrid_retrieval_when_embeddings_exist(fake_gemini):
    fake = fake_gemini(answer="Five days [Art. 95].")
    law_services.embed_missing(fake.embed, batch_size=200)
    result = services.answer("paid leave every year", client=fake)
    assert result.retrieval == "hybrid"
    assert ("embed", "RETRIEVAL_QUERY", 1) in fake.calls


@pytest.mark.django_db
def test_no_match_says_so():
    result = services.answer("xqzzv blorft")
    assert result.mode == "none" and not result.sources and "Nothing" in result.notice


@pytest.mark.django_db
def test_long_questions_are_trimmed(settings):
    result = services.answer("overtime " * 200)
    assert len(result.question) <= settings.QUESTION_MAX_LENGTH


def test_segment_splits_text_and_citations():
    segments, kept, dropped = services.segment(
        "A [Art. 95] b [PD 851 Sec. 1] c [Art. 1]", {"Art. 95", "PD 851 Sec. 1"}
    )
    assert (kept, dropped) == (2, 1)
    assert [s.cite for s in segments if s.cite] == ["Art. 95", "PD 851 Sec. 1"]
    assert segments[1].anchor == "src-art-95"


@pytest.mark.django_db
def test_short_articles_are_quoted_whole_with_their_exceptions():
    card = services.answer("service incentive leave").sources[0]
    assert card.label == "Art. 95"
    assert "less than ten employees" in card.quote, "clause (b), the exception, must be shown"


@pytest.mark.django_db
def test_weak_keyword_matches_are_left_out():
    result = services.answer("Ilang araw ang service incentive leave?")
    labels = [c.label for c in result.sources]
    assert labels[0] == "Art. 95"
    # Retirement (287) and maternity (294, 133) only share words like "leave": dropped. Art. 134
    # ("Family Planning Services; Incentives") is a borderline match and may stay.
    assert not {"Art. 287", "Art. 294", "Art. 133"} & set(labels)
    assert len(labels) <= 2


def test_republic_act_citations_are_recognized():
    segments, kept, dropped = services.segment(
        "105 days [RA 11210 Sec. 5]; 7 days [RA 8187 Sec. 2].",
        {"RA 11210 Sec. 5", "RA 8187 Sec. 2"},
    )
    assert (kept, dropped) == (2, 0)


@pytest.mark.django_db
def test_maternity_question_finds_the_expanded_law():
    labels = [c.label for c in services.answer("How many days of maternity leave?").sources]
    assert any(label.startswith("RA 11210") for label in labels), labels
