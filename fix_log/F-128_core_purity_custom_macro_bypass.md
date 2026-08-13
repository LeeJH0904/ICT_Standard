# F-128 · 임의 이름 보드 매크로가 core 순수성 검사를 우회

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/core_purity_verify.py:65-80,169-230` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §1-5 — “`project_code/firmware/core/`를 특정 보드용으로 수정”하는 것을 금지한다. 개발 착수 지시서 §3.3은 `core/`의 보드 판별 매크로가 0개인지 기계 판정하도록 요구한다.

## 현상

F-122 보완 뒤 검증기는 `ARDUINO`, `__AVR__`, `ESP32`, `ESP8266`, `__XTENSA__`, `PLATFORMIO`라는 알려진 이름만 정규식과 `gcc -D` 조합으로 검사한다. 빌드 플래그로 정의하는 임의 이름의 조건부 컴파일은 이름 목록에 없으므로 세 겹 검사를 모두 통과한다.

```c
#if SIAP_PLATFORM
int siap_board_specific_branch = 1;
#else
int siap_board_specific_branch = 0;
#endif
```

이 파일에 검증기의 `_check_includes_textual`, `_check_includes_compiler`, `_check_board_macros`를 그대로 실행한 결과 세 위반 목록과 판정 불가 목록이 모두 비었고 `VERIFIER_ACCEPTS=True`였다. 그러나 gcc 전처리 결과는 기본 빌드에서 `=0`, `-DSIAP_PLATFORM=1`에서 `=1`로 갈렸다.

## 영향

보드별로 다른 `core/` 코드가 신설 검증기 `6/6`을 통과할 수 있다. 서로 다른 MCU 3종이 동일 프로토콜 코어를 쓴다는 핵심 주장 1의 기계 증거가 여전히 우회 가능하다. F-122의 처리 사유인 “원본 이름은 어딘가에 나타나야 한다”는 가정은 원본 이름 자체를 빌드 플래그에서 임의로 정하면 성립하지 않는다.

## 재현

1. 위 코드를 임시 `.c` 파일로 둔다.
2. `core_purity_verify.py`의 세 검사 함수에 그 파일을 전달한다 — 위반 0건.
3. `gcc -E -P file.c` — `siap_board_specific_branch = 0`.
4. `gcc -E -P -DSIAP_PLATFORM=1 file.c` — `siap_board_specific_branch = 1`.

## 제안

알려진 보드 이름의 차단 목록으로 “보드 분기 0개”를 증명하지 말고, include guard 등 허용된 전처리 조건을 제외한 `core/`의 조건부 컴파일 자체를 독립적으로 제한하거나 실제 보드 3종의 전처리·오브젝트 동일성을 대조한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | 보고된 PoC(`#if SIAP_PLATFORM ... #endif`)를 `project_code/firmware/core/_f128_poc.c`로 배치 후 실행 — 6/6 통과·exit 0 재현. F-122로 보완한 (a')/(b')는 여전히 "알려진 보드 이름 목록"(ARDUINO·__AVR__·ESP32·ESP8266·__XTENSA__·PLATFORMIO)에 의존해, 목록에 없는 임의 이름은 텍스트 스캔도 gcc 매크로 조합도 못 잡는 구조적 한계임을 확인. PoC 제거 후 원상복구 확인 |
| 2026-08-08 | 수정완료 | 판정 방향을 블랙리스트에서 화이트리스트로 전환하는 셋째 겹 (c)를 신설: `core/`의 모든 `#if`/`#ifdef`/`#ifndef`/`#elif`는 ① 표준 include guard(`#ifndef NAME` 바로 다음 줄이 `#define NAME`) ② 컴파일러 자기식별(`defined(__GNUC__)`/`defined(__clang__)`, bitpack.h의 SIAP_WUR가 실제로 쓰는 패턴) 둘 중 하나가 아니면 전부 위반으로 본다 — 이름을 몰라도 "목록 밖의 존재 자체"가 증거가 되므로 임의 이름 매크로도 구조적으로 잡힌다. 기존 (a)/(b)/(a')/(b')는 "무엇을 숨겼는가"를 보여주는 부가 증거로 유지. 회귀 테스트 신설: `test_f128_arbitrary_macro_name_is_caught`(PoC가 블랙리스트(b)는 통과하고 화이트리스트(c)에서만 잡히는지 이중 확인), `test_clean_core_files_still_pass`에 실제 bitpack.h 패턴(`#if defined(__GNUC__)` + include guard)을 포함해 화이트리스트 오탐 없음 확인. 결함 주입: (c) 검사 함수와 호출부를 통째로 되돌린 사전수정본으로 실행 — `test_f128_...`·`test_clean_core_files_still_pass` 2건이 `AttributeError`로 정확히 실패함을 확인(함수 자체가 없어짐), 수정본 복원 후 `tools/tests/` 6/6 재통과. 실제 PoC 재투입 시 7/7 중 (c) 1건만 FAIL로 잡히고 F-122 PoC도 여전히 잡힘(회귀 없음)을 확인. 정상 `core/` 6개 파일은 7/7 통과(오탐 없음) 유지. `python tools/run_all.py` 12/12 재확인 |
