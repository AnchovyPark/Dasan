"""초기 설정(onboarding) — 대화 시작 전에 '어떤 에이전트/말투/역할'인지 먼저 정한다.

객관식이 아니라 열린 질문으로 자유롭게 받은 뒤, 사용자의 말을 그대로 저장하지 않고
모델이 '행동 지침'으로 다듬어(distill) alignment.md에 넣는다. 그래야 첫 메시지부터
정렬된 상태로 출발하고, 원문 말투가 아니라 정제된 규칙이 시스템 프롬프트에 들어간다.
"""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

DISTILL_SYSTEM = (
    "너는 사용자의 자유로운 답변을 개인 에이전트의 '행동 지침'으로 다듬는 편집자다. "
    "사용자가 원하는 말투·답변 방식·역할·규칙을 간결한 한국어 지시문으로 정리하라.\n"
    "규칙:\n"
    "- 사용자의 말을 그대로 옮기지 말고 명확한 행동 지시로 바꿔라.\n"
    "- 말투는 반드시 하나로 통일된 형태로 지정하라(예: '친근한 반말로 통일. 존댓말·개조식 혼용 금지').\n"
    "- 마크다운 불릿(- )만 출력하라. 서론·설명·코드펜스·제목 없이.\n"
    "- 사용자가 비운 항목은 지어내지 말고 생략하라."
)

# (라벨, 질문문) — 예시를 곁들여 자유 서술을 유도한다
QUESTIONS = [
    ("말투", "말투는 어떤 느낌이 좋아요?\n   예: 친구처럼 아주 편한 반말 / 친근하지만 예의 있게 / 공손하고 정중하게"),
    ("답변 방식", "답변은 어떤 식이 좋아요?\n   예: 결론만 짧게 / 필요하면 근거까지 자세히 / 상황에 따라"),
    ("역할", "저를 어떤 조수로 쓰고 싶어요? 주로 무슨 일을 맡길 건가요?\n   예: 이 프로젝트 코딩을 돕는 직설적인 시니어 개발자"),
    ("그 외", "그 외에 꼭 지켜줬으면 하는 규칙이 있으면 적어주세요. (없으면 Enter)"),
]

_DEFAULT = "# 말투\n- 해요체(부드러운 존댓말)로 통일. 개조식·반말 혼용 금지.\n# 답변\n- 결론부터 간결히."


def _collect(console: Console) -> dict[str, str]:
    answers: dict[str, str] = {}
    for key, q in QUESTIONS:
        console.print(f"[bold]{q}[/bold]")
        ans = Prompt.ask("  →", default="").strip()
        if ans:
            answers[key] = ans
    return answers


def _clean(text: str) -> str:
    """모델이 혹시 붙인 코드펜스를 걷어낸다."""
    t = text.strip()
    if t.startswith("```"):
        lines = [ln for ln in t.splitlines() if not ln.strip().startswith("```")]
        t = "\n".join(lines).strip()
    return t


def run_onboarding(service, console: Console | None = None) -> None:
    console = console or Console()
    console.print(
        Panel(
            "[bold]Dasan 초기 설정[/bold]\n"
            "어떤 조수이길 원하는지 편하게 말해 주세요. 제가 정리해서 반영할게요.",
            border_style="cyan",
        )
    )
    store = service.alignment
    if store.load().strip():
        console.print("[yellow]기존 설정을 덮어씁니다.[/yellow]\n")

    while True:
        answers = _collect(console)
        if not answers:
            console.print("[dim]입력이 없어 기본값(해요체·간결)으로 둘게요.[/dim]\n")
            store.write(_DEFAULT)
            return

        console.print("\n[dim]정리하는 중…[/dim]")
        raw = "\n".join(f"[{k}] {v}" for k, v in answers.items())
        try:
            distilled = _clean(service.complete(DISTILL_SYSTEM, raw))
        except Exception as e:
            console.print(f"[red]정리 중 오류: {e}[/red] 입력을 그대로 저장할게요.")
            distilled = ""
        if not distilled:  # 정제 실패 시 최소한 원문 요지라도 저장
            distilled = "\n".join(f"- {k}: {v}" for k, v in answers.items())

        console.print(Panel(distilled, title="이렇게 반영할게요", border_style="green"))
        if Confirm.ask("이대로 저장할까요?", default=True):
            store.write(distilled)
            console.print(
                f"[green]저장했어요.[/green] [dim]{store.path}[/dim]  "
                "(나중에 `dasan init` 로 바꿀 수 있어요)\n"
            )
            return
        console.print("[dim]다시 해볼게요.[/dim]\n")
