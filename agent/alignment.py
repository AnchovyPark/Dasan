"""ALIGNMENT 저장소 — 사용자의 지속적 선호를 파일 한 곳에 누적한다.

세션 개념과 무관한 '이 사용자'의 전역 규칙이므로 세션 DB가 아니라
~/.dasan/alignment.md 같은 단일 파일에 마크다운 불릿으로 쌓는다.
"""
from __future__ import annotations

import os
from pathlib import Path


def _atomic_write(path: Path, text: str) -> None:
    """임시 파일에 전부 쓴 뒤 교체한다. 쓰는 도중 실패해도 기존 파일이 보존된다."""
    # 파이프 입력 등에서 섞여 들어온 인코딩 불가 문자(서러게이트)는 버린다
    text = text.encode("utf-8", errors="ignore").decode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class AlignmentStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path).expanduser()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> str:
        """현재까지 누적된 정렬 텍스트. 없으면 빈 문자열."""
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8").strip()

    def write(self, text: str) -> None:
        """정렬 파일을 통째로 덮어쓴다(초기 설정 onboarding에서 사용)."""
        _atomic_write(self._path, text.rstrip() + "\n")

    def add(self, note: str) -> None:
        """지속적 선호 한 줄을 불릿으로 추가한다(완전 중복은 무시)."""
        note = " ".join(note.split()).strip()
        if not note:
            return
        lines = [ln for ln in self.load().splitlines() if ln.strip()]
        bullet = f"- {note}"
        if bullet in lines:
            return
        lines.append(bullet)
        _atomic_write(self._path, "\n".join(lines) + "\n")
