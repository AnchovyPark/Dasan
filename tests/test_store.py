"""SessionStore 테스트(세션별 파일·마이그레이션·컴팩션 메타). 실행: python tests/test_store.py"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.session.store import SessionStore, safe_name


def test_migration_and_crud():
    tmp = Path(tempfile.mkdtemp())
    legacy = tmp / "sessions.db"

    # 옛 단일 파일 형식 만들기
    conn = sqlite3.connect(legacy)
    conn.executescript(
        """
        CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
        CREATE TABLE messages (session_id TEXT, seq INTEGER, item TEXT,
                               PRIMARY KEY (session_id, seq));
        """
    )
    conn.execute("INSERT INTO sessions VALUES ('main', '2026-01-01T00:00:00+00:00')")
    for i in range(3):
        conn.execute(
            "INSERT INTO messages VALUES ('main', ?, ?)",
            (i, json.dumps({"role": "user", "content": f"msg{i}"})),
        )
    conn.commit()
    conn.close()

    store = SessionStore(str(tmp / "sessions"), legacy_db=str(legacy))
    assert not legacy.exists() and (tmp / "sessions.db.bak").exists()
    assert store.exists("main")
    assert len(store.load_messages("main")) == 3

    # 생성/저장/목록
    name = store.create_session("내 프로젝트: 테스트?")
    store.save_messages(name, [{"role": "user", "content": "안녕"}])
    assert store.load_messages(name)[0]["content"] == "안녕"
    sessions = store.list_sessions()
    assert len(sessions) == 2 and all(len(t) == 3 for t in sessions)

    # 컴팩션 메타
    assert store.get_compaction(name) == (0, "")
    store.set_compaction(name, 7, "- 기억")
    assert store.get_compaction(name) == (7, "- 기억")
    store.set_compaction(name, 9, "- 갱신")  # upsert
    assert store.get_compaction(name) == (9, "- 갱신")

    # 비우기(세션은 유지)
    store.save_messages(name, [])
    assert store.load_messages(name) == [] and store.exists(name)
    store.close()


def test_safe_name():
    assert safe_name("a/b\\c") == "a-b-c"
    for bad in ("   ", "...", ""):
        try:
            safe_name(bad)
            raise AssertionError(f"빈 이름이 통과하면 안 됨: {bad!r}")
        except ValueError:
            pass


if __name__ == "__main__":
    for fn in [test_migration_and_crud, test_safe_name]:
        fn()
        print(f"OK {fn.__name__}")
    print("모든 테스트 통과")
