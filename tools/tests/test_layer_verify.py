"""F-206 회귀 — project_docs import 금지를 project_code 전체에 적용한다.

이전 검증기는 출력과 규약에서 project_code 전체 금지를 선언했지만 실제로는
contracts/만 순회해 backend/ 같은 다른 구현 계층의 위반을 통과시켰다.

실행: python -m pytest tools/tests/test_layer_verify.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from tools import layer_verify as lv


def _point_to_temp_tree(monkeypatch, root: Path) -> Path:
    project_code = root / "project_code"
    project_code.mkdir()
    monkeypatch.setattr(lv, "ROOT", root)
    monkeypatch.setattr(lv, "PROJECT_CODE", project_code)
    return project_code


def test_f206_backend_project_docs_import_is_caught(monkeypatch):
    """F-206 재현: contracts 밖 backend 위반도 전체 출구를 실패시킨다."""
    with tempfile.TemporaryDirectory() as tmp:
        project_code = _point_to_temp_tree(monkeypatch, Path(tmp))
        backend = project_code / "backend"
        backend.mkdir()
        (backend / "bad.py").write_text(
            "from project_docs.contracts import frame\n", encoding="utf-8"
        )

        assert lv.main() == 1, (
            "F-206 재발: backend의 project_docs import가 계층 검증 전체를 "
            "실패시키지 않았다"
        )


def test_f206_clean_project_code_still_passes(monkeypatch):
    """정상 구현 파일은 project_code 전수 검사에서도 오탐 없이 통과한다."""
    with tempfile.TemporaryDirectory() as tmp:
        project_code = _point_to_temp_tree(monkeypatch, Path(tmp))
        backend = project_code / "backend"
        backend.mkdir()
        (backend / "clean.py").write_text("import json\n", encoding="utf-8")

        assert lv.main() == 0
