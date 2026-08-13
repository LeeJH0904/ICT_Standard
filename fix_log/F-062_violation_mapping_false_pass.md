# F-062 · 벡터별 기대 오류가 뒤바뀌어도 골든 검증기가 통과함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/contracts/vectors/golden_verify.py:118-153` |
| 발견일 | 2026-08-05 |
| 상태 | 수정완료 |

## 근거

0943 7.3.1과 표 7-10은 Version 오류를 `INVALID_VERSION(0x01)`, Node ID 오류를 `INVALID_NODE_ID(0x03)`로 구분한다. 골든 벡터 명세서 §3.3과 CLAUDE.md §6.3도 주입별 기대 코드를 1:1로 확정한다.

## 현상

검증기는 각 violation의 이름과 숫자가 열거에 존재하는지만 확인한 뒤, CLAUDE 표와는 `code_name`의 정렬된 전체 목록만 비교한다. 어떤 주입에 어떤 오류가 붙었는지는 비교하지 않는다.

메모리 사본에서 X01과 X02의 `violations` 객체 전체를 서로 바꿔도 `INVALID_VERSION`과 `INVALID_NODE_ID`의 전체 집합은 그대로여서 **21/21, 종료코드 0**으로 통과했다.

## 영향

Version 오류를 Node ID 오류로, Node ID 오류를 Version 오류로 판정하는 잘못된 골든 정답이 C·Python·backend 세 구현에 동시에 전파될 수 있다. "CLAUDE.md 6.3 위반 8종과 정확히 대응"이라는 PASS 문구가 사실이 아니다.

## 재현

```text
1. golden.jsonl 사본에서 X01.violations와 X02.violations를 서로 교환한다.
2. golden_verify.py에 사본을 주입한다.
3. 21/21, exit 0으로 통과한다.
```

## 제안

CLAUDE.md 표 또는 검증기 내 독립 매핑을 주입 식별자/핵심 필드와 기대 `(code, code_name, clause)`에 1:1로 대조한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-05 | 확인 | 재현 성공. X01 과 X02 의 `violations` 를 통째로 교환했는데 **21/21, exit 0** 이었다. 검증기가 `code_name` 의 정렬된 전체 목록만 비교해, 집합이 같으면 어느 주입에 붙었는지는 보지 않았다 |
| 2026-08-05 | 수정완료 | **① 주입 라벨 도입.** 벡터마다 `inject` 를 적고(`version` · `unregistered_node` · `payload_length` · `message_type` · `transmission_type` · `value_type` · `subtype` · `nec_battery_low`), 검증기의 `INJECT_EXPECT` 표와 `(code, code_name, clause)` 를 1:1 대조한다. 라벨 집합 자체도 정확히 일치해야 한다 |
| 2026-08-05 | 수정완료 | **② 바이트에서 재판정.** 벡터에 적힌 기대를 보지 않고 프레임 내용만으로 위반을 다시 도출해 기록과 대조한다. Version·Payload Length·Message Type·Transmission Type·Value Type·Subtype 6종이 바이트로 결정된다. Node ID 등록 여부는 게이트웨이의 런타임 상태라 바이트 판정 대상에서 제외하고 라벨 대조로만 본다 |
| 2026-08-05 | 수정완료 | 이 검사는 **정상·경계 44건에도 적용**된다 — 아무 규칙도 걸리지 않아야 한다. 교환 변형에서 두 항목이 동시에 FAIL(25/28, exit 1) |
