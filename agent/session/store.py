"""SQLite 기반 세션 저장/조회 — 세션 하나당 파일 하나.

~/.dasan/sessions/<이름>.db 처럼 세션 이름별로 sqlite 파일을 만든다.
아이템 형태는 프로바이더마다 다르므로({"role","content"} 이거나
{"type":"function_call",...} 등) role/content로 분해하지 않고 아이템을
통째로 JSON 직렬화해 저장한다. 저장은 '전부 지우고 다시 넣는' 방식.

과거 단일 파일(~/.dasan/sessions.db) 형식을 발견하면 세션별 파일로
옮기고 원본은 .bak 으로 남긴다.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Windows 파일명에 쓸 수 없는 문자들
_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    seq INTEGER PRIMARY KEY,
    item TEXT NOT NULL
);
"""


def safe_name(name: str) -> str:
    """세션 이름을 파일명으로 쓸 수 있게 다듬는다. 못 쓰면 ValueError."""
    cleaned = _INVALID.sub("-", name).strip().strip(".")
    if not cleaned:
        raise ValueError(f"세션 이름으로 쓸 수 없습니다: {name!r}")
    return cleaned


class SessionStore:
    def __init__(self, dir_path: str, legacy_db: str | None = None) -> None:
        self._dir = Path(dir_path).expanduser()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._conns: dict[str, sqlite3.Connection] = {}
        if legacy_db:
            self._migrate_legacy(Path(legacy_db).expanduser())

    # --- 내부 ---

    def _path(self, name: str) -> Path:
        return self._dir / f"{name}.db"

    def _conn(self, name: str) -> sqlite3.Connection:
        if name not in self._conns:
            conn = sqlite3.connect(str(self._path(name)))
            conn.row_factory = sqlite3.Row
            conn.executescript(_SCHEMA)
            conn.commit()
            self._conns[name] = conn
        return self._conns[name]

    def _migrate_legacy(self, legacy: Path) -> None:
        """옛 단일 DB(sessions.db)의 세션들을 세션별 파일로 옮긴다."""
        if not legacy.exists():
            return
        try:
            old = sqlite3.connect(str(legacy))
            old.row_factory = sqlite3.Row
            sessions = old.execute("SELECT id, created_at FROM sessions").fetchall()
            for row in sessions:
                name = safe_name(row["id"])
                if self._path(name).exists():
                    continue
                items = [
                    r["item"]
                    for r in old.execute(
                        "SELECT item FROM messages WHERE session_id = ? ORDER BY seq",
                        (row["id"],),
                    )
                ]
                conn = self._conn(name)
                with conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO meta(key, value) VALUES ('created_at', ?)",
                        (row["created_at"],),
                    )
                    conn.executemany(
                        "INSERT INTO messages(seq, item) VALUES (?, ?)",
                        list(enumerate(items)),
                    )
            old.close()
            legacy.rename(legacy.with_name(legacy.name + ".bak"))
        except sqlite3.Error:
            pass  # 형식이 다르거나 손상됐으면 건드리지 않는다

    # --- 공개 API (name = 세션 제목이자 파일명) ---

    def create_session(self, name: str) -> str:
        """세션 파일을 만들고 실제(정리된) 이름을 반환한다."""
        name = safe_name(name)
        conn = self._conn(name)
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('created_at', ?)",
            (datetime.now(timezone.utc).isoformat(),),
        )
        conn.commit()
        return name

    def exists(self, name: str) -> bool:
        try:
            return self._path(safe_name(name)).exists()
        except ValueError:
            return False

    def list_sessions(self) -> list[tuple[str, str, int]]:
        """(이름, 생성일, 메시지 수) 목록을 생성일 순으로 반환."""
        out = []
        for f in self._dir.glob("*.db"):
            conn = self._conn(f.stem)
            row = conn.execute("SELECT value FROM meta WHERE key = 'created_at'").fetchone()
            created = row["value"] if row else ""
            count = conn.execute("SELECT COUNT(*) AS n FROM messages").fetchone()["n"]
            out.append((f.stem, created, count))
        out.sort(key=lambda t: t[1])
        return out

    def load_messages(self, name: str) -> list[dict]:
        cur = self._conn(safe_name(name)).execute(
            "SELECT item FROM messages ORDER BY seq"
        )
        return [json.loads(r["item"]) for r in cur.fetchall()]

    def get_compaction(self, name: str) -> tuple[int, str]:
        """(compacted_until 커서, digest 텍스트). 없으면 (0, '')."""
        conn = self._conn(safe_name(name))
        rows = dict(
            conn.execute(
                "SELECT key, value FROM meta WHERE key IN ('compacted_until', 'digest')"
            ).fetchall()
        )
        return int(rows.get("compacted_until", 0)), rows.get("digest", "") or ""

    def set_compaction(self, name: str, until: int, digest: str) -> None:
        conn = self._conn(safe_name(name))
        with conn:
            conn.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                [("compacted_until", str(until)), ("digest", digest)],
            )

    def save_messages(self, name: str, messages: list[dict]) -> None:
        conn = self._conn(safe_name(name))
        with conn:  # 트랜잭션
            conn.execute("DELETE FROM messages")
            conn.executemany(
                "INSERT INTO messages(seq, item) VALUES (?, ?)",
                [
                    (i, json.dumps(m, ensure_ascii=False))
                    for i, m in enumerate(messages)
                ],
            )

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()
