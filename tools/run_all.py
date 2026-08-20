#!/usr/bin/env python3
"""전체 회귀 — tools/*_verify.py 전량 + project_docs/**/*_verify.py 전량.

개발_착수_지시서 §3.0 신설 / §4: "디렉터리 전수 탐색이며 목록을 하드코딩하지
않는다(F-094)." 검사 대상을 이름으로 나열하지 않고 glob 으로 찾는다 — 새
검증기가 추가되면 이 파일을 고치지 않아도 자동으로 포함된다.

실행: python tools/run_all.py   (저장소 루트에서)
종료 코드: 전부 통과 0 / 하나라도 실패 1
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# F-102 — 한국어 Windows 기본 콘솔은 CP949 다. 2중 방어(F-045 원칙) — 출력
# 문자는 CP949 안에서 고르는 것이 원칙이고, 이건 새 문자가 섞여도 이 스크립트
# 자신의 print() 가 중단되지 않게만 막는다.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
PROJECT_DOCS_DIR = REPO_ROOT / "project_docs"
PYTHON = sys.executable


def _utf8_env() -> dict[str, str]:
    """하위 파이썬 프로세스가 로케일과 무관하게 항상 UTF-8 로 쓰게 강제한다.
    표준 출력이 파이프(subprocess capture)면 PEP 528 의 콘솔 UTF-8 처리가
    적용되지 않아, 한국어 Windows 에서는 cp949 로 인코딩된다 — 이걸 "utf-8"
    로만 디코딩하면 한글이 조용히 깨진다 (F-096, dev_verify.py 에서 처음 발견).
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _safe_print(text: str) -> None:
    """콘솔 코드페이지(Windows 기본 cp949)가 표현 못 하는 문자가 하위 검증기
    출력에 섞여 있어도 죽지 않는다 — CLAUDE.md §3.5(F-045)와 같은 원칙이며,
    여기서는 우리 문자열이 아니라 하위 프로세스 출력이라 미리 고를 수 없다."""
    enc = sys.stdout.encoding or "utf-8"
    print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def discover_scripts() -> list[Path]:
    """tools/*_verify.py (최상위) + project_docs/**/*_verify.py (전체 하위) 를 찾는다.

    예외 1건: `project_docs/db/verify.py` 는 접두어 없이 정확히 `verify.py` 로
    이름 붙어 있어 `*_verify.py` 패턴에 걸리지 않는다. 이름 하나를 나열하는
    대신, "verify.py" 라는 정확한 이름도 함께 매칭하는 일반 규칙으로 흡수한다
    (특정 문서 목록이 아니라 패턴을 넓힌 것 — F-094 가 금지하는 "열거"가 아니다).
    이 격차는 개발 착수 시점에 발견되어 사용자에게 보고됐다.
    """
    scripts: set[Path] = set()

    if TOOLS_DIR.exists():
        scripts.update(TOOLS_DIR.glob("*_verify.py"))

    if PROJECT_DOCS_DIR.exists():
        for p in PROJECT_DOCS_DIR.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if p.name.endswith("_verify.py") or p.name == "verify.py":
                scripts.add(p)

    return sorted(scripts, key=lambda p: str(p.relative_to(REPO_ROOT)))


def run_script(script: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [PYTHON, str(script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            env=_utf8_env(),
        )
        ok = proc.returncode == 0
        out = (proc.stdout or "") + (proc.stderr or "")
        return ok, out.strip()
    except subprocess.TimeoutExpired:
        return False, "시간 초과(300초)"
    except OSError as exc:
        return False, f"실행 오류: {exc}"


def main() -> int:
    scripts = discover_scripts()
    print(f"=== tools/run_all.py : 검증기 {len(scripts)}개 발견 ===\n")
    if not scripts:
        print("검증기를 하나도 찾지 못했다 - tools/ 또는 project_docs/ 경로를 확인한다.")
        return 1

    results: list[tuple[Path, bool, str]] = []
    for script in scripts:
        ok, out = run_script(script)
        results.append((script, ok, out))
        rel = script.relative_to(REPO_ROOT)
        mark = "OK" if ok else "FAIL"
        _safe_print(f"[{mark}] {rel}")
        if not ok:
            for line in out.splitlines()[-15:]:
                _safe_print(f"    {line}")

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n=== {passed}/{total} 통과 ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
