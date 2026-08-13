# F-055 · API가 32비트 FLOAT로 패킹할 수 없는 값을 허용함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/api/openapi.json:1887-1980`, `api_verify.py:325-355`, `siap/spec_verify.py:51-56` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 표 7-14 — `Value Type`은 `FLOAT: 0x02`를 정의하고 `Value` 길이는 **32 bit**로 규정한다.

SIAP 명세서 §7은 표준의 표현 방식 공백을 **IEEE-754 single precision (4 byte), big-endian**으로 결정했다.

## 현상

`ControlAction`의 FLOAT 분기는 `type: number`만 두어 IEEE-754 단정밀도로 표현할 수 없는 유한 JSON 숫자도 허용한다. 예를 들어 `1e39`, `-1e39`, 매우 큰 정수는 OpenAPI 스키마에서 유효하지만 `spec_verify.py`의 `struct.pack('>f', ...)` 경로에서는 `OverflowError`가 난다.

API 명세서 §4.3-a는 "인코딩 계층과 API 계층이 같은 반례 집합으로 검증"된다고 주장하지만, 현재 반례 10종에는 FLOAT 초과값이 없다.

## 영향

전송 불가능한 명령이 API 승인 스냅샷과 DB에는 정상 저장된 뒤 실행 단계에서 늦게 실패한다. F-054가 해결하려던 계층 간 판정 불일치가 FLOAT 경로에는 그대로 남아 있다.

## 재현

```text
ControlAction {"value": 1e39, "value_type": "FLOAT"}
→ JSON Schema Draft 2020-12: ACCEPTED
→ struct.pack('>f', 1e39): OverflowError: float too large to pack with f format
```

## 제안

API 계약과 검증 반례에 IEEE-754 단정밀도 유한 범위를 반영하고, 프로토콜 패커도 범위 초과를 일관된 검증 오류로 변환한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 재현 성공. `jsonschema` 4.26.0 에서 `{"value":1e39,"value_type":"FLOAT"}` ACCEPTED, `struct.pack('>f',1e39)` 은 `OverflowError`. 이분 탐색으로 `struct` 의 실제 상한이 `3.4028235677973362e38`(반올림 경계)임도 확인했다 |
| 2026-08-03 | 수정완료 | **상한을 표현 가능한 최대 유한값 `3.4028234663852886e38`(`7F7FFFFF`)로 잡았다.** `struct` 가 반올림으로 받아주는 경계보다 좁지만, '단정밀도로 표현 가능한 범위'라는 정의가 더 명확하고 설명하기 쉽다. 범위 안의 정밀도 손실은 float32 의 성질이므로 오류로 보지 않는다 |
| 2026-08-03 | 수정완료 | `openapi.json` 의 FLOAT 분기에 `minimum`·`maximum` 추가. 프로토콜 계층 `spec_verify.pack_value()` 도 함께 고쳐 `OverflowError` 대신 `ValueRangeError` 를 던진다 — **호출자가 잡아야 할 예외가 둘로 늘어나는 것**이 이 결함의 두 번째 얼굴이었다. `inf`·`nan` 도 거부한다 |
| 2026-08-03 | 수정완료 | 반례 집합에 FLOAT 를 넣었다. API 검증 반례 10 → **13종**(1e39 · -1e39 · 1e308), 정상값 6 → **8종**(±최댓값). SIAP 4차 검증 18 → **23종**(FLOAT 1e39 · -1e39 · inf · nan 차단 + 최댓값 왕복 `7F7FFFFF`) |
| 2026-08-03 | 수정완료 | **지적의 핵심은 반례 집합의 공백이었다.** F-054 에서 '두 계층이 같은 반례로 검증된다'고 적었지만 그 반례에 FLOAT 가 없었다. 검사 방식을 고쳐도 반례가 빠져 있으면 결과는 같다는 점을 API 명세서 §7.1 에 명시했다 |
