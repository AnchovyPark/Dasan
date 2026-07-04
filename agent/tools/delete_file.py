"""delete_file — 파일 삭제. workspace 안 + '파일만'(폴더 삭제는 막아 사고 방지)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..workspace import Workspace
from .registry import Tool


class DeleteFileInput(BaseModel):
    path: str = Field(description="삭제할 파일 경로(작업 폴더 안)")


def make_delete_file_tool(ws: Workspace) -> Tool:
    def _run(inp: DeleteFileInput) -> str:
        p = ws.resolve(inp.path)  # workspace 밖이면 거부
        if not p.exists():
            raise FileNotFoundError(f"파일이 없습니다: {p}")
        if p.is_dir():
            raise IsADirectoryError("폴더는 삭제할 수 없습니다(파일만 가능).")
        p.unlink()
        return f"삭제: {p}"

    return Tool(
        name="delete_file",
        description="작업 폴더 안의 파일 하나를 삭제한다. 폴더는 삭제하지 않는다.",
        input_model=DeleteFileInput,
        run=_run,
    )
