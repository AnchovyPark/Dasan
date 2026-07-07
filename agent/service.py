"""AgentService — 프론트엔드 무관 코어.

CLI·TUI·Discord·웹 등 어떤 표면이든 이 respond() 하나만 호출하면 된다.
세션 id로 상태를 불러오고 저장하므로 표면은 상태를 몰라도 된다(무상태 호출).
"""
from __future__ import annotations

import os
from typing import Callable

from .alignment import AlignmentStore
from .config import Config
from .core.loop import AgentLoop
from .prompt import compose_system
from .providers.openai_oauth_adapter import OpenAIOAuthAdapter
from .session import compact
from .session.store import SessionStore
from .tools.delete_file import make_delete_file_tool
from .tools.edit_file import make_edit_file_tool
from .tools.list_dir import make_list_dir_tool
from .tools.move_file import make_move_file_tool
from .tools.read_file import make_read_file_tool
from .tools.registry import ToolRegistry
from .tools.remember import make_remember_tool
from .tools.run_command import make_run_command_tool
from .tools.search import make_search_tool
from .tools.write_file import make_write_file_tool
from .workspace import Workspace


class AgentService:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        from .auth.store import TokenStore

        self._token_store = TokenStore(cfg.auth_path)
        self._adapter = OpenAIOAuthAdapter(
            self._token_store, cfg.model, cfg.base_url, cfg.reasoning_effort,
            web_search=cfg.web_search,
        )
        self._alignment = AlignmentStore(cfg.alignment_path)
        self._workspace = Workspace.load(
            cfg.workspace_file, env_override=os.environ.get("AGENT_WORKSPACE") or None
        )
        # 위험 명령 승인 함수. 기본은 거부(비대화형 안전), TUI가 대화형으로 교체한다.
        self._approver: Callable[[str], bool] = lambda cmd: False

        ws = self._workspace
        self._registry = ToolRegistry()
        self._registry.register(make_read_file_tool(ws))
        self._registry.register(make_list_dir_tool(ws))
        self._registry.register(make_search_tool(ws))
        self._registry.register(make_write_file_tool(ws))
        self._registry.register(make_edit_file_tool(ws))
        self._registry.register(make_delete_file_tool(ws))
        self._registry.register(make_move_file_tool(ws))
        self._registry.register(make_run_command_tool(ws, lambda cmd: self._approver(cmd)))
        self._registry.register(make_remember_tool(self._alignment))
        exposed = [
            "read_file", "list_dir", "search",
            "write_file", "edit_file", "delete_file", "move_file", "run_command",
            "remember_preference",
        ]

        self._loop = AgentLoop(
            self._adapter, self._registry, exposed_tools=exposed,
            max_steps=cfg.max_steps,
        )
        self._sessions = SessionStore(cfg.sessions_dir, legacy_db=cfg.legacy_db_path)

    # --- 인증/세션 관리 ---

    def logged_in(self) -> bool:
        return self._token_store.logged_in()

    @property
    def alignment(self) -> AlignmentStore:
        return self._alignment

    # --- workspace(가드레일) ---

    def workspace_root(self) -> str:
        return str(self._workspace.root)

    def set_workspace(self, path: str) -> str:
        """작업 폴더를 바꾸고 저장한다(여러 프로젝트 전환). 새 루트 경로 반환."""
        return str(self._workspace.set_root(path))

    def set_approver(self, fn: Callable[[str], bool]) -> None:
        """위험 명령 실행 승인 함수를 주입한다(표면별)."""
        self._approver = fn

    def needs_onboarding(self) -> bool:
        """정렬 파일이 비어 있으면(첫 실행) 초기 설정이 필요하다."""
        return not self._alignment.load().strip()

    def new_session(self, name: str) -> str:
        """제목으로 세션을 만들고 실제(파일명으로 정리된) 이름을 반환."""
        return self._sessions.create_session(name)

    def latest_session(self) -> str | None:
        """가장 최근에 만든 세션 이름. 없으면 None."""
        sessions = self._sessions.list_sessions()
        return sessions[-1][0] if sessions else None

    def session_exists(self, sid: str) -> bool:
        return self._sessions.exists(sid)

    def list_sessions(self) -> list[tuple[str, str, int]]:
        """(이름, 생성일, 메시지 수) 목록."""
        return self._sessions.list_sessions()

    def message_count(self, sid: str) -> int:
        return len(self._sessions.load_messages(sid))

    def clear_session(self, sid: str) -> None:
        """세션의 대화 내용을 전부 비운다(세션 자체는 유지). digest·커서도 초기화."""
        self._sessions.save_messages(sid, [])
        self._sessions.set_compaction(sid, 0, "")

    # --- 대화 ---

    def respond(
        self,
        sid: str,
        text: str,
        on_event: Callable[..., None] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        """세션 sid에 사용자 발화를 넣고 최종 답변을 반환. 대화는 저장된다.

        DB의 raw는 불변으로 두고, 모델에는 [digest(시스템에 합침)] + [최근 창
        원문(오래된 도구 출력은 스텁 치환)]만 보낸다. 턴이 끝나면 필요 시
        오래된 턴을 digest로 접는다(컴팩션).
        """
        all_items = self._sessions.load_messages(sid)
        cursor, digest = self._sessions.get_compaction(sid)
        send = compact.prepare_for_send(all_items[cursor:])  # 전송용 복사본
        prepared = len(send)
        send.extend(self._adapter.user_message(text))
        # 매 요청마다 최신 ALIGNMENT·digest 반영
        system = compose_system(self._alignment.load(), digest)
        answer = self._loop.run(
            send, system=system, on_event=on_event, on_delta=on_delta
        )
        # 루프가 새로 만든 아이템(유저 메시지 포함)만 raw에 이어붙여 저장
        all_items.extend(send[prepared:])
        self._sessions.save_messages(sid, all_items)
        self.compact_session(sid, on_event=on_event)  # 답변 후 뒷정리(필요 시)
        return answer

    def compact_session(
        self,
        sid: str,
        force: bool = False,
        on_event: Callable[..., None] | None = None,
    ) -> bool:
        """원문 창의 오래된 턴들을 digest로 접는다. 접었으면 True.

        force=False면 창의 유저 턴이 TRIGGER_TURNS를 넘을 때만 동작한다.
        실패해도 예외를 밖으로 던지지 않는다(다음 턴에 재시도되므로).
        """
        emit = on_event or (lambda *a, **k: None)
        all_items = self._sessions.load_messages(sid)
        cursor, digest = self._sessions.get_compaction(sid)
        tail = all_items[cursor:]
        if not force and not compact.should_compact(tail):
            return False
        folded, _kept = compact.fold_split(tail)
        if not folded:
            return False
        emit("compact_start", folding=compact.count_turns(folded))
        try:
            new_digest = compact.update_digest(self.complete, digest, folded)
        except Exception as e:
            emit("compact_failed", error=str(e))
            return False
        self._sessions.set_compaction(sid, cursor + len(folded), new_digest)
        emit("compact_done", digest_len=len(new_digest))
        return True

    def complete(self, system: str, user: str) -> str:
        """도구·세션 없이 1회성 응답을 받는다(초기 설정 정제 등에 사용)."""
        messages = self._adapter.user_message(user)
        resp = self._adapter.call(messages, [], system=system)
        return resp.text or ""

    def close(self) -> None:
        self._sessions.close()
