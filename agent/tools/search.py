"""search — 파일 내용을 정규식으로 검색(grep 유사). 코드에서 무언가 찾을 때의 핵심 도구."""
from __future__ import annotations

import os
import re
from fnmatch import fnmatch
from pathlib import Path

from pydantic import BaseModel, Field

from .registry import Tool

# 검색에서 통째로 건너뛸 디렉터리(잡음/대용량 방지)
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".idea", ".dasan",
}
MAX_FILE_BYTES = 1_000_000  # 이보다 큰 파일은 스킵


class SearchInput(BaseModel):
    query: str = Field(description="찾을 정규식 또는 문자열")
    path: str = Field(default=".", description="검색 시작 경로 (파일 또는 디렉터리, 기본: 현재 폴더)")
    glob: str | None = Field(default=None, description="파일명 필터. 예: '*.py'. 없으면 모든 텍스트 파일")
    max_results: int = Field(default=100, description="반환할 최대 매칭 줄 수")


def _iter_files(root: Path):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        # 하위 탐색에서 잡음 폴더 가지치기
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for fn in filenames:
            yield Path(dirpath) / fn


def _run(inp: SearchInput) -> str:
    root = Path(inp.path).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"경로가 존재하지 않습니다: {root}")
    try:
        rx = re.compile(inp.query)
    except re.error as e:
        raise ValueError(f"정규식이 올바르지 않습니다: {e}")

    out: list[str] = []
    for f in _iter_files(root):
        if inp.glob and not fnmatch(f.name, inp.glob):
            continue
        try:
            if f.stat().st_size > MAX_FILE_BYTES:
                continue
            data = f.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:1024]:  # 바이너리로 추정 → 스킵
            continue
        text = data.decode("utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if rx.search(line):
                out.append(f"{f}:{i}: {line.strip()[:200]}")
                if len(out) >= inp.max_results:
                    out.append(f"... (max_results {inp.max_results} 도달 — 더 있을 수 있음)")
                    return "\n".join(out)
    return "\n".join(out) if out else "일치하는 내용이 없습니다."


search_tool = Tool(
    name="search",
    description=(
        "파일들의 내용을 정규식으로 검색해 'path:줄번호: 내용' 형식으로 반환한다(grep 유사). "
        "코드/텍스트에서 특정 문자열·패턴이 어디 있는지 찾을 때 사용."
    ),
    input_model=SearchInput,
    run=_run,
)
