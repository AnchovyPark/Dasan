"""run_command — 작업 폴더에서 쉘 명령 실행.

쉘은 완벽히 샌드박싱할 수 없으므로(명령이 밖으로 빠져나갈 수 있음) 가드는 두 겹:
1) cwd 를 workspace 로 고정.
2) 극도로 위험한 패턴(rm -rf, format, dd, Remove-Item -Recurse 등)은 approve()로
   사용자 승인을 받는다. 승인 함수는 표면이 주입한다(TUI=대화형 확인, 비대화형=거부).
"""
from __future__ import annotations

import re
import subprocess
from typing import Callable

from pydantic import BaseModel, Field

from ..workspace import Workspace
from .registry import Tool

MAX_OUTPUT = 20_000

# 승인 없이는 실행하지 않는 '극도로 위험한' 패턴
DANGER = [
    r"\brm\s+-[a-z]*[rf]",          # rm -rf, rm -fr, rm -r ...
    r"\brmdir\b",
    r"\bdel\b.*[/\\]",              # del /s, del \path
    r"\bRemove-Item\b.*-Recurse",   # PowerShell 재귀 삭제
    r"\bRemove-Item\b.*-Force",
    r"\bformat\b",
    r"\bmkfs",
    r"\bdd\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bsudo\b",
    r"\bchmod\s+-R\b",
    r"\bgit\s+clean\s+-[a-z]*d[a-z]*f|-[a-z]*f[a-z]*d",  # git clean -fd
    r":\s*\(\s*\)\s*\{",            # fork bomb
    r">\s*/dev/sd",
]


def is_dangerous(cmd: str) -> bool:
    return any(re.search(p, cmd, re.IGNORECASE) for p in DANGER)


class RunCommandInput(BaseModel):
    command: str = Field(description="작업 폴더에서 실행할 쉘 명령")
    timeout: int = Field(default=120, description="타임아웃(초). 기본 120.")


def make_run_command_tool(ws: Workspace, approve: Callable[[str], bool]) -> Tool:
    def _run(inp: RunCommandInput) -> str:
        cmd = inp.command
        if is_dangerous(cmd) and not approve(cmd):
            raise PermissionError(f"위험한 명령이라 사용자가 실행을 거부했습니다: {cmd}")
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(ws.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=inp.timeout,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        if len(out) > MAX_OUTPUT:
            out = out[:MAX_OUTPUT] + "\n... (출력이 잘렸습니다)"
        return f"[exit {proc.returncode}]\n{out}" if out else f"[exit {proc.returncode}] (출력 없음)"

    return Tool(
        name="run_command",
        description=(
            "작업 폴더(workspace)에서 쉘 명령을 실행하고 exit code와 출력을 반환한다. "
            "테스트 실행(pytest), git 확인(git status/diff), 빌드 등에 사용. "
            "삭제·포맷 같은 극도로 위험한 명령은 사용자 승인이 필요하다."
        ),
        input_model=RunCommandInput,
        run=_run,
    )
