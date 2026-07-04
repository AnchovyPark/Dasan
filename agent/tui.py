"""CC/Codex 스타일 터미널 채팅 UI.

스크롤형 대화 전사 + 하단 입력. 답변은 토큰 단위로 실시간 스트리밍되고,
도구 호출은 흐린 상태 줄로 표시된다. 슬래시 명령으로 세션을 관리한다.
"""
from __future__ import annotations

import sys

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.panel import Panel

from .service import AgentService

HELP = """[bold]명령[/bold]
  /new        새 세션 시작
  /sessions   세션 목록
  /clear      화면 지우기
  /help       이 도움말
  /exit /quit 종료 (Ctrl-D 도 가능)"""


def _print_header(console: Console, cfg, sid: str, resumed: int | None) -> None:
    sub = f"이어가기 · 이전 {resumed}개" if resumed is not None else "새 세션"
    console.print(
        Panel(
            f"[bold]Dasan[/bold]  ·  모델 [cyan]{cfg.model}[/cyan]  ·  세션 [dim]{sid}[/dim]  ·  {sub}\n"
            "[dim]/help 로 명령 · 파일 관련 질문이면 read_file 로 읽고 답합니다[/dim]",
            border_style="cyan",
        )
    )


def run_tui(service: AgentService, session_id: str | None = None) -> None:
    console = Console()

    if session_id:
        sid = session_id
        resumed = service.message_count(sid) or None  # 0개면 새 세션처럼 표시
    else:
        sid = service.new_session()
        resumed = None
    _print_header(console, service.cfg, sid, resumed)

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
        state = {"started": False}

        def on_event(kind: str, **kw) -> None:
            if kind == "tool_call":
                console.print(f"[dim]● {kw['name']}({kw['input']})[/dim]")
            elif kind == "tool_result":
                tag = "[red]오류[/red]" if kw["is_error"] else ""
                preview = kw["output"].replace("\n", " ")[:100]
                console.print(f"[dim]  ↳ {tag}{preview}[/dim]")
            elif kind == "refusal":
                console.print("[yellow]모델이 응답을 거부했습니다[/yellow]")
            elif kind == "max_steps":
                console.print("[yellow]최대 단계 수 도달[/yellow]")

        def on_delta(token: str) -> None:
            if not state["started"]:
                console.print("\n[bold green]Dasan ›[/bold green] ", end="")
                state["started"] = True
            sys.stdout.write(token)
            sys.stdout.flush()

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
