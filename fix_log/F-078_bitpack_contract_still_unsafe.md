# F-078 · F-075의 비트폭 거부 계약이 아직 강제되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `CLAUDE.md:218-222` · `project_docs/firmware/펌웨어_설계서.md:255-281,328-331,343-351` |
| 발견일 | 2026-08-05 |
| 상태 | 수정완료 |

## 근거

0943 표 7-6은 `Message Identifier`를 16bit, 표 7-8은 `GCG ID`와 `Node ID`를 각각 20bit로 정의한다. 표 7-14의 `Value`는 32bit다. 비트 패커는 최소 16·20·32bit 경계를 정확히 처리해야 한다.

## 현상

F-075 보완에는 서로 독립적인 세 문제가 남았다.

1. 개발 정본 `CLAUDE.md`의 4함수 원형은 여전히 `void bp_write(...)`와 `void bp_write_f32(...)`다. 펌웨어 §4.1의 `bool` 계약과 정면으로 충돌한다.
2. 펌웨어 §4.1은 반환형을 `bool`로 바꾸면 검사 누락이 `-Wunused-result` 경고로 드러난다고 단정한다. 일반 C 함수는 반환형만으로 미사용 경고 대상이 되지 않는다. GCC 15.2에서 `-Wall -Wextra -Wunused-result`로 평범한 `bool bp_write()`의 반환값을 버려도 경고가 0건이었다.
3. 범위식 `val >= (1u << nbits)`는 20·32bit 계약에 쓸 수 없다. AVR에서 `unsigned int`는 16bit이므로 `1u << 20`부터 시프트 폭을 넘고, 32bit 호스트에서도 `1u << 32`는 정의되지 않는다. 실제 GCC는 상수 32 반례에 `left shift count >= width of type`을 경고한다. 이는 §4.3의 "32bit는 폭 검사가 항상 성공" 및 테스트 #4·#8과 모순이다.

## 영향

Claude가 개발 규약을 따르면 반환 계약 자체가 `void`로 되돌아간다. 펌웨어 문서만 따라도 호출자가 `false`를 버릴 때 컴파일러가 막지 않으며, 20·32bit 필드의 범위 검사 결과는 타깃별로 잘못되거나 정의되지 않을 수 있다. F-075의 목적인 조용한 절단 방지가 아직 구조적으로 보장되지 않는다.

## 재현

```text
1) bool bp_write(void) { return false; }
   int main(void) { bp_write(); }
   gcc -O2 -Wall -Wextra -Wunused-result ...
   → 경고 없음

2) uint32_t bad32(uint32_t v) { return v >= (1u << 32); }
   gcc -O2 -Wall -Wextra -Wshift-count-overflow ...
   → warning: left shift count >= width of type
```

## 제안

개발 규약과 설계서의 원형을 하나로 맞추고, 반환값 미사용을 실제로 진단하는 함수 계약을 명시한다. 범위 검사는 `nbits == 32`를 별도로 처리하고 20bit 시프트도 32bit 상수형에서 수행하도록 계약을 고친 뒤, AVR 타깃 컴파일과 호스트 경고-실패 테스트를 회귀에 포함한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-05 | 확인 | 세 지적 모두 **실제로 컴파일해 확인했다**(gcc 13.3.0). ① `CLAUDE.md` §4.2 의 원형이 `void bp_write(...)` 그대로였다 — 9차에서 설계서만 고쳤다. ② `bool` 반환형만으로는 경고가 나지 않는다: `plain()` 의 반환값을 버려도 `-Wall -Wextra -Wunused-result` 에서 경고 0건, `warn_unused_result` 속성을 붙인 `tagged()` 만 경고했다. ③ `1u << 32` 는 `warning: left shift count >= width of type` + `comparison of unsigned expression in '>= 0' is always true` 로 **검사 자체가 무력화**된다. AVR 의 `unsigned int` 가 16bit 라 `1u << 20` 도 UB 라는 지적도 맞다 |
| 2026-08-05 | 수정완료 | **① 두 문서의 원형을 하나로 맞췄다.** `CLAUDE.md` §4.2 를 `SIAP_WUR bool bp_write(...)` / `SIAP_WUR bool bp_write_f32(...)` 로 바꾸고, '쓰기 2종은 범위 초과 시 `false` 를 반환하고 아무것도 기록하지 않는다 — 마스킹 래핑 금지(F-044)를 규약이 아니라 구조로 강제한다' 를 §4.2 본문에 넣었다 |
| 2026-08-05 | 수정완료 | **② `SIAP_WUR` 매크로를 명시했다.** `__GNUC__` 가드 안에서 `__attribute__((warn_unused_result))` 로 정의하고, `firmware/tests/Makefile` 에 `-Werror=unused-result` 를 추가해 **검사 누락을 빌드 실패로** 만들었다. 실측한 gcc 출력을 설계서 §4.1 에 그대로 인용했다 — '속성과 플래그 둘 중 하나만 있으면 무효' 임을 Makefile 주석에도 남겼다 |
| 2026-08-05 | 수정완료 | **③ 범위식을 마스크 기반으로 바꿨다.** `if (nbits == 0 \|\| nbits > 32) return false; if (nbits < 32 && val > ((uint32_t)0xFFFFFFFFul >> (32 - nbits))) return false;` — 시프트를 아예 쓰지 않으므로 AVR 16bit `int` 와 `1u << 32` UB 를 동시에 피한다. `nbits == 32` 는 `uint32_t` 전 범위라 검사가 필요 없고, 이것이 §4.3 의 '32bit 는 검사 생략' 과 일관된다. 14/16/20bit 상한표(`0x00003FFF` / `0x0000FFFF` / `0x000FFFFF`)를 함께 실었다 |
| 2026-08-05 | 수정완료 | **설계 단계에서 실제로 컴파일해 검증했다.** `gcc -std=c99 -O2 -Wall -Wextra -Wconversion -Wshift-count-overflow -Werror` 로 ① `nbits`=1~32 **전 폭 스윕**(각 폭 최대값 기록·왕복, 최대값+1 거부, `bitpos`·`buf` 불변), ② 헤더 96bit 연속 기록이 골든 `N01`(`12 00 00 00 01 00 00 00 00 10 00 03`)과 바이트 일치 — 전량 통과. 호스트 테스트 케이스를 6 → **11종**으로 늘렸다(전 폭 스윕, 반환값 버림 빌드 실패 포함) |
| 2026-08-05 | 수정완료 | **회귀 검사 5종**: 설계서 원형이 `SIAP_WUR bool`, `CLAUDE.md` 원형이 동일, `warn_unused_result` + `-Werror=unused-result` 둘 다 명시, 마스크 상한표가 14·16·20bit 를 덮고 `nbits == 32` 분기 존재, Makefile 이 `-Wshift-count-overflow` 를 켬. 결함 주입 5종 전량 exit 1 |
