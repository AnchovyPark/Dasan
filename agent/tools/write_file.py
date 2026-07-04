"""write_file — 텍스트 파일 생성/덮어쓰기. 에이전트가 실제로 결과물을 남길 수 있게 한다."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from .registry import Tool


class WriteFileInput(BaseModel):
    path: str = Field(description="쓸 파일 경로")
    content: str = Field(description="파일에 쓸 전체 내용")
    overwrite: bool = Field(
        default=False,
        description="파일이 이미 있을 때 덮어쓸지 여부. 기본 False(있으면 거부).",
    )


def _run(inp: WriteFileInput) -> str:
    p = Path(inp.path).expanduser()
    existed = p.exists()
    if existed:
        if p.is_dir():
            raise IsADirectoryError(f"디렉터리입니다: {p}")
        if not inp.overwrite:
            raise FileExistsError(f"이미 존재합니다(덮어쓰려면 overwrite=true): {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(inp.content, encoding="utf-8")
    return f"{'덮어씀' if existed else '생성'}: {p} ({len(inp.content)}자)"


write_file_tool = Tool(
    name="write_file",
    description=(
        "텍스트 파일을 생성하거나 덮어쓴다. 부모 폴더는 자동 생성. "
        "기존 파일을 바꾸려면 overwrite=true 를 명시해야 한다(실수 방지)."
    ),
    input_model=WriteFileInput,
    run=_run,
)
