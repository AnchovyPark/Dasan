"""AgentService — 프론트엔드 무관 코어.

CLI·TUI·Discord·웹 등 어떤 표면이든 이 respond() 하나만 호출하면 된다.
세션 id로 상태를 불러오고 저장하므로 표면은 상태를 몰라도 된다(무상태 호출).
"""
from __future__ import annotations

from typing import Callable

from .config import Config
from .core.loop import AgentLoop
from .providers.openai_oauth_adapter import OpenAIOAuthAdapter
from .session.store import SessionStore
from .tools.read_file import read_file_tool
from .tools.registry import ToolRegistry


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(read_file_tool)
    return reg


class AgentService:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        from .auth.store import TokenStore

        self._token_store = TokenStore(cfg.auth_path)
        self._adapter = OpenAIOAuthAdapter(self._token_store, cfg.model, cfg.base_url)
        self._registry = build_registry()
        self._loop = AgentLoop(self._adapter, self._registry, exposed_tools=["read_file"])
        self._sessions = SessionStore(cfg.db_path)

    # --- 인증/세션 관리 ---

    def logged_in(self) -> bool:
        return self._token_store.logged_in()

    def new_session(self) -> str:
        return self._sessions.create_session()

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
        answer = self._loop.run(messages, on_event=on_event, on_delta=on_delta)
        self._sessions.save_messages(sid, messages)
        return answer

    def close(self) -> None:
        self._sessions.close()
