#!/usr/bin/env python3
"""tools/nodetype_verify.py — `project_code/backend/**`에 노드·디바이스
**종류** 하드코딩이 없는가(CLAUDE.md §1-6, 주장 3 "서버 코드 수정 0줄").

CLAUDE.md §0 이 증명하라는 것은 "새 MCU 보드를 추가해도 backend/ 를 고치지
않는다"이다 — 이건 **보드/MCU 종류**의 문제이지, 물리량 서브타입(TEMPERATURE
등)을 SQL 테이블명으로 매핑하는 것과는 다른 층위다. 후자는 SQLite 테이블
명이 리터럴일 수밖에 없고, 이미 `contracts/frame.py::Subtype` 레지스트리와
`schema.sql`의 CHECK 목록을 그대로 미러링한다(0937_요구사항_대조표.md §4.3
"종류는 Subtype 레지스트리 조회로만 해석") — 그 자체가 새 MCU 보드
추가와는 무관하다.

다섯 가지를 본다:
  ① 보드/MCU 이름 리터럴이 `backend/**` 소스 텍스트에 전혀 없다.
  ② API 쿼리 파라미터 `subtype`은 열거형(enum/Literal)이 아니라 자유
     문자열이다 — openapi.json(F-030 근거)과 실제 FastAPI 시그니처 양쪽.
  ③ `backend/**`에 특정 `node_id` 정수 리터럴을 조건으로 분기하는 코드가
     없다 — 있으면 "그 노드"를 위한 특례가 서버 코드에 박힌 것이다.
  ④ `backend/services/**`에 액추에이터 종류 이름(1369-P1 6.3.4 / 물리
     장치명)이 문자열 리터럴로 없다(F-190) — 있으면 "그 장치"를 위한
     문구가 서비스 코드에 박힌 것이다. ①~③은 보드·노드 하드코딩만
     보고 장치 종류 하드코딩은 놓쳤다(F-190 재현: 기존 코드가 그대로
     있는데도 통과했다) — 이 항목이 그 틈을 메운다.
  ⑤ (F-194) ④는 토큰 6개로 닫힌 목록이라 목록 밖 장치명("환기팬" 등)은
     구조적으로 놓친다 — 새 장치명은 무한하므로 어떤 목록도 완전할 수
     없다. 그래서 ⑤는 문자열을 나열하지 않고 **직접 실행**해 증명한다 —
     `mms._threshold_draft()`에 서로 다른 무작위 마커 2개를 `output_spec.
     recommend_action`으로 넣어 호출하고, (a) 각 출력이 자신의 마커를
     그대로 담는지, (b) 마커 자리를 지운 두 출력이 완전히 같은지(다른
     요인이 섞이지 않았는지) 본다 — "출력이 그 데이터 필드의 순수
     함수"임을 증명하면 어떤 장치명을 넣어도 하드코딩될 수 없다.

독립 입력(F-080) — `project_docs/api/openapi.json`(설계)과
`backend/**/*.py` 소스(구현) 양쪽을 함께 본다.

실행: python tools/nodetype_verify.py   (저장소 루트에서)
종료 코드: 통과 0 / 실패 1
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECT_CODE = REPO_ROOT / "project_code"
BACKEND_DIR = PROJECT_CODE / "backend"
SERVICES_DIR = BACKEND_DIR / "services"
OPENAPI_PATH = REPO_ROOT / "project_docs" / "api" / "openapi.json"
sys.path.insert(0, str(PROJECT_CODE))

#: CLAUDE.md §0 주장 1 — "MCU 3종이 동일 응용계층으로 혼용 동작". 이 이름들이
#: backend/ 에 등장하면 그 보드를 위한 특례 코드가 있다는 뜻이다.
_BOARD_TOKENS = ("arduino", "uno", "mega2560", "esp32", "esp-32", "esp8266",
                  "attiny", "attiny85", "pro_mini", "promini", "pro mini")

#: F-190 — 1369-P1 6.3.4 액추에이터 명칭(firmware/core/subtype_registry.h 의
#: 주석과 동일 어휘). 이 토큰이 backend/services/**/*.py 의 "문자열 리터럴"
#: (docstring 제외)에 등장하면 그 장치를 위한 문구가 서비스 코드에 박힌
#: 것이다 — 장치별 문구는 `control_model.output_spec`(DB, 데이터)에서만
#: 나와야 한다(§3.5 결정표).
_DEVICE_KIND_TOKENS = ("창 개폐", "보온덮개", "송풍기", "관수", "냉난방", "차광")


def _docstring_const_ids(tree: ast.AST) -> set[int]:
    """모듈·클래스·함수의 첫 문장이 문자열 리터럴이면 그 노드는 독스트링
    이다 — 설계 의도를 설명하는 산문이지 사용자에게 나가는 생성 문구가
    아니므로 장치 토큰 검사에서 뺀다."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _iter_backend_py() -> list[Path]:
    return sorted(p for p in BACKEND_DIR.rglob("*.py") if "__pycache__" not in p.parts)


#: 오탐 허용 목록 — 반드시 사유를 적는다(fix_log/meta_verify.py 의 ALLOW 와
#: 같은 원칙). (파일명, 줄에 포함된 부분문자열) 쌍으로 매칭한다.
_ALLOW: set[tuple[str, str]] = {
    # ingest.py 는 "보드 종류가 이 함수에 전달되지 않는다"는 사실을
    # 설명하려고 보드 이름을 **부재의 증거**로 언급한다 — 실제로 그
    # 이름으로 분기하지 않는다(코드 자체가 model_name 을 Subtype 코드에서만
    # 유도한다). 하드코딩의 반대 사례를 서술한 주석까지 걸리는 오탐이다.
    ("ingest.py", "어느 보드(Uno/Pro Mini/"),
    ("ingest.py", "ESP32)가 보냈는지는 이 함수에 아예 전달되지 않는다"),
}


def _allowed(fname: str, line: str) -> bool:
    return any(f == fname and frag in line for f, frag in _ALLOW)


def _check_board_tokens(files: list[Path]) -> list[str]:
    failures = []
    for f in files:
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            lower = line.lower()
            for token in _BOARD_TOKENS:
                if token in lower and not _allowed(f.name, line):
                    failures.append(
                        f"{f.relative_to(REPO_ROOT)}:{i}: 보드/MCU 이름 리터럴 발견 - {token!r}"
                    )
    return failures


def _check_node_id_literal_branch(files: list[Path]) -> list[str]:
    """`if <expr with name node_id> == <상수>:` 형태 — 특정 노드 하나를
    겨냥한 분기. 변수명이 정확히 'node_id'일 때만 본다(오탐 최소화)."""
    failures = []
    for f in files:
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            left = node.left
            if not (isinstance(left, ast.Name) and left.id == "node_id"):
                continue
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) \
                        and isinstance(comparator.value, int):
                    failures.append(
                        f"{f.relative_to(REPO_ROOT)}:{node.lineno}: "
                        f"node_id == {comparator.value} - 특정 노드 하드코딩 의심"
                    )
    return failures


def _check_device_kind_literal(files: list[Path]) -> list[str]:
    """`backend/services/**/*.py`의 문자열 리터럴(독스트링 제외 — f-string
    리터럴 조각도 `ast.Constant`로 잡힌다)에 액추에이터 명칭이 있는가
    (F-190). `backend/services/` 바깥은 보지 않는다 — 테스트 픽스처의
    자유 문장(WIZARD 초안 예시 등)과 repository.py 독스트링의 서술은
    "서버가 생성하는 문구"가 아니라 오탐이기 때문이다(F-190 근거)."""
    failures = []
    for f in files:
        if SERVICES_DIR not in f.parents:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        doc_ids = _docstring_const_ids(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            if id(node) in doc_ids:
                continue
            for token in _DEVICE_KIND_TOKENS:
                if token in node.value and not _allowed(f.name, node.value):
                    failures.append(
                        f"{f.relative_to(REPO_ROOT)}:{node.lineno}: "
                        f"장치 종류 문자열 하드코딩 의심 - {token!r} in {node.value!r}"
                    )
    return failures


def _check_threshold_draft_is_data_driven() -> list[str]:
    """F-194 — ④의 6토큰 목록은 구조적으로 불완전하다(목록 밖 장치명은
    통과한다, 재현: "환기팬 가동"). 여기서는 금지어를 나열하지 않고
    직접 실행해 "출력이 `output_spec.recommend_action`의 순수 함수"임을
    증명한다 — 이 성질이 성립하면 그 값이 무엇이든(목록에 있든 없든)
    소스에 다른 문구가 섞여 나올 수 없다."""
    failures: list[str] = []
    from backend.services import mms

    class _FakeModel:
        def __init__(self, output_spec: str) -> None:
            self.output_spec = output_spec

    forecast = {"response": {"body": {"items": {"item": [{"category": "TMX", "fcstValue": "40"}]}}}}
    inputs = {"crop_tmax_c": 10, "forecast_payload": forecast}   # tmax(40) > threshold(10) 분기 고정

    marker_a, marker_b = os.urandom(8).hex(), os.urandom(8).hex()
    model_a = _FakeModel(json.dumps({"recommend_action": marker_a}))
    model_b = _FakeModel(json.dumps({"recommend_action": marker_b}))
    out_a = mms._threshold_draft(model_a, inputs)
    out_b = mms._threshold_draft(model_b, inputs)

    if marker_a not in out_a:
        failures.append(
            f"_threshold_draft() 출력이 output_spec.recommend_action 을 반영하지 않는다 "
            f"(마커 {marker_a!r} 이 출력에 없음 - 하드코딩된 고정 문구를 의심)"
        )
    if marker_b not in out_b:
        failures.append(
            f"_threshold_draft() 출력이 output_spec.recommend_action 을 반영하지 않는다 "
            f"(마커 {marker_b!r} 이 출력에 없음 - 하드코딩된 고정 문구를 의심)"
        )
    if not failures and out_a.replace(marker_a, "\0") != out_b.replace(marker_b, "\0"):
        failures.append(
            "recommend_action 마커만 바꿨는데 마커 자리 밖에서도 출력이 달라진다 "
            f"(a={out_a!r} b={out_b!r}) - 데이터 외 다른 요인이 섞여 있다"
        )
    return failures


def _check_subtype_param_untyped() -> list[str]:
    """`openapi.json`의 `subtype` 파라미터 컴포넌트가 enum 을 갖지 않는가."""
    failures = []
    spec = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    param = spec.get("components", {}).get("parameters", {}).get("subtype")
    if param is None:
        failures.append("openapi.json 에 components.parameters.subtype 이 없다")
        return failures
    if "enum" in param.get("schema", {}):
        failures.append("openapi.json 의 subtype 파라미터가 enum 으로 닫혀 있다 - 열거 금지(F-030 근거)")
    return failures


def _check_api_py_subtype_signature() -> list[str]:
    """`backend/api.py`의 라우트 함수 시그니처에서 `subtype` 파라미터가
    `Literal[...]`·`Enum` 서브클래스가 아니라 `str | None`인지 AST로 본다."""
    failures = []
    api_path = BACKEND_DIR / "api.py"
    tree = ast.parse(api_path.read_text(encoding="utf-8"), filename=str(api_path))
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for arg in node.args.args + node.args.kwonlyargs:
            if arg.arg != "subtype" or arg.annotation is None:
                continue
            found = True
            ann_src = ast.dump(arg.annotation)
            if "Literal" in ann_src or "Enum" in ann_src:
                failures.append(
                    f"backend/api.py:{node.lineno} ({node.name}) - subtype 파라미터가 "
                    f"Literal/Enum 으로 닫혀 있다: {ann_src}"
                )
    if not found:
        failures.append("backend/api.py 에 subtype 파라미터를 받는 라우트가 없다 - 검사 대상 소실")
    return failures


def main() -> int:
    if not BACKEND_DIR.exists():
        print(f"[FAIL] {BACKEND_DIR} 없음")
        return 1

    files = _iter_backend_py()
    failures: list[str] = []

    board_failures = _check_board_tokens(files)
    if board_failures:
        failures.extend(board_failures)
    else:
        print(f"[OK] 보드/MCU 이름 리터럴 0건 (backend/**/*.py {len(files)}개 파일)")

    node_failures = _check_node_id_literal_branch(files)
    if node_failures:
        failures.extend(node_failures)
    else:
        print("[OK] node_id 정수 리터럴 분기 0건")

    device_failures = _check_device_kind_literal(files)
    if device_failures:
        failures.extend(device_failures)
    else:
        print("[OK] backend/services/** 장치 종류 문자열 하드코딩 0건 (F-190)")

    dynamic_failures = _check_threshold_draft_is_data_driven()
    if dynamic_failures:
        failures.extend(dynamic_failures)
    else:
        print("[OK] _threshold_draft() 출력이 recommend_action 데이터의 순수 함수 (F-194)")

    subtype_spec_failures = _check_subtype_param_untyped()
    if subtype_spec_failures:
        failures.extend(subtype_spec_failures)
    else:
        print("[OK] openapi.json subtype 파라미터가 열거되지 않음")

    subtype_impl_failures = _check_api_py_subtype_signature()
    if subtype_impl_failures:
        failures.extend(subtype_impl_failures)
    else:
        print("[OK] backend/api.py subtype 파라미터가 자유 문자열(str)")

    print()
    if failures:
        print(f"[FAIL] {len(failures)}건")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("[PASS] tools/nodetype_verify.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
