"""core/ 하드웨어 의존성 0 검증 — CLAUDE.md §1-5 / 펌웨어 설계서 §2.

  "project_code/firmware/core/ 를 특정 보드용으로 수정" 은 공모전 실격·감점
  사유다(CLAUDE.md §1-5) — "동일 응용계층" 주장이 무너진다. 이 검증기는 그
  주장을 기계로 판정하는 지점이다(개발_착수_지시서 §3.3 신설 검증기).

판정 두 가지:
  1. core/ 의 .c/.h 파일은 설계서 §2.1의 시스템 헤더 3종과 core/ 내부
     프로젝트 헤더만 include 한다.
  2. core/ 안에 보드 판별 매크로(#if defined(ARDUINO), #ifdef __AVR__ 등)가
     0개다 — 조건부 컴파일로 갈라치기하지 않는다.

F-118 — 원문 한 줄에 정규식이 직접 나타날 때만 include/지시문으로 인식하면
`#include/**/<Arduino.h>` 처럼 주석으로 포장하거나 줄을 이어 쓴 코드가
우회한다. 그래서 두 겹으로 본다:
  (a) 주석·줄 이어쓰기를 정규화한 텍스트에 대한 regex 스캔 (빠르고 gcc 불필요)
  (b) `gcc -E` 로 실제 전처리해 컴파일러 자신이 무엇을 포함시켰는지 확인
      (독립 입력 대조, F-080 원칙) — 이쪽이 최종 근거다. 존재하지 않는
      금지 헤더(예: avr/pgmspace.h)를 참조하면 전처리 자체가 실패하는데,
      그 실패 메시지에 금지 헤더 이름이 있으면 그것 자체가 위반 증거다.

F-122 — 위 두 겹 모두 "보드 매크로가 정의되지 않은 채로" 검사한다는 공통 전제가
있었다. 자체 매크로로 간접화하면 둘 다 우회된다:
    #define SIAP_BOARD ARDUINO
    #define SIAP_PLATFORM_HEADER <Arduino.h>
    #if SIAP_BOARD
    #include SIAP_PLATFORM_HEADER
    ...
(a) 는 `#include SIAP_PLATFORM_HEADER` 가 `<`/`"` 로 시작하지 않아 매치하지
않고, `#if SIAP_BOARD` 조건절 텍스트에도 보드 매크로 이름이 그대로 나타나지
않는다. (b) 는 `ARDUINO`·`__AVR__` 등을 아무것도 정의하지 않고 전처리하므로
`#if SIAP_BOARD`(= `#if ARDUINO` = undefined = 0) 가 거짓으로 접혀 `#include`
자체가 전처리기에 도달하지 않는다 — 실제 보드 빌드(Arduino IDE·PlatformIO)는
이 매크로들을 항상 정의하고 시작하므로, 정의 없이 하는 검사는 실제 빌드
조건을 재현하지 못한다. 대응:
  (a') `#define` 지시문의 치환 목록에도 보드 매크로 이름이 있으면 즉시
       위반으로 본다 — 매크로를 한 번 더 감싸도 원본 이름이 어딘가의
       치환 목록에는 나타나야 한다.
  (b') 지원 보드 매크로 조합(ARDUINO·__AVR__·ESP32·ESP8266·__XTENSA__·
       PLATFORMIO) 을 하나씩 정의해 gcc -E 를 반복한다 — 정의되지 않은
       한 번만으로는 조건부 분기 뒤에 숨은 include 를 절대 못 본다.

F-128 — F-122 의 (a')·(b') 는 여전히 "알려진 보드 이름 목록"이라는 전제에
기대고 있었다. 빌드 플래그로 정의하는 임의 이름은 그 목록에 없으므로
    #if SIAP_PLATFORM
    ...
    #endif
같은 코드는 (a')(이름이 목록에 없다)도 (b')(그 이름을 -D 로 정의해 보지
않았다)도 통과한다. 블랙리스트는 구조적으로 "우리가 아는 이름"만 막을 수
있다. 그래서 셋째 겹은 반대 방향으로 판정한다 — 화이트리스트:
  (c) core/ 안의 모든 #if/#ifdef/#ifndef/#elif 는 다음 둘 중 하나가
      **아니면** 전부 위반이다.
        · 헤더 include guard — `#ifndef NAME` 바로 다음 줄이 `#define NAME`
        · 컴파일러 자기식별 — `#if defined(__GNUC__)` / `defined(__clang__)`
          (bitpack.h 의 SIAP_WUR 정의처럼 *보드가 아니라 컴파일러* 이식성)
      이름을 알든 모르든, 목록에 없는 조건부 컴파일은 그 존재 자체가
      위반이다 — (a)/(b) 두 겹은 여전히 "무엇을 숨겼는가"를 설명하는
      부가 증거로 남긴다.

F-211 — 플랫폼 헤더 블랙리스트는 `string.h`와 알려지지 않은 SDK 헤더를
통과시켰다. include 경계도 반대 방향으로 판정한다 — 화이트리스트:
  (a) 소스 지시문은 <stdint.h>·<stddef.h>·<stdbool.h>, 또는 실제 core/
      안에 존재하는 따옴표 헤더만 허용한다.
  (b) gcc -H trace의 직접 include(depth 1)도 같은 목록과 대조한다. 허용된
      표준 헤더가 구현 내부에서 끌어오는 전이 헤더는 core의 직접 의존이
      아니므로 이 판정에서 제외한다.

실행: python tools/core_purity_verify.py   (저장소 루트에서)
종료 코드: 0 = 위반 없음, 1 = 위반 있음
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = ROOT / "project_code" / "firmware" / "core"

# 펌웨어 설계서 §2.1의 완전한 시스템 헤더 허용 목록.
_ALLOWED_SYSTEM_HEADERS = frozenset({"stdint.h", "stddef.h", "stdbool.h"})

# 금지 보드 판별 매크로 — #if/#ifdef/#elif 조건절 안에서 찾는다.
_BOARD_MACRO_RE = re.compile(
    r"\b(ARDUINO\w*|__AVR__?|__AVR\w*|ESP32\w*|ESP8266\w*|__XTENSA__|PLATFORMIO)\b"
)
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"])([^">]+)[">]')
_IFDIRECTIVE_RE = re.compile(r"^\s*#\s*(if|ifdef|elif)\b(.*)$")
# F-128 (c) — 화이트리스트 판정용.
_IFNDEF_RE = re.compile(r"^\s*#\s*ifndef\s+(\w+)\s*$")
_DEFINE_NAME_RE = re.compile(r"^\s*#\s*define\s+(\w+)\b")
# 컴파일러 자기식별만 허용 — 보드 이름이 아니라 툴체인 이식성(bitpack.h 의
# SIAP_WUR). `#if defined(X)` 와 `#ifdef X` 두 표기 모두 받는다.
_ALLOWED_COMPILER_IDENTS = {"__GNUC__", "__clang__"}
_DEFINED_X_RE = re.compile(r"^defined\s*\(\s*(\w+)\s*\)$")
# F-122 — #define 의 치환 목록(우변)에 보드 매크로 이름이 있으면, 그 이름을
# 다른 매크로로 감싸 #if/#include 에 쓰더라도 정의 시점에는 원본이 노출된다.
_DEFINE_RE = re.compile(r'^\s*#\s*define\s+(\w+)(?:\([^)]*\))?\s+(.*)$')

# F-122 (b') — 실제 보드 빌드가 켜고 시작하는 판별 매크로 조합. 하나씩
# 정의해 전처리를 반복한다 — 정의되지 않은 상태(기존 baseline)만으로는
# 조건부 분기 뒤에 숨은 include 를 볼 수 없다.
_BOARD_MACRO_DEFINES: tuple[str, ...] = (
    "ARDUINO=1", "__AVR__=1", "ESP32=1", "ESP8266=1", "__XTENSA__=1", "PLATFORMIO=1",
)


def _source_files() -> list[Path]:
    if not CORE_DIR.exists():
        return []
    return sorted(p for p in CORE_DIR.rglob("*") if p.suffix in (".c", ".h"))


def _is_within_core(path: Path) -> bool:
    try:
        path.resolve().relative_to(CORE_DIR.resolve())
        return True
    except ValueError:
        return False


def _source_include_violation(source: Path, opener: str, header: str) -> str | None:
    """소스 include 하나를 설계서 §2.1의 완전한 허용 목록과 대조한다."""
    header = header.strip()
    if opener == "<":
        if header in _ALLOWED_SYSTEM_HEADERS:
            return None
        return f"비허용 시스템 헤더 <{header}>"

    target = (source.parent / header).resolve()
    if _is_within_core(target) and target.is_file():
        return None
    return f"core/ 내부에 존재하지 않는 프로젝트 헤더 '{header}'"


def _compiler_include_violation(name_or_path: str) -> str | None:
    """gcc -H가 보여 준 직접 include의 해석 결과를 같은 허용 목록과 대조한다."""
    path = Path(name_or_path.strip()).resolve()
    if _is_within_core(path) and path.is_file():
        return None
    if path.name in _ALLOWED_SYSTEM_HEADERS:
        return None
    return f"비허용 직접 include {name_or_path.strip()}"


def _is_disallowed_compiler_header(name_or_path: str) -> bool:
    """F-122 전처리 실패 경로와 호환되는 F-211 허용 목록 판정 wrapper."""
    return _compiler_include_violation(name_or_path) is not None


def _strip_comments_and_joins(text: str) -> str:
    """C 주석(`/* */`, `//`)과 줄 이어쓰기(줄 끝의 `\\`)를 제거해, 전처리기가
    보는 모양에 가깝게 정규화한다(F-118). 문자열·문자 리터럴 내부의 `/*`는
    구분하지 않는다 — 이 저장소의 지시문 조건절에 그런 리터럴이 올 일이
    없고, 검증기 목적상 과도하게 안전한 쪽(더 잡는 쪽)이 낫다."""
    text = re.sub(r"\\\r?\n", "", text)                       # 줄 이어쓰기
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)   # 블록 주석
    text = re.sub(r"//[^\n]*", "", text)                      # 줄 주석
    return text


_HEADER_LITERAL_RE = re.compile(r'([<"])([^">]+\.h)[">]')


def _check_includes_textual(files: list[Path]) -> list[str]:
    """(a) 정규화된 텍스트의 include를 명시적 허용 목록으로 스캔.

    F-122 — `#include SIAP_PLATFORM_HEADER` 처럼 헤더 이름을 매크로로
    간접화하면 `_INCLUDE_RE`(직접 `<..>`/`"..."` 만 매치)를 피해간다. 그래서
    `#define` 치환 목록 안의 헤더 형태 리터럴(`<x.h>`/`"x.h"`)도 함께 본다 —
    간접화해도 실제 헤더 이름은 어딘가의 치환 목록에 그대로 나타나야 한다."""
    bad: list[str] = []
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        normalized = _strip_comments_and_joins(raw)
        for lineno, line in enumerate(normalized.splitlines(), 1):
            m = _INCLUDE_RE.match(line)
            if m:
                opener, header = m.group(1), m.group(2).strip()
                reason = _source_include_violation(f, opener, header)
                if reason:
                    bad.append(
                        f"{f.relative_to(ROOT)}:~{lineno}(정규화 후): "
                        f"{line.strip()} ({reason})"
                    )
                continue
            dm = _DEFINE_RE.match(line)
            if dm:
                for lit in _HEADER_LITERAL_RE.finditer(dm.group(2)):
                    opener, header = lit.group(1), lit.group(2)
                    reason = _source_include_violation(f, opener, header)
                    if reason:
                        bad.append(
                            f"{f.relative_to(ROOT)}:~{lineno}(정규화 후): {line.strip()}  "
                            f"(간접 정의: {reason})"
                        )
    return bad


def _preprocess_includes(f: Path, defines: tuple[str, ...] = ()) -> tuple[list[str] | None, str]:
    """(b) gcc -E -H로 전처리해 이 파일의 직접 include(depth 1)를 얻는다.
    gcc 가 없거나 전처리가 실패하면 (None, stderr) 를 돌려준다.
    `defines` 는 `-D이름=값` 형태로 미리 켜 둘 매크로들이다(F-122)."""
    cmd = ["gcc", "-E", "-H", "-x", "c"]
    for d in defines:
        cmd += ["-D", d]
    cmd += ["-I", str(CORE_DIR), str(f)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError as exc:
        return None, f"gcc 실행 실패: {exc}"
    included: list[str] = []
    for line in proc.stderr.splitlines():
        m = re.match(r"^([.]+)\s+(.+?)\s*$", line)
        if m and len(m.group(1)) == 1:
            included.append(m.group(2))
    if proc.returncode != 0:
        return None, proc.stderr
    return included, ""


def _check_includes_compiler(files: list[Path]) -> tuple[list[str], list[str]]:
    """(b) 의 결과. (위반 목록, 판정 불가 목록) 을 따로 돌려준다 — gcc 실행
    실패 등 "위반은 아니지만 확인도 못 했다"는 상태를 숨기지 않는다.

    F-122 (b') — 매크로를 아무것도 정의하지 않은 baseline 한 번만으로는
    `#if SIAP_BOARD`(간접 매크로) 뒤에 숨은 `#include` 가 전처리기에 도달하지
    않는다. 실제 보드 빌드가 켜고 시작하는 판별 매크로를 하나씩 정의해
    반복하고, baseline 포함 어느 조합에서든 허용 목록 밖 직접 include가 나오면
    위반이다. 허용 표준 헤더의 전이 include는 depth 2 이상이라 제외한다."""
    bad: list[str] = []
    unknown: list[str] = []
    for f in files:
        for defines in ((),) + tuple((d,) for d in _BOARD_MACRO_DEFINES):
            label = "정의 없음(baseline)" if not defines else f"-D{defines[0]}"
            included, err = _preprocess_includes(f, defines)
            if included is None:
                # 전처리 자체가 실패했다. 실패 사유(못 찾은 헤더 이름)에 비허용
                # 헤더가 있으면 그 자체가 위반 증거다 — 설치되지 않은 SDK도
                # "그걸 include 하려 했다"는 의도는 확인된다.
                found = re.findall(r"([\w./\\-]+\.h)", err)
                disallowed_hits = [h for h in found if _is_disallowed_compiler_header(h)]
                if disallowed_hits:
                    bad.append(f"{f.relative_to(ROOT)} [{label}]: 전처리 실패 — 비허용 헤더 참조 흔적 ({disallowed_hits[0]})")
                elif not defines:
                    # baseline 전처리 자체가 안 되면 판정 불가다. 매크로를
                    # 켠 조합에서의 실패는 (비허용 헤더가 없는 한) 정상적인
                    # 조건부 분기 결과일 수 있어 판정 불가로 세지 않는다.
                    unknown.append(f"{f.relative_to(ROOT)}: 전처리 자체가 실패했다 (gcc 없음 또는 다른 오류): {err.strip()[-200:]}")
                continue
            for inc in included:
                if _is_disallowed_compiler_header(inc):
                    bad.append(f"{f.relative_to(ROOT)} [{label}]: 실제 전처리 결과에 {inc} 포함")
    return bad, unknown


def _check_board_macros(files: list[Path]) -> list[str]:
    """정규화된 텍스트에서 #if/#ifdef/#elif 조건절의 보드 판별 매크로를 찾는다.

    F-122 (a') — 조건절 텍스트만 보면 `#if SIAP_BOARD` 처럼 보드 매크로를
    자체 매크로로 한 번 감싼 간접 조건을 놓친다. 그래서 `#define` 지시문의
    치환 목록(우변)도 함께 본다 — 몇 겹을 감싸든 원본 이름은 어딘가의
    치환 목록에 나타나야 하기 때문이다."""
    bad: list[str] = []
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        normalized = _strip_comments_and_joins(raw)
        for lineno, line in enumerate(normalized.splitlines(), 1):
            m = _IFDIRECTIVE_RE.match(line)
            if m:
                cond = m.group(2)
                hit = _BOARD_MACRO_RE.search(cond)
                if hit:
                    bad.append(f"{f.relative_to(ROOT)}:~{lineno}(정규화 후): {line.strip()}  (매크로: {hit.group(0)})")
                continue
            dm = _DEFINE_RE.match(line)
            if dm:
                macro_name, replacement = dm.group(1), dm.group(2)
                hit = _BOARD_MACRO_RE.search(replacement)
                if hit:
                    bad.append(
                        f"{f.relative_to(ROOT)}:~{lineno}(정규화 후): {line.strip()}  "
                        f"(간접 정의: #define {macro_name} 의 치환 목록에 보드 매크로 {hit.group(0)})"
                    )
    return bad


def _check_conditional_whitelist(files: list[Path]) -> list[str]:
    """(c) F-128 — 화이트리스트. core/ 안의 모든 #if/#ifdef/#ifndef/#elif 는
    include guard 이거나 컴파일러 자기식별이 아니면 전부 위반이다. 이름을
    미리 알아야 하는 (a)/(b) 와 달리, 목록에 없는 조건부 컴파일은 그 존재
    자체가 증거이므로 임의 이름의 매크로(빌드 플래그로 정의)도 잡는다."""
    bad: list[str] = []
    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        normalized = _strip_comments_and_joins(raw)
        lines = normalized.splitlines()
        for i, line in enumerate(lines):
            m_guard = _IFNDEF_RE.match(line)
            if m_guard:
                guard_name = m_guard.group(1)
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    dm = _DEFINE_NAME_RE.match(lines[j])
                    if dm and dm.group(1) == guard_name:
                        continue   # 허용 — 표준 include guard 형태
                bad.append(
                    f"{f.relative_to(ROOT)}:~{i + 1}(정규화 후): {line.strip()}  "
                    f"(include guard 형태가 아님 — 바로 다음 줄이 #define {guard_name} 이 아님)"
                )
                continue

            m_if = _IFDIRECTIVE_RE.match(line)
            if not m_if:
                continue
            cond = m_if.group(2).strip()
            dm2 = _DEFINED_X_RE.match(cond)
            ident = dm2.group(1) if dm2 else cond
            if ident in _ALLOWED_COMPILER_IDENTS:
                continue
            bad.append(
                f"{f.relative_to(ROOT)}:~{i + 1}(정규화 후): {line.strip()}  "
                f"(화이트리스트 밖 조건부 컴파일 — include guard·__GNUC__·__clang__ 만 허용)"
            )
    return bad


def main() -> int:
    R: list[tuple[bool, str, str]] = []

    def t(name: str, ok: bool, note: str = "") -> None:
        R.append((bool(ok), name, note))

    files = _source_files()
    t(f"core/ 스캔 대상 {len(files)}개 .c/.h 파일 발견", len(files) > 0,
      "0개면 아직 core/ 가 비어 있다 — 단계 2b 는 siap_frame.c/.h 를 만든 뒤 통과해야 한다"
      if not files else "")

    bad_inc_text = _check_includes_textual(files)
    t("(a) 소스 include 허용 목록 — 표준 타입 헤더 3종 또는 core/ 내부 헤더만 사용 (F-211)",
      not bad_inc_text, "; ".join(bad_inc_text))

    bad_inc_cc, unknown_cc = _check_includes_compiler(files)
    t("(b) gcc -H 직접 include 허용 목록 — 매크로 간접화도 동일 경계 적용 (F-118·F-211)",
      not bad_inc_cc, "; ".join(bad_inc_cc))
    t("(b) gcc -E 전처리가 전 파일에서 실행 가능했다 (판정 불가 0건)",
      not unknown_cc, "; ".join(unknown_cc))

    bad_macro = _check_board_macros(files)
    t("core/ 안에 보드 판별 매크로(#if defined(ARDUINO), #ifdef __AVR__ 등)가 0개 (\"동일 응용계층\" 주장의 근거)",
      not bad_macro, "; ".join(bad_macro))

    bad_whitelist = _check_conditional_whitelist(files)
    t("(c) 화이트리스트 — core/ 조건부 컴파일이 include guard·컴파일러 자기식별뿐 (F-128, 임의 이름 매크로도 포함)",
      not bad_whitelist, "; ".join(bad_whitelist))

    # 독립 입력 대조 (F-080, CLAUDE.md §6.2) — 이 파일 하나만 읽고 판정하지
    # 않는다. bitpack.h 자신이 이미 "core/ 는 플랫폼 헤더를 include 하지
    # 않는다"고 선언한 문서 주석과, 위 실측 스캔 결과가 일치하는지도 본다.
    bitpack_h = CORE_DIR / "bitpack.h"
    doc_claims_purity = bitpack_h.exists() and "하드웨어 의존성 0" in bitpack_h.read_text(encoding="utf-8", errors="replace")
    t("bitpack.h 자체 문서 주석이 core/ 순수성을 선언 (독립 입력 대조, F-080)",
      doc_claims_purity, "" if doc_claims_purity else "bitpack.h 를 찾지 못했거나 문구가 바뀌었다")

    w = max(len(n) for _, n, _ in R)
    print("core/ 하드웨어 의존성 0 검증 (CLAUDE.md §1-5)\n")
    for ok, n, note in R:
        print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
    p = sum(1 for o, *_ in R if o)
    print(f"\n  {p}/{len(R)} 통과")
    return 0 if p == len(R) else 1


if __name__ == "__main__":
    sys.exit(main())
