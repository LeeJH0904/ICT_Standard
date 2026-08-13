# F-111 · 단계 2a Windows 빌드가 금지 실행파일을 남겨 전체 회귀를 깨뜨림

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/tests/Makefile:22-32` |
| 발견일 | 2026-08-08 |
| 상태 | 수정완료 |

## 근거

`CLAUDE.md:38`은 `.exe`를 저장소에 두는 것을 금지한다. 개발 착수 지시서 §4·§5.2는 단계 종료 때 이전 검증기를 포함한 `python tools/run_all.py` 전량 통과를 요구하고, 단계 0의 `offline_verify.py`는 제출 대상에 실행파일이 0개인지 검사한다.

## 현상

Windows의 MinGW GCC 15.2.0에서 단계 2a 출구의 `make test_bitpack`을 그대로 실행했다. Makefile의 `-o test_bitpack`은 실제로 `project_code/firmware/tests/test_bitpack.exe`(99,734 byte)를 만들었다. 테스트 자체는 34/34로 통과했지만 그 직후 전체 회귀는 다음처럼 실패했다.

- `python tools/run_all.py`: `offline_verify.py`만 실패하여 10/11, exit 1
- `python tools/offline_verify.py`: 실행파일 1개 발견, 4/5
- `python fix_log/meta_verify.py`: 같은 실행파일 때문에 84/86, exit 1
- `python tools/where.py`: 단계 0의 오프라인 출구가 실패하여 현재 단계를 다시 `단계 0`으로 판정

`make -n clean`도 `rm -f test_bitpack`만 출력한다. Windows가 실제 생성한 `test_bitpack.exe`를 제거하지 않으므로 clean 경로로도 해소되지 않는다. `.gitignore`에 `*.exe`는 있지만 `offline_verify.py:227-238`의 제출 스캔은 `CLAUDE.md` §2.1 디렉터리 제외만 적용하고 이 파일을 제출 대상에서 제외하지 않는다.

## 영향

단계 2a의 지정 출구를 정상 수행하는 행위 자체가 이전 단계의 오프라인 제출 출구를 깨뜨린다. 따라서 현 상태에서는 단계 2a의 누적 출구 조건을 Windows에서 동시에 만족할 수 없고, 제출 후보에도 금지 실행파일 1개가 남는다.

## 재현

1. `cd project_code/firmware/tests`
2. `make test_bitpack` 실행 — exit 0, `test_bitpack.exe` 생성.
3. `.\test_bitpack` 실행 — 34/34, exit 0.
4. 저장소 루트에서 `python tools/run_all.py` 실행.
5. 실제 결과: `offline_verify.py`가 `project_code\\firmware\\tests\\test_bitpack.exe`를 검출해 10/11, exit 1.
6. `python tools/where.py` 실행 — 현재 단계가 0으로 회귀.

## 제안

Windows의 실제 출력명까지 포함하는 플랫폼 독립 빌드·정리 규칙을 둔다. 단계 2a 실행 후에도 제출 스캔에 바이너리가 남지 않게 하고, `make clean`이 실제 산출물(`test_bitpack` 또는 `test_bitpack.exe`)을 모두 제거하는 회귀를 Windows에서 고정한다. 수정 뒤에는 단계 2a 출구 직후 `offline_verify.py`·`run_all.py`·`meta_verify.py`·`where.py`를 순서대로 재실행한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-08 | 신규 | GPT 단계 2a 검증에서 Windows MinGW GCC가 `test_bitpack.exe`를 남겨 하위 검증 체인 전체가 무너지는 것을 재현 |
| 2026-08-08 | 확인 | `make test_bitpack` 실행 후 `test_bitpack.exe`(99,734byte)가 실제로 남고, `python tools/offline_verify.py`가 이를 검출해 실패하는 것을 재현 |
| 2026-08-08 | 수정완료 | `Makefile`의 `clean` 타깃이 `test_bitpack`과 `test_bitpack.exe` 두 이름을 모두 명시적으로 지우도록 수정(추후 F-113 처리 중 셸 의존성 자체를 없애기 위해 `clean.py`(Python)로 재작성 — 처리 기록은 F-113 항목 참조). 제안된 재검증 순서(단계 2a 출구 → `offline_verify.py` → `run_all.py` → `meta_verify.py` → `where.py`)를 그대로 실행해 전부 통과 확인. 회귀: `python tools/offline_verify.py` 전체 통과(실행파일 0개) · `python tools/run_all.py` **11/11** · `python fix_log/meta_verify.py` **86/86** · `python tools/where.py` 단계 2a 통과·현재 단계 2b 판정 |
| 2026-08-08 | 확인 (재현, GPT 2차 검증) | **위 "수정완료" 처리가 불완전했다.** 재검증 시 재현 절차 사이에 `make clean`을 수동으로 끼워 넣어 통과를 확인했는데, 실제 출구 명령(`make test_bitpack && ./test_bitpack`)과 `where.py`는 그 clean 호출을 하지 않는다 — clean 없이 그대로 실행하면 `test_bitpack.exe`가 여전히 남고 `offline_verify.py`(10/11)·`run_all.py`(10/11)·`meta_verify.py`(84/86)가 깨지며, `where.py`는 자신이 만든 잔여물 때문에 두 번째 실행에서 단계 0으로 후퇴함을 GPT가 재현. 근본 원인은 "clean 자체가 되는가"가 아니라 "누가 언제 clean을 부르는가"였다 |
| 2026-08-08 | 수정완료 (재수정) | 검증기 스스로 정리하도록 근본 수정 — `tools/offline_verify.py`의 `check_no_binaries()`가 실행파일 스캔 직전 `project_code/firmware/` 아래 모든 `Makefile`에 대해 `make clean`을 먼저 시도(`_clean_known_build_dirs()`). "알려진 빌드 산출물은 검증기가 알아서 치우고, 그래도 남는 낯선 실행파일만 위반으로 본다" — 판정 기준을 낮추는 게 아니라 정상 개발 잔여물과 진짜 위반을 가른다. `tools/where.py`의 `check_stage_2a`·`_rebuild_and_run_all_tests`(2c용)에도 각각 `try/finally`로 자기 정리를 추가해 이중 방어. 검증: **clean을 한 번도 수동으로 부르지 않고** "빌드→실행→`offline_verify.py`→`run_all.py`→`meta_verify.py`→`where.py`(3연속)"를 그대로 실행 — 전부 통과, `where.py` 3연속 실행 모두 단계 2b로 일관(자기 오염 재발 없음) |
