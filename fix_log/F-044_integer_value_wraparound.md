# F-044 · INT·UINT 범위 초과가 조용히 래핑됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/siap/spec_verify.py:35-38,54-56` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 표 7-14 — `Value Type`은 INT, UNSIGNED INT, FLOAT를 구분하며 `Value` 길이는 32비트다.

SIAP 명세서 §7 — USER DEPENDENT 필드는 `DEVICE_MAIN_INFO.Value Type`을 따른다.

## 현상

INT와 UINT 모두 `int(value) & 0xFFFFFFFF`로 패킹되어 타입별 허용 범위를 검사하지 않는다. UINT 음수와 2^32 이상, INT 범위 밖의 값이 오류 없이 다른 값으로 바뀐다. signed INT를 다시 복원하는 왕복 검증도 없다.

## 영향

골든 벡터 생성 단계에서 잘못된 입력이 정상 바이트로 위장한다. 센서값·제어값이 조용히 전혀 다른 값으로 전송될 수 있으며 상호운용성 테스트의 정답 자체가 오염된다.

## 재현

```text
UINT -1        -> FFFFFFFF
UINT 2^32      -> 00000000
INT 2^31       -> 80000000  (signed 해석 시 -2^31)
INT -2^31-1    -> 7FFFFFFF
```

## 제안

INT는 `-2^31..2^31-1`, UINT는 `0..2^32-1`을 강제하고 범위 밖은 실패시킨다. 두 타입의 최솟값·최댓값·초과값과 signed 왕복 테스트를 추가한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 재현 성공. `int(v)&0xFFFFFFFF` 로 UINT −1 → FFFFFFFF, UINT 2^32 → 00000000, INT 2^31 → 80000000(−2^31), INT −2^31−1 → 7FFFFFFF 가 오류 없이 통과했다. signed 복원 경로도 없었다 |
| 2026-08-03 | 수정완료 | `pack_value(bw, vtype, value)` / `unpack_value(br, vtype)` 신설. INT −2^31..2^31−1, UINT 0..2^32−1 을 강제하고 범위 밖·소수·Reserved(0x03)는 `ValueRangeError` 로 실패시킨다. INT 는 2의 보수로 복원한다. `device_main_info` 와 `device_property` 가 모두 이 경로를 쓴다 |
| 2026-08-03 | 수정완료 | `spec_verify.py` 에 4차 검증 15종 신설 — 경계값 6종의 실제 바이트 대조(80000000/FFFFFFFF/7FFFFFFF/00000000/FFFFFFFF/41CA6666)와 왕복, 범위 밖 6종 차단, 동일 비트열 FFFFFFFF 의 INT/UINT 해석 분리, DEVICE_PROPERTY 경계값 5필드 적용. F-026 이 주장했던 왕복 테스트가 여기서 실제로 생겼다 |
| 2026-08-03 | 수정완료 | `spec_examples.json` 은 바이트 단위로 변화 없음(1929B 동일) — 기존 골든 벡터는 오염되지 않았음을 확인 |
