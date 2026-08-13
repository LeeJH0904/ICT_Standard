# F-121 · where.py가 test_node_state 부재를 놓치고 단계 2c를 통과

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/where.py:134-168,250-257` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

개발 착수 지시서 §3.4 — 단계 2c 출구는 “① `./test_node_state` ② `project_code/firmware/tests` 4종 전량 (`make && ./test_*`) ③ `python project_docs/firmware/firmware_verify.py`”다. 같은 문서 §0.1은 “출구 명령을 순서대로 돌려 처음 실패하는 단계가 현재 단계”라고 정한다.

## 현상

현재 `project_code/firmware/core/node_state.c/.h`와 `firmware/tests/test_node_state.c`가 모두 없고 Makefile의 `TARGETS`에도 `test_node_state`가 없다. 그런데 `_rebuild_and_run_all_tests()`는 Makefile이 우연히 만든 `test_*` 실행파일만 전수 탐색하고 필수 집합에 `test_node_state`가 포함됐는지는 검사하지 않는다.

직접 실행한 `python tools/where.py`는 단계 2c에서 `test_bitpack`, `test_golden`, `test_siap_frame`, `test_status_codes` 네 개만 실행한 뒤 “단계 2c - 통과”, “현재 단계: 3”을 출력했다. F-098 처리 기록의 “결과 목록 자체로 드러난다”는 관찰 가능성은 필수 타깃 존재를 강제하지 않는다.

## 영향

상태 머신 구현과 전용 테스트가 전혀 없어도 다음 단계로 진행할 수 있다. 현재 단계 도출이라는 `where.py`의 핵심 계약이 다시 거짓 양성을 낸다.

## 재현

```text
> python tools/where.py
[단계 2c] firmware/core/node_state - 통과
    [OK] ./test_bitpack.exe
    [OK] ./test_golden.exe
    [OK] ./test_siap_frame.exe
    [OK] ./test_status_codes.exe
    [OK] python project_docs/firmware/firmware_verify.py
>>> 현재 단계: 3 (siap/ 게이트웨이)

실제 파일: node_state.c 없음, node_state.h 없음, test_node_state.c 없음
```

## 제안

단계별 필수 타깃 집합을 출구 명령에서 도출해 `test_node_state`의 소스·Makefile 타깃·실행 결과를 모두 요구해야 한다. 디렉터리 전수 탐색은 추가 테스트를 놓치지 않는 용도로만 쓰고 필수 집합 검사를 대체하면 안 된다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 확인 | 저장소 루트에서 `python tools/where.py` 실행해 재현: `project_code/firmware/core/node_state.c/.h`, `project_code/firmware/tests/test_node_state.c` 모두 부재, `firmware/tests/Makefile` 36번째 줄 `TARGETS`에도 `test_node_state` 없음(5번째 줄 주석은 "추가한다"고만 적혀 있어 실제 미반영). 이 상태에서 `check_stage_2c()`가 [단계 2c] 통과 · 현재 단계 3 을 출력함을 확인 — 보고된 현상과 일치 |
| 2026-08-08 | 수정완료 | `check_stage_2c()`를 재작성: ① `node_state.c`·`node_state.h`·`test_node_state.c` 3개 소스 파일 존재를 먼저 명시적으로 검사(없으면 즉시 실패, 무엇이 없는지 상세에 나열) ② `firmware/tests/Makefile` 본문에 `test_node_state` 문자열이 있는지 검사(TARGETS 미등록이면 즉시 실패) ③ `_rebuild_and_run_all_tests()` 실행 후, 반환된 `./test_*` 항목 이름을 직접 훑어 `test_node_state`가 실제로 실행됐는지 재확인(이름 불일치·빌드는 됐지만 목록에서 빠지는 경우까지 대비). 회귀 테스트 `tools/tests/test_where.py` 신설(3종): 소스 부재·Makefile 미등록·재빌드 결과에서 이름이 빠지는 경우 각각 실패를 검증. 결함 주입: 수정 전 `check_stage_2c()`(재빌드 후 무조건 통과로 간주하는 버전)로 일시 되돌려 3개 테스트 전부 실패함을 확인한 뒤 수정본으로 복원 — 3개 테스트 재통과. 수정 후 `python tools/where.py` 재실행 결과 `[단계 2c] 실패`·`현재 단계: 2c`로 정정됨을 확인. `python tools/run_all.py` 12/12 통과(회귀 없음) |
