"""edit_file — 파일의 특정 텍스트만 안전하게 치환. write_file 전체 덮어쓰기보다 안전."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..workspace import Workspace
from .registry import Tool


class EditFileInput(BaseModel):
    path: str = Field(description="수정할 파일 경로(작업 폴더 안)")
    old: str = Field(description="바꿀 기존 텍스트(파일에 정확히 일치해야 함)")
    new: str = Field(description="대체할 새 텍스트")
    replace_all: bool = Field(
        default=False, description="여러 곳을 모두 바꿀지. 기본 False(유일하지 않으면 거부)."
    )


def make_edit_file_tool(ws: Workspace) -> Tool:
    def _run(inp: EditFileInput) -> str:
        p = ws.resolve(inp.path)  # workspace 밖이면 거부
        if not p.exists():
            raise FileNotFoundError(f"파일이 없습니다: {p}")
        if p.is_dir():
            raise IsADirectoryError(f"디렉터리입니다: {p}")
        text = p.read_text(encoding="utf-8")
        count = text.count(inp.old)
        if count == 0:
            raise ValueError("바꿀 기존 텍스트를 찾지 못했습니다. 정확히 일치하는지 확인하세요.")
        if count > 1 and not inp.replace_all:
            raise ValueError(
                f"기존 텍스트가 {count}곳에서 발견됐습니다. 더 구체적으로 지정하거나 replace_all=true 를 쓰세요."
            )
        new_text = (
            text.replace(inp.old, inp.new)
            if inp.replace_all
            else text.replace(inp.old, inp.new, 1)
        )
        p.write_text(new_text, encoding="utf-8")
        return f"수정: {p} ({count if inp.replace_all else 1}곳 치환)"

    return Tool(
        name="edit_file",
        description=(
            "파일에서 'old' 텍스트를 찾아 'new'로 치환한다(작업 폴더 안에서만). "
            "일부만 고칠 때 write_file보다 안전. old는 파일에 정확히 일치해야 하며, "
            "유일하지 않으면 replace_all=true 가 필요하다."
        ),
        input_model=EditFileInput,
        run=_run,
    )
