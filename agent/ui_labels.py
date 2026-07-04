"""도구 이벤트를 사용자 친화적인 진행 문구로 바꾼다.

표면(TUI/CLI)이 원시 로그(● read_file({...}) + 파일 내용 preview) 대신
"파일을 읽어볼게요 → 내용을 파악했어요" 같은 짧은 상태만 보여주게 하는 도우미.
원시 로그는 AGENT_DEBUG 일 때만 노출한다.
"""
from __future__ import annotations

from pathlib import Path

_DOING = {
    "list_dir": "경로를 확인해볼게요",
    "read_file": "파일을 읽어볼게요",
    "search": "관련 내용을 찾아볼게요",
    "write_file": "파일을 저장할게요",
    "edit_file": "파일을 수정할게요",
    "delete_file": "파일을 삭제할게요",
    "move_file": "파일을 옮길게요",
    "run_command": "명령을 실행할게요",
    "remember_preference": "선호를 기억해둘게요",
}
_DONE = {
    "list_dir": "경로를 확인했어요",
    "read_file": "내용을 파악했어요",
    "search": "검색을 마쳤어요",
    "write_file": "저장했어요",
    "edit_file": "수정했어요",
    "delete_file": "삭제했어요",
    "move_file": "옮겼어요",
    "run_command": "실행했어요",
    "remember_preference": "기억했어요",
}


def _target(name: str, inp: dict) -> str:
    """진행 문구에 곁들일 짧은 대상 표시(전체 경로/JSON 대신 파일명·명령만)."""
    if not isinstance(inp, dict):
        return ""
    if name in ("read_file", "write_file", "list_dir", "edit_file", "delete_file"):
        p = inp.get("path")
        if p:
            return Path(str(p)).name or str(p)
    if name == "move_file":
        s = inp.get("src")
        if s:
            return Path(str(s)).name or str(s)
    if name == "search":
        q = inp.get("query")
        if q:
            return f"'{q}'"
    if name == "run_command":
        c = inp.get("command")
        if c:
            return str(c)[:40]
    return ""


def doing(name: str, inp: dict) -> str:
    """도구 실행 시작 시 보여줄 문구."""
    base = _DOING.get(name, f"{name} 실행할게요")
    target = _target(name, inp)
    return f"{base} ({target})" if target else base


def done(name: str, is_error: bool) -> str:
    """도구 실행 완료 시 보여줄 문구(성공만; 실패는 표면이 실제 오류를 보여줌)."""
    if is_error:
        return "문제가 생겼어요"
    return _DONE.get(name, "완료했어요")
