# F-177 · 편측 유효범위 밖 측정값이 정상 저장됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/ingest.py:253` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.1369-Part1 6.3.2 — “데이터의 유효범위를 벗어난 측정값은 측정오류로 무시”해야 하며, “측정형 데이터는 유효범위가 관리되어야 한다.”

## 현상

F-171 수정은 `lower_limit`과 `upper_limit`이 둘 다 `NULL`이 아닐 때만 범위를 검사한다. 스키마는 각 경계를 독립적으로 nullable로 허용하므로 하한만 0인 장치에 -10이 들어오거나 상한만 100인 장치에 101이 들어오면 정상 `env_measurement`로 저장된다.

## 영향

F-171이 수정완료 상태지만 같은 표준 요구가 편측 범위에서 그대로 우회된다. 센서가 제공하는 한쪽 경계가 무시되어 분석용 정상 데이터에 측정 오류가 섞인다.

## 재현

```text
lower_limit=0.0, upper_limit=NULL로 센서 등록
value=-10.0 NOTI_DEVICE_VALUE 처리
ONE_SIDED_RANGE_STORED={'value': -10.0, 'lower_limit': 0.0, 'upper_limit': None}
```

기존 `backend/tests` 159/159, DB 제약 103/103, `db_live_verify` 15/15가 모두 통과한 상태에서 재현됐다.

## 제안

각 경계가 존재할 때 독립적으로 하한·상한을 검사하는 반례를 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — F-171 최초 구현이 `lo is not None and hi is not None and not (lo <= value <= hi)`로 **두 경계 모두 있을 때만** 검사해, `schema.sql`이 각 경계를 독립적으로 nullable로 허용한다는 사실과 어긋남을 확인 |
| 2026-08-11 | 수정완료 | `ingest.py::_handle_device_value`의 범위 검사를 `(lo is not None and value < lo) or (hi is not None and value > hi)`로 바꿔 있는 경계만 독립적으로 검사하도록 고쳤다 — 편측 등록에서도 그 경계는 그대로 강제되고, 두 경계 다 없으면 이전처럼 아무 것도 거르지 않는다(원래 의미 보존) |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_ingest.py::test_handle_device_value_one_sided_lower_limit_rejects_below`·`test_handle_device_value_one_sided_upper_limit_rejects_above` 신설 — 하한만/상한만 등록된 센서 각각 그 경계 밖 값이 저장되지 않음을 확인. `cd project_code && python -m pytest backend/tests/` **168/168** 재확인 |
