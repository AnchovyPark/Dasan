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
    "remember_preference": "선호를 기억해둘게요",
}
_DONE = {
    "list_dir": "경로를 확인했어요",
    "read_file": "내용을 파악했어요",
    "search": "검색을 마쳤어요",
    "write_file": "저장했어요",
    "remember_preference": "기억했어요",
}


def _target(name: str, inp: dict) -> str:
    """진행 문구에 곁들일 짧은 대상 표시(전체 경로/JSON 대신 파일명·검색어만)."""
    if not isinstance(inp, dict):
        return ""
    if name in ("read_file", "write_file", "list_dir"):
        p = inp.get("path")
        if p:
            return Path(str(p)).name or str(p)
    if name == "search":
        q = inp.get("query")
        if q:
            return f"'{q}'"
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
