"""list_dir — 디렉터리 내용 나열. 에이전트가 프로젝트 구조를 훑을 때 쓴다."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .registry import Tool

MAX_ENTRIES = 500


class ListDirInput(BaseModel):
    path: str = Field(default=".", description="목록을 볼 디렉터리 경로 (기본: 현재 폴더)")


def _run(inp: ListDirInput) -> str:
    p = Path(inp.path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"경로가 존재하지 않습니다: {p}")
    if not p.is_dir():
        raise NotADirectoryError(f"디렉터리가 아닙니다: {p}")

    entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    lines: list[str] = []
    for e in entries[:MAX_ENTRIES]:
        if e.is_dir():
            lines.append(f"{e.name}/")
        else:
            try:
                size = e.stat().st_size
            except OSError:
                size = 0
            lines.append(f"{e.name}\t{size}B")
    if len(entries) > MAX_ENTRIES:
        lines.append(f"... ({len(entries) - MAX_ENTRIES}개 더 생략)")

    header = f"{p}  ({len(entries)}개 항목)"
    body = "\n".join(lines) if lines else "(비어 있음)"
    return f"{header}\n{body}"


list_dir_tool = Tool(
    name="list_dir",
    description="디렉터리 안의 파일·하위폴더 목록을 반환한다(폴더는 이름 뒤 '/'). 프로젝트 구조 파악에 사용.",
    input_model=ListDirInput,
    run=_run,
)
