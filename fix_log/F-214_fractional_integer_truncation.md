# F-214 · INT·UINT 소수 입력을 정수로 조용히 절삭

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/codec.py:L148` |
| 발견일 | 2026-08-12 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0943 표 7-14 — Value Type은 `INT`·`UNSIGNED INT`·`FLOAT`로 구분되고 Value는 선택된 형식의 32bit 값이다.

SIAP 메시지 명세서 §10.4 — 범위 밖 차단 10종에 “정수 자리의 소수”를 포함한다.

## 현상

`pack_int()`와 `pack_uint()`가 먼저 `int(value)`를 호출한다. Python의 `int(1.5)`는 예외 없이 `1`이므로 이후 범위 검사도 통과한다. `ValueRangeError`가 발생하지 않고 다른 값을 정상 인코딩한다.

## 영향

사용자가 보낸 1.5가 1로 바뀌어도 성공한 Frame으로 전송된다. 설계 검증기 `spec_verify.py`는 같은 입력을 차단한다고 판정하지만 실제 단계 3 코덱은 차단하지 않아 설계와 구현이 갈린다.

## 재현

```powershell
cd project_code
python -c 'from siap.codec import pack_int,pack_uint; print(pack_int(1.5),pack_uint(1.5))'
```

실행 결과:

```text
1 1
```

## 제안

INT·UINT 경로는 변환 뒤 원래 값에 소수부가 있었는지 확인하거나, 허용 입력 타입과 정수 동등성을 명시적으로 검사한 뒤 범위 검사를 수행한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
