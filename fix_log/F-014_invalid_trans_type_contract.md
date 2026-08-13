# F-014 · 유효하지 않은 Transmission Type을 계약 타입으로 표현 불가

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/contracts/frame.py:118-120, 169-177` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 표 7-6 — "Transmission Type ... Unicast: 0x00 ... Multicast: 0x01 ... Broadcast: 0x02"

0943 표 7-10 — "INVALID_TRANSMISSION_TYPE | 0x08 | 데이터 전송방법 오류"

`Frame_구조_명세서.md` §1 — "파싱 실패해도 `violations`가 채워진 `Frame`을 반환한다."

## 현상

`Header.trans_type`은 `TransType`으로 선언되어 있지만 열거형에는 정상값 0x00~0x02만 있다. 기능 2의 명시된 주입 케이스인 원본값 0x03을 열거형으로 변환하면 `ValueError`가 발생한다. 원본 오류값을 유지하면서 타입 계약도 지키는 `Header`를 만들 수 없다.

## 영향

디코더가 자연스럽게 `TransType(raw_value)`를 사용하면 예외를 던지지 않는다는 계약을 위반한다. 단순 정수 3을 억지로 넣으면 런타임은 통과하지만 `Header` 타입 계약이 거짓이 된다.

## 재현

```powershell
cd project_docs/contracts
python -B -c "from frame import TransType; print(TransType(3))"
# ValueError: 3 is not a valid TransType
```

## 제안

원본 2비트 값을 보존할 수 있도록 헤더 필드 계약을 조정하거나, 정상 해석값과 원본값을 분리한다. `contracts/` 변경 절차에 따라 사용자 승인 후 처리해야 한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | `TransType(3)` → `ValueError` 재현. 위반 케이스 #5(Transmission Type=0x03)를 `Header`에 담을 수 없음을 확인 |
| 2026-08-03 | 수정완료 | `Header.trans_type`을 raw `int`로 변경. `msg_type`이 이미 raw int인 것과 동일한 원칙 — **헤더는 전송 원본을 보존하고 해석은 분리한다.** `resolve_trans_type(raw) -> TransType \| None` 및 `Header.trans` 프로퍼티 추가. 회귀 테스트 5종 추가 (`test_contract.py`) |
| 2026-08-03 | — | `contracts/` 변경이므로 CLAUDE.md §5 절차 적용. 표준 근거: 표 7-6(정의값 3종) + 표 7-10(`INVALID_TRANSMISSION_TYPE`). 사용자 승인 하에 처리 |
