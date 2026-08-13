# F-054 · API가 INT·UINT 32비트 제어값 범위를 강제하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json:1877-1906`, `api_verify.py:214-233` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 표 7-14 — `Value Type`은 INT·UNSIGNED INT·FLOAT를 구분하고 `Value` 길이는 32비트다.

F-044에서 INT `-2^31..2^31-1`, UINT `0..2^32-1` 및 정수 여부를 명세 검증의 기준으로 확정했다.

## 현상

`ControlAction.value`는 조건 없는 `type:number` 하나다. `value_type`이 UINT 또는 INT여도 음수 UINT, 소수, 범위 초과값을 모두 허용한다. OpenAPI 3.1/JSON Schema 2020-12의 `if/then` 또는 `oneOf`로 타입별 제약을 표현할 수 있지만 사용하지 않았다. `api_verify.py`는 `value_type` enum만 비교하고 값 범위는 검사하지 않는다.

## 재현

다음 객체들은 현재 OpenAPI 스키마와 Python `jsonschema` 4.23.0에서 모두 ACCEPTED다.

```json
{"value": -1,         "value_type": "UINT"}
{"value": 1.5,        "value_type": "UINT"}
{"value": 4294967296, "value_type": "UINT"}
{"value": 2147483648, "value_type": "INT"}
```

## 영향

잘못된 제어값을 승인 스냅샷에 저장할 수 있고, 실행 시 SIAP 빌더의 `ValueRangeError`로 늦게 실패한다. API 계약만 보고 만든 클라이언트는 표준상 전송 불가능한 요청을 정상으로 판단한다.

## 제안

`ControlAction`을 Value Type별 `oneOf` 또는 `if/then`으로 분기해 INT/UINT의 JSON 타입과 범위를 강제하고, F-044 경계·초과 반례를 API 검증에도 재사용한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 재현 성공. `jsonschema` 4.26.0 으로 `{"value":-1,"value_type":"UINT"}`, `{"value":1.5,...}`, `2^32`, `INT 2^31` 이 모두 ACCEPTED 였다. F-044 로 프로토콜 계층은 막았으나 API 계약에는 반영되지 않아, 계약만 보고 만든 클라이언트가 전송 불가능한 요청을 정상으로 판단한다 |
| 2026-08-03 | 수정완료 | OpenAPI 3.1(JSON Schema 2020-12)의 `allOf` + `if`/`then` 으로 `value_type` 별 분기를 넣었다. INT `-2^31..2^31-1` 정수, UINT `0..2^32-1` 정수, FLOAT `number`. 표 7-14 의 32bit 규정을 API 계층에서도 강제한다 |
| 2026-08-03 | 수정완료 | **F-044 의 반례 집합을 그대로 재사용한다.** 인코딩 계층과 API 계층이 같은 반례로 검증되므로 두 곳의 판정이 어긋날 수 없다. 반례 10종 거부 / 경계·정상 6종 허용 |
| 2026-08-03 | 수정완료 | `jsonschema` 를 의존성으로 추가하지 않았다(CLAUDE.md §4.3). 필요한 키워드만 구현한 60줄 평가기를 `api_verify.py` 에 두었고, 개발 중 `jsonschema` 4.26.0 과 **20개 케이스에서 판정이 전부 일치**함을 확인했다. 제출물은 표준 라이브러리만으로 돈다 |
