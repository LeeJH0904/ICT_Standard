#!/usr/bin/env python3
"""현재 개발 단계를 판정한다.

개발_착수_지시서 §0.1: "현재 단계를 파일에 적어 두지 않는다. 상태 파일은 갱신을
빠뜨리는 순간 실제와 갈린다(F-090·F-094). 출구 명령을 순서대로 돌려 처음
실패하는 단계가 현재 단계다."

이 스크립트는 그 규칙을 그대로 구현한다: 단계 0부터 순서대로 각 단계의 출구
명령을 실제로 실행하고, 처음으로 실패하는 단계를 "현재 단계"로 출력한다.
그 앞 단계들은 전부 통과해야 한다(회귀).

실행: python tools/where.py   (저장소 루트에서)
종료 코드: 항상 0 (진단 도구 자체의 성공/실패가 아니라 판정 결과를 출력한다).
콘솔 출력 문자는 CLAUDE.md §3.5(F-045)와 같은 원칙으로 CP949 표현 범위 안에서 고른다.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

# F-102 — 한국어 Windows 기본 콘솔은 CP949 다. 출력 문자는 그 안에서 고르는 것이
# 원칙이고(§3.5), 이 가드는 새 문자가 섞여도 중단만은 막는 2중 방어다(F-045 원칙).
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

# (설명, 통과여부, 상세). 통과여부는 3치다 — True=통과 / False=실패 /
# None=자동 판정 불가(사람이 직접 확인해야 함). F-098: 이전에는 자동화할 수
# 없는 항목(헤드리스 렌더 4장·실측 캡처)을 아예 실행하지 않고 조용히 빠뜨려
# 완료 단계를 과대 판정했다 — 이제는 "통과로 간주하지 않고 MANUAL 로 남긴다."
CheckResult = tuple[str, bool | None, str]


def _utf8_env() -> dict[str, str]:
    """하위 파이썬 프로세스가 로케일과 무관하게 항상 UTF-8 로 쓰게 강제한다.
    표준 출력이 파이프면 PEP 528 의 콘솔 UTF-8 처리가 적용되지 않아 한국어
    Windows 에서는 cp949 로 인코딩된다 — "utf-8" 로만 디코딩하면 한글이
    조용히 깨진다 (F-096, dev_verify.py 에서 처음 발견. run_all.py 와 동일 조치)."""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _safe_print(text: str) -> None:
    """하위 명령 출력에 콘솔 코드페이지가 표현 못 하는 문자가 섞여 있어도 죽지
    않는다 (run_all.py 와 동일한 이유 — F-045 원칙, 우리 문자열이 아니다)."""
    enc = sys.stdout.encoding or "utf-8"
    print(text.encode(enc, errors="replace").decode(enc, errors="replace"))


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 180) -> tuple[bool, str]:
    """명령을 실행하고 (성공여부, 합쳐진 출력) 을 돌려준다. 실행 자체가 실패해도 예외를 던지지 않는다."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_utf8_env(),
        )
        ok = proc.returncode == 0
        out = (proc.stdout or "") + (proc.stderr or "")
        return ok, out.strip()[-2000:]
    except FileNotFoundError as exc:
        return False, f"실행 파일 없음: {exc}"
    except subprocess.TimeoutExpired:
        return False, "시간 초과"
    except OSError as exc:
        return False, f"실행 오류: {exc}"


def _exists(rel: str) -> CheckResult:
    p = REPO_ROOT / rel
    return (f"{rel} 존재", p.exists(), "" if p.exists() else "파일/디렉터리 없음")


def _pip_offline_install_check() -> CheckResult:
    """오프라인 설치 — 빠른 단일 표본(win_amd64, py311)만 임시 디렉터리에 설치해
    실제 개발 환경(pip 캐시·site-packages)을 건드리지 않고 확인한다. (지시서의
    실행 명령은 pip install 그대로이며, 여기서는 부작용 회피를 위해 --target
    임시 디렉터리를 덧붙인 것뿐.) where.py 는 세션마다 자주 도는 빠른 진단이라
    표본 하나만 본다 — 플랫폼 6종(3.11~3.13 × win/linux) 전수는 아래
    tools/offline_verify.py 가 별도로, 더 깊게 확인한다."""
    req = REPO_ROOT / "project_code" / "requirements.txt"
    wheels = REPO_ROOT / "project_code" / "wheels"
    if not req.exists() or not wheels.exists():
        return ("오프라인 설치(표본: win_amd64/py311)", False, "requirements.txt 또는 wheels/ 없음")

    with tempfile.TemporaryDirectory() as tmp:
        ok, out = _run(
            [
                PYTHON, "-m", "pip", "install",
                "-r", str(req),
                "--no-index", "--find-links", str(wheels),
                "--target", tmp,
                "--platform", "win_amd64",
                "--python-version", "311",
                "--implementation", "cp",
                "--abi", "cp311",
                "--only-binary=:all:",
            ],
            timeout=60,
        )
        return ("오프라인 설치(표본: win_amd64/py311)", ok, out if not ok else "")


def _run_py(rel: str, args: list[str] | None = None, cwd: Path | None = None) -> CheckResult:
    p = REPO_ROOT / rel
    if not p.exists():
        return (f"python {rel}", False, "파일 없음")
    ok, out = _run([PYTHON, str(p)] + (args or []), cwd=cwd)
    return (f"python {rel}", ok, out)


def _manual(desc: str, note: str) -> CheckResult:
    """자동으로 참/거짓을 낼 수 없는 출구 항목. None 은 '통과'로 세지 않는다 —
    사람이 직접 확인하기 전에는 다음 단계로 넘어가지 않는다 (F-098)."""
    return (desc, None, note)


def _rebuild_and_run_all_tests(stage_label: str) -> list[CheckResult]:
    """firmware/tests 를 매번 소스에서 재빌드하고, 그 결과로 생긴 test_* 실행
    파일을 이름을 나열하지 않고 전수 탐색해 전부 돌린다.

    F-098 재현: 이전 단계 2c 는 기존 test_node_state 바이너리 하나만 실행하고
    make 도, 나머지 test_bitpack/test_siap_frame/test_status_codes/test_golden
    재실행도 하지 않아 오래된 바이너리가 그대로 '통과'로 잡혔다. 개발_착수_지시서
    §3.4 출구 ②는 "project_code/firmware/tests 4종 전량(make && ./test_*)"이다."""
    tests_dir = REPO_ROOT / "project_code" / "firmware" / "tests"
    if not tests_dir.exists():
        return [(f"{stage_label}: firmware/tests/ (make && ./test_*)", False, "디렉터리 없음")]

    results: list[CheckResult] = []
    try:
        ok, out = _run(["make"], cwd=tests_dir, timeout=180)
        results.append((f"{stage_label}: make (firmware/tests 전체 재빌드)", ok, out if not ok else ""))
        if not ok:
            return results

        test_bins = sorted(
            p for p in tests_dir.iterdir()
            if p.is_file() and p.name.startswith("test_") and p.suffix not in {".c", ".h", ".o", ".obj"}
        )
        if not test_bins:
            results.append((f"{stage_label}: test_* 실행 파일", False, "빌드 산출물 0개"))
            return results
        for p in test_bins:
            ok2, out2 = _run([str(p)], cwd=tests_dir)
            results.append((f"./{p.name}", ok2, out2))
        return results
    finally:
        # F-111 과 같은 이유 — 여기서 만든 실행파일들을 치우지 않으면
        # 이 스크립트 자신의 다음 실행에서 단계 0 오프라인 스캔이
        # 그 잔여물 때문에 실패한다.
        _run(["make", "clean"], cwd=tests_dir)


def check_stage_0() -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(_exists("project_code/requirements.txt"))
    results.append(_exists("project_code/wheels"))
    results.append(_exists("project_code/run.py"))
    results.append(_pip_offline_install_check())

    # F-144 — "'미구현' 출력"을 요구하던 옛 버전은 단계 0 시점의 스냅샷 사실을
    # 검사한 것이었다 — check_stage_4() 는 정반대로 "단계 4부터는 '미구현'
    # 문구가 사라져야 한다"고 명시적으로 요구한다(설계상 의도된 전이).
    # 그 문구를 여기서 계속 요구하면 단계 4가 완료되는 순간 이 단계 0
    # 검사가 영구히 깨지고, main() 은 첫 실패 단계에서 멈추므로 "현재
    # 단계"가 0으로 후퇴한다 — 이미 지나간 단계의 일회성 사실을 매번
    # 재검증하는 구조적 결함이다. 이제는 "정상 종료(exit 0)"만 본다 —
    # 그 이상의 실질 동작 검증은 check_stage_4() 의 몫이다.
    # 회귀 테스트: tools/tests/test_where.py::test_stage_0_does_not_require_no_구현_output_f144
    ok, out = _run([PYTHON, str(REPO_ROOT / "project_code" / "run.py"), "--mode", "simulate"])
    results.append(("run.py --mode simulate 가 정상 종료(exit 0)한다", ok, "" if ok else out))

    results.append(_run_py("tools/offline_verify.py"))
    return results


def check_stage_1() -> list[CheckResult]:
    return [
        _run_py("project_code/contracts/test_contract.py"),
        _run_py("project_docs/contracts/vectors/golden_verify.py"),
        _run_py("tools/layer_verify.py"),
    ]


def check_stage_2a() -> list[CheckResult]:
    tests_dir = REPO_ROOT / "project_code" / "firmware" / "tests"
    if not (tests_dir / "test_bitpack.c").exists():
        return [("firmware/tests/test_bitpack.c 존재", False, "파일 없음")]
    try:
        ok, out = _run(["make", "test_bitpack"], cwd=tests_dir)
        if not ok:
            return [("make test_bitpack", False, out)]
        ok2, out2 = _run([str(tests_dir / "test_bitpack")], cwd=tests_dir)
        return [("make test_bitpack", True, ""), ("./test_bitpack", ok2, out2)]
    finally:
        # F-111 — 여기서 만든 test_bitpack(.exe) 를 치우지 않으면 이
        # 진단 스크립트 자신의 다음 실행에서 단계 0(오프라인 실행파일
        # 스캔)이 그 잔여물 때문에 실패한다 — where.py 가 where.py 를
        # 오염시키는 자기 회귀였다. 성공·실패 어느 경우든 정리한다.
        _run(["make", "clean"], cwd=tests_dir)


def check_stage_2b() -> list[CheckResult]:
    """F-117 — 이전에는 make 를 부르지 않고 기존 바이너리 존재 여부만 봤다.
    check_stage_2a() 가 finally 에서 부르는 `make clean` 이 (Makefile 의
    CLEAN_FILES 에 2b 타깃도 있으므로) 2b 산출물까지 지우는데 2b 는 재빌드를
    안 해 순차 실행(단계 0→1→2a→2b) 시 구조적으로 통과할 수 없었다.
    check_stage_2a() 와 동일하게 여기서 직접 빌드하고, 성공·실패 모두
    finally 에서 정리한다. "빌드 자체 실패"와 "빌드는 됐는데 실행 파일이
    없다"(플랫폼별 이름 불일치 등)를 서로 다른 사유로 구분해 보고한다."""
    tests_dir = REPO_ROOT / "project_code" / "firmware" / "tests"
    targets = ("test_siap_frame", "test_status_codes", "test_golden")
    if not (tests_dir / "test_siap_frame.c").exists():
        return [("firmware/tests/test_siap_frame.c 존재", False, "파일 없음")]
    try:
        ok, out = _run(["make", *targets], cwd=tests_dir)
        if not ok:
            return [(f"make {' '.join(targets)}", False, out)]
        results: list[CheckResult] = [(f"make {' '.join(targets)}", True, "")]
        for bin_name in targets:
            # F-117 재발 방지 — .exists() 로 미리 걸러내지 않는다. Windows 에서
            # 확장자 없는 경로를 CreateProcess 에 넘기면 .exe 를 자동으로 찾아
            # 실행하지만(check_stage_2a 가 이미 이 방식에 기대고 있다), pathlib
            # 의 Path.exists() 는 그 자동 확장자 탐색을 하지 않아 "빌드는 됐는데
            # 실행 파일이 없다"는 거짓 실패를 냈다. 그냥 실행을 시도하고, 실행
            # 자체가 안 됐을 때(_run 의 FileNotFoundError 분기)만 "실행 파일
            # 누락"으로 본다 — 그래야 make 실패와 실행파일 누락과 실제 테스트
            # 실패 셋을 모두 구분해서 보고할 수 있다.
            p = tests_dir / bin_name
            ok2, out2 = _run([str(p)], cwd=tests_dir)
            results.append((f"./{bin_name}", ok2, out2))
        results.append(_run_py("tools/core_purity_verify.py"))
        return results
    finally:
        # F-117 — 성공이든 실패든 이 단계가 만든 바이너리를 치운다. 그렇지
        # 않으면 이 진단 스크립트 자신의 다음 실행(또는 offline_verify.py 의
        # 실행파일 스캔)이 잔여물로 오염된다 — check_stage_2a 와 같은 이유.
        _run(["make", "clean"], cwd=tests_dir)


def check_stage_2c() -> list[CheckResult]:
    # §3.4 출구: ① ./test_node_state ② firmware/tests 4종 전량(make && ./test_*)
    # ③ firmware_verify.py 50/50.
    #
    # F-121 — 이전에는 "①은 재빌드 후 전수 실행에 포함되므로 결과 목록 자체로
    # 드러난다"고 가정했다. 그러나 node_state.c/.h·test_node_state.c 가 없으면
    # Makefile 의 TARGETS 자체에 test_node_state 가 빠져 `make` 가 그대로
    # 성공하고, 전수 탐색은 우연히 남아 있던 4종(2a·2b 산출물)만 찾아 전부
    # 통과시켰다 — node_state 가 전혀 없어도 단계 2c 가 "통과"로 오판됐다.
    # 필수 소스 존재와 Makefile 등록을 먼저 명시적으로 검사하고, 재빌드
    # 결과에도 test_node_state 실행이 실제로 포함됐는지 이름으로 재확인한다.
    results: list[CheckResult] = []
    tests_dir = REPO_ROOT / "project_code" / "firmware" / "tests"
    core_dir = REPO_ROOT / "project_code" / "firmware" / "core"
    required = [
        core_dir / "node_state.c",
        core_dir / "node_state.h",
        tests_dir / "test_node_state.c",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
    if missing:
        results.append((
            "2c: node_state 소스 존재 (node_state.c/.h, test_node_state.c)",
            False,
            "없음: " + ", ".join(missing),
        ))
        return results

    makefile = tests_dir / "Makefile"
    if makefile.exists() and "test_node_state" not in makefile.read_text(encoding="utf-8", errors="replace"):
        results.append((
            "2c: Makefile TARGETS 에 test_node_state 등록",
            False,
            "Makefile 에 test_node_state 타깃이 없음",
        ))
        return results

    results.extend(_rebuild_and_run_all_tests("2c"))
    ran = {desc[2:] for desc, _, _ in results if desc.startswith("./")}
    node_state_ran = any(name.startswith("test_node_state") for name in ran)
    if not node_state_ran:
        results.append((
            "2c: ./test_node_state 실행됨",
            False,
            "소스·Makefile 등록은 있으나 재빌드 후 전수 실행 목록에 test_node_state 가 없음",
        ))

    results.append(_run_py("project_docs/firmware/firmware_verify.py"))
    return results


def check_stage_3() -> list[CheckResult]:
    results: list[CheckResult] = []
    siap_tests = REPO_ROOT / "project_code" / "siap" / "tests"
    if not siap_tests.exists() or not any(siap_tests.glob("test_*.py")):
        results.append(("pytest siap/tests/", False, "테스트 파일 없음"))
    else:
        ok, out = _run([PYTHON, "-m", "pytest", "siap/tests/"], cwd=REPO_ROOT / "project_code")
        results.append(("pytest siap/tests/", ok, out))
    results.append(_run_py("tools/xcodec_verify.py"))
    return results


def check_stage_4() -> list[CheckResult]:
    results: list[CheckResult] = []
    for mode in ("simulate", "replay"):
        ok, out = _run([PYTHON, str(REPO_ROOT / "project_code" / "run.py"), "--mode", mode])
        # 단계 4부터는 "미구현" 문구가 사라져야 한다 — 실제로 프레임을 주고받는다.
        really_works = ok and "미구현" not in out
        results.append((f"run.py --mode {mode} (실제 동작)", really_works, out if not really_works else ""))
    results.append(_run_py("tools/mode_verify.py"))
    return results


def check_stage_5() -> list[CheckResult]:
    results: list[CheckResult] = []
    backend_tests = REPO_ROOT / "project_code" / "backend" / "tests"
    if not backend_tests.exists() or not any(backend_tests.glob("test_*.py")):
        results.append(("pytest backend/tests/", False, "테스트 파일 없음"))
    else:
        ok, out = _run([PYTHON, "-m", "pytest", "backend/tests/"], cwd=REPO_ROOT / "project_code")
        results.append(("pytest backend/tests/", ok, out))
    results.append(_run_py("project_docs/db/verify.py"))
    results.append(_run_py("tools/db_live_verify.py"))
    return results


def check_stage_6() -> list[CheckResult]:
    results: list[CheckResult] = []
    api_test = REPO_ROOT / "project_code" / "backend" / "tests" / "test_api.py"
    if not api_test.exists():
        results.append(("pytest backend/tests/test_api.py", False, "파일 없음"))
    else:
        ok, out = _run([PYTHON, "-m", "pytest", "backend/tests/test_api.py"], cwd=REPO_ROOT / "project_code")
        results.append(("pytest backend/tests/test_api.py", ok, out))
    results.append(_run_py("project_docs/api/api_verify.py"))
    results.append(_run_py("tools/route_verify.py"))
    results.append(_run_py("tools/gate_e2e.py"))
    results.append(_run_py("tools/nodetype_verify.py"))
    return results


def check_stage_7() -> list[CheckResult]:
    # §3.9 출구 ③ "4화면 렌더 확인 (headless 스크린샷 4장)". 헤드리스 브라우저는
    # CLAUDE.md §4.1(의존성 최소화, 신규 패키지는 사용자 확인 후) 대상이라 여기서
    # 임의로 추가하지 않는다 — 그래서 자동 판정 불가로 명시한다 (F-098: 이전에는
    # 이 항목 자체가 없어서 검증기 2건만으로 단계가 '통과'로 잡혔다).
    return [
        _run_py("project_docs/web/web_verify.py"),
        _run_py("tools/web_live_verify.py"),
        _manual(
            "4화면 렌더 확인 (headless 스크린샷 4장)",
            "헤드리스 브라우저 도입은 신규 의존성이라 사용자 확인이 먼저 필요하다 "
            "(CLAUDE.md §4.1). 사람이 index/verify/rules/settings 4화면을 직접 렌더해 확인한다.",
        ),
    ]


# CLAUDE.md §2 디렉터리 구조 정본 — firmware/ 아래 보드 3종 디렉터리 이름.
# backend/ 노드 종류 하드코딩 금지(§1-6)는 서버 코드에 적용되며, 이미 설계로
# 고정된 firmware 디렉터리 이름을 진단 스크립트가 아는 것은 그 규칙과 무관하다.
BOARD_DIRS = ["arduino_sensor_node", "arduino_actuator_node", "esp32_node"]

# 펌웨어 설계서 §3.1(타깃 제원)·§3.4(정적 메모리 표) 의 정본 SRAM 용량과,
# 개발_착수_지시서 §1.5 의 예산선("SRAM 40% 이하")을 그대로 옮긴다. ESP32는
# §3.1 이 "여유가 있으므로 제약이 되지 않는다"고 명시해 대상에서 뺀다 — 대신
# avr-size 자체가 AVR 전용 도구라 ESP32 .elf 에는 애초에 적용하지 않는다.
SRAM_BUDGET_BYTES = {"arduino_sensor_node": 2048, "arduino_actuator_node": 2048}
SRAM_BUDGET_RATIO = 0.40

# avr-size 기본(berkeley) 출력의 데이터 행: "   text   data    bss    dec    hex  file"
_AVR_SIZE_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+[0-9A-Fa-f]+\s+\S+\s*$")


def _parse_avr_size(output: str) -> tuple[int, int, int] | None:
    """avr-size 출력에서 (text, data, bss) 를 뽑는다. 헤더 행은 숫자로 시작하지
    않으므로 자동으로 걸러진다. F-104: 이전에는 이 파싱이 아예 없어 avr-size
    가 종료 코드 0만 내면(크기와 무관하게) 통과했다 — 999,999,999 byte 짜리
    가짜 출력도 그대로 OK였다."""
    for line in output.splitlines():
        m = _AVR_SIZE_RE.match(line)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


def _build_and_size(board_dir: Path) -> list[CheckResult]:
    """보드 디렉터리를 실제로 재빌드하고 avr-size 를 실측한 뒤, AVR 보드 2종은
    펌웨어 설계서 §3.1·§3.4 의 SRAM 예산과 실제로 비교한다. 결과를 재사용하지
    않는다 — §1.5 "실측값이 설계서의 추정치를 대체한다"의 실측이 매번 새로 나와야
    한다."""
    name = board_dir.name
    if not board_dir.exists():
        return [(f"{name}: 빌드", False, "디렉터리 없음")]
    makefile = board_dir / "Makefile"
    if not makefile.exists():
        return [(f"{name}: 빌드", False, "Makefile 없음")]

    results: list[CheckResult] = []
    ok, out = _run(["make"], cwd=board_dir, timeout=180)
    results.append((f"{name}: make", ok, out if not ok else ""))
    if not ok:
        return results

    artifacts = list(board_dir.glob("*.elf"))
    if not artifacts:
        results.append((f"{name}: 빌드 산출물(.elf)", False, ".elf 없음"))
        return results
    size_ok, size_out = _run(["avr-size", str(artifacts[0])], cwd=board_dir)
    results.append((f"{name}: avr-size 실측", size_ok, size_out))
    if not size_ok:
        return results

    budget = SRAM_BUDGET_BYTES.get(name)
    if budget is None:
        # ESP32 — §3.1 상 제약이 아니므로 예산 비교 항목 자체를 만들지 않는다
        # (자동화 불가를 MANUAL 로 남기는 것과 다르다: 여기는 설계서가 이미
        # "제약 아님"이라고 판정을 끝낸 경우다).
        return results

    parsed = _parse_avr_size(size_out)
    if parsed is None:
        results.append((f"{name}: avr-size 출력 해석", False,
                         f"text/data/bss 파싱 실패:\n{size_out}"))
        return results
    text, data, bss = parsed
    sram_used = data + bss
    ratio = sram_used / budget
    within = ratio <= SRAM_BUDGET_RATIO
    results.append((
        f"{name}: SRAM 예산 대조 (실측 {sram_used}B / {budget}B = {ratio:.1%}, "
        f"상한 {SRAM_BUDGET_RATIO:.0%})",
        within,
        "" if within else
        (f"펌웨어 설계서 §3.1·§3.4, 개발_착수_지시서 §1.5 SRAM 40% 예산 초과 "
         f"(text={text} data={data} bss={bss})"),
    ))
    return results


def check_stage_8() -> list[CheckResult]:
    # §3.10 출구: ① 3종 빌드 + avr-size 실측이 설계서 예산 안
    # ② board_verify.py — core/ 오브젝트 해시 3종 동일
    # ③ project_code/logs/*.jsonl 실측 캡처가 replay 로 재생
    # F-098: 이전에는 ②(board_verify.py) 만 실행하고 ①③은 아예 실행하지 않았다.
    results: list[CheckResult] = []
    firmware_dir = REPO_ROOT / "project_code" / "firmware"
    for board_name in BOARD_DIRS:
        results.extend(_build_and_size(firmware_dir / board_name))
    results.append(_run_py("tools/board_verify.py"))
    results.append(_manual(
        "project_code/logs/*.jsonl 실측 캡처가 replay 로 재생",
        "결측·위반·지연·오류알림이 실제로 들어 있고 합성이 아님(CLAUDE.md §1-1)은 "
        "촬영 세션 없이 기계로 판정할 수 없다. 파일 존재·replay 실행 성공은 "
        "확인하되, '합성이 아니다'는 사람이 최종 판단한다.",
    ))
    return results


STAGES: list[tuple[str, str, Callable[[], list[CheckResult]]]] = [
    ("0", "골격 · 오프라인 의존성", check_stage_0),
    ("1", "contracts/ 이관", check_stage_1),
    ("2a", "firmware/core/bitpack", check_stage_2a),
    ("2b", "firmware/core/siap_frame", check_stage_2b),
    ("2c", "firmware/core/node_state", check_stage_2c),
    ("3", "siap/ 게이트웨이", check_stage_3),
    ("4", "sim/ · 전송 계층", check_stage_4),
    ("5", "backend/ 저장 계층", check_stage_5),
    ("6", "services/ · api.py", check_stage_6),
    ("7", "web/ 화면 4종", check_stage_7),
    ("8", "보드 3종 바인딩 · 실물 통합", check_stage_8),
]


def main() -> int:
    print("=== tools/where.py : 단계 출구 명령 순차 판정 ===\n")
    for stage_id, name, check_fn in STAGES:
        results = check_fn()
        statuses = [ok for _, ok, _ in results]
        if all(s is True for s in statuses):
            stage_mark = "통과"
        elif any(s is False for s in statuses):
            stage_mark = "실패"
        else:
            stage_mark = "수동확인 필요"  # 전부 True 또는 None, False 는 없음
        print(f"[단계 {stage_id}] {name} - {stage_mark}")
        for desc, ok, detail in results:
            if ok is True:
                line_mark = "OK"
            elif ok is None:
                line_mark = "MANUAL"
            else:
                line_mark = "FAIL"
            _safe_print(f"    [{line_mark}] {desc}")
            if ok is not True and detail:
                for line in detail.splitlines()[-8:]:
                    _safe_print(f"        {line}")
        if stage_mark != "통과":
            print(f"\n>>> 현재 단계: {stage_id} ({name})")
            if stage_mark == "수동확인 필요":
                print(">>> 자동 판정 항목은 전부 통과했다. [MANUAL] 항목은 사람이 직접 확인해야")
                print(">>> 이 단계가 끝난 것으로 볼 수 있다 (F-098: 자동화 불가 항목을 통과로 간주하지 않는다).")
            else:
                print(">>> 위 [FAIL] 항목이 이 단계에서 아직 통과하지 못한 출구 조건이다.")
            return 0
        print()

    print(">>> 모든 단계의 출구 명령이 통과했다. 단계 8 이후 상태다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
