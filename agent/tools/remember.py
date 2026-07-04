"""remember_preference — 사용자의 지속적 선호를 ALIGNMENT에 저장하는 도구.

AlignmentStore 인스턴스를 클로저로 묶어 만든다(도구 자체는 상태를 갖지 않되
저장 위치는 서비스가 주입). 저장된 내용은 다음 요청부터 시스템 프롬프트에 반영된다.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..alignment import AlignmentStore
from .registry import Tool


class RememberInput(BaseModel):
    note: str = Field(
        description=(
            "사용자가 앞으로도 지켜주길 바라는 지속적 선호/규칙 한 줄. "
            "예: '답변은 항상 한국어로', '코드에는 주석 최소화', '결론부터 짧게'."
        )
    )


def make_remember_tool(store: AlignmentStore) -> Tool:
    def _run(inp: RememberInput) -> str:
        store.add(inp.note)
        return f"기억했다(다음 응답부터 적용): {inp.note}"

    return Tool(
        name="remember_preference",
        description=(
            "사용자가 앞으로도 계속 지켜주길 바라는 '지속적 선호/규칙'을 감지하면 호출해 영구 저장한다. "
            "일회성 지시(이번만 짧게 등)는 저장하지 말고, 계속 적용될 성향일 때만 저장하라."
        ),
        input_model=RememberInput,
        run=_run,
    )
