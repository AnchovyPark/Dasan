"""ALIGNMENT 저장소 — 사용자의 지속적 선호를 파일 한 곳에 누적한다.

세션 개념과 무관한 '이 사용자'의 전역 규칙이므로 세션 DB가 아니라
~/.dasan/alignment.md 같은 단일 파일에 마크다운 불릿으로 쌓는다.
"""
from __future__ import annotations

from pathlib import Path


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
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(text.rstrip() + "\n", encoding="utf-8")

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
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
