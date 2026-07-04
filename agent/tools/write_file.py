"""write_file — 텍스트 파일 생성/덮어쓰기. workspace 안으로 제한(가드)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..workspace import Workspace
from .registry import Tool


class WriteFileInput(BaseModel):
    path: str = Field(description="쓸 파일 경로(작업 폴더 안)")
    content: str = Field(description="파일에 쓸 전체 내용")
    overwrite: bool = Field(
        default=False,
        description="파일이 이미 있을 때 덮어쓸지 여부. 기본 False(있으면 거부).",
    )


def make_write_file_tool(ws: Workspace) -> Tool:
    def _run(inp: WriteFileInput) -> str:
        p = ws.resolve(inp.path)  # workspace 밖이면 여기서 거부
        existed = p.exists()
        if existed:
            if p.is_dir():
                raise IsADirectoryError(f"디렉터리입니다: {p}")
            if not inp.overwrite:
                raise FileExistsError(f"이미 존재합니다(덮어쓰려면 overwrite=true): {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(inp.content, encoding="utf-8")
        return f"{'덮어씀' if existed else '생성'}: {p} ({len(inp.content)}자)"

    return Tool(
        name="write_file",
        description=(
            "텍스트 파일을 생성하거나 덮어쓴다(작업 폴더 안에서만). 부모 폴더는 자동 생성. "
            "기존 파일 전체를 바꿀 때만 쓰고, 일부만 고칠 땐 edit_file 을 우선 사용. "
            "덮어쓰려면 overwrite=true."
        ),
        input_model=WriteFileInput,
        run=_run,
    )
