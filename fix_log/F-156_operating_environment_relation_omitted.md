# F-156 · operating_env 관계 저장 누락

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/ingest.py:158` · `project_code/backend/repository.py:156` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

1369-P1 7.2.3.4는 작동 환경을 장치상태와 환경상태의 관계 데이터로 규정한다. 7.1(10)은 장치상태 1건이 N개 환경상태로 구성된 작동 환경을 가진다고 한다.

## 현상

온도 센서와 냉난방기 상태를 한 정상 Frame에 넣자 `env_state_data=1`, `device_state_data=1`, `operating_env=0`이었다. 두 저장 함수의 반환 ID를 ingest가 버리고 관계 INSERT를 하지 않는다.

## 영향

동일 관측의 장치 동작과 환경 조건을 연결할 수 없다. 테이블 31개 존재 검사는 이 누락을 놓친다.

## 재현

위 복합 Frame 처리 뒤 세 테이블의 COUNT를 조회한다. backend 134/134, DB 98/98, live 11/11은 모두 통과한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 표준 원문(`TTAK.KO-10.1369-Part1.md` 7.1(10)·7.2.4.1)을 직접 대조 — "1개의 장치상태 데이터는 N개의 환경상태 데이터로 구성된 작동 환경을 가진다"를 확인. `backend/ingest.py::_handle_device_value()`가 `device_state_ids`/`env_state_ids`를 전혀 추적하지 않고 `operating_env` INSERT를 호출하는 지점이 없음을 코드로 확인 |
| 2026-08-10 | 수정완료 | `repository.py`에 `record_operating_env()` 신설. `ingest.py::_handle_device_value()`가 같은 프레임에서 만든 `env_state_id`·`device_state_id`를 모았다가, **장치상태가 정확히 1건**일 때만(모호하지 않은 경우) 각 환경상태를 그 장치상태에 묶는다 — `env_state_id`가 `UNIQUE`라 환경상태 1건은 장치상태 1건에만 귀속될 수 있어(7.1(10)), 장치상태가 2건 이상이면 프레임만으로 짝을 정할 수 없다(표준 미규정, 틀리게 짝짓느니 비움을 택함 — CLAUDE.md §3.5 갱신 대상) |
| 2026-08-10 | 회귀테스트 | `backend/tests/test_ingest.py`에 3건 신설 — 센서+액추에이터 1건씩이면 결속됨, 액추에이터 2건이면(모호) 결속하지 않음, 환경상태 없이 장치상태만 있으면 결속 없음. `backend/tests/test_repository.py`에 `record_operating_env` 단위 테스트 2건(정상 결속, `env_state_id` UNIQUE 위반) 추가 |
