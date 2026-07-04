"""move_file — 파일/폴더 이동·이름변경. 원본·대상 모두 workspace 안이어야 함."""
from __future__ import annotations

import shutil

from pydantic import BaseModel, Field

from ..workspace import Workspace
from .registry import Tool


class MoveFileInput(BaseModel):
    src: str = Field(description="원본 경로(작업 폴더 안)")
    dst: str = Field(description="대상 경로(작업 폴더 안)")
    overwrite: bool = Field(default=False, description="대상이 이미 있을 때 덮어쓸지. 기본 False.")


def make_move_file_tool(ws: Workspace) -> Tool:
    def _run(inp: MoveFileInput) -> str:
        s = ws.resolve(inp.src)  # 둘 다 workspace 밖이면 거부
        d = ws.resolve(inp.dst)
        if not s.exists():
            raise FileNotFoundError(f"원본이 없습니다: {s}")
        if d.exists() and not inp.overwrite:
            raise FileExistsError(f"대상이 이미 있습니다(덮어쓰려면 overwrite=true): {d}")
        d.parent.mkdir(parents=True, exist_ok=True)
        if d.exists() and inp.overwrite:
            if d.is_dir():
                raise IsADirectoryError(f"대상이 디렉터리라 덮어쓸 수 없습니다: {d}")
            d.unlink()
        shutil.move(str(s), str(d))
        return f"이동: {s} → {d}"

    return Tool(
        name="move_file",
        description="작업 폴더 안에서 파일/폴더를 이동하거나 이름을 바꾼다. 원본과 대상 모두 작업 폴더 안이어야 한다.",
        input_model=MoveFileInput,
        run=_run,
    )
