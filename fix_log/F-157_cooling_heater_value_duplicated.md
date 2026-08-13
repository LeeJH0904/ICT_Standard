# F-157 · 냉난방기 Value 중복 저장

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/repository.py:222` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §3.5는 0943의 단일 Value를 장치상태의 첫 물리량에만 저장하고 나머지는 NULL로 두며, 전원은 `Value != 0`으로 해석한다고 결정했다.

## 현상

`COOLING_HEATER`는 같은 값을 전원과 온도에 모두 쓴다. value 18.5의 실제 행은 `(power=1, temperature=18.5, wind_level=NULL)`이었다.

## 영향

관측 근거가 하나인데 두 물리량을 관측한 것처럼 저장하여 §3.5 결정과 데이터 진위를 깨뜨린다.

## 재현

냉난방기 등록 뒤 value 18.5인 `NOTI_DEVICE_VALUE`를 처리하고 `dsd_cooling_heater`를 조회한다. backend 134/134는 통과한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | `repository.py::record_device_state()`의 `COOLING_HEATER` 분기를 직접 읽어 확인 — `1 if value else 0`(power)과 `value`(temperature)를 같은 인자로 동시에 채우고 있었다. `FAN` 분기(같은 표에서 power만 채우고 wind_level은 NULL)와 대조해 비일관성 확인 — CLAUDE.md §3.5가 이미 "주 필드에만 값을 싣고 나머지는 NULL"이라고 결정해 뒀는데 냉난방기만 그 결정을 어기고 있었다 |
| 2026-08-10 | 수정완료 | `dsd_cooling_heater` INSERT를 `power`만 채우고 `temperature`·`wind_level`은 `NULL`로 고정 — `FAN`과 동일한 패턴으로 맞췄다 |
| 2026-08-10 | 회귀테스트 | `backend/tests/test_repository.py::test_record_device_state_cooling_heater_only_fills_power` 신설(power=1/0 두 값 모두 temperature·wind_level이 NULL임을 확인). `backend/tests/test_ingest.py::test_handle_device_value_cooling_heater_does_not_duplicate_value` 로 ingest 경로도 별도 확인 |
