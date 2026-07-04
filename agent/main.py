"""CLI 진입점.

`pip install -e .` 후 `dasan` 명령으로 실행:
  dasan                       # 채팅 TUI (start 기본)
  dasan start [--session ID]  # 채팅 TUI
  dasan login                 # OpenAI(ChatGPT) OAuth 로그인
  dasan list                  # 세션 목록
  dasan ask "질문..." [--session ID]   # 단발 질문 (스크립트용)

(설치 안 했으면 `python3 -m agent.main <같은 인자>` 로도 동일하게 동작)
"""
from __future__ import annotations

import argparse
import os
import sys

from .auth.store import TokenStore
from .config import load_config
from .service import AgentService
from .ui_labels import doing, done


def make_event_printer():
    debug = bool(os.environ.get("AGENT_DEBUG"))

    def on_event(kind: str, **kw) -> None:
        if kind == "tool_call":
            if debug:
                print(f"  [도구 호출] {kw['name']}({kw['input']})")
            else:
                print(f"  · {doing(kw['name'], kw['input'])}")
        elif kind == "tool_result":
            if debug:
                tag = "오류" if kw["is_error"] else "결과"
                preview = kw["output"].replace("\n", " ")[:120]
                print(f"  [도구 {tag}] {preview}")
            elif kw["is_error"]:
                preview = kw["output"].replace("\n", " ")[:120]
                print(f"  ↳ 문제가 생겼어요: {preview}")
            else:
                print(f"  ↳ {done(kw['name'], False)}")
        elif kind == "refusal":
            print("  [모델이 응답을 거부했습니다]")
        elif kind == "max_steps":
            print("  [최대 단계 수에 도달했습니다]")
        elif kind == "truncated":
            print("  [응답이 잘렸습니다(max_tokens)]")

    return on_event


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dasan", description="개인 에이전트 하네스")
    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="채팅 TUI 시작")
    p_start.add_argument("--session", help="이어서 진행할 세션 id")

    sub.add_parser("login", help="OpenAI(ChatGPT) OAuth 로그인")
    sub.add_parser("init", help="초기 설정(말투·길이·역할) 진행/변경")
    sub.add_parser("list", help="세션 목록 출력")

    p_ws = sub.add_parser("workspace", help="작업 폴더(수정·실행 허용 범위) 보기/변경")
    p_ws.add_argument("path", nargs="?", help="설정할 폴더 (없으면 현재 표시)")

    p_ask = sub.add_parser("ask", help="단발 질문 (스크립트용)")
    p_ask.add_argument("question", nargs="+", help="질문")
    p_ask.add_argument("--session", help="이어서 진행할 세션 id")

    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    command = args.command or "start"  # 인자 없으면 채팅 TUI
    session = getattr(args, "session", None)

    cfg = load_config()

    if command == "login":
        from .auth import flow

        try:
            TokenStore(cfg.auth_path).save_login(flow.login())
        except Exception as e:
            print(f"[로그인 실패] {e}", file=sys.stderr)
            sys.exit(1)
        print(f"로그인 완료. 토큰 저장: {cfg.auth_path}")
        return

    service = AgentService(cfg)

    if command == "list":
        for sid, created in service.list_sessions():
            print(f"{sid}\t{created}")
        service.close()
        return

    if command == "workspace":
        path = getattr(args, "path", None)
        if path:
            try:
                print(f"작업 폴더 설정: {service.set_workspace(path)}")
            except Exception as e:
                print(f"[실패] {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"현재 작업 폴더: {service.workspace_root()}")
        service.close()
        return

    if not service.logged_in():
        print("먼저 로그인하세요: dasan login", file=sys.stderr)
        service.close()
        sys.exit(1)

    if command == "init":  # 정제에 모델을 쓰므로 로그인 이후
        from .onboarding import run_onboarding

        run_onboarding(service)
        service.close()
        return

    if session and not service.session_exists(session):
        print(f"세션을 찾을 수 없습니다: {session}", file=sys.stderr)
        service.close()
        sys.exit(1)

    if command == "start":
        if service.needs_onboarding():  # 첫 실행이면 대화 전에 초기 설정
            from .onboarding import run_onboarding

            run_onboarding(service)
        from .tui import run_tui

        run_tui(service, session or service.main_session())
        return

    if command == "ask":
        sid = session or service.main_session()
        try:
            answer = service.respond(
                sid, " ".join(args.question), on_event=make_event_printer()
            )
            print(f"\n{answer}\n")
        except Exception as e:
            print(f"\n[오류] {e}\n", file=sys.stderr)
        service.close()


if __name__ == "__main__":
    main()
