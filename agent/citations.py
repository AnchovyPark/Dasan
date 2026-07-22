"""웹 검색 citation을 일반 Markdown 링크로 바꾼다.

Responses API의 원문에는 ChatGPT UI만 해석하는 private-use citation 토큰이
들어올 수 있다. Discord·CLI에서는 그대로 노출되므로 토큰을 제거하고,
output_text.annotations의 URL을 읽을 수 있는 출처 목록으로 붙인다.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# 예: \ue200cite\ue202turn1search0\ue202turn1search1\ue201
_CITATION_TOKEN = re.compile(r"\ue200cite\ue202.*?\ue201")


def _annotation_fields(annotation: dict) -> tuple[str, str] | None:
    """Responses API의 URL citation annotation에서 (url, title)을 꺼낸다."""
    if annotation.get("type") != "url_citation":
        return None

    # 백엔드 버전에 따라 필드가 직접 있거나 url_citation 안에 중첩될 수 있다.
    payload = annotation.get("url_citation")
    if not isinstance(payload, dict):
        payload = annotation

    url = str(payload.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    title = str(payload.get("title") or "").strip()
    if not title:
        title = urlparse(url).netloc or "출처"
    return url, title


def _escape_title(title: str) -> str:
    """Markdown 링크 라벨을 깨뜨리는 최소 문자를 이스케이프한다."""
    return title.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def format_web_citations(text: str, annotations: list[dict] | None = None) -> str:
    """불투명 citation 토큰을 제거하고 고유 URL을 Markdown 출처로 덧붙인다."""
    cleaned = _CITATION_TOKEN.sub("", text or "")
    # 토큰 제거 뒤 생길 수 있는 문장 끝 공백만 정리한다.
    cleaned = re.sub(r"[ \t]+(?=\n|$)", "", cleaned).strip()

    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for annotation in annotations or []:
        fields = _annotation_fields(annotation)
        if fields is None:
            continue
        url, title = fields
        if url in seen or url in cleaned:
            continue
        seen.add(url)
        links.append((url, title))

    if not links:
        return cleaned

    rendered = "\n".join(
        f"- [{_escape_title(title)}](<{url}>)" for url, title in links
    )
    return f"{cleaned}\n\n출처:\n{rendered}" if cleaned else f"출처:\n{rendered}"
