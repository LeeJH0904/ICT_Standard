# F-173 · 등록 정체성과 다른 장치 값 알림을 그대로 저장

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/ingest.py:215` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.1369-Part1 §7.1(6)은 하나의 장치 설치 정보가 하나의 장치 기본정보를 가져야 한다고 규정하고, §7.2.2.5는 설치 장치의 기본정보를 `device_info_id`로 참조하도록 한다. 값 저장 시에도 알림의 장치 종류가 그 등록 정체성과 일치해야 이 관계가 유지된다.

## 현상

F-169 수정은 재연결 UPDATE에 `device_info_id`를 추가했지만, `_handle_device_value()`는 여전히 node/device 번호로만 설치 행을 찾는다. 알림의 `dmi.dev_type`·subtype을 설치 행의 `device_info.device_kind`·`siap_subtype`과 대조하지 않고 알림이 주장한 종류에 따라 센서/액추에이터 저장 경로를 선택한다.

## 영향

등록상 SENSOR인 장치가 ACTUATOR 알림을 보내도 같은 설치 식별자 아래 액추에이터 상태가 저장된다. F-169에서 지적한 “등록 정체성과 이후 값 subtype 불일치”의 두 번째 경로가 남아 있으며, 신설 회귀 테스트는 등록과 알림이 모두 HUMIDITY인 정상 일치 사례만 검사해 이를 놓친다.

## 재현

임시 DB에서 node 3/device 1을 HUMIDITY SENSOR로 등록한 뒤 같은 주소로 ACTUATOR/IRRIGATION_VALVE 값 100을 알렸다.

```text
REGISTERED_IDENTITY={'device_kind': 'SENSOR', 'model_name': 'SIAP-0x02', 'siap_subtype': 2}
MISMATCH_STATE_ROWS=[{'subtype': 'IRRIGATION_VALVE', 'open_level': 100.0}]
VIOLATIONS=0
```

제출된 backend 테스트 157/157와 SIAP+backend 테스트 259/259가 통과하는 상태에서 재현된다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — F-169는 `upsert_device_install_info()`의 UPDATE 절에 `device_info_id`를 추가해 "재연결로 종류가 바뀌는" 경로는 막았지만, `_handle_device_value()`는 여전히 `(node_id, dmi.device_id)`로 설치 행만 찾고 `dmi.subtype`/`dev_type`을 등록값과 대조하지 않아 재연결 없이도(같은 등록 상태에서) 다른 종류의 값 알림이 그대로 저장됨을 확인. 지적대로 F-169가 만든 회귀 테스트(HUMIDITY↔HUMIDITY)는 등록과 알림의 subtype이 일치하는 경우만 다뤄 이 경로를 놓쳤다 |
| 2026-08-11 | 수정완료 | `ingest.py::_handle_device_value`에서 `install`을 찾은 직후 `install["siap_subtype"] != dmi.subtype`이면 그 요소를 건너뛰도록 추가. `ENV_SUBTYPES`(`repository.py`)와 `DEVICE_STATE_SUBTYPES`가 서로소(교집합 0, 실측 확인)임을 이용해 subtype 코드 하나만 대조하면 `dev_type` 불일치(SENSOR↔ACTUATOR)까지 함께 걸러진다 — 별도의 `dev_type` 대조를 추가할 필요가 없었다 |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_ingest.py::test_handle_device_value_subtype_mismatch_with_registration_is_skipped` 신설 — 재현 그대로 HUMIDITY(SENSOR) 등록 상태에서 IRRIGATION_VALVE(ACTUATOR) 값을 보내 `env_measurement`·`device_state_data` 둘 다 0건임을 확인. `cd project_code && python -m pytest backend/tests/` **158/158** 재확인 |
