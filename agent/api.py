from __future__ import annotations

import os
from typing import Callable

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .config import load_config
from .service import AgentService


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    workspace: str


class HealthResponse(BaseModel):
    status: str
    logged_in: bool
    workspace: str
    default_session: str


app = FastAPI(title="Dasan Agent API")


def _require_token(authorization: str | None) -> None:
    token = os.environ.get("DASAN_API_TOKEN") or ""
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="invalid DASAN_API_TOKEN")


def _with_service(fn: Callable[[AgentService], object]) -> object:
    service = AgentService(load_config())
    try:
        return fn(service)
    finally:
        service.close()


def _default_session() -> str:
    return os.environ.get("DASAN_API_SESSION") or "bongsu"


@app.get("/api/health", response_model=HealthResponse)
def health(authorization: str | None = Header(default=None)) -> HealthResponse:
    _require_token(authorization)

    def run(service: AgentService) -> HealthResponse:
        return HealthResponse(
            status="ok",
            logged_in=service.logged_in(),
            workspace=service.workspace_root(),
            default_session=_default_session(),
        )

    return _with_service(run)  # type: ignore[return-value]


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest, authorization: str | None = Header(default=None)) -> ChatResponse:
    _require_token(authorization)

    def run(service: AgentService) -> ChatResponse:
        if not service.logged_in():
            raise HTTPException(status_code=401, detail="Dasan login required")

        sid = request.session_id or _default_session()
        if not service.session_exists(sid):
            sid = service.new_session(sid)

        reply = service.respond(sid, request.message)
        return ChatResponse(
            reply=reply,
            session_id=sid,
            workspace=service.workspace_root(),
        )

    return _with_service(run)  # type: ignore[return-value]
