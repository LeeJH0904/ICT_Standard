# F-113 · SIAP_WUR 제거가 bitpack 빌드와 테스트를 그대로 통과함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/tests/test_bitpack.c:1-8` · `project_code/firmware/tests/Makefile:18-29` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md:257-263`은 `bp_write`와 `bp_write_f32` 반환값을 버리면 `-Werror=unused-result`로 빌드가 실패해야 한다고 규정한다. 펌웨어 설계서 §4.1(`:313-314`)도 `SIAP_WUR`와 Makefile 옵션이 함께 검사 누락을 빌드 실패로 만든다고 명시한다. 개발 착수 지시서 §3.2는 `SIAP_WUR` 부착 여부를 GPT 검증 항목으로 지정한다.

## 현상

현재 실제 헤더에는 두 함수 모두 `SIAP_WUR`가 있고, 반환값을 버리는 별도 스니펫을 실제 옵션으로 컴파일하면 `-Werror=unused-result` 때문에 exit 1이 된다. 현재 구현은 맞다.

그러나 원본 `test_bitpack.c`의 모든 쓰기 호출은 반환값을 사용한다. 호출자가 보는 헤더에서 두 선언의 `SIAP_WUR`를 제거한 변형을 메모리 주입해 원본 테스트를 컴파일·실행하자 경고 없이 34/34, exit 0이었다. Makefile에 `-Werror=unused-result`가 있어도 폐기 호출이 한 번도 없으므로 속성 제거 회귀를 검출하지 못한다. 테스트 머리말도 이 검사를 커밋되지 않는 임시 스니펫으로만 확인했다고 명시한다.

## 영향

향후 헤더에서 속성이 빠져도 자동 출구는 녹색이다. 그 뒤 인코더가 쓰기 결과를 실수로 버리더라도 빌드가 막히지 않아 F-078에서 구조로 강제한 범위 오류 전파 계약이 다시 규약 의존으로 돌아간다.

## 재현

1. 테스트 번역 단위가 보는 `bp_write`·`bp_write_f32` 선언에서 `SIAP_WUR`를 제거한다.
2. 원본 Makefile과 같은 경고 옵션으로 원본 `test_bitpack.c`와 실제 `bitpack.c`를 컴파일·실행한다.
3. 실제 결과: 컴파일 exit 0, 테스트 34/34, exit 0.
4. 대조군으로 현재 실제 헤더를 include하고 `bp_write(...)` 반환값을 버리는 스니펫을 컴파일한다.
5. 실제 결과: `ignoring return value ... [-Werror=unused-result]`, exit 1.

## 제안

반환값을 의도적으로 버리는 별도 컴파일 실패 스니펫을 두고, “컴파일 실패가 성공”인 회귀 타깃을 `make test_bitpack` 출구에 포함한다. `bp_write`와 `bp_write_f32` 각각을 검사하며, `SIAP_WUR` 또는 `-Werror=unused-result` 어느 한쪽을 제거해도 출구가 실패해야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 2a 검증에서 `SIAP_WUR` 제거가 원본 테스트·빌드를 그대로 통과하는 것을 재현 |
| 2026-08-08 | 확인 | 헤더에서 `bp_write`·`bp_write_f32`의 `SIAP_WUR`를 제거한 뒤 원본 `test_bitpack.c`를 같은 옵션으로 컴파일·실행 — 경고 없이 34/34·exit 0으로 통과함을 확인 |
| 2026-08-08 | 수정완료 | "컴파일 실패가 성공"인 전용 스니펫 두 개(`test_bitpack_wur_bp_write.c`·`test_bitpack_wur_bp_write_f32.c`, 각 함수 반환값을 일부러 버림)를 신설하고, `Makefile`에 `check_wur` 타깃을 두어 `test_bitpack`의 선행조건으로 걸었다(각 스니펫이 "컴파일 성공"하면 회귀로 판정해 `exit 1`). **처리 도중 셸 문법(`if/then/fi`, 리다이렉션)으로 짠 최초 버전이 `tools/where.py`가 PowerShell에서 `make`를 부를 때(POSIX sh를 못 찾아 `mingw32-make`가 cmd.exe로 떨어지는 경로)만 깨지는 것을 추가로 발견** — `check_wur.py`·`clean.py`(Python)로 재작성해 Make 레시피를 "python 스크립트 인자..." 한 줄로 통일했다(F-111의 `clean` 타깃도 이 김에 같은 방식으로 통합). 이 과정에서 `subprocess.run(text=True)`가 gcc 진단 속 UTF-8 문자(소스 주석의 em dash)를 로케일 기본(cp949)으로 디코딩하려다 `UnicodeDecodeError`로 죽는 것도 함께 발견해 `encoding="utf-8", errors="replace"`로 명시했다(F-045·F-096·F-102와 같은 부류). 결함 주입 재현: `bp_write`의 `SIAP_WUR` 제거 시 `make test_bitpack`이 정확히 `check_wur` 단계에서 실패(exit 2) · `bp_write_f32` 제거 시도 동일 — Git Bash(`mingw32-make`, sh)와 PowerShell(`make.exe`, cmd.exe 폴백) 양쪽에서 확인 후 원상복구. 회귀: `make test_bitpack && ./test_bitpack` **39/39**, 두 환경 모두 exit 0 |
