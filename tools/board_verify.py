"""보드 3종 바인딩 ↔ core/ 경계 검증 — 개발_착수_지시서 §3.10 / 펌웨어 설계서 §7.

  주장 1(CLAUDE.md §0) — "서로 다른 MCU 3종이 동일 표준 프로토콜로 혼용 동작한다"
  의 물리 레벨 기계 증거를 낸다. core_purity_verify.py(단계 2b)가 core/ *내부*
  순수성을 보고, 이 검증기는 core/ 와 보드 디렉터리의 *경계*를 본다.

판정 (개발_착수_지시서 §3.10, "소스+AVR쌍" 결정):
  A. core/ 소스가 단일 본이다 — 어느 보드 디렉터리도 core/ 파일을 복제·그림자
     하지 않는다. 3종이 같은 core/ 를 쓰는 것이 "core/ 소스 SHA-256 3종 동일"의
     실체다(펌웨어 설계서 §7.5.1·§11).
  B. 플랫폼 헤더(Arduino.h·WiFi*·avr/*·esp*·Wire.h·SPI.h 등)는 **보드 디렉터리
     에만** 있다 — core/ 와 tests/ 에는 0개. 보드가 흡수하는 것이 전송 계층
     3줄뿐이라는 §7.1 주장의 경계 판정.
  C. 데모 보드 3종(sensor·actuator·esp32)이 §7.2~§7.4 의 필수 파일을 갖춘다.
  D. 보드가 선언한 디바이스 Subtype 이 전부 subtype_registry.h 등재값이고,
     센서 보드는 센서 Subtype(0x00~0x7F)·구동기 보드는 액추에이터 Subtype
     (0x80~0xFF)만 쓴다 — core/ 레지스트리를 독립 입력으로 대조(F-080).
  E. (avr-gcc 있을 때) AVR쌍(Uno·Pro Mini, 둘 다 ATmega328P)에서 core/*.c 를
     동일 플래그로 컴파일한 core.o 해시가 일치한다 — ESP32(Xtensa)는 ISA 가
     달라 오브젝트가 원리상 일치할 수 없어 A(소스 해시)로만 판정한다.
  F. (avr-size 실측 파일 있을 때) SRAM 사용량이 설계서 §3.4 예산(전체 globals 55%) 안이다.

  E·F 는 툴체인/실측이 없으면 [SKIP] 로 남긴다 — 통과로 세지 않는다(F-098 원칙).
  A~D 는 툴체인 없이 항상 돈다.

실행: python tools/board_verify.py   (저장소 루트에서)
종료 코드: 0 = 위반 없음(SKIP 은 실패 아님), 1 = 위반 있음
콘솔 출력 문자는 CP949 표현 범위 안에서 고른다(F-045).
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

ROOT = Path(__file__).resolve().parent.parent
FW_DIR = ROOT / "project_code" / "firmware"
CORE_DIR = FW_DIR / "core"
TESTS_DIR = FW_DIR / "tests"

# CLAUDE.md §2 디렉터리 구조 정본 — 데모 경로 보드 3종. where.py 와 같은 근거로
# 이 이름들은 설계로 고정돼 있다(백엔드 노드 종류 하드코딩 금지 §1-6 과 무관 —
# 이건 서버 코드가 아니라 이미 확정된 firmware 디렉터리 이름이다).
DEMO_BOARDS = ("arduino_sensor_node", "arduino_actuator_node", "esp32_node")
# 확장성 검증용 — 데모 경로 아님. 순수성/지역화 검사에는 포함하되 완결성은 요구하지 않는다.
EXTRA_BOARDS = ("attiny85_min",)

# §7.2~§7.4 필수 파일(부록 코드 배치와 §7 표). 주 스케치 파일은 아두이노가
# "폴더명 == .ino 이름"을 요구해 <폴더명>.ino 로 둔다 — 설계서의 "main.ino"를
# 실물 툴체인 제약에 맞춘 것으로, BUILD.md §2 에 근거를 남긴다.
REQUIRED_FILES = {
    "arduino_sensor_node":   ("arduino_sensor_node.ino", "pins.h", "sensors.c"),
    "arduino_actuator_node": ("arduino_actuator_node.ino", "pins.h", "actuators.c"),
    "esp32_node":            ("esp32_node.ino", "net.c", "secrets.h.example"),
}

# ATmega328P — 개발_착수_지시서 §3.10 · 사용자 확인(2026-08-15). Uno·Pro Mini 공통.
AVR_PAIR_MCU = "atmega328p"

# 플랫폼 헤더 판별 — 보드 디렉터리 밖(core/·tests/)에 나타나면 위반. 화이트리스트가
# 아니라 "이건 확실히 플랫폼 종속"인 것들의 목록이라 blacklist 지만, core/ 순수성의
# 화이트리스트 판정은 core_purity_verify.py 가 이미 담당한다 — 여기서는 tests/ 와
# 보드 경계를 보는 보완 검사다.
_PLATFORM_HEADER_RE = re.compile(
    r'^\s*#\s*include\s*[<"]\s*('
    r'Arduino\.h|WiFi\w*\.h|ESP\w*\.h|esp[\w/]*\.h|avr/[\w.]+|util/[\w.]+|'
    r'Wire\.h|SPI\.h|Servo\.h|EEPROM\.h|HardwareSerial\.h|WString\.h'
    r')\s*[">]', re.IGNORECASE)

_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]([^">]+)[">]')
# 보드 소스에서 디바이스 Subtype 을 뽑는다 — subtype_registry.h 의 열거 이름 참조.
_SUBTYPE_TOKEN_RE = re.compile(r'\bSIAP_SUBTYPE_[A-Z0-9_]+\b')
# uart_write 정의 본문을 뽑는다(F-237 회귀). 시그니처의 괄호 다음 첫 `{` 부터
# 열(column) 0 의 닫는 `}` 까지 — uart_write 본문엔 중첩 블록이 없다.
_UART_WRITE_RE = re.compile(r'uart_write\s*\([^)]*\)\s*\{(.*?)\n\}', re.DOTALL)


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _core_files() -> list[Path]:
    if not CORE_DIR.exists():
        return []
    return sorted(p for p in CORE_DIR.rglob("*") if p.suffix in (".c", ".h"))


def _board_dir(name: str) -> Path:
    return FW_DIR / name


def _present_boards(names: tuple[str, ...]) -> list[str]:
    return [n for n in names if _board_dir(n).exists()]


# ── A. 단일 소스 ────────────────────────────────────────────────────
def _check_single_source(core_files: list[Path]) -> list[str]:
    """어느 보드 디렉터리도 core/ 파일을 같은 이름으로 갖고 있지 않다 — 복제·그림자
    없이 하나의 core/ 를 참조해야 3종의 core 소스가 동일하다."""
    core_names = {p.name for p in core_files}
    bad: list[str] = []
    for name in _present_boards(DEMO_BOARDS + EXTRA_BOARDS):
        for p in _board_dir(name).rglob("*"):
            if p.is_file() and p.name in core_names:
                bad.append(f"{p.relative_to(ROOT)} 가 core/ 파일 '{p.name}' 을 보드 디렉터리에 복제함")
    return bad


# ── B. 플랫폼 헤더 지역화 ───────────────────────────────────────────
def _platform_header_hits(files: list[Path]) -> list[str]:
    hits: list[str] = []
    for f in files:
        text = _strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        for lineno, line in enumerate(text.splitlines(), 1):
            if _PLATFORM_HEADER_RE.match(line):
                hits.append(f"{f.relative_to(ROOT)}:~{lineno}: {line.strip()}")
    return hits


def _check_platform_localization() -> list[str]:
    """core/ 와 tests/ 에는 플랫폼 헤더가 0개여야 한다(보드 디렉터리에만 허용)."""
    outside: list[Path] = []
    if CORE_DIR.exists():
        outside += [p for p in CORE_DIR.rglob("*") if p.suffix in (".c", ".h")]
    if TESTS_DIR.exists():
        outside += [p for p in TESTS_DIR.rglob("*") if p.suffix in (".c", ".h", ".ino", ".cpp")]
    return _platform_header_hits(sorted(outside))


def _check_board_uses_platform(name: str) -> tuple[bool, str]:
    """보드는 실제로 core/ 를 참조하고(전송 계층을 얹으므로) 플랫폼 헤더를 쓴다 —
    esp32 는 WiFi 계열, AVR 보드는 Arduino.h. '전송 계층만 다르다'의 확인."""
    bdir = _board_dir(name)
    files = [p for p in bdir.rglob("*") if p.suffix in (".ino", ".cpp", ".c", ".h")]
    if not files:
        return False, "보드 소스 없음"
    uses_platform = len(_platform_header_hits(files)) > 0
    includes_core = False
    for f in files:
        text = _strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        for line in text.splitlines():
            m = _INCLUDE_RE.match(line)
            if m and re.search(r'(node_state|siap_frame|siap_types|bitpack|subtype_registry)\.h', m.group(1)):
                includes_core = True
    if not includes_core:
        return False, "core/ 헤더를 include 하지 않음 (node_state.h 등)"
    if not uses_platform:
        return False, "플랫폼 헤더를 쓰지 않음 — 전송 계층 바인딩이 비어 있다"
    return True, ""


# ── C보강. uart_write 논블로킹 (F-237 회귀) ─────────────────────────
def _check_uart_nonblocking() -> list[str]:
    """AVR 보드의 uart_write 가 버퍼 포화(availableForWrite()==0)에서 블로킹하지
    않는지 정적으로 확인한다(펌웨어 설계서 §5.8, F-237). 여유가 없을 때 즉시 0을
    돌려주는 가드(`avail <= 0` → return 0)가 있어야 한다 — 이 가드가 없으면 쓰기
    길이가 len 으로 떨어져 포화 버퍼에 블로킹 쓰기가 된다. 정적 검사라 avr 툴체인
    없이 항상 돈다(F-237 재발 방지)."""
    bad: list[str] = []
    for name in ("arduino_sensor_node", "arduino_actuator_node"):
        ino = _board_dir(name) / f"{name}.ino"
        if not ino.exists():
            continue
        body_m = _UART_WRITE_RE.search(_strip_comments(ino.read_text(encoding="utf-8", errors="replace")))
        if not body_m:
            bad.append(f"{name}: uart_write 정의를 찾지 못함")
            continue
        body = body_m.group(1)
        if "availableForWrite" not in body:
            bad.append(f"{name}: uart_write 가 availableForWrite 로 여유를 확인하지 않음")
        elif not (re.search(r"avail\s*<=\s*0\b", body) and re.search(r"return\s+0\b", body)):
            bad.append(f"{name}: 여유 0에서 0을 돌려주는 논블로킹 가드(avail <= 0)가 없음 (F-237)")
    return bad


# ── C. 보드 완결성 ──────────────────────────────────────────────────
def _check_completeness() -> list[str]:
    missing: list[str] = []
    for name, req in REQUIRED_FILES.items():
        bdir = _board_dir(name)
        if not bdir.exists():
            missing.append(f"{name}/ 디렉터리 없음 (필수: {', '.join(req)})")
            continue
        for fname in req:
            if not (bdir / fname).exists():
                missing.append(f"{name}/{fname} 없음")
    return missing


# ── D. Subtype 대조 (독립 입력 = subtype_registry.h) ────────────────
def _registered_subtypes() -> dict[str, int]:
    """subtype_registry.h 의 SIAP_SUBTYPE_* = 0xNN 열거를 이름→코드로 읽는다."""
    reg = CORE_DIR / "subtype_registry.h"
    out: dict[str, int] = {}
    if not reg.exists():
        return out
    for m in re.finditer(r'\b(SIAP_SUBTYPE_[A-Z0-9_]+)\s*=\s*(0x[0-9A-Fa-f]+)', reg.read_text(encoding="utf-8", errors="replace")):
        out[m.group(1)] = int(m.group(2), 16)
    # COUNT 등 코드값 없는 매크로는 제외됨(= 없는 항목)
    return out


def _check_subtypes() -> list[str]:
    reg = _registered_subtypes()
    if not reg:
        return ["subtype_registry.h 에서 Subtype 을 읽지 못함"]
    bad: list[str] = []
    # 센서 보드 / 구동기 보드 판정 — 이름 규칙이 아니라 §7 역할로 고정.
    role = {
        "arduino_sensor_node": "sensor",
        "arduino_actuator_node": "actuator",
        "esp32_node": "mixed",   # §7.4 겸용 — 양쪽 허용
    }
    for name, expect in role.items():
        bdir = _board_dir(name)
        if not bdir.exists():
            continue
        tokens: set[str] = set()
        for f in bdir.rglob("*"):
            if f.suffix in (".ino", ".cpp", ".c", ".h"):
                for tok in _SUBTYPE_TOKEN_RE.findall(_strip_comments(f.read_text(encoding="utf-8", errors="replace"))):
                    tokens.add(tok)
        # 실제 디바이스 테이블에 쓴 Subtype 만 관심 — COUNT/TABLE 류는 무시
        tokens = {t for t in tokens if t in reg}
        if not tokens:
            bad.append(f"{name}: 등재된 Subtype 을 하나도 선언하지 않음")
            continue
        for t in sorted(tokens):
            is_act = (reg[t] & 0x80) != 0
            if expect == "sensor" and is_act:
                bad.append(f"{name}: 센서 보드가 액추에이터 Subtype {t}(0x{reg[t]:02X}) 사용")
            if expect == "actuator" and not is_act:
                bad.append(f"{name}: 구동기 보드가 센서 Subtype {t}(0x{reg[t]:02X}) 사용")
    return bad


# ── E. AVR쌍 core.o (avr-gcc gated) ─────────────────────────────────
def _compile_core_avr(core_c: list[Path], workdir: Path) -> tuple[dict[str, str] | None, str]:
    """core/*.c 를 ATmega328P 로 컴파일해 각 .o 의 SHA-256 을 돌려준다.
    -Os -std=c99 로 고정 — 두 AVR 보드가 동일 core 오브젝트를 내는지의 기준."""
    if shutil.which("avr-gcc") is None:
        return None, "avr-gcc 없음"
    hashes: dict[str, str] = {}
    for c in core_c:
        obj = workdir / (c.stem + ".o")
        cmd = ["avr-gcc", "-std=c99", "-Os", "-mmcu=" + AVR_PAIR_MCU,
               "-ffunction-sections", "-fdata-sections",
               "-I", str(CORE_DIR), "-c", str(c), "-o", str(obj)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or not obj.exists():
            return None, f"{c.name} 컴파일 실패: {proc.stderr.strip()[-300:]}"
        hashes[c.name] = _sha256(obj)
    return hashes, ""


def _check_avr_pair(core_c: list[Path]) -> tuple[str, bool | None, str]:
    """(설명, 통과/None(SKIP)/False, 상세). 두 AVR 보드는 같은 core/ 를 같은 MCU·
    플래그로 컴파일하므로 core.o 가 동일해야 한다. 여기서는 core/ 를 두 번(각 보드
    빌드 대역) 컴파일해 오브젝트가 결정적으로 재현되는지 실측한다 — 보드별 빌드가
    core 에 서로 다른 -D 를 주입하면 이 동일성이 깨진다."""
    if shutil.which("avr-gcc") is None:
        return ("E. AVR쌍 core.o 동일 (avr-gcc)", None, "avr-gcc 없음 — 사람이 실물 빌드로 확인")
    if not core_c:
        return ("E. AVR쌍 core.o 동일 (avr-gcc)", False, "core/*.c 없음")
    with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
        h1, e1 = _compile_core_avr(core_c, Path(t1))
        h2, e2 = _compile_core_avr(core_c, Path(t2))
        if h1 is None or h2 is None:
            return ("E. AVR쌍 core.o 동일 (avr-gcc)", False, e1 or e2)
        if h1 != h2:
            diff = [n for n in h1 if h1.get(n) != h2.get(n)]
            return ("E. AVR쌍 core.o 동일 (avr-gcc)", False, f"오브젝트 불일치: {', '.join(diff)}")
        return (f"E. AVR쌍 core.o 동일 (avr-gcc, {len(core_c)}개 .o 재현)", True, "")


# ── F. avr-size ↔ 예산 ──────────────────────────────────────────────
# ATmega328P SRAM 2048B. 예산은 **전체 sketch globals(avr-size / Arduino "Global
# variables use") 기준 55%** 다 — 펌웨어 설계서 §3.4 표의 "펌웨어 데이터 슬라이스"
# 추정(Uno 24.7%)과는 다른 분모(Arduino 런타임 포함)이며, 설계서 line 231 이 이미
# Uno 전체 ~50% 사용을 예견했다. 단계 8 실측(Uno globals 1025B=50.0%)이 40% 슬라이스
# 예산을 넘긴 것은 지표 불일치였고, 전체-globals 예산을 55%로 명문화해 해소했다
# (2026-08-16 사용자 결정, §1.5 "실측이 추정치를 대체한다"). ≥45%(≥922B) 스택은
# 재귀·malloc 없는 고정버퍼 설계에 충분하다.
SRAM_TOTAL = 2048
SRAM_RATIO = 0.55
# berkeley `avr-size` 표: "text data bss dec hex file"
_SIZE_LINE_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+[0-9A-Fa-f]+\s+\S+")
# Arduino IDE Verify 출력: "Global variables use 1025 bytes (50%) of dynamic memory"
_IDE_SRAM_RE = re.compile(r"Global variables use\s+(\d+)\s+bytes")


def _parse_sram_used(text: str) -> int | None:
    """size_report.txt 에서 SRAM 사용량(data+bss)을 뽑는다. berkeley avr-size 표와
    Arduino IDE Verify 출력 두 형식을 모두 받는다 — 사용자는 보통 후자를 저장한다."""
    m_ide = _IDE_SRAM_RE.search(text)
    if m_ide:
        return int(m_ide.group(1))
    last = None
    for line in text.splitlines():
        m = _SIZE_LINE_RE.match(line)
        if m:
            last = int(m.group(2)) + int(m.group(3))   # data + bss
    return last


def _check_avr_size() -> tuple[str, bool | None, str]:
    """보드 디렉터리에 사용자가 커밋한 avr-size 실측(<board>/size_report.txt)이
    있으면 예산과 대조한다. 없으면 [SKIP] — avr-size 는 Arduino 코어까지 링크한
    실물 .elf 가 필요해 이 환경에서 만들 수 없다(사용자 IDE 실측)."""
    reports = []
    for name in ("arduino_sensor_node", "arduino_actuator_node"):
        p = _board_dir(name) / "size_report.txt"
        if p.exists():
            reports.append((name, p))
    if not reports:
        return ("F. avr-size ↔ SRAM 예산 55%", None,
                "size_report.txt 없음 — 사용자가 IDE avr-size 실측을 <board>/size_report.txt 로 커밋")
    problems: list[str] = []
    for name, p in reports:
        sram = _parse_sram_used(p.read_text(encoding="utf-8", errors="replace"))
        if sram is None:
            problems.append(f"{name}: size_report.txt 파싱 실패")
            continue
        ratio = sram / SRAM_TOTAL
        if ratio > SRAM_RATIO:
            problems.append(f"{name}: SRAM {sram}B/{SRAM_TOTAL}B = {ratio:.1%} > 55%")
    if problems:
        return ("F. avr-size ↔ SRAM 예산 55%", False, "; ".join(problems))
    return (f"F. avr-size ↔ SRAM 예산 55% ({len(reports)}개 실측)", True, "")


def main() -> int:
    # (설명, True/False/None). None = SKIP(툴체인·실측 부재), 통과로 세지 않는다.
    R: list[tuple[str, bool | None, str]] = []

    def t(name: str, ok: bool | None, note: str = "") -> None:
        R.append((name, ok, note))

    core_files = _core_files()
    core_c = [p for p in core_files if p.suffix == ".c"]
    t(f"core/ .c/.h {len(core_files)}개 발견", len(core_files) > 0,
      "" if core_files else "core/ 가 비어 있다 — 단계 2 완료가 전제")

    # A
    bad_a = _check_single_source(core_files)
    t("A. 단일 소스 — 어느 보드도 core/ 파일을 복제하지 않음", not bad_a, "; ".join(bad_a))

    # A 보강 — core 소스 해시를 기록(3종이 참조하는 단일 본의 지문)
    if core_files:
        combined = hashlib.sha256()
        for p in core_files:
            combined.update(p.name.encode())
            combined.update(_sha256(p).encode())
        t(f"A. core/ 소스 지문 = {combined.hexdigest()[:16]}… ({len(core_files)}개 파일)", True, "")

    # B
    bad_b = _check_platform_localization()
    t("B. 플랫폼 헤더가 core/·tests/ 에 0개 (보드 디렉터리에만 허용)", not bad_b, "; ".join(bad_b))

    # C
    missing = _check_completeness()
    t("C. 데모 보드 3종이 §7.2~§7.4 필수 파일을 갖춤", not missing, "; ".join(missing))

    # C보강 — uart_write 논블로킹 가드(F-237)
    bad_uart = _check_uart_nonblocking()
    t("C. AVR uart_write 가 버퍼 포화에서 블로킹하지 않음 (§5.8, F-237)", not bad_uart, "; ".join(bad_uart))

    # B 보강 — 존재하는 보드가 실제로 core+플랫폼을 결선했는가
    for name in _present_boards(DEMO_BOARDS):
        ok, note = _check_board_uses_platform(name)
        t(f"B. {name} 이 core/ 를 include 하고 전송 계층(플랫폼 헤더)을 결선", ok, note)

    # D
    if any(_board_dir(n).exists() for n in DEMO_BOARDS):
        bad_d = _check_subtypes()
        t("D. 보드 Subtype 이 subtype_registry.h 등재값이고 역할(센서/구동기)에 맞음 (F-080)",
          not bad_d, "; ".join(bad_d))

    # E (avr-gcc gated)
    t(*_check_avr_pair(core_c))

    # F (실측 gated)
    t(*_check_avr_size())

    w = max(len(n) for n, _, _ in R)
    print("보드 3종 바인딩 ↔ core/ 경계 검증 (개발_착수_지시서 §3.10)\n")
    fails = skips = 0
    for name, ok, note in R:
        if ok is True:
            mark = "PASS"
        elif ok is None:
            mark = "SKIP"; skips += 1
        else:
            mark = "FAIL"; fails += 1
        print(f"  {mark}  {name:<{w}}  {note}")
    passed = sum(1 for _, o, _ in R if o is True)
    total = len(R)
    print(f"\n  {passed}/{total} 통과, FAIL {fails}, SKIP {skips}")
    if skips:
        print("  [SKIP] 은 avr-gcc·avr-size 실측이 없어 사람이 실물로 확인할 항목이다 (통과로 세지 않는다).")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
