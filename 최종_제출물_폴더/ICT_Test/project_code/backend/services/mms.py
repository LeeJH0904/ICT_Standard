"""
backend/services/mms.py — TTAK.KO-10.0937 6.3 MMS(모델관리서비스) / 부속서 A 3.2.

담당 조항: 6.3-1·2·3·4·5·6·10 · A.3-3·5·6
진입점: get_model · run_model · draft_rule · approve_rule · reject_rule

승인 게이트는 `backend/schema.sql`의 CHECK·트리거가 이미 봉인했다 — 이 모듈은
그 게이트를 "시도조차 못 하게" 감싸기만 하고, 우회 경로를 새로 만들지 않는다.
AI 초안은 `approved_at`이 NULL인 동안 `action_json`·`target_install_id`를
절대 가질 수 없다 — DB가 구조로 강제하므로 이 파일은 그 사실을 다시
검사하지 않는다.
"""
from __future__ import annotations

import json
import os
import sqlite3

try:                    # 패키지로 import될 때
    from backend import repository
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent))
    from backend import repository


class RuleGateError(Exception):
    """승인 게이트가 막았다 — `sqlite3.IntegrityError`(CHECK 또는 트리거의
    `RAISE(ABORT,...)`)를 감싼다. `api.py`가 이 예외를 RFC 9457 Problem
    (409 또는 400)으로 옮긴다."""

    def __init__(self, message: str, *, constraint: str | None = None) -> None:
        super().__init__(message)
        self.constraint = constraint


class RuleNotFound(LookupError):
    pass


def get_model(conn: sqlite3.Connection, model_id: str):
    """0937 6.3-2 — 모델 메타정보(명칭·입력값·출력값·실행방법·개발자) 조회."""
    return repository.get_control_model(conn, model_id)


def _output_spec(model) -> dict:
    """`control_model.output_spec`(6.3-2 "출력값" 메타정보) 을 dict 로 연다.
    이 값이 권장 조치 문구의 정본이다 — Python 소스에 장치 종류
    문자열을 박지 않는다. 형식이 깨져 있으면 빈 dict — 호출자가 기본
    문구로 대체한다(파싱 실패로 초안 생성 자체를 막지 않는다)."""
    try:
        spec = json.loads(model.output_spec)
    except (TypeError, ValueError):
        return {}
    return spec if isinstance(spec, dict) else {}


def _extract_tmax(payload: dict) -> float | None:
    """`fixtures/kma_forecast_mock.json`(또는 실제 응답)의 TMX(최고기온)
    항목을 읽는다. 0937 6.3-3 "입력값으로 DMS 제공 값 사용" — dms.py가
    수집한 `public_data_record.payload`를 그대로 읽는 지점."""
    items = payload.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    for it in items:
        if it.get("category") == "TMX":
            try:
                return float(it["fcstValue"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _threshold_draft(model, inputs: dict) -> str:
    """0937 6.3-6 내장 실행 방법(`exec_method='threshold'`). `llm_draft`의
    폴백 경로이기도 하다(THRESHOLD_FALLBACK) — 생성형 AI 없이도
    오프라인에서 항상 결과를 낸다.

    `inputs['forecast_payload']`는 `api.py`가 `dms.fetch_public_data()`
    결과에서 채워 넘긴다(6.3-4 "사전 획득 방식") — 이 함수는 공공데이터를
    직접 수집하지 않는다.

    임계값과 권장 조치 문구는 이 함수(=backend 소스) 어디에도 상수로
    없다. 임계값은 모델의 `input_spec`이 선언한 대로 호출자가
    `inputs['crop_tmax_c']`로 공급한다(6.3-3 "입력값") — 작물마다 다른
    기준을 서버 코드 수정 없이 요청마다 바꿀 수 있다. 권장 조치 문구는
    모델의 `output_spec.recommend_action`을 그대로 쓴다(6.3-2 "출력값"
    메타정보) — 송풍기·냉난방기 등 다른 장치를 위한 모델을 추가할 때도
    `control_model` 행 하나만 새로 등록하면 된다.
    """
    payload = inputs.get("forecast_payload")
    tmax = _extract_tmax(payload) if isinstance(payload, dict) else None
    if tmax is None:
        return "예보 데이터가 없어 임계값을 평가할 수 없습니다 — 공공데이터 수집 후 다시 시도하십시오."
    threshold = inputs.get("crop_tmax_c")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        return ("작물별 고온 임계값(inputs.crop_tmax_c)이 없어 평가할 수 없습니다 — "
                "온실 작물 기준값을 지정해 다시 시도하십시오.")
    recommend = _output_spec(model).get("recommend_action", "장치 가동")
    if tmax > threshold:
        return (f"예보 최고기온 {tmax:.0f}°C가 임계값 {threshold:.0f}°C를 "
                f"초과합니다 — {recommend}을 권장합니다.")
    return (f"예보 최고기온 {tmax:.0f}°C는 임계값 {threshold:.0f}°C 이하입니다 — "
            f"별도 조치가 필요하지 않습니다.")


def _try_llm_draft(inputs: dict) -> str | None:
    """생성형 AI 제공자 연동 시도. 이 참조 구현은 실제 제공자를 붙이지 않고
    (의존성 최소화) 항상 `None`을 돌려 호출자가 threshold로 폴백하게 한다 —
    미승인 AI 규칙이 구동기로 전달되지 않는다는 원칙은 이 함수가 무엇을 하든
    DB CHECK가 이미 지킨다: `control_rule.action_json`은 승인 전까지 항상 NULL이다."""
    del inputs  # 이 참조 구현 범위에서는 사용하지 않는다
    return None


def run_model(conn: sqlite3.Connection, model_id: str, inputs: dict) -> tuple[str, str]:
    """0937 6.3-6 — "메타정보에 등록된 모델 실행 방법에 따라 모델을 구동하고
    출력값 수신이 가능해야 한다". `control_model.exec_method`가
    `llm_draft`면 생성형 AI를 시도하고, 없거나 실패하면 threshold로
    자동 전환한다.

    반환: (draft_text, generation). `generation` ∈ {AI, THRESHOLD_FALLBACK} —
    `control_rule.origin='AI_DRAFT'`일 때만 호출되므로 이 두 값만 허용된다
    (schema.sql CHECK와 대칭, `draft_rule()` 참조)."""
    model = get_model(conn, model_id)
    if model is None:
        raise RuleNotFound(f"control_model {model_id} 없음")
    if model.exec_method == "llm_draft":
        text = _try_llm_draft(inputs)
        if text is not None:
            return text, "AI"
    return _threshold_draft(model, inputs), "THRESHOLD_FALLBACK"


def draft_rule(conn: sqlite3.Connection, *, origin: str, model_id: str | None = None,
               inputs: dict | None = None, draft_text: str | None = None,
               condition_expr: str | None = None):
    """`POST /api/v1/rules` — 0937 6.3 "제어 명령을 위자드 선택 방식, 스크립트
    입력 방식 등으로 직접 만들어서 등록"(A.3-5). `origin='AI_DRAFT'`면
    서버가 `run_model()`로 모델을 돌려 `draft_text`를 만든다 —
    클라이언트가 보낸 문구를 그대로 AI 산출물로 저장하지 않는다.

    `action`·`target_install_id`는 이 함수의 인자에 아예 없다 — 받지
    않으므로 실을 수도 없다."""
    if origin == "AI_DRAFT":
        if not model_id:
            raise ValueError("origin=AI_DRAFT 는 model_id 가 필수다")
        text, generation = run_model(conn, model_id, inputs or {})
    else:
        # WIZARD/SCRIPT — schema.sql CHECK: origin='AI_DRAFT' 가 아니면
        # generation 은 NULL 이거나 origin 과 같아야 한다.
        text, generation = draft_text, origin
    rule_id = repository.insert_control_rule(
        conn, origin=origin, draft_text=text or "", model_id=model_id,
        generation=generation, condition_expr=condition_expr,
    )
    conn.commit()
    return repository.get_control_rule(conn, rule_id)


def approve_rule(conn: sqlite3.Connection, rule_id: str, *, user_id: str,
                  condition_expr: str, action: dict, target_install_id: str):
    """`POST /api/v1/rules/{id}/approve` — 0937 부속서 A 3.2 절차 3 "사용자는
    최종 의사결정 후 제어 조건 조정을 한다". 조건식·명령·대상·승인자·
    승인시각을 한 번의 UPDATE로 동시에 채운다 — 부분 승인 상태가 없다
   ."""
    rule = repository.get_control_rule(conn, rule_id)
    if rule is None:
        raise RuleNotFound(f"control_rule {rule_id} 없음")
    if rule.is_approved:
        raise RuleGateError(
            "이미 승인된 규칙이다 — 승인은 철회·재승인되지 않는다. 새 규칙을 만들어라.",
            constraint="trg_rule_approval_irrevocable",
        )
    try:
        repository.approve_control_rule(
            conn, rule_id, condition_expr=condition_expr,
            action_json=json.dumps(action, ensure_ascii=False),
            target_install_id=target_install_id, approved_by=user_id,
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise RuleGateError(str(e), constraint=repository.constraint_name_from_error(e)) from e
    return repository.get_control_rule(conn, rule_id)


def reject_rule(conn: sqlite3.Connection, rule_id: str, *, user_id: str, reason: str):
    """`POST /api/v1/rules/{id}/reject` — 거부도 승인과 대칭으로
    영속·불변이다(0937 부속서 A 3.2 절차 3 "조정"에는 반려가 포함된다)."""
    rule = repository.get_control_rule(conn, rule_id)
    if rule is None:
        raise RuleNotFound(f"control_rule {rule_id} 없음")
    if rule.is_approved or rule.is_rejected:
        raise RuleGateError(
            "이미 승인되었거나 거부된 규칙이다.",
            constraint="trg_rule_reject_immutable" if rule.is_rejected else "trg_rule_approval_irrevocable",
        )
    try:
        repository.reject_control_rule(conn, rule_id, reason=reason, rejected_by=user_id)
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise RuleGateError(str(e), constraint=repository.constraint_name_from_error(e)) from e
    return repository.get_control_rule(conn, rule_id)
