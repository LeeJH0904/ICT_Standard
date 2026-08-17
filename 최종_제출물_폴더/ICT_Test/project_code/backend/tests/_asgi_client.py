"""
backend/tests/_asgi_client.py — 의존성 없는 최소 ASGI 테스트 클라이언트.

`httpx`(FastAPI/Starlette `TestClient`가 요구하는 라이브러리)는 `wheels/`에
없다 — 새 의존성을 추가하려면 CLAUDE.md §4.1 "의존성 최소화, 추가 전 사용자
확인"을 거쳐야 한다. `pytest backend/tests/test_api.py`는 단계 6 출구
명령이라 오프라인 판정 환경에서도 반드시 통과해야 하므로, 이미 API
명세서 §7.0이 `jsonschema` 대신 둔 "60줄짜리 자체 평가기"와 같은 원칙으로
표준 라이브러리(`asyncio`)만으로 ASGI 요청 1건을 흘려보내는 최소
드라이버를 둔다. `tools/route_verify.py`·`tools/gate_e2e.py`도 이 모듈을
공유한다 — 같은 이유로 같은 반례가 생기지 않게 한다(F-080과 같은 원칙:
검증기가 검증 대상과 다른 독립 경로로 요청을 흘려보내면 자기 검증
순환이 된다 — 여기서는 검증기 종류가 아니라 "새 의존성을 피한다"는
목적의 중복 회피다).
"""
from __future__ import annotations

import asyncio
import json as _json
from typing import Any


class ASGIResponse:
    def __init__(self, status: int, headers: list[tuple[bytes, bytes]], body: bytes) -> None:
        self.status_code = status
        self.headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in headers}
        self._body = body

    def json(self) -> Any:
        return _json.loads(self._body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self._body.decode("utf-8", "replace")


def _build_scope(method: str, path: str, query: str, headers: dict[str, str] | None,
                  body: bytes, has_json: bool) -> dict:
    hdr_list: list[tuple[bytes, bytes]] = []
    if has_json:
        hdr_list.append((b"content-type", b"application/json"))
    for k, v in (headers or {}).items():
        # ASGI 스펙(및 HTTP/2)은 헤더 이름을 소문자로 요구한다 — Starlette가
        # 대소문자를 그대로 신뢰해 매칭하므로, 대문자가 섞이면(예: X-User-Id)
        # FastAPI 의 Header(..., alias="X-User-Id") 의존성이 "없음"으로 본다.
        hdr_list.append((k.lower().encode("latin-1"), str(v).encode("latin-1")))
    hdr_list.append((b"content-length", str(len(body)).encode("latin-1")))
    return {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method.upper(), "path": path, "raw_path": path.encode("utf-8"),
        "query_string": query.encode("utf-8"), "headers": hdr_list,
        "client": ("testclient", 12345), "server": ("testserver", 80), "scheme": "http",
    }


async def _call_async(app, method: str, path: str, json_body: dict | None,
                       headers: dict[str, str] | None, query: str) -> ASGIResponse:
    body = b"" if json_body is None else _json.dumps(json_body).encode("utf-8")
    scope = _build_scope(method, path, query, headers, body, json_body is not None)

    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    status_holder: dict = {}
    headers_holder: list = []
    chunks: list[bytes] = []

    async def send(message):
        if message["type"] == "http.response.start":
            status_holder["status"] = message["status"]
            headers_holder.extend(message.get("headers", []))
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return ASGIResponse(status_holder.get("status", 0), headers_holder, b"".join(chunks))


def call(app, method: str, path: str, *, json: dict | None = None,
         headers: dict[str, str] | None = None, query: str = "") -> ASGIResponse:
    """요청 1건을 ASGI 앱에 흘려보내고 응답 전체를 모아 돌려준다(비스트리밍)."""
    return asyncio.run(_call_async(app, method, path, json, headers, query))


async def _call_stream_async(app, path: str, query: str, headers: dict[str, str] | None,
                              max_chunks: int, timeout: float) -> tuple[int, bytes]:
    scope = _build_scope("GET", path, query, headers, b"", False)

    async def receive():
        await asyncio.sleep(3600)   # 클라이언트가 끊기 전까지 더 보낼 요청 본문이 없다
        return {"type": "http.disconnect"}

    status_holder: dict = {}
    chunks: list[bytes] = []
    done = asyncio.Event()

    async def send(message):
        if message["type"] == "http.response.start":
            status_holder["status"] = message["status"]
        elif message["type"] == "http.response.body":
            if message.get("body"):
                chunks.append(message["body"])
            if len(chunks) >= max_chunks:
                done.set()

    task = asyncio.ensure_future(app(scope, receive, send))
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
    return status_holder.get("status", 0), b"".join(chunks)


def call_stream(app, path: str, *, query: str = "", headers: dict[str, str] | None = None,
                max_chunks: int = 1, timeout: float = 2.0) -> tuple[int, bytes]:
    """SSE 등 스트리밍 응답에서 청크 최대 `max_chunks`개(또는 `timeout`초)
    만큼만 모으고 끊는다 — 무한 제너레이터를 끝까지 기다리지 않는다."""
    return asyncio.run(_call_stream_async(app, path, query, headers, max_chunks, timeout))
