"""CLI 진입점.

사용:
  python -m agent.main --login                           # OpenAI(ChatGPT) OAuth 로그인
  python -m agent.main                                   # 채팅 TUI (CC 스타일)
  python -m agent.main "이 파일 요약해줘: ./notes.txt"   # 단발 질문 (스크립트용)
  python -m agent.main --session <id>                    # 세션 이어가기 (TUI/단발)
  python -m agent.main --list                            # 세션 목록
"""
from __future__ import annotations

import argparse
import sys

from .auth.store import TokenStore
from .config import load_config
from .service import AgentService


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
        elif kind == "max_steps":
            print("  [최대 단계 수에 도달했습니다]")

    return on_event


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="개인 에이전트 하네스 (MVP)")
    parser.add_argument("question", nargs="*", help="질문 (없으면 채팅 TUI)")
    parser.add_argument("--login", action="store_true", help="OpenAI(ChatGPT) OAuth 로그인")
    parser.add_argument("--session", help="이어서 진행할 세션 id")
    parser.add_argument("--list", action="store_true", help="세션 목록 출력")
    args = parser.parse_args(argv)

    cfg = load_config()

    if args.login:
        from .auth import flow

        try:
            TokenStore(cfg.auth_path).save_login(flow.login())
        except Exception as e:
            print(f"[로그인 실패] {e}", file=sys.stderr)
            sys.exit(1)
        print(f"로그인 완료. 토큰 저장: {cfg.auth_path}")
        return

    service = AgentService(cfg)

    if args.list:
        for sid, created in service.list_sessions():
            print(f"{sid}\t{created}")
        service.close()
        return

    if not service.logged_in():
        print("먼저 로그인하세요: python -m agent.main --login", file=sys.stderr)
        service.close()
        sys.exit(1)

    if args.session and not service.session_exists(args.session):
        print(f"세션을 찾을 수 없습니다: {args.session}", file=sys.stderr)
        service.close()
        sys.exit(1)

    # 질문이 없으면 채팅 TUI, 있으면 단발(스크립트용)
    if not args.question:
        from .tui import run_tui

        run_tui(service, args.session)
        return

    sid = args.session or service.new_session()
    if not args.session:
        print(f"새 세션: {sid}")
    try:
        answer = service.respond(sid, " ".join(args.question), on_event=make_event_printer())
        print(f"\n{answer}\n")
    except Exception as e:
        print(f"\n[오류] {e}\n", file=sys.stderr)
    service.close()


if __name__ == "__main__":
    main()
