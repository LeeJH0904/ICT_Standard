"""backend/tests/test_services_mms.py — backend/services/mms.py 단위 테스트.

회귀 테스트 전용 — HTTP 계층을 거치지 않고 서비스 함수를 직접 호출해
"장치 종류가 다른 모델을 추가해도 mms.py 소스가 한 글자도 바뀌지 않는다"는
확장성을 검증한다. `control_model` 행을 seed가 아니라 이
테스트가 직접 INSERT 해서 검증하는 것이 핵심이다 — seed.sql 만 통과하는
검사라면 "seed 가 우연히 맞다"와 "코드가 일반적이다"를 구별하지 못한다.
"""
from __future__ import annotations

import json
import logging
import urllib.error

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
    소스에 "송풍기"라는 문자열을 하드코딩하지 않는다."""
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
    """원칙과 대칭 — 값을 추측해 합성하지 않는다. 서버
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

class _FakeOpenAIResponse:
    def __init__(self, body: bytes, *, status: int = 200, headers: dict | None = None):
        self.body = body
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def getcode(self):
        return self.status

    def read(self, size: int = -1):
        return self.body if size < 0 else self.body[:size]


def _llm_inputs() -> dict:
    return {
        "crop_tmax_c": 33,
        "forecast_payload": {
            "response": {"body": {"items": {"item": [
                {"category": "TMX", "fcstValue": "34"},
            ]}}},
        },
    }


def _openai_response(draft_text: str) -> bytes:
    return json.dumps({
        "status": "completed",
        "error": None,
        "output": [{
            "type": "message",
            "status": "completed",
            "content": [{
                "type": "output_text",
                "text": json.dumps({"draft_text": draft_text}, ensure_ascii=False),
            }],
        }],
    }, ensure_ascii=False).encode("utf-8")


def _set_openai_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_TIMEOUT_SEC", "8")


@pytest.mark.parametrize("missing", ["OPENAI_API_KEY", "OPENAI_MODEL"])
def test_llm_draft_missing_required_setting_does_not_call_network_f189(conn, monkeypatch, missing):
    _set_openai_env(monkeypatch)
    monkeypatch.delenv(missing)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("설정 부재 상태에서 외부 호출을 해서는 안 된다")

    monkeypatch.setattr(mms.urllib.request, "urlopen", fail_if_called)
    text, generation = mms.run_model(conn, "demo-model-llm-irrigation", _llm_inputs())
    assert generation == "THRESHOLD_FALLBACK"
    assert "34" in text and "33" in text


def test_llm_draft_valid_openai_response_uses_responses_api_and_stays_unapproved_f189(
        conn, monkeypatch):
    _set_openai_env(monkeypatch)
    captured = {}
    ai_text = "예보 최고기온이 임계값을 초과하므로 관수 장치 가동을 권장합니다. 사람 승인 전에는 실행되지 않는 초안입니다."

    def fake_urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeOpenAIResponse(_openai_response(ai_text))

    monkeypatch.setattr(mms.urllib.request, "urlopen", fake_urlopen)
    rule = mms.draft_rule(
        conn, origin="AI_DRAFT", model_id="demo-model-llm-irrigation",
        inputs=_llm_inputs(),
    )

    assert rule.generation == "AI"
    assert rule.draft_text == ai_text
    assert rule.condition_expr is None
    assert rule.action_json is None
    assert rule.target_install_id is None
    assert rule.approved_at is None
    assert rule.approved_by is None

    request = captured["request"]
    assert request.full_url == "https://api.openai.com/v1/responses"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer unit-test-key"
    assert request.get_header("Content-type") == "application/json"
    assert captured["timeout"] == 8.0
    assert b"unit-test-key" not in request.data

    body = json.loads(request.data.decode("utf-8"))
    assert body["model"] == "gpt-5.4-mini"
    assert body["store"] is False
    assert body["max_output_tokens"] == 300
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "rule_draft",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"draft_text": {"type": "string"}},
            "required": ["draft_text"],
            "additionalProperties": False,
        },
    }
    sent_input = json.loads(body["input"][0]["content"][0]["text"])
    assert set(sent_input) == {
        "forecast_tmax_c", "crop_tmax_c", "recommend_action", "source",
    }
    assert sent_input["forecast_tmax_c"] == 34.0
    assert sent_input["crop_tmax_c"] == 33.0


@pytest.mark.parametrize("raw", [
    b"not-json",
    json.dumps({"status": "incomplete", "error": None, "output": []}).encode(),
    json.dumps({
        "status": "completed", "error": None,
        "output": [{"type": "message", "status": "completed",
                    "content": [{"type": "refusal", "refusal": "cannot"}]}],
    }).encode(),
    _openai_response(""),
    _openai_response("잘못된\n제어문자"),
    json.dumps({
        "status": "completed", "error": None,
        "output": [{"type": "message", "status": "completed", "content": [{
            "type": "output_text",
            "text": json.dumps({"draft_text": "초안", "action_json": {}}),
        }]}],
    }).encode(),
])
def test_openai_response_validation_rejects_untrusted_shapes_f189(raw):
    assert mms._parse_openai_response(raw) is None


def test_llm_draft_http_error_falls_back_without_secret_in_log_f189(
        conn, monkeypatch, caplog):
    _set_openai_env(monkeypatch)

    def fail_http(request, *, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", {}, None)

    monkeypatch.setattr(mms.urllib.request, "urlopen", fail_http)
    with caplog.at_level(logging.WARNING):
        text, generation = mms.run_model(
            conn, "demo-model-llm-irrigation", _llm_inputs(),
        )
    assert generation == "THRESHOLD_FALLBACK"
    assert "34" in text
    assert "401" in caplog.text
    assert "unit-test-key" not in caplog.text
    assert "Authorization" not in caplog.text


def test_llm_draft_transport_error_and_oversized_response_fall_back_f189(
        conn, monkeypatch):
    _set_openai_env(monkeypatch)

    def fail_transport(request, *, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(mms.urllib.request, "urlopen", fail_transport)
    _, generation = mms.run_model(conn, "demo-model-llm-irrigation", _llm_inputs())
    assert generation == "THRESHOLD_FALLBACK"

    oversized = b"x" * (mms._OPENAI_MAX_RESPONSE_BYTES + 1)
    monkeypatch.setattr(
        mms.urllib.request, "urlopen",
        lambda request, *, timeout: _FakeOpenAIResponse(oversized),
    )
    _, generation = mms.run_model(conn, "demo-model-llm-irrigation", _llm_inputs())
    assert generation == "THRESHOLD_FALLBACK"


def test_llm_draft_rejects_non_https_base_url_without_network_f189(conn, monkeypatch):
    _set_openai_env(monkeypatch)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://api.openai.com/v1")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("검증되지 않은 Base URL로 API 키를 보내서는 안 된다")

    monkeypatch.setattr(mms.urllib.request, "urlopen", fail_if_called)
    _, generation = mms.run_model(conn, "demo-model-llm-irrigation", _llm_inputs())
    assert generation == "THRESHOLD_FALLBACK"

@pytest.mark.parametrize("threshold", [float("nan"), float("inf"), 10 ** 1000])
def test_threshold_draft_invalid_numeric_input_does_not_raise_f189(conn, threshold):
    model = repository.get_control_model(conn, "demo-model-llm-irrigation")
    text = mms._threshold_draft(model, {
        "crop_tmax_c": threshold,
        "forecast_payload": {
            "response": {"body": {"items": {"item": [
                {"category": "TMX", "fcstValue": "34"},
            ]}}},
        },
    })
    assert "다시 시도" in text


def test_openai_response_requires_explicit_null_error_f189():
    raw = json.dumps({
        "status": "completed",
        "output": [{
            "type": "message", "status": "completed",
            "content": [{
                "type": "output_text",
                "text": json.dumps({"draft_text": "초안"}),
            }],
        }],
    }).encode()
    assert mms._parse_openai_response(raw) is None


def test_llm_draft_rejects_non_ascii_api_key_without_network_f189(conn, monkeypatch):
    _set_openai_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "한글-키")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("HTTP 헤더에 안전하지 않은 키로 호출해서는 안 된다")

    monkeypatch.setattr(mms.urllib.request, "urlopen", fail_if_called)
    _, generation = mms.run_model(conn, "demo-model-llm-irrigation", _llm_inputs())
    assert generation == "THRESHOLD_FALLBACK"
