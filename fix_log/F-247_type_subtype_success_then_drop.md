# F-247 · Type/Subtype 불일치를 SUCCESS 승인한 뒤 백엔드에서 폐기한다

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 코드버그 |
| 대상 | 제출본 `project_code/siap/codec.py` · `project_code/siap/link.py:334` · `project_code/backend/ingest.py:272` |
| 발견일 | 2026-08-18 |
| 상태 | 수정완료 |

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
| 2026-08-18 | 확인 | `encode_dmi`/`decode_dmi`가 `value_type`·`subtype 등록`은 검사하나 Type↔Subtype 불변식(`Subtype.dev_type`)은 검사하지 않아 (ACTUATOR, HUMIDITY[SENSOR])가 위반 없이 통과함을 확인 |
| 2026-08-18 | 수정완료 | `siap/codec.py` `decode_dmi`에 Type↔Subtype 불변식 검사 추가 — `DevType(dev_type_raw) is not Subtype(subtype).dev_type`이면 `INVALID_DEVICE_TYPE(0x05, 표 7-14)` 위반(subtype 자체는 등록됐으나 Type 필드가 그 subtype에 부적합). `encode_dmi`에도 대칭 검사 추가("한쪽만 막으면 판정 기준이 무너진다" 원칙). `REQ_SET_NODE_DEVICE_PROPERTY_ALL`의 DP는 `decode_dp→decode_dmi` 경유라 함께 커버. 결과: 불일치→INVALID_DEVICE_TYPE 회신(SUCCESS 아님) + `is_valid=False`라 `ingest.handle`이 `frame_violation`에 기록(조용한 폐기 해소). `backend/ingest.py`의 폐기 가드(F-175)는 방어선으로 유지하되 주석을 "codec이 상류에서 잡으므로 정상 경로에서 미실행되는 이중 방어"로 갱신. 정상 벡터(SENSOR+HUMIDITY, ACTUATOR+FAN) 왕복 정상, 365건 테스트 통과 |
| 2026-08-18 | 수정완료 | **회귀 테스트**: 제출본 `siap/tests/test_codec.py::test_decode_rejects_type_subtype_mismatch_f247` 추가(encode/decode 양쪽 불일치→INVALID_DEVICE_TYPE, SENSOR+HUMIDITY·ACTUATOR+FAN 정상 왕복). 통과 확인 |
| 2026-08-18 | 수정완료 | **적용 범위**: 제출본(`최종_제출물_폴더/ICT_Test/project_code/siap/codec.py`·`backend/ingest.py`·`siap/tests/test_codec.py`)에 적용. 이후 사용자 지시로 **개발 트리(저장소 루트 `project_code/`)에도 동일 패치 이식**(codec.py encode/decode_dmi·ingest.py 가드 주석·tests) — dev 고유 F-참조 주석은 보존. dev 367 통과. link.py는 변경 없음(위반 회신은 기존 `_default_reply`→`error_response` 경로가 처리). `meta_verify.py` 회귀 검사에서 F-247 발견돼 목록에서 빠짐 |
