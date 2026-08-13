# F-180 · 연결 등록의 Type/Subtype 불일치가 장치 정체성을 분기함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/ingest.py:151` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-10.1369-Part1 7.1(6) — “장치설치 정보는 1개의 장치 정보를 가지며”, 7.2.2.5는 `device_info_id`가 설치된 장치의 기본 정보를 나타낸다고 규정한다.

CLAUDE.md §3.5의 Subtype 레지스트리 결정과 `contracts/frame.py::Subtype.dev_type`은 환경상태 Subtype을 SENSOR, 장치상태 Subtype을 ACTUATOR로 고정한다.

## 현상

F-175 수정은 `_handle_device_value()`에서 Type/Subtype 불일치를 건너뛰지만, `_handle_connection()`은 같은 검사를 하지 않는다. 최초 `REQ_SET_CONNECTION`에 `HUMIDITY` Subtype과 `ACTUATOR` Type을 넣으면 `device_info.device_kind='ACTUATOR'`와 `siap_subtype=HUMIDITY`가 함께 저장된다. 이후 같은 주소에서 정상 `HUMIDITY/SENSOR` 값을 보내면 환경 측정으로 받아들여 장치 기본정보와 측정 종류가 서로 갈린다.

## 영향

하나의 장치설치 정보가 참조하는 장치 기본정보는 액추에이터인데 실제 축적 데이터는 센서가 되는 1369-P1 정체성 모순이 영속된다. F-175가 수정완료여도 연결 등록 경로의 동일 불변식은 닫히지 않았다.

## 재현

```text
REQ_SET_CONNECTION: subtype=HUMIDITY(0x02), dev_type=ACTUATOR
REGISTERED={'device_kind': 'ACTUATOR', 'siap_subtype': 2}
NOTI_DEVICE_VALUE: subtype=HUMIDITY(0x02), dev_type=SENSOR, value=55
ENV_ROWS=1
DEVICE_STATE_ROWS=0
```

기존 `backend/tests` 159/159가 통과한 상태에서 재현됐다.

## 제안

연결 등록 전에 `dmi.dev_type is Subtype(dmi.subtype).dev_type` 불변식을 값 알림과 동일하게 검증하고 반례를 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — F-175는 `_handle_device_value()`에만 `dmi.dev_type is not Subtype(dmi.subtype).dev_type` 가드를 추가했고, `_handle_connection()`(REQ_SET_CONNECTION 처리)에는 같은 검사가 없어 최초 등록 시점에 이미 정체성이 어긋날 수 있음을 확인 |
| 2026-08-11 | 수정완료 | `_handle_connection()`에 F-175와 동일한 `dmi.dev_type is not Subtype(dmi.subtype).dev_type` 가드를 `name is None` 확인 직후·`device_info`/`device_install_info` 생성 이전에 추가 — 불일치 조합은 등록 자체를 만들지 않는다. F-176(`device_manage` 결속) 코드와 같은 함수·같은 라운드라 한 커밋으로 함께 반영했다 |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_ingest.py::test_handle_connection_dev_type_inconsistent_with_subtype_is_skipped` 신설 — 재현 그대로 HUMIDITY subtype + ACTUATOR Type 연결 등록이 `device_info`·`device_install_info` 어느 것도 만들지 않음을 확인. `cd project_code && python -m pytest backend/tests/` **168/168** 재확인 |
