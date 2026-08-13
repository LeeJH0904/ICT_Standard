# F-026 · USER DEPENDENT 패킹과 내장 Value Type 불일치

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/siap/spec_verify.py:41-50`, `project_docs/contracts/test_contract.py` F-022 회귀 |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 표 7-14 — "Value Type ... INT: 0x00 UNSIGNED INT: 0x01 FLOAT: 0x02", `Value` 길이 32비트

SIAP 명세서 §7 — "DEVICE_PROPERTY의 USER DEPENDENT 5필드는 DEVICE_MAIN_INFO.Value Type을 따른다"

## 현상

`device_property()`는 이미 직렬화된 `main` 바이트와 별도의 `value_type` 인자를 받으며, 기본값은 항상 FLOAT(2)다. 따라서 `main` 안의 Value Type이 UINT여도 호출자가 인자를 생략하면 경계값을 IEEE-754로 패킹한다. 현재 회귀 테스트는 dataclass 필드가 `int`인지 만 확인하고 실제 패킹 바이트를 검사하지 않는다.

## 영향

F-022에서 확정한 구현 결정이 예시 생성기와 향후 골든 벡터에 강제되지 않는다. UINT 값 1이 `00000001`이 아니라 FLOAT 1.0인 `3F800000`으로 기록될 수 있다.

## 재현

```text
main Value Type = UINT, lower_value = 1
device_property(..., value_type 생략)  -> 3f800000
device_property(..., value_type=1)    -> 00000001
```

## 제안

중복 인자를 제거하고 구조화된 `DeviceMainInfo.value_type`에서 타입을 단일 도출한다. INT/UINT/FLOAT 각각의 경계값과 실제 바이트 왕복 테스트를 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | UINT 디바이스에서 `value_type` 생략 시 경계값 1이 `3f800000`(FLOAT 1.0)으로 패킹됨을 재현. 올바른 값은 `00000001` |
| 2026-08-03 | 수정완료 | **중복 인자를 제거했다.** `main_value_type(main)` 헬퍼가 `DEVICE_MAIN_INFO` 바이트의 offset 17·len 2 에서 Value Type을 직접 도출한다. 타입 출처가 하나뿐이므로 어긋날 수 없다. INT/UINT/FLOAT 실제 바이트 왕복 테스트는 이 시점에 추가하지 못했다 |
| 2026-08-03 | 수정완료 | **F-043 정정** — 위 기록의 '왕복 테스트 추가'는 사실이 아니었다. 해당 테스트는 F-044 처리 시 `spec_verify.py` 4차 검증으로 실제 신설했다 |
