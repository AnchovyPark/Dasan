"""CLI 진입점.

`pip install -e .` 후 `dasan` 명령으로 실행:
  dasan                       # 새 세션 시작 (초기 설정 + 제목 정하기)
  dasan start                 # 위와 동일
  dasan start --<제목>        # 저장된 세션 이어가기 (예: dasan start --main)
  dasan login                 # OpenAI(ChatGPT) OAuth 로그인
  dasan update                # 최신 버전으로 업데이트 (pipx 설치/개발 설치 자동 감지)
  dasan list                  # 세션 목록
  dasan ask "질문..." [--session 제목]  # 단발 질문 (스크립트용, 기본=최근 세션)

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
        elif kind == "web_search":
            print(f"  · 웹 검색: {kw['query'][:60]}")
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

    p_start = sub.add_parser("start", help="새 세션 시작 (--<제목> 으로 이어가기)")
    p_start.add_argument("--session", help="이어서 진행할 세션 제목")

    sub.add_parser("login", help="OpenAI(ChatGPT) OAuth 로그인")

    p_update = sub.add_parser("update", help="Dasan을 최신 버전으로 업데이트")
    p_update.add_argument("--branch", help="설치할 브랜치 (기본: main)")

    p_serve = sub.add_parser("serve", help="Bongsu 같은 웹 클라이언트용 로컬 API 서버 실행")
    p_serve.add_argument("--host", default="127.0.0.1", help="바인드 주소 (기본: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=8790, help="포트 (기본: 8790)")
    p_serve.add_argument("--reload", action="store_true", help="개발용 자동 재시작")

    sub.add_parser("init", help="초기 설정(말투·길이·역할) 진행/변경")
    sub.add_parser("list", help="세션 목록 출력")

    p_ws = sub.add_parser("workspace", help="작업 폴더(수정·실행 허용 범위) 보기/변경")
    p_ws.add_argument("path", nargs="?", help="설정할 폴더 (없으면 현재 표시)")

    p_ask = sub.add_parser("ask", help="단발 질문 (스크립트용)")
    p_ask.add_argument("question", nargs="+", help="질문")
    p_ask.add_argument("--session", help="이어서 진행할 세션 제목 (기본=최근 세션)")

    return parser


def _update(branch: str | None) -> None:
    """설치 방식을 감지해 최신 버전으로 갱신한다.

    - 개발(editable) 설치(소스에 .git이 있음): 리포에서 git pull — 수정이 즉시 반영된다.
    - pipx 전역 설치: GitHub에서 최신을 받아 강제 재설치한다.
    """
    import shutil
    import subprocess
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    if (repo_root / ".git").exists():
        print(f"개발 설치 감지 — git pull ({repo_root})")
        r = subprocess.run(["git", "-C", str(repo_root), "pull", "--ff-only"])
        sys.exit(r.returncode)

    branch = branch or os.environ.get("DASAN_BRANCH") or "main"
    spec = f"git+https://github.com/AnchovyPark/Dasan.git@{branch}"
    pipx = shutil.which("pipx")
    cmd = (
        [pipx, "install", "--force", spec]
        if pipx
        else [sys.executable, "-m", "pipx", "install", "--force", spec]
    )
    print(f"업데이트 중: {spec}")
    r = subprocess.run(cmd)
    if r.returncode == 0:
        print("업데이트 완료. 새 터미널부터 적용됩니다.")
    else:
        print(
            "업데이트 실패. 설치 스크립트를 다시 실행해보세요:\n"
            "  (Windows)     irm https://raw.githubusercontent.com/AnchovyPark/Dasan/main/install.ps1 | iex\n"
            "  (macOS/Linux) curl -fsSL https://raw.githubusercontent.com/AnchovyPark/Dasan/main/install.sh | bash",
            file=sys.stderr,
        )
    sys.exit(r.returncode)


def main(argv: list[str] | None = None) -> None:
    args, extra = _build_parser().parse_known_args(argv)
    command = args.command or "start"  # 인자 없으면 채팅 TUI
    session = getattr(args, "session", None)

    # `dasan start --<제목>` 지원: 정의되지 않은 --옵션을 세션 제목으로 해석
    for tok in extra:
        if command == "start" and tok.startswith("--") and len(tok) > 2:
            session = tok[2:]
        else:
            print(f"알 수 없는 인자: {tok}", file=sys.stderr)
            sys.exit(2)

    if command == "update":  # 설정·로그인 불필요
        _update(getattr(args, "branch", None))
        return

    if command == "serve":  # 설정은 API 앱에서 요청마다 로드
        import uvicorn

        uvicorn.run(
            "agent.api:app",
            host=getattr(args, "host", "127.0.0.1"),
            port=getattr(args, "port", 8790),
            reload=bool(getattr(args, "reload", False)),
        )
        return

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
        for sid, created, count in service.list_sessions():
            print(f"{sid}\t{created[:16].replace('T', ' ')}\t메시지 {count}개")
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
        print(f"세션을 찾을 수 없습니다: {session}  (`dasan list` 로 확인)", file=sys.stderr)
        service.close()
        sys.exit(1)

    if command == "start":
        from .tui import run_tui

        if not session:  # 새 세션: 매번 초기 설정(온보딩)부터
            from .onboarding import run_onboarding

            run_onboarding(service)
        run_tui(service, session)
        return

    if command == "ask":
        sid = session or service.latest_session()
        if sid is None:
            print("세션이 없습니다. 먼저 `dasan start` 로 만드세요.", file=sys.stderr)
            service.close()
            sys.exit(1)
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
