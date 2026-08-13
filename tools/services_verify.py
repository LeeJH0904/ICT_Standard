#!/usr/bin/env python3
"""tools/services_verify.py — 0937 서비스 요구사항이 대조표 문구가 아니라
**실제 소스**에서 닫혀 있는가(F-191).

`project_docs/services/services_verify.py`는 설계 문서 4종(대조표·조항·
아키텍처·schema.sql/openapi.json)만 서로 대조한다 — `project_code/` 구현을
읽지 않는다(§2 디렉터리 규칙, "project_docs/**/*_verify.py 는 설계 문서를
본다"). 그래서 함수가 **정의**돼 있다는 사실과 그 함수가 **실제로 호출**
되는지는 구분하지 못했다 — `fms.check_stale_devices()`가 정의만 되고
아무 데서도 불리지 않는데도 대조표는 6.4-3을 ✅로 판정했다(F-191).

이 검증기는 그 반대쪽, "구현이 실제로 그 진입점을 쓰는가"만 본다.

실행: python tools/services_verify.py   (저장소 루트에서)
종료 코드: 통과 0 / 실패 1
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "project_code" / "backend"


def _iter_backend_py() -> list[Path]:
    return sorted(p for p in BACKEND_DIR.rglob("*.py") if "__pycache__" not in p.parts)


#: F-195 — 정적으로 결코 실행되지 않는 문장을 걸러낸다. `ast.walk()`는
#: `if False: ...` 블록도, `return` 뒤에 남은 죽은 코드도 그냥 방문한다 —
#: "호출 흔적이 소스에 있다"와 "그 호출이 실행될 수 있다"는 다르다(F-195
#: 재현: `if False:` 안의 4개 호출이 전부 "운영 코드 호출"로 잡혔다).
#: **완전한 도달가능성(호출 그래프) 분석은 아니다** — 상수 조건 분기와
#: return/raise/continue/break 뒤의 후속 문장만 죽은 코드로 인정한다.
#: 이 경계 밖(예: 아무도 안 부르는 함수 전체)은 놓칠 수 있다는 뜻이고,
#: 그 한계는 의도적이다(§4.3 검증기 비례성 — 전체 호출 그래프 분석은
#: 이 프로젝트 규모에 비해 과하다).
_TERMINALS = (ast.Return, ast.Raise, ast.Continue, ast.Break)


def _dead_node_ids(tree: ast.Module) -> set[int]:
    dead: set[int] = set()

    def mark_dead(node: ast.AST) -> None:
        for n in ast.walk(node):
            dead.add(id(n))

    def visit_block(stmts: list[ast.stmt]) -> None:
        terminated = False
        for stmt in stmts:
            if terminated:
                mark_dead(stmt)
                continue
            visit_stmt(stmt)
            if isinstance(stmt, _TERMINALS):
                terminated = True

    def visit_stmt(stmt: ast.stmt) -> None:
        if isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Constant):
            live, dead_branch = (stmt.body, stmt.orelse) if stmt.test.value else (stmt.orelse, stmt.body)
            for s in dead_branch:
                mark_dead(s)
            visit_block(live)
            return
        if isinstance(stmt, ast.Try):
            visit_block(stmt.body)
            for h in stmt.handlers:
                visit_block(h.body)
            visit_block(stmt.orelse)
            visit_block(stmt.finalbody)
            return
        for field in ("body", "orelse", "finalbody"):
            val = getattr(stmt, field, None)
            if isinstance(val, list) and val and isinstance(val[0], ast.stmt):
                visit_block(val)

    visit_block(tree.body)
    return dead


def _live_calls(tree: ast.Module, dead: set[int]) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and id(n) not in dead]


def _call_sites(files: list[Path], func_name: str) -> list[tuple[Path, int]]:
    """`func_name(...)` 형태의 **살아 있는** 호출 지점만 찾는다(정의도,
    죽은 코드도 아니다). AST 로 `ast.Call`을 본다 — 문자열 grep 은
    주석·독스트링의 언급까지 집어 F-191 같은 "언급은 있지만 배선은
    없다"를 놓친다."""
    hits: list[tuple[Path, int]] = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in _live_calls(tree, _dead_node_ids(tree)):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else \
                   fn.id if isinstance(fn, ast.Name) else None
            if name == func_name:
                hits.append((f, node.lineno))
    return hits


def _record_alert_kinds(files: list[Path]) -> dict[str, list[tuple[Path, int]]]:
    """`record_alert(..., kind="X", ...)`의 **살아 있는** 호출에서 `kind`
    키워드 인자의 문자열 리터럴 값을 모은다. f-string 등 동적 값은 세지
    않는다(정적 분석의 한계 — 이 프로젝트의 실제 호출은 전부 리터럴이다)."""
    out: dict[str, list[tuple[Path, int]]] = {}
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in _live_calls(tree, _dead_node_ids(tree)):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else \
                   fn.id if isinstance(fn, ast.Name) else None
            if name != "record_alert":
                continue
            for kw in node.keywords:
                if kw.arg == "kind" and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    out.setdefault(kw.value.value, []).append((f, node.lineno))
    return out


def main() -> int:
    files = _iter_backend_py()
    failures: list[str] = []

    # 6.4-3 — "정해진 시간에 데이터가 수집되지 않는 경우 알림" 이 실제로
    # 도는가. 정의 파일(fms.py)·테스트 바깥에서 최소 1건 호출돼야 한다 —
    # 테스트만 부르고 실제 배선(api.py)이 빠지는 회귀는 테스트 호출만으로
    # "외부 호출 있음"이 되면 못 잡는다.
    calls = _call_sites(files, "check_stale_devices")
    production = [(f, ln) for f, ln in calls
                  if f.name != "fms.py" and "tests" not in f.parts]
    if production:
        print(f"[OK] check_stale_devices() 운영 코드 호출 {len(production)}건 (0937 6.4-3)")
        for f, ln in production:
            print(f"       - {f.relative_to(REPO_ROOT)}:{ln}")
    else:
        failures.append(
            "check_stale_devices() 가 fms.py·backend/tests/ 바깥(운영 코드)에서 호출되지 않는다 "
            "(정의만 있고 배선이 없다 — F-191)"
        )

    # 6.5-2 — "긴급 상황시 사용자 알림"의 alert.kind 4종 중, 프레임에서
    # 오지 않는 두 종류(CONTROL_TIMEOUT·NO_DATA)가 실제 record_alert()
    # 호출에 등장하는가. NODE_ERROR·DISCONNECT 는 ingest.py 경로(§ frame
    # 소비)에서 이미 별도로 나온다 — 여기서는 다시 세지 않는다.
    kinds = _record_alert_kinds(files)
    required = {"NODE_ERROR", "DISCONNECT", "CONTROL_TIMEOUT", "NO_DATA"}
    missing_kinds = sorted(required - set(kinds))
    if missing_kinds:
        failures.append(
            f"record_alert(kind=...) 호출에 등장하지 않는 alert.kind: {missing_kinds} "
            "(0937 6.5-2 — 긴급 상황 알림 4종 중 일부가 실제로 발생하지 않는다)"
        )
    else:
        print(f"[OK] alert.kind 4종({sorted(required)}) 전부 실제 record_alert() 호출에 등장 (0937 6.5-2)")

    print()
    if failures:
        print(f"[FAIL] {len(failures)}건")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[PASS] tools/services_verify.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
