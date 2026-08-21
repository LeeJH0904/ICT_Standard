"""project_code/.env 로더 회귀 테스트(F-254)."""
from __future__ import annotations

import os

import pytest

from backend.config import ALLOWED_ENV_KEYS, EnvFileError, load_env_file


def _clear_supported(monkeypatch) -> None:
    for name in ALLOWED_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)


def test_missing_env_file_is_noop(tmp_path, monkeypatch):
    _clear_supported(monkeypatch)
    assert load_env_file(tmp_path / ".env", environ={}) == ()


def test_loads_supported_values_and_ignores_blank_keys(tmp_path, monkeypatch):
    environ = {}
    _clear_supported(monkeypatch)
    environ = {}
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# submission settings\n"
        "KMA_API_KEY=kma-test-key\n"
        "OPENAI_BASE_URL=https://api.openai.com/v1\n"
        "OPENAI_API_KEY=\n"
        "export OPENAI_MODEL='unit-test-model'\n"
        "OPENAI_TIMEOUT_SEC=8  # seconds\n",
        encoding="utf-8",
    )

    loaded = load_env_file(env_file, environ=environ)

    assert set(loaded) == {
        "KMA_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "OPENAI_TIMEOUT_SEC"
    }
    assert environ["KMA_API_KEY"] == "kma-test-key"
    assert "OPENAI_API_KEY" not in environ
    assert environ["OPENAI_MODEL"] == "unit-test-model"
    assert environ["OPENAI_TIMEOUT_SEC"] == "8"
    assert all(name not in os.environ for name in ALLOWED_ENV_KEYS)


def test_process_environment_has_priority(tmp_path, monkeypatch):
    _clear_supported(monkeypatch)
    environ = {"OPENAI_MODEL": "process-model"}
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_MODEL=file-model\n", encoding="utf-8")

    assert load_env_file(env_file, environ=environ) == ()
    assert environ["OPENAI_MODEL"] == "process-model"


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("TYPO_API_KEY=secret-value\n", "지원하지 않는 환경변수 이름"),
        ("OPENAI_API_KEY=first\nOPENAI_API_KEY=second\n", "중복"),
        ("OPENAI_API_KEY='secret-value\n", "따옴표"),
        ("OPENAI_API_KEY\n", "NAME=VALUE"),
    ],
)
def test_invalid_file_is_rejected_without_partial_application(
    tmp_path, monkeypatch, content, expected
):
    _clear_supported(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_MODEL=should-not-be-applied\n" + content,
        encoding="utf-8",
    )

    with pytest.raises(EnvFileError) as caught:
        load_env_file(env_file, environ={})

    message = str(caught.value)
    assert expected in message
    assert "secret-value" not in message
    assert "OPENAI_MODEL" not in os.environ
