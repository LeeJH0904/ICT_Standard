# F-051 · ControlAction이 금지한 대상 장치 속성을 허용함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json:1877-1914`, `API_명세서.md` §4.3 |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

API 명세서 §4.3 — "`action`에 대상 장치를 넣지 않는다", `ControlAction = { value, value_type, duration_sec }`

OpenAPI 3.1 Schema Object는 JSON Schema 2020-12를 따르며, JSON Schema에서 `additionalProperties`를 생략하면 미선언 속성은 기본적으로 허용된다.

## 현상

`RuleDraftRequest`, `ApproveRequest`, `ManualControlRequest`에는 `additionalProperties:false`가 있지만 중첩된 `ControlAction`에는 없다. 따라서 아래 객체가 OpenAPI 스키마상 유효하다. `api_verify.py`도 선언된 `properties`에 `install_id`가 없는지만 보고 PASS하므로 이를 놓친다.

## 재현

```json
{
  "condition_expr": "temp > 40",
  "action": {"value": 1, "value_type": "UINT", "install_id": "B"},
  "target_install_id": "A"
}
```

Python `jsonschema` 4.23.0으로 위 `ControlAction`을 검증하면 ACCEPTED다.

## 영향

F-049 후속 결정인 대상 단일 출처가 API 계약에서 성립하지 않는다. 대상 A와 중첩 대상 B가 동시에 승인 JSON에 남아 구현·화면마다 다른 값을 선택할 수 있다.

## 제안

`ControlAction` 자체를 닫힌 객체로 만들고 검증기도 `additionalProperties:false`를 확인한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 재현 성공. `jsonschema` 4.26.0 으로 `{"value":1,"value_type":"UINT","install_id":"B"}` 를 `ControlAction` 에 넣으면 ACCEPTED 다. 최상위 요청 본문 3종에만 `additionalProperties:false` 를 걸고 중첩 객체를 빠뜨렸다 |
| 2026-08-03 | 수정완료 | `ControlAction` 을 닫힌 객체로 만들었다(`additionalProperties: false`). F-049 의 '대상 단일 출처' 결정이 API 계약에서도 성립한다 |
| 2026-08-03 | 수정완료 | **검증 방식을 바꿨다.** '선언된 properties 에 install_id 가 없는가'만 보던 검사가 이 결함을 통과시켰다. 이제 반례를 스키마에 **실제로 평가해 넣어본다** — 반례 10종 거부 / 정상값 6종 허용 |
| 2026-08-03 | 수정완료 | 요청 본문 스키마 4종(`RuleDraftRequest`·`ApproveRequest`·`ManualControlRequest`·`ControlAction`)이 전부 닫혀 있는지 검사하는 항목을 추가했다. 중첩 객체를 또 빠뜨리지 않게 한다 |
