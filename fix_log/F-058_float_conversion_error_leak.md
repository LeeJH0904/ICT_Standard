# F-058 · 큰 정수의 FLOAT 변환에서 원시 OverflowError가 누출됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/siap/spec_verify.py:55-67` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 표 7-14 — `Value Type = FLOAT`의 `Value` 길이는 **32 bit**다.

SIAP 명세서 §7은 이를 IEEE-754 single precision으로 해석하고, F-055 처리 기록은 범위 밖 입력이 호출자에게 `ValueRangeError` 하나로 전달되도록 고쳤다고 명시한다.

## 현상

`pack_value()`는 FLOAT 분기에서 먼저 `fv = float(value)`를 실행한 뒤 유한성·범위를 검사한다. `1e39` 같은 Python float는 새 검사에서 `ValueRangeError`가 되지만, `10**400` 같은 큰 정수는 `float(value)` 자체가 먼저 `OverflowError`를 던진다.

따라서 F-055 처리 기록의 "호출자는 `ValueRangeError` 하나만 잡으면 된다"는 계약이 입력 형태에 따라 깨진다. 추가된 23종 SIAP 검증에도 변환 단계에서 실패하는 큰 정수 반례는 없다.

## 영향

같은 32비트 FLOAT 범위 초과가 어떤 값에서는 도메인 오류, 어떤 값에서는 원시 변환 예외로 노출된다. 호출자가 명세대로 `ValueRangeError`만 처리하면 큰 정수 입력에서 실행 흐름이 중단된다.

## 재현

```text
pack_value(BitWriter(), 2, 1e39)
→ ValueRangeError: IEEE-754 single 범위 초과

pack_value(BitWriter(), 2, 10**400)
→ OverflowError: int too large to convert to float
```

## 제안

FLOAT 변환 단계에서 발생하는 타입·값·오버플로 예외까지 `ValueRangeError`로 정규화하고, 큰 정수 반례를 SIAP 검증에 포함한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 재현 성공. FLOAT 경로에서 `10**400` → `OverflowError`, `'abc'` → `ValueError`, `None` → `TypeError` 가 그대로 누출됐다. F-055 처리 기록의 '호출자는 ValueRangeError 하나만 잡으면 된다' 가 입력 형태에 따라 깨진다 |
| 2026-08-03 | 확인 | **정수 경로에도 같은 누출이 있었다.** `int(float('inf'))` → `OverflowError`, `int('abc')` → `ValueError`, `int(None)` → `TypeError`. 지적은 FLOAT 만 짚었으나 원인이 같으므로 범위를 좁히지 않았다 |
| 2026-08-03 | 수정완료 | FLOAT·정수 두 경로의 변환을 `try` 로 감싸 `OverflowError`·`ValueError`·`TypeError` 를 `ValueRangeError` 로 정규화한다. `raise ... from e` 로 원인 예외를 보존해 디버깅 정보는 잃지 않는다 |
| 2026-08-03 | 수정완료 | SIAP 4차 검증에 변환 단계 반례 6종 추가 — FLOAT `10**400`·`'abc'`·`None`, INT `inf`·`'abc'`, UINT `None`. 23 → **29종** |
| 2026-08-03 | 수정완료 | API 검증 반례에도 같은 값을 넣었다(13 → **17종**). F-055 에서 '두 계층이 같은 반례 집합으로 검증된다'고 적었으므로 한쪽만 늘리면 그 주장이 다시 거짓이 된다. 자체 JSON Schema 평가기와 `jsonschema` 4.26.0 의 판정이 새 케이스에서도 일치함을 확인했다 |
