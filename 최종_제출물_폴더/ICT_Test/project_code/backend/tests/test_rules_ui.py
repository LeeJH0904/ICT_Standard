"""rules.html의 AI 초안 모델 고정 및 생성 경로 표시 회귀 테스트."""
from pathlib import Path


RULES_HTML = Path(__file__).resolve().parents[2] / "web" / "rules.html"


def _source() -> str:
    return RULES_HTML.read_text(encoding="utf-8")


def test_ai_draft_model_is_internal_fixed_value():
    source = _source()

    assert 'id="draft-model"' not in source
    assert 'name="model_id"' not in source
    assert 'model-suggestions' not in source
    assert 'const AI_DRAFT_MODEL_ID = "demo-model-llm-irrigation";' in source
    assert "body.model_id = AI_DRAFT_MODEL_ID;" in source
    assert 'document.getElementById("draft-model")' not in source


def test_result_cards_show_only_actual_ai_generation_paths():
    source = _source()

    assert 'rule.generation === "AI"' in source
    assert 'rule.generation === "THRESHOLD_FALLBACK"' in source
    assert source.count("${generationPathHtml(rule)}") == 3
    assert "origin=${escapeHtml(rule.origin)}" not in source
    assert "generation=${escapeHtml(rule.generation" not in source


def test_ai_draft_uses_dms_forecast_and_only_accepts_crop_threshold_f256():
    source = _source()

    assert 'id="draft-inputs"' not in source
    assert 'id="draft-crop-tmax"' in source
    assert 'name="crop_tmax_c"' in source
    assert "JSON.parse(raw)" not in source
    assert "body.inputs = { crop_tmax_c: cropTmax };" in source
    # F-258 — 힌트 문구가 "선택한 온실"의 예보를 쓴다로 갱신됐다. forecast_tmax_c
    # 를 클라이언트가 보내지 않고 서버가 DMS 예보를 쓴다는 F-256 보장은 그대로다.
    assert "예보 최고기온은 서버가 선택한 온실의 DMS 공공데이터에서 가져옵니다." in source
    # F-256 보장(클라이언트가 예보값을 '전송'하지 않는다)은 유지하되, F-259 로
    # 서버가 돌려준 예보값을 '표시'하는 것은 허용된다 — 둘은 다르다. 전송 금지는
    # 요청 본문에 예보값 키가 실리지 않는 것으로 정밀 검사한다(blanket 금지 대신).
    assert "inputs.forecast_tmax_c" not in source     # 입력으로 넣지 않는다
    assert "body.forecast_tmax_c" not in source        # 본문 필드로 보내지 않는다
    assert "forecast_tmax_c: " not in source           # 어떤 전송 객체의 키로도 두지 않는다
    # F-258 — 더미데이터 표시가 payload._meta.note 휴리스틱에서 서버가 준
    # data_origin(LIVE/FALLBACK/DEMO_FIXTURE) 배지로 대체됐다. 폴백 데이터가
    # 무표시로 실데이터처럼 보이지 않는다는 F-256·§7 보장은 배지로 유지된다.
    assert "function originBadge(origin)" in source
    assert "originBadge(r.data_origin)" in source
    assert "실데이터(LIVE)" in source and "데모 고정값(DEMO_FIXTURE)" in source


def test_public_data_table_renders_location_and_forecast_metadata_f259():
    """F-259 — ①공공데이터 표가 F-258 위치 결속(온실 위경도·등록 격자)과
    예보 대상일·최고기온(TMX)을 서버 명시 필드에서 렌더한다. 표시 필드의
    존재만이 아니라 '서버가 준 값을 읽어 셀을 만든다'는 배선을 검사한다."""
    source = _source()
    # 표 헤더에 새 컬럼이 있다.
    for header in ("위경도(WGS84)", "온실 격자(등록)", "예보(대상일·최고기온)"):
        assert header in source
    # 렌더 배선 — 온실 객체의 위경도·등록 격자와 레코드의 예보 명시 필드를 읽는다.
    assert "ghLatLon(gh)" in source and "ghGrid(gh)" in source
    assert "forecastCell(r.forecast_date, r.forecast_tmax_c)" in source
    # 예보 필드는 화면이 payload 를 다시 파싱하지 않고 서버 명시 필드로 받는다.
    assert "r.forecast_date" in source and "r.forecast_tmax_c" in source
    assert "payload.response" not in source            # KMA 스키마 재파싱 없음


def test_result_cards_bind_forecast_evidence_f259():
    """F-259 제안 §3 — 초안 카드(미승인·승인·거부)가 rule.forecast 결속으로
    표와 같은 근거(온실·위경도·등록격자·발표회차·예보대상일·TMX·출처)를 보인다."""
    source = _source()
    assert "function forecastLineHtml(rule)" in source
    assert "const f = rule.forecast;" in source
    assert source.count("${forecastLineHtml(rule)}") == 3   # 세 카드 모두
    assert "근거 예보 —" in source
    assert "originBadge(f.data_origin)" in source
