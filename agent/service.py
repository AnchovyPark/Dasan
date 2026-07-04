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

# 세션 개념을 두지 않고 하나의 에이전트가 계속 이어가는 단일 세션 id.
MAIN_SESSION = "main"


class AgentService:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        from .auth.store import TokenStore

        self._token_store = TokenStore(cfg.auth_path)
        self._adapter = OpenAIOAuthAdapter(
            self._token_store, cfg.model, cfg.base_url, cfg.reasoning_effort
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

        self._loop = AgentLoop(self._adapter, self._registry, exposed_tools=exposed)
        self._sessions = SessionStore(cfg.db_path)

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

    def new_session(self) -> str:
        return self._sessions.create_session()

    def main_session(self) -> str:
        """항상 같은 단일 세션을 이어간다. 없으면 만들어 두고 그 id를 반환."""
        self._sessions.ensure(MAIN_SESSION)
        return MAIN_SESSION

    def session_exists(self, sid: str) -> bool:
        return self._sessions.exists(sid)

    def list_sessions(self) -> list[tuple[str, str]]:
        return self._sessions.list_sessions()

    def message_count(self, sid: str) -> int:
        return len(self._sessions.load_messages(sid))

    # --- 대화 ---

    def respond(
        self,
        sid: str,
        text: str,
        on_event: Callable[..., None] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        """세션 sid에 사용자 발화를 넣고 최종 답변을 반환. 대화는 저장된다."""
        messages = self._sessions.load_messages(sid)
        messages.extend(self._adapter.user_message(text))
        system = compose_system(self._alignment.load())  # 매 요청마다 최신 ALIGNMENT 반영
        answer = self._loop.run(
            messages, system=system, on_event=on_event, on_delta=on_delta
        )
        self._sessions.save_messages(sid, messages)
        return answer

    def complete(self, system: str, user: str) -> str:
        """도구·세션 없이 1회성 응답을 받는다(초기 설정 정제 등에 사용)."""
        messages = self._adapter.user_message(user)
        resp = self._adapter.call(messages, [], system=system)
        return resp.text or ""

    def close(self) -> None:
        self._sessions.close()
