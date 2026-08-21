"""실행 환경 설정 로더.

`project_code/.env`의 이 애플리케이션 전용 변수만 읽는다. 외부 패키지 없이
표준 라이브러리만 사용하며, 이미 프로세스 환경에 있는 값은 덮어쓰지 않는다.
"""
from __future__ import annotations

import os
import re
from collections.abc import MutableMapping
from pathlib import Path


ENV_FILE_PATH = Path(__file__).resolve().parent.parent / ".env"
ALLOWED_ENV_KEYS = frozenset({
    "KMA_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "OPENAI_TIMEOUT_SEC",
})
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class EnvFileError(ValueError):
    """`.env`의 안전한 해석을 할 수 없을 때 발생한다."""


def _error(path: Path, line_no: int, message: str) -> EnvFileError:
    return EnvFileError(f"{path.name}:{line_no}: {message}")


def _parse_value(raw_value: str, *, path: Path, line_no: int) -> str:
    value = raw_value.strip()
    if not value:
        return ""

    if value[0] in {"'", '"'}:
        quote = value[0]
        if len(value) < 2 or value[-1] != quote:
            raise _error(path, line_no, "따옴표가 닫히지 않았다")
        value = value[1:-1]
    else:
        # 공백 뒤의 #만 주석으로 본다. 키 값 안의 #은 그대로 유지한다.
        comment = re.search(r"\s+#", value)
        if comment:
            value = value[:comment.start()].rstrip()

    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise _error(path, line_no, "제어 문자는 사용할 수 없다")
    return value


def load_env_file(
    path: str | Path | None = None,
    *,
    environ: MutableMapping[str, str] | None = None,
) -> tuple[str, ...]:
    """`.env`를 검증해 프로세스 환경에 추가하고 실제 추가된 이름을 반환한다.

    파일이 없으면 아무것도 하지 않는다. 빈 값은 미설정으로 취급한다.
    파일 전체를 먼저 검증하므로 중간까지만 적용되는 상태는 만들지 않는다.
    """
    env_path = Path(path) if path is not None else ENV_FILE_PATH
    target_environ = os.environ if environ is None else environ
    if not env_path.exists():
        return ()
    if not env_path.is_file():
        raise EnvFileError(f"{env_path.name}: 일반 파일이 아니다")

    try:
        lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise EnvFileError(f"{env_path.name}: UTF-8 파일을 읽을 수 없다") from exc

    parsed: dict[str, str] = {}
    for line_no, source_line in enumerate(lines, start=1):
        line = source_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise _error(env_path, line_no, "NAME=VALUE 형식이 아니다")

        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not _ENV_NAME_RE.fullmatch(name):
            raise _error(env_path, line_no, "환경변수 이름 형식이 잘못되었다")
        if name not in ALLOWED_ENV_KEYS:
            raise _error(env_path, line_no, f"지원하지 않는 환경변수 이름: {name}")
        if name in parsed:
            raise _error(env_path, line_no, f"환경변수가 중복되었다: {name}")
        parsed[name] = _parse_value(raw_value, path=env_path, line_no=line_no)

    loaded: list[str] = []
    for name, value in parsed.items():
        if value and name not in target_environ:
            target_environ[name] = value
            loaded.append(name)
    return tuple(loaded)
