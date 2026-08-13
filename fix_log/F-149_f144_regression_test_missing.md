# F-149 · F-144 수정완료에 회귀 테스트가 없어 메타 검증 실패

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `fix_log/F-144_where_stage0_stage4_assertion_conflict.md` · `fix_log/meta_verify.py:225-273` · `tools/tests/test_where.py` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

fix_log/README.md §7 — 코드버그는 재현 절차가 필수다. CLAUDE.md §11.3 — 코드버그는 재현·수정 뒤 회귀 테스트를 추가한다. `meta_verify.py` §5는 상태가 `수정완료`인 코드버그 ID가 검증 코드에 실제로 존재하는지 강제한다.

## 현상

F-144의 본체 수정은 실제로 적용돼 `python tools/where.py`가 단계 0~4를 통과하고 현재 단계 5를 정확히 출력한다. 그러나 F-144 상세 처리 기록에는 직접 실행 확인만 있고 회귀 테스트가 추가되지 않았다. `tools/tests/test_where.py`와 다른 검증 소스 어디에도 F-144가 없어 필수 메타 검증이 실패한다.

## 영향

상태는 `수정완료`지만 제출 전 필수 명령 `python fix_log/meta_verify.py`가 `수정완료 코드버그에 대응 회귀 테스트 존재 ['F-144']`로 실패하며 결과는 94/95, 종료 코드 1이다. 수정 상태만 바뀌고 완료 조건은 닫히지 않았다.

## 재현

```text
> python tools/where.py
단계 0~4 통과, 현재 단계: 5, exit 0

> python fix_log/meta_verify.py
FAIL 수정완료 코드버그에 대응 회귀 테스트 존재 ['F-144']
94/95 통과, exit 1
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `grep -rn "F-144" tools/ project_code/` 결과 0건 — F-144 본체 수정은 적용돼 있으나 어떤 소스에도 ID 가 언급되지 않아 `meta_verify.py` §5 스캔이 "회귀 테스트 없음"으로 판정하는 것을 확인. 지적대로 `python fix_log/meta_verify.py` 실행 시 94/95 |
| 2026-08-09 | 수정완료 | (1) `tools/where.py::check_stage_0()` 의 F-144 관련 주석에 ID 를 명시하고 회귀 테스트 경로를 주석으로 남김. (2) `tools/tests/test_where.py` 에 `test_stage_0_does_not_require_no_구현_output_f144` 추가 — `_run`을 몽키패치해 "exit 0 이지만 '미구현' 문구가 없는" (단계 4 완료 후의 실제 상태를 흉내낸) 출력을 주고 `check_stage_0()` 의 판정이 여전히 통과인지 확인. `__main__` 폴백 실행 목록에도 등록. **결함 주입 검증**: `check_stage_0()` 을 F-144 수정 이전(= "미구현" 문구 요구)으로 일시 되돌리자 새 테스트가 정확히 실패(`assert False is True`)하는 것을 확인한 뒤 복원, `tools/tests/test_where.py` 4/4 재통과. **검증**: `python fix_log/meta_verify.py` 재실행 → "수정완료 코드버그에 대응 회귀 테스트 존재" 행이 빈 목록으로 통과, 95/95 |
