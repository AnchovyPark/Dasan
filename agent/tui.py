"""CC/Codex 스타일 터미널 채팅 UI.

스크롤형 대화 전사 + 하단 입력. 답변은 토큰 단위로 실시간 스트리밍되고,
도구 호출은 흐린 상태 줄로 표시된다. 슬래시 명령으로 세션을 관리한다.
"""
from __future__ import annotations

import os
import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from .service import AgentService
from .ui_labels import doing, done

HELP = """[bold]명령[/bold]
  /init         초기 설정(말투·길이·역할) 다시 하기
  /workspace [경로]  작업 폴더 보기/변경(수정·실행 허용 범위)
  /new          새 세션 시작
  /sessions     세션 목록
  /clear        화면 지우기
  /help         이 도움말
  /exit /quit   종료 (Ctrl-D 도 가능)"""


def _print_header(console: Console, service: AgentService, sid: str, resumed: int | None) -> None:
    cfg = service.cfg
    sub = f"이어가기 · 이전 {resumed}개" if resumed is not None else "새 세션"
    console.print(
        Panel(
            f"[bold]Dasan[/bold]  ·  모델 [cyan]{cfg.model}[/cyan]  ·  세션 [dim]{sid}[/dim]  ·  {sub}\n"
            f"[dim]작업 폴더(수정·실행 허용): {service.workspace_root()}[/dim]\n"
            "[dim]/help 로 명령 · 파일 탐색·수정·명령 실행을 직접 합니다[/dim]",
            border_style="cyan",
        )
    )


def _make_approver(console: Console):
    """위험 명령 실행 전 사용자 승인을 받는 함수."""
    def approve(cmd: str) -> bool:
        console.print(f"\n[yellow]⚠ 위험할 수 있는 명령이에요:[/yellow] [bold]{cmd}[/bold]")
        return Confirm.ask("실행할까요?", default=False)

    return approve


def run_tui(service: AgentService, session_id: str | None = None) -> None:
    console = Console()
    service.set_approver(_make_approver(console))  # 위험 명령은 대화형 승인

    if session_id:
        sid = session_id
        resumed = service.message_count(sid) or None  # 0개면 새 세션처럼 표시
    else:
        sid = service.new_session()
        resumed = None
    _print_header(console, service, sid, resumed)

    prompt = PromptSession(history=InMemoryHistory())

    while True:
        try:
            text = prompt.prompt("\nYou › ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]종료합니다.[/dim]")
            break

        if not text:
            continue

        # 슬래시 명령
        if text.startswith("/"):
            cmd = text[1:].split()[0].lower()
            if cmd in ("exit", "quit"):
                break
            if cmd == "help":
                console.print(HELP)
                continue
            if cmd == "clear":
                console.clear()
                continue
            if cmd == "init":
                from .onboarding import run_onboarding

                run_onboarding(service, console)
                continue
            if cmd == "workspace":
                parts = text.split(maxsplit=1)
                if len(parts) > 1:
                    try:
                        root = service.set_workspace(parts[1].strip())
                        console.print(f"[green]작업 폴더 변경:[/green] [dim]{root}[/dim]")
                    except Exception as e:
                        console.print(f"[red]변경 실패:[/red] {e}")
                else:
                    console.print(f"현재 작업 폴더: [dim]{service.workspace_root()}[/dim]")
                continue
            if cmd == "new":
                sid = service.new_session()
                console.print(f"[green]새 세션:[/green] [dim]{sid}[/dim]")
                continue
            if cmd == "sessions":
                for s, created in service.list_sessions():
                    mark = " [cyan]←현재[/cyan]" if s == sid else ""
                    console.print(f"  [dim]{s}[/dim]  {created}{mark}")
                continue
            console.print(f"[yellow]알 수 없는 명령: {text}[/yellow]  (/help)")
            continue

        # 이벤트/스트리밍 콜백
        debug = bool(os.environ.get("AGENT_DEBUG"))
        state = {"started": False}

        def on_event(kind: str, **kw) -> None:
            if kind == "tool_call":
                if debug:
                    console.print(f"[dim]● {kw['name']}({kw['input']})[/dim]")
                else:
                    console.print(f"[dim]· {doing(kw['name'], kw['input'])}[/dim]")
            elif kind == "tool_result":
                if debug:
                    tag = "[red]오류[/red] " if kw["is_error"] else ""
                    preview = kw["output"].replace("\n", " ")[:100]
                    console.print(f"[dim]  ↳ {tag}{preview}[/dim]")
                elif kw["is_error"]:
                    # 실패는 감추지 않고 실제 오류를 보여준다
                    preview = kw["output"].replace("\n", " ")[:120]
                    console.print(f"[red]  ↳ 문제가 생겼어요: {preview}[/red]")
                else:
                    console.print(f"[dim]  ↳ {done(kw['name'], False)}[/dim]")
            elif kind == "refusal":
                console.print("[yellow]모델이 응답을 거부했습니다[/yellow]")
            elif kind == "max_steps":
                console.print("[yellow]최대 단계 수 도달[/yellow]")
            elif kind == "truncated":
                console.print("[yellow]응답이 잘렸습니다(max_tokens)[/yellow]")

        def on_delta(token: str) -> None:
            if not state["started"]:
                console.print("\n[bold green]Dasan ›[/bold green] ", end="")
                state["started"] = True
            sys.stdout.write(token)
            sys.stdout.flush()

        # 제출 직후 즉시 신호를 줘서 '멍하니 기다리는' 공백을 없앤다
        console.print("[dim]· 생각 중…[/dim]")

        try:
            answer = service.respond(sid, text, on_event=on_event, on_delta=on_delta)
        except Exception as e:
            console.print(f"\n[red][오류][/red] {e}")
            continue

        if state["started"]:
            sys.stdout.write("\n")
            sys.stdout.flush()
        else:
            # 스트리밍이 없었던 경우(예: 도구만 돌고 텍스트 없음) 대비
            console.print(f"\n[bold green]Dasan ›[/bold green] {answer}")

    service.close()
