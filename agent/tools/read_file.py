"""read_file — 로컬 텍스트 파일 읽기. 읽기는 제한하지 않되 상대경로는 workspace 기준."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..workspace import Workspace
from .registry import Tool

MAX_BYTES = 200_000  # 과도하게 큰 파일은 컨텍스트 보호를 위해 거부


class ReadFileInput(BaseModel):
    path: str = Field(description="읽을 로컬 텍스트 파일의 경로")


def make_read_file_tool(ws: Workspace) -> Tool:
    def _run(inp: ReadFileInput) -> str:
        p = ws.resolve(inp.path, must_be_inside=False)
        if not p.exists():
            raise FileNotFoundError(f"경로가 존재하지 않습니다: {p}")
        if p.is_dir():
            raise IsADirectoryError(f"파일이 아니라 디렉터리입니다: {p}")
        data = p.read_bytes()
        if len(data) > MAX_BYTES:
            raise ValueError(f"파일이 너무 큽니다 ({len(data)} bytes > {MAX_BYTES})")
        return data.decode("utf-8", errors="replace")

    return Tool(
        name="read_file",
        description="로컬 텍스트 파일을 읽어 그 내용을 문자열로 반환한다.",
        input_model=ReadFileInput,
        run=_run,
    )
