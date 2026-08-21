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
    assert "예보 최고기온은 서버가 DMS 공공데이터의 최신 레코드에서 가져옵니다." in source
