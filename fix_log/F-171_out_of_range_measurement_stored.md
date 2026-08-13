# F-171 · 유효범위 밖 환경값을 정상 측정으로 저장

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/ingest.py:221` · `project_code/backend/repository.py:171` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

TTAK.KO-06.1369-Part1 §6.3.2는 센서 유효범위를 벗어난 값은 측정 오류로 보고 무시해야 하며, 센서별 유효범위를 관리해야 한다고 명시한다. DB 설계서 §1-4도 측정값과 유효범위·오류 정보를 함께 관리하도록 정한다.

## 현상

환경 값 알림 처리기는 장치의 `lower_limit`·`upper_limit`을 측정 행에 복사하지만 현재 값이 그 범위 안인지 판정하지 않는다. 저장 함수도 subtype만 확인하고 값을 그대로 INSERT한다.

## 영향

센서 고장이나 비정상 값이 오류·격리 표시 없이 정상 환경 데이터로 축적된다. 분석·제어가 이 값을 신뢰하면 잘못된 판단으로 이어질 수 있다.

## 재현

유효범위 0~50으로 등록한 TEMP 센서에 0943 계약상 형식이 올바른 값 999 알림을 넣었다.

```text
OUT_OF_RANGE_STORED {value:999.0,lower_limit:0.0,upper_limit:50.0} env_count=1
```

프로토콜 위반은 생성되지 않았고 DB에도 오류 표시는 없었다. 기존 backend 테스트 **151/151**, DB 정적 검증 **103/103**, DB 실연결 검증 **11/11**이 모두 통과하는 상태에서 재현된다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — `ingest.py::_handle_device_value`가 SENSOR 값을 `install["lower_limit"]`/`upper_limit`와 대조하지 않고 그대로 `record_env_measurement()`에 넘겨 저장함을 확인. `record_device_state()`(액추에이터 경로)의 `valid_range` 처리와 달리, 센서 경로는 유효범위를 "복사"만 하고 "판정"하지 않고 있었다 |
| 2026-08-11 | 수정완료 | `ingest.py::_handle_device_value`에 1369-P1 §6.3.2 근거로 범위 검사를 추가 — `install["lower_limit"]`·`upper_limit`가 둘 다 있고 값이 그 범위(경계값 포함, `lo <= value <= hi`) 밖이면 `record_env_measurement()`를 호출하지 않고 그 요소만 건너뛴다("무시해야 하며"를 문자 그대로 — 정상 데이터로 축적하지 않는다). **알림(alert) 발행은 이번에 추가하지 않았다** — `alert.kind` CHECK 제약(`NO_DATA`/`NODE_ERROR`/`DISCONNECT`/`THRESHOLD`/`CONTROL_TIMEOUT`)에 "센서 판독값이 유효범위를 벗어남"에 맞는 종류가 없고, `THRESHOLD`는 `0937_요구사항_대조표.md` §5-6이 이미 **다른 의미**(0943 표 7-15 `Lower/Upper Value` 기반 "업무 임계값 초과 이벤트", 아직 미구현)로 예약해 둔 값이라 재사용하면 두 개념이 섞인다. 새 `kind` 추가는 `schema.sql`(2곳) · DB 설계서 · `verify.py` 건수 갱신이 딸린 스키마 변경이라 이 코드버그 수정 범위를 넘어선다고 판단해 보류하고, 아래에 사용자 보고로 남긴다 |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_ingest.py::test_handle_device_value_sensor_out_of_range_is_discarded`(값 999, 범위 -40~80 → 저장 0건) · `test_handle_device_value_sensor_within_range_boundary_is_kept`(경계값 80 → 저장 1건, 배타적 오탈락 방지) 신설. `cd project_code && python -m pytest backend/tests/` **157/157** 재확인 |
