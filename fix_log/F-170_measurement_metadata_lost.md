# F-170 · 환경 측정 위치 누락과 재연결 시 설치 메타데이터 소실

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/ingest.py:223` · `project_code/backend/repository.py:102` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-06.1369-Part1 §6.3.2는 측정값·측정 시각·측정 위치·측정 장치 정보를 함께 관리하도록 권고하고 측정 단위 관리를 요구한다. §7.2.3.3은 환경 측정 정보의 위치가 측정 장치의 설치 위치 참조로 결정된다고 명시한다. DB 설계서 §1-4도 값·단위·오류·범위를 함께 저장하는 모델을 정한다.

## 현상

환경 값 알림 처리기는 `record_env_measurement()`에 값·단위·범위만 넘기고 설치 위치와 위치 단위를 넘기지 않는다. 또한 기존 장치가 재연결되면 `upsert_device_install_info()`가 호출 인자의 `None`을 그대로 UPDATE하여 서버가 관리하던 `install_location`, `install_loc_unit`, `unit`을 지운다.

## 영향

환경 측정 행의 위치 메타데이터가 처음부터 비어 있고, 재연결 후에는 그 위치를 복원할 설치 정보와 단위까지 사라진다. 표준이 요구한 측정 위치 추적과 단위 해석을 할 수 없다.

## 재현

설치 행에 위치 `GH-A-1`, 위치 단위 `m`, 측정 단위 `C`를 넣은 임시 DB에서 정상 TEMP 알림을 처리한 뒤 같은 장치를 재연결했다.

```text
ENV_BEFORE_RECONNECT {location:None,location_unit:None} {unit:C}
INSTALL_AFTER_RECONNECT {install_location:None,install_loc_unit:None,unit:None}
```

기존 backend 테스트 **151/151 통과** 상태에서 재현된다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — ① `ingest.py::_handle_device_value`가 `repository.record_env_measurement()` 호출에 `location`/`location_unit`을 넘기지 않아 `env_state_data.location`이 항상 NULL임을 확인. ② `repository.py::upsert_device_install_info`의 UPDATE 절이 `install_location`·`install_loc_unit`·`unit`을 호출자가 넘긴 값(재연결 경로에서는 항상 None) 그대로 덮어써, 다른 경로로 이미 채워진 값도 재연결 시 사라짐을 임시 DB로 재현 |
| 2026-08-11 | 수정완료 | ① `ingest.py::_handle_device_value`의 `record_env_measurement()` 호출에 `location=install["install_location"], location_unit=install["install_loc_unit"]` 추가 — 1369-P1 §7.2.3.3(환경 측정 위치는 측정 장치의 설치 위치를 참조)을 그대로 따른다. ② `repository.py::upsert_device_install_info`의 UPDATE 절에서 `install_location`·`install_loc_unit`·`unit` 세 컬럼을 `COALESCE(?, 기존컬럼)`으로 바꿔, 호출자가 실제 값을 줬을 때만 갱신하고 `None`이면 기존 값을 보존하도록 고쳤다(F-158이 `installed_at`에 적용한 "재연결로 지우지 않는다" 원칙과 같은 결). `device_info_id` UPDATE 추가(F-169)와 같은 자리라 한 번에 반영했다 |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_repository.py::test_upsert_device_install_info_reconnect_preserves_unset_location_and_unit` 신설 — 위치·단위 설정 후 위치 정보 없는 재연결이 그 값을 보존하는지 확인. `backend/tests/test_ingest.py::test_handle_device_value_env_measurement_carries_install_location` 신설 — 값 알림 처리가 실제로 위치를 `env_state_data`에 싣는지 end-to-end 확인. `cd project_code && python -m pytest backend/tests/` **157/157** 재확인 |
