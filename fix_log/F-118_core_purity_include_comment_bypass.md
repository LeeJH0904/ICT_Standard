# F-118 · core 순수성 검증기가 전처리 주석 include를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/core_purity_verify.py:42-77` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §1-5는 `project_code/firmware/core/`를 특정 보드용으로 수정하는 것을 금지한다. 개발 착수 지시서 §3.3은 신설 검증기가 `Arduino.h`, `avr/*`, `esp*` include와 보드 판별 매크로가 0개인지 기계 판정하도록 요구한다.

## 현상

검증기는 원문 한 줄에 정규식 `#\\s*include\\s*[<"]`가 직접 나타날 때만 include로 인식한다. C 전처리기는 주석을 공백으로 치환하므로 `#include/**/<Arduino.h>`는 유효한 플랫폼 include지만 정규식은 놓친다.

## 영향

보드 의존 헤더를 core에 넣어 동일 응용계층 주장을 깨뜨린 코드가 신설 검증기를 통과한다. 검증기의 핵심 금지 항목이 우회 가능하다.

## 재현

1. 임시 core에 실제 `bitpack.h`와 `bad.c`를 둔다.
2. `bad.c` 내용은 `#include/**/<Arduino.h>`와 평범한 선언 하나다.
3. `CORE_DIR`만 임시 경로로 바꿔 원본 `core_purity_verify.main()`을 실행한다.
4. 실제 결과: **4/4, exit 0**.
5. 같은 문자열을 `gcc -E -x c -`에 입력하면 `Arduino.h`를 찾으려다 실패한다. 즉 컴파일러는 실제 include로 인식한다.

## 제안

주석과 줄 이어쓰기를 전처리 규칙에 맞게 정규화한 뒤 지시문을 검사하거나, 컴파일러의 전처리/의존성 출력으로 실제 포함 헤더를 판정한다. 주석 삽입과 줄 연결 반례를 회귀로 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | 임시 `core/bad_temp.c`(`#include/**/<Arduino.h>`)를 두고 원본 `core_purity_verify.main()`을 실행 — 원문 한 줄 정규식(`^\s*#\s*include\s*[<"]`)이 주석으로 갈라진 지시문을 못 잡아 4/4 거짓 통과함을 재현. `gcc -E`로 같은 파일을 전처리하면 `Arduino.h`를 찾다 실패해 컴파일러는 실제 include로 인식함을 대조 확인 |
| 2026-08-08 | 수정완료 | `tools/core_purity_verify.py`를 두 겹으로 재작성: (a) `_strip_comments_and_joins()`로 블록/줄 주석과 줄 이어쓰기(`\`+개행)를 정규화한 텍스트에 대해 기존 regex 재스캔 (b) `gcc -E -x c`로 실제 전처리해 `# N "path"` 라인마커로 진짜 포함된 헤더 목록을 얻어 대조 — 전처리 자체가 실패하면 stderr 에서 금지 헤더 이름을 추출해 "전처리 실패 자체가 위반 증거"로 별도 분류(gcc 없음 등 무관한 실패와 구분). 보드 판별 매크로 검사(`#if defined(ARDUINO)` 등)도 같은 정규화 텍스트를 쓰도록 통일. 결함 주입 재현: `#include/**/<Arduino.h>` 파일 주입 → (a)(b) 두 검사 모두 FAIL 로 정확히 검출(4/6), 원상복구(파일 삭제) 후 6/6 재확인. 회귀: `python tools/core_purity_verify.py` 실제 저장소 대상 **6/6 통과**(includes 텍스트/컴파일러 이중 확인 + 보드 매크로 0 + bitpack.h 자기선언 대조) |
