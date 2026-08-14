# F-211 · core 금지 헤더가 순수성 검증을 통과

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/bitpack.c:L10` · `siap_frame.c:L17` · `siap_frame.h:L11` · `tools/core_purity_verify.py:L78-L121` · 펌웨어 설계서 §2.1 |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md` §0의 첫째 핵심 주장은 Uno·Pro Mini·ESP32가 `firmware/core/`를 수정하지 않고 같은 응용계층으로 동작하는 것이다. §1-5와 §4.2는 core의 보드·플랫폼 의존을 금지하고 AVR 타깃·의존성 최소화를 요구한다.

단계 2의 직접 판정 기준인 펌웨어 설계서 §2.1은 `string.h`를 금지 목록에 명시하고, core가 허용하는 헤더를 `stdint.h`·`stddef.h`·`stdbool.h` 셋으로 한정한다. 표준 원문은 C 헤더 선택을 규정하지 않으므로, 이 프로젝트 결정이 구현 기준이다.

## 현상

`bitpack.c:L10`, `siap_frame.c:L17`, `siap_frame.h:L11`은 현재 모두 `#include <string.h>`를 사용한다. 설계서가 명시적으로 금지한 헤더인데도 공식 `core_purity_verify.py`는 7/7, `firmware_verify.py`는 51/51을 통과한다. 전자는 `stdio.h`, 이름이 `arduino`·`esp`로 시작하는 헤더, `avr/` 경로만 금지하고, 후자는 설계 문서에 허용 목록 문구가 있는지만 검사하기 때문이다.

더 넓은 반례로, 임시 core 복제본에 include guard와 `#include <windows.h>`만 든 `platform_probe.h`를 추가해도 텍스트 검사, GCC 전처리, 조건부 컴파일 화이트리스트가 모두 PASS하여 7/7로 종료했다. 실제 GCC가 `windows.h`를 성공적으로 전처리했으므로 판정 불가도 아니었다.

## 영향

현재 구현부터 단계 2 설계의 core 의존성 경계를 위반한다. 또한 검증기 초록 결과만으로는 하드웨어·플랫폼 의존성 0이나 세 MCU 동일 응용계층 주장을 보증할 수 없고, 알려진 이름 밖의 플랫폼 SDK도 그대로 통과한다. `memcpy`가 실제 AVR 빌드에서 인라인되는지 libc 링크·flash 비용을 만드는지는 단계 8 실측 전에는 확인되지 않는다.

## 재현

```text
1. 현재 저장소에서 python tools/core_purity_verify.py를 실행한다.
   core 3파일의 #include <string.h>가 존재해도 7/7 통과한다.
2. project_code/firmware/core/를 임시 디렉터리에 복제하고 다음 파일을 추가한다.

   #ifndef SIAP_PLATFORM_PROBE_H
   #define SIAP_PLATFORM_PROBE_H
   #include <windows.h>
   #endif

3. tools.core_purity_verify.CORE_DIR을 그 임시 디렉터리로 지정하고 main()을 실행한다.

결과:
  PASS  core/ 스캔 대상 9개 .c/.h 파일 발견
  PASS  (a) 정규화된 텍스트 스캔
  PASS  (b) gcc -E 실제 전처리
  PASS  (c) 조건부 컴파일 화이트리스트
  7/7 통과
```

## 제안

현재 `string.h` 사용을 설계 결정과 일치시키고, 플랫폼 헤더 블랙리스트를 늘리는 대신 core 파일이 include할 수 있는 프로젝트 내부 헤더와 세 허용 헤더를 명시적 허용 목록으로 판정한다. GCC include trace도 같은 허용 목록과 대조하고, `windows.h`처럼 설치 환경에서 실제로 열리는 비허용 헤더를 결함 주입 회귀로 고정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-13 | 확인 | 현재 `core/`의 `string.h` 3건이 존재해도 공식 검증기가 7/7·종료코드 0인 것을 재현했다. 별도 임시 core 복제본에 `#include <windows.h>`를 추가한 반례도 GCC 전처리 성공 상태에서 7/7·종료코드 0으로 통과함을 독립 재현했다. 설계서 §2.1의 명시적 허용 목록과 구현·검증기가 불일치하므로 오류를 수용한다. |
| 2026-08-13 | 수정완료 | `bitpack.h/.c`에 겹치지 않는 객체 표현용 `bp_memcpy`를 추가해 FLOAT·INT 타입 펀닝의 `memcpy`를 대체하고, `siap_frame.c`의 1바이트 재동기 슬라이드는 좌측 복사 루프로 바꿔 core의 `string.h` 3건을 제거했다. `core_purity_verify.py`는 소스 지시문과 GCC `-H` 직접 include(depth 1)를 각각 `stdint.h`·`stddef.h`·`stdbool.h` 또는 실제 core 내부 헤더 허용 목록과 대조한다. 회귀 테스트에 `string.h`, `windows.h`, core 밖 경로, 미존재 내부 헤더 반례와 정상 세 헤더를 고정했다. 결함 재주입 시 `windows.h`가 소스/GCC 양쪽에서 FAIL하여 5/7·종료코드 1, 정상 core는 7/7이었다. C 빌드·실행은 bitpack 41/41, siap_frame 148/148, status_codes 53/53, golden 253/253(53벡터), 도구 테스트 32/32, firmware_verify 51/51, golden_verify 31/31, `tools/run_all.py` 20/20을 통과했다. |
