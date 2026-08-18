# F-247 · Type/Subtype 불일치를 SUCCESS 승인한 뒤 백엔드에서 폐기한다

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 코드버그 |
| 대상 | 제출본 `project_code/siap/codec.py` · `project_code/siap/link.py:334` · `project_code/backend/ingest.py:272` |
| 발견일 | 2026-08-18 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0943 7.3.1 표 7-10은 `INVALID_DEVICE_TYPE(0x05)`와
`INVALID_DATA_SUBTYPE(0x07)`을 요청 처리 오류로 정의한다. 제출 계약의
`Subtype.dev_type`은 각 자체 할당 Subtype이 SENSOR인지 ACTUATOR인지 정한다.

## 현상

`ACTUATOR + HUMIDITY(SENSOR 정의)` DMI를 담은
`REQ_SET_NODE_DEVICE_PROPERTY_ALL`을 디코드하면 위반이 없고 `_default_reply()`는
SUCCESS를 보낸다. 이후 backend ingest는 Type/Subtype 불일치를 발견해 해당 요소를
조용히 `continue`한다.

`F-175`에서 backend 예외를 막기 위한 폐기 가드는 추가됐지만, 당시 처리 기록도
프로토콜 RSC 판정은 범위 밖으로 남겼다. 이번 검수는 그 잔여 경로가 최종 제출본에서
SUCCESS 승인과 무저장으로 실제 분리됨을 확인했다.

## 영향

송신 노드는 속성 등록이 성공했다고 믿지만 서비스 DB에는 장치가 생기지 않는다.
적합성 화면도 위반을 표시하지 않아 원인 추적이 어렵다.

## 재현

```text
입력: dev_type=ACTUATOR, subtype=HUMIDITY, value_type=FLOAT
decode_frame().violations = ()
_default_reply().rsc = SUCCESS
Subtype(HUMIDITY).dev_type = SENSOR
```

## 제안

프로젝트가 정의한 Subtype↔Type 불변식을 응답 전에 검증하고 불일치에 적절한 RSC를
반환한다. backend 폐기 가드는 방어선으로 유지하되 위반 프레임을 로그에 남긴다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
|  |  |  |
