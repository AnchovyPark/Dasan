"""ReAct 루프: 추론 → 도구 호출 감지 → 도구 실행 → 관찰 반복 → 최종 답변.

루프는 특정 프로바이더 SDK를 모른다. 어댑터는 정규화된 응답
(text/tool_calls/raw_content/stop_reason)과 메시지 빌더(리스트 반환)를
제공하기만 하면 되므로, 어댑터를 교체해도 이 파일은 그대로다.
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
        on_event: Callable[..., None] | None = None,
    ) -> None:
        self._adapter = adapter
        self._registry = registry
        self._exposed = exposed_tools
        self._max_steps = max_steps
        self._system = system
        self._on_event = on_event or (lambda *a, **k: None)

    def run(self, messages: list[dict]) -> str:
        """messages를 제자리에서 이어붙이며 최종 답변 텍스트를 반환한다."""
        tools = self._registry.schemas(self._exposed)
        final_text = ""

        for _ in range(self._max_steps):
            resp = self._adapter.call(messages, tools, system=self._system)
            messages.extend(self._adapter.assistant_message(resp))
            if resp.text:
                final_text = resp.text

            if resp.stop_reason != "tool_use":
                self._emit_stop(resp)
                return final_text

            results = []
            for tc in resp.tool_calls:
                self._on_event("tool_call", name=tc.name, input=tc.input)
                output, is_error = self._registry.execute(tc.name, tc.input)
                self._on_event(
                    "tool_result", name=tc.name, output=output, is_error=is_error
                )
                results.append((tc, output, is_error))
            messages.extend(self._adapter.tool_result_message(results))

        self._on_event("max_steps")
        return final_text

    def _emit_stop(self, resp: Any) -> None:
        if resp.stop_reason == "refusal":
            self._on_event("refusal")
        elif resp.stop_reason == "max_tokens":
            self._on_event("truncated")
