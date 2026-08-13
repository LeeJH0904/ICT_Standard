#!/usr/bin/env python3
"""tools/route_verify.py — 실제 FastAPI 라우트 ↔ `openapi.json` 오퍼레이션 대조.

개발_착수_지시서 §3.8(단계 6) 신설 검증기. 독립 입력 2종(F-080):
  ① `project_docs/api/openapi.json` — 설계 정본
  ② `backend/api.py::create_app()`가 실제로 등록한 FastAPI 라우트 — 구현

**개수가 아니라 집합을 대조한다**(F-056) — `POST /rules`를 지우고
`POST /health`를 만들어도 개수만 세면 통과한다. 경로+메서드 쌍을 정확히
맞춰본다.

실행: python tools/route_verify.py   (저장소 루트에서)
종료 코드: 통과 0 / 실패 1
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CODE = REPO_ROOT / "project_code"
OPENAPI_PATH = REPO_ROOT / "project_docs" / "api" / "openapi.json"

sys.path.insert(0, str(PROJECT_CODE))

#: API 명세서 §3 — 쓰기 7건. 개수가 아니라 이 집합과 정확히 일치해야 한다(F-056).
EXPECTED_WRITE_PATHS: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/api/v1/rules"),
    ("POST", "/api/v1/rules/{ruleId}/approve"),
    ("POST", "/api/v1/rules/{ruleId}/reject"),
    ("POST", "/api/v1/rules/{ruleId}/execute"),
    ("POST", "/api/v1/control"),
    ("PATCH", "/api/v1/device-property"),
    ("POST", "/api/v1/sim/inject"),
})

#: FastAPI가 자동으로 붙이는 문서 라우트 — openapi.json 오퍼레이션 대상이 아니다.
_DOC_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _openapi_operations() -> set[tuple[str, str]]:
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    ops: set[tuple[str, str]] = set()
    for path, methods in spec["paths"].items():
        for method in methods:
            if method.upper() in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                ops.add((method.upper(), path))
    return ops


def _fastapi_routes():
    from backend.api import create_app
    from contracts.fake_link import FakeFrameBuilder, FakeSiapLink

    link = FakeSiapLink()
    link.start("simulate")
    builder = FakeFrameBuilder(gcg_id=1)
    app = create_app(db_path=":memory:", link=link, builder=builder,
                      run_mode="simulate", proto_mode="strict")
    routes: set[tuple[str, str]] = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if path is None or methods is None or path in _DOC_ROUTES:
            continue
        for m in methods:
            if m == "HEAD":
                continue
            routes.add((m, path))
    return routes


def main() -> int:
    failures: list[str] = []

    spec_ops = _openapi_operations()
    impl_routes = _fastapi_routes()

    # 검사 1 — 경로+메서드 집합이 정확히 같다 (개수만이 아니라)
    missing = spec_ops - impl_routes
    extra = impl_routes - spec_ops
    if missing:
        failures.append(f"openapi.json 에는 있지만 구현에 없는 오퍼레이션: {sorted(missing)}")
    if extra:
        failures.append(f"구현에는 있지만 openapi.json 에 없는 라우트: {sorted(extra)}")
    if not missing and not extra:
        print(f"[OK] 라우트 집합 일치 - {len(spec_ops)}건")

    # 검사 2 — 오퍼레이션 개수 23종 (경로 22)
    if len(spec_ops) != 23:
        failures.append(f"openapi.json 오퍼레이션 수가 23이 아니다: {len(spec_ops)}")
    else:
        print("[OK] openapi.json 오퍼레이션 23건")
    n_paths = len({p for _, p in spec_ops})
    if n_paths != 22:
        failures.append(f"openapi.json 경로 수가 22가 아니다: {n_paths}")
    else:
        print("[OK] openapi.json 경로 22건")

    # 검사 3 — 쓰기 7건이 허용 집합과 정확히 일치 (F-056, 개수만 세지 않는다)
    write_routes = {(m, p) for m, p in impl_routes if m != "GET"}
    if write_routes != EXPECTED_WRITE_PATHS:
        failures.append(
            f"쓰기 경로 집합이 허용 목록과 다르다.\n"
            f"  누락: {sorted(EXPECTED_WRITE_PATHS - write_routes)}\n"
            f"  초과: {sorted(write_routes - EXPECTED_WRITE_PATHS)}"
        )
    else:
        print(f"[OK] 쓰기 경로 집합 일치 - {len(write_routes)}건 (API 명세서 §3)")

    # 검사 4 — openapi.json 의 쓰기 오퍼레이션도 같은 집합인가(설계 문서 자기 일관성)
    spec_writes = {(m, p) for m, p in spec_ops if m != "GET"}
    if spec_writes != EXPECTED_WRITE_PATHS:
        failures.append(
            f"openapi.json 의 쓰기 오퍼레이션이 허용 목록과 다르다: "
            f"{sorted(spec_writes.symmetric_difference(EXPECTED_WRITE_PATHS))}"
        )
    else:
        print("[OK] openapi.json 쓰기 오퍼레이션도 동일 집합")

    print()
    if failures:
        print(f"[FAIL] {len(failures)}건")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[PASS] tools/route_verify.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
