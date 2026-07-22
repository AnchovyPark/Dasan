"""웹 검색 citation을 일반 Markdown 링크로 바꾼다.

Responses API의 원문에는 ChatGPT UI만 해석하는 private-use citation 토큰이
들어올 수 있다. Discord·CLI에서는 그대로 노출되므로 토큰을 제거하고,
output_text.annotations의 URL을 읽을 수 있는 출처 목록으로 붙인다.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# 예: citeturn1search0turn1search1
# cite 외에 navlist 등 다른 마커도 같은 PUA 괄호(...)를 쓴다.
_PUA_BLOCK = re.compile(r"[^]*")
# 복사 과정에서 PUA 문자만 떨어져 나간 맨몸 형태:
# citeturn1search0turn2search1 / cite turn1search0 turn2search1
_INTERNAL_CITE = re.compile(
    r"\b(?:(?:cite|citation)\s*)?turn\d+[a-z]+\d+"
    r"(?:\s*turn\d+[a-z]+\d+)*",
    re.IGNORECASE,
)
# 짝이 깨진 채 남은 특수 문자 잔여물
_PUA_STRAY = re.compile(r"[-]")


def strip_citation_tokens(text: str) -> str:
    """ChatGPT 전용 citation/특수 토큰을 모두 제거한다.

    모델 출력뿐 아니라 사용자가 이런 토큰을 복사·붙여넣기한 입력에도 쓴다 —
    특수 토큰이 입력에 섞이면 백엔드가 턴 중간에 실패할 수 있다.
    """
    cleaned = _PUA_BLOCK.sub("", text or "")
    # 닫는 괄호가 빠진 citation은 PUA 제거 뒤에야 citeturn... 형태가 된다.
    cleaned = _PUA_STRAY.sub("", cleaned)
    return _INTERNAL_CITE.sub("", cleaned)


def sanitize_message_item(item: dict) -> dict:
    """Responses message의 text 필드에서 내부 citation만 제거한 복사본을 만든다."""
    if item.get("type") != "message":
        return item

    changed = False
    content: list = []
    for part in item.get("content", []):
        if not isinstance(part, dict) or not isinstance(part.get("text"), str):
            content.append(part)
            continue
        cleaned = strip_citation_tokens(part["text"])
        if cleaned != part["text"]:
            changed = True
            content.append({**part, "text": cleaned})
        else:
            content.append(part)
    return {**item, "content": content} if changed else item


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
    cleaned = strip_citation_tokens(text)
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
