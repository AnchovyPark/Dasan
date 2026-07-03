"""ReAct 루프: 추론 → 도구 호출 감지 → 도구 실행 → 관찰 반복 → 최종 답변.

루프는 특정 프로바이더 SDK를 모른다. 어댑터는 정규화된 응답과 메시지
빌더(리스트 반환), 그리고 선택적 토큰 스트리밍(on_delta)만 제공하면 된다.
이벤트/스트리밍 콜백은 run() 인자로 받아 프론트엔드마다 다르게 꽂는다.
"""
from __future__ import annotations

from typing import Any, Callable

from ..tools.registry import ToolRegistry

DEFAULT_SYSTEM = (
    "너는 로컬 파일과 프로젝트를 다루는 개인 에이전트다. "
    "파일 내용이 필요하면 read_file 도구를 사용해 실제로 읽은 뒤 답하라. "
    "추측하지 말고 도구로 확인하라."
)


class AgentLoop:
    def __init__(
        self,
        adapter: Any,
        registry: ToolRegistry,
        exposed_tools: list[str],
        max_steps: int = 10,
        system: str = DEFAULT_SYSTEM,
    ) -> None:
        self._adapter = adapter
        self._registry = registry
        self._exposed = exposed_tools
        self._max_steps = max_steps
        self._system = system

    def run(
        self,
        messages: list[dict],
        on_event: Callable[..., None] | None = None,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        """messages를 제자리에서 이어붙이며 최종 답변 텍스트를 반환한다.

        on_event: 도구 호출/결과/중단 등 상태 알림
        on_delta: 답변 토큰 스트리밍 (있으면 어댑터가 실시간으로 흘림)
        """
        emit = on_event or (lambda *a, **k: None)
        tools = self._registry.schemas(self._exposed)
        final_text = ""

        for _ in range(self._max_steps):
            resp = self._adapter.call(
                messages, tools, system=self._system, on_delta=on_delta
            )
            messages.extend(self._adapter.assistant_message(resp))
            if resp.text:
                final_text = resp.text

            if resp.stop_reason != "tool_use":
                self._emit_stop(resp, emit)
                return final_text

            results = []
            for tc in resp.tool_calls:
                emit("tool_call", name=tc.name, input=tc.input)
                output, is_error = self._registry.execute(tc.name, tc.input)
                emit("tool_result", name=tc.name, output=output, is_error=is_error)
                results.append((tc, output, is_error))
            messages.extend(self._adapter.tool_result_message(results))

        emit("max_steps")
        return final_text

    @staticmethod
    def _emit_stop(resp: Any, emit: Callable[..., None]) -> None:
        if resp.stop_reason == "refusal":
            emit("refusal")
        elif resp.stop_reason == "max_tokens":
            emit("truncated")
