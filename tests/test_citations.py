from __future__ import annotations

from agent.citations import format_web_citations, strip_citation_tokens
from agent.discord_bot import _split


TOKEN = "\ue200cite\ue202turn1search0\ue202turn1search1\ue201"


def test_strips_opaque_token_without_annotations():
    assert format_web_citations(f"확인했어. {TOKEN}") == "확인했어."


def test_appends_readable_markdown_links():
    annotations = [
        {
            "type": "url_citation",
            "url": "https://example.com/a",
            "title": "Example A",
        },
        {
            "type": "url_citation",
            "url": "https://example.com/b",
            "title": "Example B",
        },
    ]
    result = format_web_citations(f"내용이야. {TOKEN}", annotations)
    assert TOKEN not in result
    assert "[Example A](<https://example.com/a>)" in result
    assert "[Example B](<https://example.com/b>)" in result


def test_supports_nested_annotation_and_deduplicates_urls():
    annotations = [
        {
            "type": "url_citation",
            "url_citation": {
                "url": "https://example.com/a",
                "title": "A [source]",
            },
        },
        {
            "type": "url_citation",
            "url": "https://example.com/a",
            "title": "duplicate",
        },
    ]
    result = format_web_citations("답변", annotations)
    assert result.count("https://example.com/a") == 1
    assert "[A \\[source\\]]" in result


def test_does_not_append_url_already_present_in_text():
    text = "공식 링크: https://example.com/a"
    annotations = [
        {
            "type": "url_citation",
            "url": "https://example.com/a",
            "title": "Example",
        }
    ]
    assert format_web_citations(text, annotations) == text


def test_discord_split_removes_leaked_citation_token():
    chunks = _split(f"Discord 답변이야. {TOKEN}")
    assert chunks == ["Discord 답변이야."]


def test_strip_handles_pasted_input_forms():
    # PUA 괄호가 살아 있는 원형 (cite 외 마커 포함)
    assert strip_citation_tokens(f"질문 {TOKEN} 끝") == "질문  끝"
    assert strip_citation_tokens("navlist뉴스 목록") == ""
    # 복사 과정에서 PUA 문자가 떨어져 나간 맨몸 형태
    assert (
        strip_citation_tokens("citeturn602486search0turn823810search1 남는 말")
        == " 남는 말"
    )
    # 짝이 깨진 잔여 특수 문자
    assert strip_citation_tokens("짝깨짐") == "짝깨짐"
