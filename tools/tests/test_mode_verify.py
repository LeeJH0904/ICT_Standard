"""F-216 회귀 — 가상 노드 값이 골든 원본 밖으로 벗어나면 mode 출구가 실패한다."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "project_code"))

from sim import virtual_node as vn
from tools import mode_verify


def test_f216_golden_outside_values_are_caught(monkeypatch):
    monkeypatch.setattr(vn, "_load_value_pool", lambda: {
        vn.SUBTYPE_TEMPERATURE: (2, 1104517530),
        vn.SUBTYPE_HUMIDITY: (2, 1115291648),
        vn.SUBTYPE_IRRIGATION_VALVE: (1, 77),
    })
    before = len(mode_verify.R)
    mode_verify.check_virtual_node_values_match_golden()
    result = mode_verify.R.pop()
    assert len(mode_verify.R) == before
    assert result[0] is False
    assert "골든 밖 값" in result[2]


def test_current_virtual_node_values_are_in_golden():
    before = len(mode_verify.R)
    mode_verify.check_virtual_node_values_match_golden()
    result = mode_verify.R.pop()
    assert len(mode_verify.R) == before
    assert result[0] is True, result[2]
