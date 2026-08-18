"""backend/tests/test_services_mms.py — backend/services/mms.py 단위 테스트.

 회귀 테스트 전용 — HTTP 계층을 거치지 않고 서비스 함수를 직접 호출해
"장치 종류가 다른 모델을 추가해도 mms.py 소스가 한 글자도 바뀌지 않는다"는
CLAUDE.md §0 주장 3을 증명한다. `control_model` 행을 seed 가 아니라 이
테스트가 직접 INSERT 해서 검증하는 것이 핵심이다 — seed.sql 만 통과하는
검사라면 "seed 가 우연히 맞다"와 "코드가 일반적이다"를 구별하지 못한다.
"""
from __future__ import annotations

import pytest

from backend import db, repository
from backend.services import mms


@pytest.fixture()
def conn(tmp_path):
    con = db.init_db(tmp_path / "mms.db", seed=True)
    yield con
    con.close()


def _insert_model(conn, *, model_id: str, recommend_action: str, exec_method: str = "threshold") -> None:
    """seed.sql 이 하는 것과 동일한 형태의 INSERT — 테스트가 새 장치 종류
    모델을 '등록'하는 자리를 흉내낸다. mms.py 는 이 함수를 모른다."""
    conn.execute(
        "INSERT INTO control_model (id, created_at, name, input_spec, output_spec, exec_method, "
        "protocol, data_format, period_sec, developer) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (model_id, "2026-08-11T00:00:00+09:00", f"테스트 모델 {model_id}",
         '{"forecast_tmax_c":"number","crop_tmax_c":"number"}',
         f'{{"condition_expr":"string","action":"ControlAction","recommend_action":"{recommend_action}"}}',
         exec_method, None, "json", None, None),
    )
    conn.commit()


def test_threshold_draft_uses_model_recommend_action_not_hardcoded_f190(conn):
    """새 장치(송풍기) 모델을 코드 변경 없이 등록했을 때, 초안
    문구가 그 모델의 output_spec.recommend_action 을 그대로 쓴다.
    소스에 "송풍기"라는 문자열은 어디에도 없다(tools/nodetype_verify.py
    가 이를 정적으로도 확인한다)."""
    _insert_model(conn, model_id="test-fan-model", recommend_action="송풍기 가동")
    rule = mms.draft_rule(
        conn, origin="AI_DRAFT", model_id="test-fan-model",
        inputs={"crop_tmax_c": 30, "forecast_payload": {
            "response": {"body": {"items": {"item": [{"category": "TMX", "fcstValue": "35"}]}}}
        }},
    )
    assert rule.generation == "THRESHOLD_FALLBACK"
    assert "송풍기" in rule.draft_text
    assert "35" in rule.draft_text and "30" in rule.draft_text


def test_threshold_draft_different_model_different_wording_f190(conn):
    """같은 forecast·같은 crop_tmax_c 라도 모델이 다르면 문구가 다르다 —
    문구가 모델별 데이터에서 왔다는 증거(하드코딩이면 항상 동일했을 것)."""
    _insert_model(conn, model_id="test-cool-model", recommend_action="냉난방기 냉방 가동")
    rule = mms.draft_rule(
        conn, origin="AI_DRAFT", model_id="test-cool-model",
        inputs={"crop_tmax_c": 20, "forecast_payload": {
            "response": {"body": {"items": {"item": [{"category": "TMX", "fcstValue": "25"}]}}}
        }},
    )
    assert "냉난방기 냉방 가동" in rule.draft_text
    assert "송풍기" not in rule.draft_text


def test_threshold_draft_missing_crop_threshold_is_explicit_f190(conn):
    """CLAUDE.md §1-1 원칙과 대칭 — 값을 추측해 합성하지 않는다. 서버
    상수로 33.0 을 되살리지 않았는지도 함께 본다."""
    model = repository.get_control_model(conn, "demo-model-threshold-tmax")
    text = mms._threshold_draft(model, {
        "forecast_payload": {
            "response": {"body": {"items": {"item": [{"category": "TMX", "fcstValue": "40"}]}}}
        }
    })
    assert "crop_tmax_c" in text
    assert "40" not in text


def test_threshold_draft_below_threshold_no_action_recommended(conn):
    model = repository.get_control_model(conn, "demo-model-threshold-tmax")
    text = mms._threshold_draft(model, {
        "crop_tmax_c": 33,
        "forecast_payload": {
            "response": {"body": {"items": {"item": [{"category": "TMX", "fcstValue": "20"}]}}}
        },
    })
    assert "필요하지 않습니다" in text
    assert "관수" not in text
