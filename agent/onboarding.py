"""초기 설정(onboarding) — 대화 시작 전에 '어떤 에이전트/말투/길이'인지 먼저 정한다.

대화하며 사후 교정하는 대신, 첫 실행(또는 `dasan init`)에 고정 질문지로 사용자
선호를 받아 alignment.md에 박아둔다. 그래야 첫 메시지부터 정렬된 상태로 출발한다.

build_alignment()는 순수 함수(테스트 가능), run_onboarding()이 입출력을 담당.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .alignment import AlignmentStore

# 키 -> (표시명, alignment에 기록할 규칙 문장)
TONE = {
    "1": ("해요체", "말투는 해요체(부드러운 존댓말)로 통일한다. 존댓말·반말·개조식(-음/-함) 혼용 금지."),
    "2": ("합니다체", "말투는 합니다체(격식 있는 존댓말)로 통일한다. 반말·개조식 혼용 금지."),
    "3": ("반말", "말투는 반말로 통일한다. 존댓말·개조식 혼용 금지."),
}
LENGTH = {
    "1": ("간결", "결론부터, 핵심만 간결하게. 요청하지 않은 제안·다음 단계 나열은 하지 않는다."),
    "2": ("보통", "핵심을 먼저 말하고 필요한 만큼만 설명한다."),
    "3": ("자세히", "배경과 근거를 충분히 설명한다."),
}


def build_alignment(tone: str, length: str, role: str = "", extra: str = "") -> str:
    """선택값으로 alignment.md 본문을 만든다(순수 함수)."""
    lines = ["# 말투", f"- {TONE[tone][1]}", "# 답변", f"- {LENGTH[length][1]}"]
    if role.strip():
        lines += ["# 역할", f"- {role.strip()}"]
    if extra.strip():
        lines += ["# 그 외", f"- {extra.strip()}"]
    return "\n".join(lines)


def run_onboarding(store: AlignmentStore, console: Console | None = None) -> None:
    console = console or Console()
    console.print(
        Panel(
            "[bold]Dasan 초기 설정[/bold]\n"
            "어떻게 답하길 원하는지 몇 가지만 정할게요. (그냥 Enter = 기본값)",
            border_style="cyan",
        )
    )
    if store.load().strip():
        console.print("[yellow]기존 설정을 덮어씁니다.[/yellow]")

    tone = Prompt.ask(
        "말투  [1] 해요체  [2] 합니다체  [3] 반말",
        choices=["1", "2", "3"], default="1",
    )
    length = Prompt.ask(
        "답변 길이  [1] 간결  [2] 보통  [3] 자세히",
        choices=["1", "2", "3"], default="1",
    )
    role = Prompt.ask("역할/성격 (선택 · 예: 직설적인 시니어 개발자처럼)", default="")
    extra = Prompt.ask("그 외 규칙 (선택)", default="")

    store.write(build_alignment(tone, length, role, extra))
    console.print(
        f"\n[green]설정을 저장했어요.[/green] "
        f"[dim]{store.path}[/dim]  (나중에 `dasan init` 로 다시 바꿀 수 있어요)\n"
    )
