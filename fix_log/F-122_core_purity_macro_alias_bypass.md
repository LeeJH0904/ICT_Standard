# F-122 · core 순수성 검증기가 간접 보드 매크로를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/core_purity_verify.py:61-65,77-78,100-113,155-169` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §1-5는 `firmware/core/`의 특정 보드용 수정을 금지한다. 개발 착수 지시서 §3.3은 플랫폼 헤더 include와 보드 판별 매크로가 0개인지 기계 판정하도록 요구한다.

## 현상

검증기는 조건식에 `ARDUINO` 등이 직접 쓰인 경우만 잡고 매크로 정의 우변은 검사하지 않는다. `#include` 뒤에 헤더명이 바로 오지 않는 매크로 include도 텍스트 검사에서 제외하며, gcc 대조는 보드 매크로 없는 호스트 전처리 한 번뿐이다.

```c
#define SIAP_BOARD ARDUINO
#define SIAP_PLATFORM_HEADER <Arduino.h>
#if SIAP_BOARD
#include SIAP_PLATFORM_HEADER
int siap_board_specific = 1;
#else
int siap_board_specific = 0;
#endif
```

이 반례는 원본 검증기를 6/6, exit 0으로 통과했다. `gcc -E -DARDUINO=1`에서는 `Arduino.h`가 포함되고 보드 전용 분기가 선택됐다.

## 영향

플랫폼 종속 `core/`가 검증기를 통과해 서로 다른 MCU 3종의 동일 프로토콜 혼용이라는 핵심 주장 1의 기계 증거가 우회된다.

## 재현

```text
core_purity_verify.py: 6/6 통과, VERIFIER_EXIT=0
ARDUINO_HEADER_MARKER_PRESENT=True
ARDUINO_BRANCH_EXPANDS_HEADER_MACRO=True
```

## 제안

지원 보드 매크로 조합별 전처리 결과를 대조하고 매크로 정의·간접 조건도 검사해야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | 보고된 PoC(`SIAP_BOARD`/`SIAP_PLATFORM_HEADER` 간접 매크로)를 `project_code/firmware/core/_f122_poc.c`로 실제 배치 후 `python tools/core_purity_verify.py` 실행 — 6/6 통과·exit 0 재현. 원인: (a) 텍스트 스캔은 `#include SIAP_PLATFORM_HEADER`처럼 헤더명이 매크로면 매치하지 않고, `#if SIAP_BOARD`도 조건절 텍스트에 보드 매크로 원본 이름이 없어 놓침 (b) `gcc -E`가 보드 매크로를 아무것도 정의하지 않은 baseline 한 번만 돌아, `#if SIAP_BOARD`(=`#if ARDUINO`=undefined=0)가 거짓으로 접혀 `#include`가 전처리기에 도달하지 않음. PoC 제거 후 원상복구 확인 |
| 2026-08-08 | 수정완료 | 세 겹 방어로 확장: (a) `_check_includes_textual`이 `#define` 치환 목록 안의 헤더형 리터럴(`<x.h>`/`"x.h"`)도 함께 스캔 (a') `_check_board_macros`가 `#define` 치환 목록 안의 보드 매크로 이름도 함께 스캔 — 몇 겹을 감싸도 원본 이름은 어딘가의 치환 목록에 나타나야 한다는 점을 이용 (b') `_check_includes_compiler`가 `ARDUINO`·`__AVR__`·`ESP32`·`ESP8266`·`__XTENSA__`·`PLATFORMIO` 각각을 `-D이름=1`로 정의해 gcc -E 를 반복 — 실제 보드 빌드가 매크로를 켜고 시작하는 조건을 재현. 회귀 테스트 `tools/tests/test_core_purity_verify.py` 신설(2종): PoC가 텍스트 스캔·매크로 스캔 양쪽에서 잡히는지, 정상 코드가 여전히 오탐 없이 통과하는지 검증. 결함 주입: (b')만 되돌린 중간 버전과 완전 원본(사전수정본) 양쪽으로 확인 — 완전 원본에서는 회귀 테스트가 정확히 실패, 수정본 복원 후 재통과. 수정 후 실제 `project_code/firmware/core/` 6개 파일 대상 실행 결과 6/6 통과(오탐 없음) 유지 확인. `python fix_log/meta_verify.py`·`python tools/run_all.py` 재실행으로 전체 회귀 확인 |
