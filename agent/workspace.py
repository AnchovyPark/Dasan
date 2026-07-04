"""Workspace — 에이전트가 '변경/실행'할 수 있는 폴더를 한 곳으로 가둔다(가드레일 핵심).

모든 변경 계열 도구(write/edit/delete/move/run_command)는 여기 resolve()를 거쳐야
경로에 닿는다. '..'·심링크를 해소한 뒤 루트 밖이면 거부하므로 탈출을 막는다.
읽기 계열은 must_be_inside=False 로 통과시켜(제한 없음) 상대경로 기준만 workspace로 준다.

루트는 런타임에 바꿀 수 있고(여러 프로젝트 전환), 포인터 파일에 저장돼 재시작에도 유지된다.
"""
from __future__ import annotations

import os
from pathlib import Path


class Workspace:
    def __init__(self, root: str, pointer_file: str | None = None) -> None:
        self._root = Path(root).expanduser().resolve()
        self._pointer = Path(pointer_file).expanduser() if pointer_file else None

    @classmethod
    def load(cls, pointer_file: str, env_override: str | None = None) -> "Workspace":
        """env > 저장된 포인터 > 현재 폴더(cwd) 순으로 초기 루트를 정한다."""
        if env_override:
            root = env_override
        else:
            p = Path(pointer_file).expanduser()
            root = p.read_text(encoding="utf-8").strip() if p.exists() else os.getcwd()
        return cls(root, pointer_file)

    @property
    def root(self) -> Path:
        return self._root

    def set_root(self, root: str, persist: bool = True) -> Path:
        target = Path(root).expanduser().resolve()
        if not target.is_dir():
            raise NotADirectoryError(f"폴더가 아니에요: {target}")
        self._root = target
        if persist and self._pointer:
            self._pointer.parent.mkdir(parents=True, exist_ok=True)
            self._pointer.write_text(str(self._root), encoding="utf-8")
        return self._root

    def resolve(self, p: str, must_be_inside: bool = True) -> Path:
        """경로를 절대경로로 확정한다. 상대경로는 workspace 루트 기준.

        must_be_inside=True(변경 계열)면 루트 밖일 때 PermissionError.
        """
        pp = Path(p).expanduser()
        target = (pp if pp.is_absolute() else (self._root / pp)).resolve()
        if must_be_inside and not (target == self._root or target.is_relative_to(self._root)):
            raise PermissionError(
                f"workspace 밖은 변경할 수 없어요: {target}\n(workspace: {self._root})"
            )
        return target
