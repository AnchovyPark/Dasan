"""CLI 진입점.

사용:
  python -m agent.main --login                           # OpenAI(ChatGPT) OAuth 로그인
  python -m agent.main "이 파일 요약해줘: ./notes.txt"   # 단발 질문
  python -m agent.main                                   # 대화형 REPL
  python -m agent.main --session <id>                    # 세션 이어가기
  python -m agent.main --list                            # 세션 목록
"""
from __future__ import annotations

import argparse
import sys

from .auth.store import TokenStore
from .config import load_config
from .core.loop import AgentLoop
from .providers.openai_oauth_adapter import OpenAIOAuthAdapter
from .session.store import SessionStore
from .tools.read_file import read_file_tool
from .tools.registry import ToolRegistry


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(read_file_tool)
    return reg


def make_event_printer():
    def on_event(kind: str, **kw) -> None:
        if kind == "tool_call":
            print(f"  [도구 호출] {kw['name']}({kw['input']})")
        elif kind == "tool_result":
            tag = "오류" if kw["is_error"] else "결과"
            preview = kw["output"].replace("\n", " ")[:120]
            print(f"  [도구 {tag}] {preview}")
        elif kind == "refusal":
            print("  [모델이 응답을 거부했습니다]")
        elif kind == "truncated":
            print("  [출력이 잘렸습니다]")
        elif kind == "max_steps":
            print("  [최대 단계 수에 도달했습니다]")

    return on_event


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="개인 에이전트 하네스 (MVP)")
    parser.add_argument("question", nargs="*", help="질문 (없으면 대화형 REPL)")
    parser.add_argument("--login", action="store_true", help="OpenAI(ChatGPT) OAuth 로그인")
    parser.add_argument("--session", help="이어서 진행할 세션 id")
    parser.add_argument("--list", action="store_true", help="세션 목록 출력")
    args = parser.parse_args(argv)

    cfg = load_config()
    token_store = TokenStore(cfg.auth_path)

    if args.login:
        from .auth import flow

        try:
            token_store.save_login(flow.login())
        except Exception as e:
            print(f"[로그인 실패] {e}", file=sys.stderr)
            sys.exit(1)
        print(f"로그인 완료. 토큰 저장: {cfg.auth_path}")
        return

    session_store = SessionStore(cfg.db_path)

    if args.list:
        for sid, created in session_store.list_sessions():
            print(f"{sid}\t{created}")
        session_store.close()
        return

    if not token_store.logged_in():
        print("먼저 로그인하세요: python -m agent.main --login", file=sys.stderr)
        session_store.close()
        sys.exit(1)

    adapter = OpenAIOAuthAdapter(token_store, cfg.model, cfg.base_url)
    registry = build_registry()
    loop = AgentLoop(
        adapter,
        registry,
        exposed_tools=["read_file"],  # 등록 ≠ 노출: 노출 목록을 명시
        on_event=make_event_printer(),
    )

    if args.session:
        if not session_store.exists(args.session):
            print(f"세션을 찾을 수 없습니다: {args.session}", file=sys.stderr)
            session_store.close()
            sys.exit(1)
        sid = args.session
        messages = session_store.load_messages(sid)
        print(f"세션 이어가기: {sid} (이전 메시지 {len(messages)}개)")
    else:
        sid = session_store.create_session()
        messages: list[dict] = []
        print(f"새 세션: {sid}")

    def ask(question: str) -> None:
        messages.extend(adapter.user_message(question))
        try:
            answer = loop.run(messages)
        except Exception as e:  # API/네트워크 오류로 REPL이 죽지 않도록
            print(f"\n[오류] {e}\n", file=sys.stderr)
            return
        session_store.save_messages(sid, messages)
        print(f"\n{answer}\n")

    if args.question:
        ask(" ".join(args.question))
    else:
        print("질문을 입력하세요. 종료: exit / quit")
        try:
            while True:
                line = input("> ").strip()
                if line.lower() in {"exit", "quit"}:
                    break
                if not line:
                    continue
                ask(line)
        except (EOFError, KeyboardInterrupt):
            print()

    session_store.close()


if __name__ == "__main__":
    main()
