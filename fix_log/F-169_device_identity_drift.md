# F-169 · 재연결 뒤 장치 등록 정체성과 측정 subtype 불일치

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/repository.py:100` · `project_code/backend/ingest.py:215` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-06.1369-Part1 §7.1(6)은 하나의 장치 설치 정보가 정확히 하나의 장치 기본 정보를 가져야 한다고 규정한다. §7.2.2.5는 `device_info_id`가 설치된 장치의 기본 정보를 참조하며 갱신 가능한 항목이라고 명시한다.

## 현상

`upsert_device_install_info()`는 기존 설치 행을 갱신할 때 새로 전달받은 `device_info_id`를 버리고 `siap_subtype`만 바꾼다. 이후 값 알림 처리는 프레임의 node/device 번호만으로 설치 행을 찾고, 등록돼 있던 `device_info.device_kind`와 방금 바뀐 subtype을 서로 대조하지 않은 채 저장한다.

## 영향

재연결로 장치 종류가 바뀌면 새 `device_info`는 고아가 되고 설치 행은 이전 모델을 계속 참조한다. 이후 측정은 이전 장치 종류와 새 subtype이 섞인 정체성으로 영속화되어 장치별 데이터 의미가 깨진다.

## 재현

임시 DB에서 node 3/device 1을 TEMP로 연결한 뒤 같은 주소를 HUMIDITY로 재연결했다. 결과는 다음과 같았다.

```text
RECONNECT_METADATA {model_name:SIAP-0x01,device_kind:SENSOR,siap_subtype:2} device_info_count=2
```

이어 같은 주소가 계약상 유효한 ACTUATOR/IRRIGATION_VALVE 값 알림을 보내자 다음 불일치 상태가 만들어졌다.

```text
VALUE_IDENTITY_MISMATCH {device_kind:SENSOR,model_name:SIAP-0x01,siap_subtype:2,subtype:IRRIGATION_VALVE}
```

기존 backend 테스트 **151/151 통과** 상태에서 재현된다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — `repository.upsert_device_install_info`의 기존 UPDATE 문에 `device_info_id`가 SET 목록에서 빠져 있어, 재연결로 새 `device_info_id`(다른 subtype/model)를 넘겨도 저장되지 않고 `siap_subtype`만 갱신됨을 코드 리딩과 임시 DB 재현 양쪽으로 확인 |
| 2026-08-11 | 수정완료 | `project_code/backend/repository.py::upsert_device_install_info`의 UPDATE 절에 `device_info_id=?`를 추가해 재연결 시 최신 `device_info_id`로 이동하도록 고쳤다(같은 자리에서 F-170도 함께 처리 — 아래 F-170 참고). `_handle_connection`(`ingest.py`)은 이미 매 REQ_SET_CONNECTION마다 `get_or_create_device_info()`로 올바른 `device_info_id`를 구해 넘기고 있었으므로 호출자 쪽 변경은 불필요했다 — 결함은 저장 함수의 UPDATE 절 하나였다 |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_repository.py::test_upsert_device_install_info_reconnect_moves_device_info_id` 신설 — TEMPERATURE→HUMIDITY 재연결 후 `device_info_id`가 새 모델을 가리키는지 직접 검증. `backend/tests/test_ingest.py::test_handle_reconnection_with_new_subtype_stores_value_under_new_kind` 신설 — ingest 계층에서 재연결 후 값 알림이 새 subtype(HUMIDITY)으로 정확히 저장되는지 end-to-end 확인(재현의 VALUE_IDENTITY_MISMATCH 시나리오가 재발하지 않음을 증명). `cd project_code && python -m pytest backend/tests/` **157/157**(F-169·F-170·F-171 신설 6건 포함), `python -m pytest siap/tests/ backend/tests/` **259/259** 재확인 |
