"""OpenAI(ChatGPT 구독) OAuth 어댑터 — Responses API 호출을 통일 인터페이스로 감쌈.

TokenStore에서 bearer 토큰을 받아 ChatGPT/Codex 백엔드의 Responses API에
스트리밍으로 요청하고, 응답을 정규화 타입(ModelResponse/ToolCall)으로 바꾼다.
루프는 이 파일의 세부(엔드포인트/헤더/Responses 포맷)를 알지 못한다.

⚠️ 백엔드 계약(base_url·헤더·모델명·Responses 스키마)은 OpenAI가 문서화하지
않았고 Codex 버전마다 바뀐다. 이 부분이 실행 시 가장 먼저 손볼 조각이다
(config의 AGENT_BASE_URL / AGENT_MODEL 로 조정 가능).
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass

import httpx

from ..auth.store import TokenStore


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ModelResponse:
    text: str
    tool_calls: list[ToolCall]
    raw_content: list[dict]  # 다음 턴에 되돌릴 Responses output 아이템
    stop_reason: str | None


class OpenAIOAuthAdapter:
    def __init__(
        self,
        store: TokenStore,
        model: str,
        base_url: str,
        reasoning_effort: str = "high",
        web_search: bool = False,
    ) -> None:
        self._store = store
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._session_id = str(uuid.uuid4())
        # gpt-5.x는 추론 강도를 조절할 수 있다. off/none/""이면 아예 안 보낸다.
        self._reasoning = (reasoning_effort or "").strip().lower()
        self._web_search = web_search

    def call(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
        on_delta=None,
        on_event=None,
    ) -> ModelResponse:
        body: dict = {
            "model": self._model,
            "input": messages,
            "stream": True,
            "store": False,
        }
        if tools:  # 도구 없는 1회성 호출(정제·요약 등)에서는 도구를 아예 붙이지 않는다
            body["tools"] = self._to_openai_tools(tools)
            if self._web_search:
                # 백엔드 네이티브 웹 검색 — 실행은 서버가 하고 결과만 응답에 섞여 온다
                body["tools"].append({"type": "web_search"})
        if system:
            body["instructions"] = system
        if self._reasoning and self._reasoning not in ("off", "none"):
            body["reasoning"] = {"effort": self._reasoning}
        return self._normalize(self._request(body, on_delta=on_delta, on_event=on_event))

    # --- HTTP (스트리밍 + 401 재시도) ---

    def _request(self, body: dict, _retried: bool = False, on_delta=None, on_event=None) -> dict:
        headers = {
            "Authorization": f"Bearer {self._store.access_token()}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "session_id": self._session_id,
            "originator": "codex_cli_rs",
        }
        acct = self._store.account_id()
        if acct:
            headers["chatgpt-account-id"] = acct

        url = f"{self._base_url}/responses"
        debug = bool(os.environ.get("AGENT_DEBUG"))
        if debug:
            print("[DEBUG] account_id:", "설정됨" if acct else "없음")
            print("[DEBUG] 요청 본문:", json.dumps(body, ensure_ascii=False)[:2000])

        # store:false 스트리밍에서는 response.completed의 output이 비어 오므로,
        # 실제 결과 아이템은 response.output_item.done 이벤트에서 누적한다.
        output_items: list[dict] = []
        completed_output: list | None = None
        raw_lines: list[str] = []
        seen_types: list[str] = []
        with httpx.stream("POST", url, headers=headers, json=body, timeout=300) as r:
            if r.status_code == 401 and not _retried:
                self._store.force_refresh()
                return self._request(body, _retried=True, on_delta=on_delta, on_event=on_event)
            if r.status_code >= 400:
                r.read()  # 스트리밍 응답의 본문을 읽어 에러 메시지에 담는다
                raise RuntimeError(f"백엔드 {r.status_code}: {r.text}")
            for line in r.iter_lines():
                if line:
                    raw_lines.append(line)
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].lstrip()
                if data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                etype = event.get("type")
                if debug and etype:
                    seen_types.append(etype)
                if etype in ("response.failed", "error"):
                    raise RuntimeError(f"모델 오류 이벤트: {event}")
                if etype == "response.output_text.delta" and on_delta:
                    on_delta(event.get("delta") or "")
                if etype == "response.output_item.done" and event.get("item"):
                    item = event["item"]
                    output_items.append(item)
                    if item.get("type") == "web_search_call" and on_event:
                        # action이 search면 query, open_page면 url이 들어 있다
                        action = item.get("action") or {}
                        label = action.get("query") or action.get("url") or ""
                        if label:
                            on_event("web_search", query=label)
                elif etype in ("response.completed", "response.done") and "response" in event:
                    completed_output = event["response"].get("output")

        if debug:
            try:
                with open("/tmp/dasan_raw.txt", "w") as f:
                    f.write("\n".join(raw_lines))
            except OSError:
                pass
            print("[DEBUG] 이벤트타입:", seen_types)

        # 스트리밍으로 누적한 아이템 우선, 없으면 completed의 output, 그것도 없으면 단일 JSON
        output = output_items or completed_output
        if output is None:
            body_text = "\n".join(raw_lines)
            try:
                obj = json.loads(body_text)
                src = obj.get("response", obj) if isinstance(obj, dict) else {}
                output = src.get("output")
            except json.JSONDecodeError:
                output = None

        if output is None:
            if debug:
                print("[DEBUG] 원본 앞부분:", "\n".join(raw_lines)[:1500])
            raise RuntimeError("모델 응답에서 output을 찾지 못했습니다 (AGENT_DEBUG=1)")
        return {"output": output}

    # --- 정규화 ---

    def _normalize(self, response_obj: dict) -> ModelResponse:
        output = response_obj.get("output", [])
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for item in output:
            t = item.get("type")
            if t == "message":
                for c in item.get("content", []):
                    if c.get("type") in ("output_text", "text"):
                        text_parts.append(c.get("text", ""))
            elif t == "function_call":
                try:
                    args = json.loads(item.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(
                    ToolCall(id=item.get("call_id"), name=item.get("name"), input=args)
                )
        stop_reason = "tool_use" if tool_calls else "end_turn"
        # 되돌릴 때 reasoning 등은 제외해 400 위험을 줄인다(MVP 단순화).
        raw = [it for it in output if it.get("type") in ("message", "function_call")]
        if os.environ.get("AGENT_DEBUG"):
            print("[DEBUG] output 아이템 타입:", [it.get("type") for it in output])
            print(f"[DEBUG] stop={stop_reason} text_len={len(''.join(text_parts))} tools={len(tool_calls)}")
            if not text_parts and not tool_calls and output:
                print("[DEBUG] 첫 아이템 원본:", json.dumps(output[0], ensure_ascii=False)[:1000])
        return ModelResponse("".join(text_parts), tool_calls, raw, stop_reason)

    # --- 스키마/메시지 변환 ---

    @staticmethod
    def _to_openai_tools(tools: list[dict]) -> list[dict]:
        # 레지스트리의 중립 스키마({name, description, input_schema}) → Responses function 툴
        return [
            {
                "type": "function",
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            }
            for t in tools
        ]

    @staticmethod
    def user_message(text: str) -> list[dict]:
        return [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}]

    @staticmethod
    def assistant_message(resp: ModelResponse) -> list[dict]:
        return list(resp.raw_content)

    @staticmethod
    def tool_result_message(results: list[tuple[ToolCall, str, bool]]) -> list[dict]:
        out = []
        for tc, output, is_error in results:
            payload = f"ERROR: {output}" if is_error else output
            out.append({"type": "function_call_output", "call_id": tc.id, "output": payload})
        return out
