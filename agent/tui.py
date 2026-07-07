"""CC/Codex 스타일 터미널 채팅 UI.

스크롤형 대화 전사 + 하단 입력. 답변은 토큰 단위로 실시간 스트리밍되고,
도구 호출은 흐린 상태 줄로 표시된다. 슬래시 명령으로 세션을 관리한다.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule

from .service import AgentService
from .ui_labels import doing

HELP = """[bold]명령[/bold]
  /init         초기 설정(말투·길이·역할) 다시 하기
  /workspace [경로]  작업 폴더 보기/변경(수정·실행 허용 범위)
  /new          새 세션 시작
  /sessions     세션 목록
  /clear        현재 세션 대화 내용 초기화 (화면도 지움)
  /compact      오래된 턴을 지금 바로 장기 기억(digest)으로 접기
  /help         이 도움말
  /exit /quit   종료 (Ctrl-D 도 가능)"""

# 도구를 성격별로 묶어 요약 줄에 쓴다(개별 도구명 대신 '읽기 2 · 수정 3').
_TOOL_CATEGORY = {
    "read_file": "읽기", "list_dir": "읽기", "search": "읽기",
    "write_file": "수정", "edit_file": "수정",
    "delete_file": "수정", "move_file": "수정",
    "run_command": "명령", "remember_preference": "기억",
}
_CATEGORY_ORDER = ["읽기", "수정", "명령", "웹검색", "기억", "기타"]


def _tool_summary(counts: dict) -> str:
    """도구 실행 집계를 '읽기 2 · 수정 3 · 명령 1' 한 줄로 접는다(0인 항목은 뺀다)."""
    parts = [f"{c} {counts[c]}" for c in _CATEGORY_ORDER if counts.get(c)]
    return " · ".join(parts)


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


def _create_titled_session(console: Console, service: AgentService) -> str:
    """제목을 물어 새 세션을 만든다. 비우면 날짜 기반 이름을 붙인다."""
    while True:
        title = Prompt.ask("세션 제목 (Enter=자동)", default="").strip()
        if not title:
            base = datetime.now().strftime("%Y-%m-%d-%H%M")
            title, n = base, 2
            while service.session_exists(title):
                title = f"{base}-{n}"
                n += 1
        elif service.session_exists(title):
            console.print(
                f"[yellow]이미 있는 세션이에요: {title}[/yellow]  "
                f"(이어가려면 `dasan start --{title}`)"
            )
            continue
        try:
            return service.new_session(title)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")


def _make_approver(console: Console, ui: dict):
    """위험 명령 실행 전 사용자 승인을 받는 함수.

    승인은 루프 도중(스피너가 도는 중)에 일어나므로, 물어보는 동안엔
    진행 스피너를 잠시 멈췄다가 다시 켠다.
    """
    def approve(cmd: str) -> bool:
        st = ui.get("status")
        if st is not None:
            st.stop()
        console.print(f"\n[yellow]⚠ 위험할 수 있는 명령이에요:[/yellow] [bold]{cmd}[/bold]")
        ok = Confirm.ask("실행할까요?", default=False)
        if st is not None:
            st.start()
        return ok

    return approve


def run_tui(service: AgentService, session_id: str | None = None) -> None:
    console = Console()
    ui: dict = {"status": None}  # 진행 스피너 핸들 공유(승인 함수가 잠시 멈출 수 있게)
    service.set_approver(_make_approver(console, ui))  # 위험 명령은 대화형 승인

    if session_id:
        sid = session_id
        resumed = service.message_count(sid) or None  # 0개면 새 세션처럼 표시
    else:
        sid = _create_titled_session(console, service)
        resumed = None
    _print_header(console, service, sid, resumed)

    prompt = PromptSession(history=InMemoryHistory())

    while True:
        console.print(Rule(style="grey37"))  # 턴 구분선
        try:
            text = prompt.prompt(ANSI("\033[1;36m You ›\033[0m ")).strip()
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
                count = service.message_count(sid)
                if count and not Confirm.ask(
                    f"이 세션의 대화 {count}개를 모두 지울까요?", default=False
                ):
                    continue
                service.clear_session(sid)
                console.clear()
                _print_header(console, service, sid, None)
                console.print("[green]대화 내용을 비웠어요. 새로 시작합니다.[/green]")
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
            if cmd == "compact":
                console.print("[dim]· 기억 정리 중…[/dim]")
                try:
                    folded = service.compact_session(sid, force=True)
                except Exception as e:
                    console.print(f"[red]실패:[/red] {e}")
                    continue
                if folded:
                    console.print("[green]오래된 턴을 장기 기억으로 접었어요.[/green]")
                else:
                    console.print("[dim]접을 만큼 오래된 턴이 없어요.[/dim]")
                continue
            if cmd == "new":
                sid = _create_titled_session(console, service)
                console.print(f"[green]새 세션:[/green] [dim]{sid}[/dim]")
                continue
            if cmd == "sessions":
                for s, created, count in service.list_sessions():
                    mark = " [cyan]←현재[/cyan]" if s == sid else ""
                    console.print(
                        f"  [bold]{s}[/bold]  [dim]{created[:16].replace('T', ' ')}"
                        f" · 메시지 {count}개[/dim]{mark}"
                    )
                continue
            console.print(f"[yellow]알 수 없는 명령: {text}[/yellow]  (/help)")
            continue

        # 이벤트/스트리밍 콜백.
        # 작업 중엔 스피너로 '지금 하는 단계'만 보여주고, 답변이 시작되는 순간
        # 그동안의 도구 실행을 '읽기 2 · 수정 3' 요약 한 줄로 접는다.
        debug = bool(os.environ.get("AGENT_DEBUG"))
        counts: dict = defaultdict(int)
        state = {"answering": False}

        def open_answer() -> None:
            """도구 단계를 요약 한 줄로 접고 Dasan 답변 헤더를 연다(한 번만)."""
            if state["answering"]:
                return
            st = ui.get("status")
            if st is not None:
                st.stop()
                ui["status"] = None
            if counts and not debug:
                console.print(f"[dim]  {_tool_summary(counts)}[/dim]", highlight=False)
            console.print("[bold green] Dasan ›[/bold green] ", end="")
            state["answering"] = True

        def on_event(kind: str, **kw) -> None:
            if kind == "tool_call":
                counts[_TOOL_CATEGORY.get(kw["name"], "기타")] += 1
                if debug:
                    console.print(f"[dim]● {kw['name']}({kw['input']})[/dim]")
                else:
                    st = ui.get("status")
                    if st is not None:
                        st.update(f"[dim]{doing(kw['name'], kw['input'])}[/dim]")
            elif kind == "tool_result":
                if debug:
                    tag = "[red]오류[/red] " if kw["is_error"] else ""
                    preview = kw["output"].replace("\n", " ")[:100]
                    console.print(f"[dim]  ↳ {tag}{preview}[/dim]")
                elif kw["is_error"]:
                    # 실패는 접지 않고 실제 오류를 그대로 보여준다
                    preview = kw["output"].replace("\n", " ")[:120]
                    console.print(f"[red]  ↳ 문제가 생겼어요: {preview}[/red]")
            elif kind == "web_search":
                counts["웹검색"] += 1
                if debug:
                    console.print(f"[dim]● web_search({kw['query']})[/dim]")
                else:
                    st = ui.get("status")
                    if st is not None:
                        st.update(f"[dim]웹 검색: {kw['query'][:60]}[/dim]")
            elif kind == "compact_start":
                console.print(f"\n[dim]· 오래된 대화 {kw['folding']}턴을 장기 기억으로 접는 중…[/dim]")
            elif kind == "compact_done":
                console.print("[dim]  ↳ 기억 정리 완료[/dim]")
            elif kind == "compact_failed":
                console.print(f"[dim]  ↳ 기억 정리 실패(다음 턴에 재시도): {kw['error'][:80]}[/dim]")
            elif kind == "refusal":
                console.print("[yellow]모델이 응답을 거부했습니다[/yellow]")
            elif kind == "max_steps":
                console.print("[yellow]최대 단계 수 도달[/yellow]")
            elif kind == "truncated":
                console.print("[yellow]응답이 잘렸습니다(max_tokens)[/yellow]")

        def on_delta(token: str) -> None:
            open_answer()
            sys.stdout.write(token)
            sys.stdout.flush()

        try:
            if debug:
                answer = service.respond(sid, text, on_event=on_event, on_delta=on_delta)
            else:
                with console.status("[dim]생각 중…[/dim]", spinner="dots") as st:
                    ui["status"] = st
                    answer = service.respond(
                        sid, text, on_event=on_event, on_delta=on_delta
                    )
        except Exception as e:
            ui["status"] = None
            console.print(f"\n[red][오류][/red] {e}")
            continue
        finally:
            ui["status"] = None

        if state["answering"]:
            sys.stdout.write("\n")
            sys.stdout.flush()
        else:
            # 스트리밍이 없었던 경우(예: 도구만 돌고 텍스트 없음) 대비
            if counts and not debug:
                console.print(f"[dim]  {_tool_summary(counts)}[/dim]", highlight=False)
            if answer.strip():
                console.print("[bold green] Dasan ›[/bold green] ", end="")
                console.print(answer, highlight=False, markup=False)
            else:
                console.print(
                    "[dim] (응답 텍스트 없이 끝났어요 — 작업이 도중에 끊겼다면 "
                    "'계속해'라고 하면 이어서 합니다)[/dim]"
                )

    service.close()
