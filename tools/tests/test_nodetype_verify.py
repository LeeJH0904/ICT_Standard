"""F-226 회귀 — 장치 종류 검사가 services 밖 backend 제품 코드도 본다."""
from pathlib import Path

from tools import nodetype_verify


def test_f226_api_device_kind_constant_is_caught(monkeypatch):
    original = Path.read_text
    api_path = (nodetype_verify.BACKEND_DIR / "api.py").resolve()

    def injected(self, *args, **kwargs):
        text = original(self, *args, **kwargs)
        if self.resolve() == api_path:
            return text + '\nSPECIAL_DEVICE_KIND = "환기팬"\n'
        return text

    monkeypatch.setattr(Path, "read_text", injected)
    failures = nodetype_verify._check_device_kind_literal(nodetype_verify._iter_backend_py())
    assert any("api.py" in failure and "환기팬" in failure for failure in failures)


def test_f226_current_backend_has_no_device_kind_hardcoding():
    assert nodetype_verify._check_device_kind_literal(nodetype_verify._iter_backend_py()) == []
