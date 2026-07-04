"""SQLite 기반 세션 저장/조회.

대화 아이템 목록을 세션 단위로 저장한다. 아이템 형태는 프로바이더마다
다르므로({"role","content"} 이거나 {"type":"function_call",...} 등)
role/content로 분해하지 않고 아이템을 통째로 JSON 직렬화해 저장한다.
저장은 단순하게 '해당 세션 아이템을 전부 지우고 다시 넣는' 방식.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SessionStore:
    def __init__(self, db_path: str) -> None:
        # "~/.dasan/sessions.db" 같은 홈 경로를 실제 경로로 풀고 폴더를 보장한다.
        # 그래야 실행 위치와 상관없이 항상 같은 DB를 참조/저장한다.
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                session_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                item TEXT NOT NULL,
                PRIMARY KEY (session_id, seq),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
            """
        )
        self._conn.commit()

    def create_session(self) -> str:
        sid = uuid.uuid4().hex[:12]
        self._conn.execute(
            "INSERT INTO sessions(id, created_at) VALUES (?, ?)",
            (sid, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return sid

    def ensure(self, sid: str) -> None:
        """주어진 id의 세션을 (없으면) 만들어 둔다. 단일 고정 세션용."""
        if self.exists(sid):
            return
        self._conn.execute(
            "INSERT INTO sessions(id, created_at) VALUES (?, ?)",
            (sid, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    def exists(self, sid: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM sessions WHERE id = ?", (sid,))
        return cur.fetchone() is not None

    def list_sessions(self) -> list[tuple[str, str]]:
        cur = self._conn.execute(
            "SELECT id, created_at FROM sessions ORDER BY created_at"
        )
        return [(r["id"], r["created_at"]) for r in cur.fetchall()]

    def load_messages(self, sid: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT item FROM messages WHERE session_id = ? ORDER BY seq",
            (sid,),
        )
        return [json.loads(r["item"]) for r in cur.fetchall()]

    def save_messages(self, sid: str, messages: list[dict]) -> None:
        with self._conn:  # 트랜잭션
            self._conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
            self._conn.executemany(
                "INSERT INTO messages(session_id, seq, item) VALUES (?, ?, ?)",
                [
                    (sid, i, json.dumps(m, ensure_ascii=False))
                    for i, m in enumerate(messages)
                ],
            )

    def close(self) -> None:
        self._conn.close()
