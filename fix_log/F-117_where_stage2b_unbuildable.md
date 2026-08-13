# F-117 · where.py 단계 2b가 선행 정리 때문에 통과 불가능함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/where.py:194-223` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §0.1은 “출구 명령을 순서대로 돌려 처음 실패하는 단계가 현재 단계”라고 정한다. §1.2는 완료 판정을 복사해 실행 가능한 명령으로 정의한다. 따라서 각 단계 검사는 깨끗한 저장소에서 자기 출구를 재현할 수 있어야 한다.

## 현상

`check_stage_2a()`는 `finally`에서 `make clean`을 호출한다. 현재 Makefile의 clean 목록은 단계 2b의 `test_siap_frame`, `test_status_codes`, `test_golden`도 함께 삭제한다. 이어지는 `check_stage_2b()`는 make를 호출하지 않고 세 바이너리의 존재 여부만 검사한다.

## 영향

소스와 Makefile이 모두 올바르고 사용자가 직전에 2b 테스트를 빌드했어도, `where.py`가 자기 순서에서 그 산출물을 삭제한 뒤 “빌드 산출물 없음”으로 실패한다. 단계 2b는 구조적으로 통과 판정을 받을 수 없다.

## 재현

1. `project_code/firmware/tests`에서 `make`로 네 테스트를 모두 빌드한다.
2. 저장소 루트에서 `python tools/where.py`를 실행한다.
3. 단계 2a는 통과하고, 바로 다음 단계 2b의 세 실행파일은 전부 “빌드 산출물 없음”으로 실패한다.
4. 실제 판정: 현재 단계 2b, `where.py` 자체 exit 0.

## 제안

2b 검사도 소스에서 필요한 타깃을 빌드한 뒤 세 테스트와 `core_purity_verify.py`를 실행하고, 성공·실패 모두 `finally`에서 정리한다. 빌드 실패를 실행파일 누락과 구분해 보고하고, 2a→2b 순차 호출 회귀를 고정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | `project_code/firmware/tests`에서 `make`로 4종 전량 빌드 후 저장소 루트에서 `python tools/where.py` 실행 — 단계 2a 통과 직후 단계 2b 의 세 실행파일이 전부 "빌드 산출물 없음"으로 실패함을 재현. `check_stage_2a()`의 `finally: _run(["make","clean"])`가 Makefile 의 `CLEAN_FILES`(2b 타깃 포함)를 지우고, `check_stage_2b()`는 `make`를 부르지 않고 `Path.exists()`로만 확인하는 구조를 소스에서 확인 |
| 2026-08-08 | 수정완료 | `check_stage_2b()`를 `check_stage_2a()`와 동일한 패턴으로 재작성: `make test_siap_frame test_status_codes test_golden`을 직접 호출 → 실패 시 "make ... " 항목 자체를 FAIL(컴파일 로그 포함)로 보고하고 즉시 반환 → 성공 시 각 바이너리를 `_run([str(tests_dir/bin_name)], ...)`으로 직접 실행(`.exists()` 로 미리 걸러내지 않는다 — Windows 에서 확장자 없는 경로를 CreateProcess 에 넘기면 `.exe`를 자동으로 찾는 동작에 `check_stage_2a()`가 이미 기대고 있으므로 동일하게 맞춤) → 성공·실패 모두 `finally`에서 `make clean`. 결함 주입 재현: `siap_frame.c`에 구문 오류를 주입한 뒤 `where.py` 실행 → `[FAIL] make test_siap_frame test_status_codes test_golden`에 실제 gcc 오류 메시지가 담겨 보고되고(실행 파일 누락과 명확히 구분), 원상복구 후 재실행하면 즉시 통과·바이너리도 다시 정리됨을 확인. 회귀: `python tools/where.py` 연속 3회 실행 모두 단계 2b 통과·잔여 바이너리 0개 |
