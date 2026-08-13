# F-145 · live 주입 벡터의 Node ID가 simulate 등록 노드와 불일치

| 항목 | 값 |
|---|---|
| 심각도 | 치명 |
| 분류 | 코드버그 |
| 대상 | `project_code/sim/virtual_node.py:123-138` · `project_code/contracts/vectors/golden.jsonl:51-53` · `project_code/siap/codec.py:572-574` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

0943 표 7-10 — `INVALID_NODE_ID 0x03 노드 식별자 오류`, `INVALID_DATA_TYPE 0x06 데이터 타입 오류`, `INVALID_DATA_SUBTYPE 0x07 데이터 서브타입 오류`. 표 7-12 — `ERROR_BATTERY_LOW 0x07 배터리 저전력 오류`. 개발 착수 지시서 §3.6 GPT 검증과 시연 시나리오 §3.1은 X06·X07·X08이 각각 위 세 목표 판정으로 재현되어야 한다고 정한다.

## 현상

골든 X06~X08의 `Node ID`는 모두 3이다. 그러나 `VirtualNodeServer`가 등록하는 노드는 101·102·103(후발 104)뿐이다. `decode_frame()`은 Value Type·Subtype·NEC를 읽기 전에 미등록 Node ID를 검사한다. 따라서 live simulate 링크에 X06~X08을 실제 주입하면 세 벡터 모두 목표 판정 대신 `INVALID_NODE_ID (0x03) — 7.3.1`이 된다.

설계 문서가 요구한 판정 코드가 0943 표 7-10·7-12와 일치하므로 설계가 옳고, 실행 세션의 노드 식별자 구성이 틀렸다. F-060은 X08을 alert로 분류하는 계약 자체를 고친 항목이고, 본 건은 그 계약에 도달하기 전에 Node ID 검사에서 막히는 별도 결함이다.

## 영향

기능 2의 8종 중 X06·X07·X08 세 종이 live 시연에서 다른 결과를 낸다. 특히 S4-d의 NEC 알림을 위반이 아닌 alert로 분리하는 장면을 만들 수 없어 핵심 시연 기능이 붕괴한다.

## 재현

```text
1. VirtualNodeServer와 SiapNodeLink를 simulate 모드로 연결한다.
2. registry가 {101, 102, 103}이 될 때까지 기다린다.
3. inject.inject('X06', server_connection), X07, X08을 각각 새 세션에서 실행한다.
4. link.recv() 결과를 확인한다.

실측:
X06 -> INVALID_NODE_ID / 7.3.1 (기대 INVALID_DATA_TYPE / 표 7-14)
X07 -> INVALID_NODE_ID / 7.3.1 (기대 INVALID_DATA_SUBTYPE / 표 7-14)
X08 -> INVALID_NODE_ID / 7.3.1 (기대 violations 없음 + ERROR_BATTERY_LOW)
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | 재현 절차대로 golden.jsonl 을 대조해 X01~X08(X02 제외) 이 전부 `Node ID=3` 을 쓰는 것을 확인. `virtual_node.py::_default_nodes()` 는 101·102·103·(후발)104 만 등록해 3이 없었다 — GPT 지적대로 재현됨 |
| 2026-08-09 | 수정완료 | Uno 흉내 노드의 ID 를 101 → **3** 으로 변경(`sim/virtual_node.py::_default_nodes()`), 근거를 함수 docstring 에 남김. `sim/tests/test_virtual_node.py` 의 `{101,102,103}` 단언을 `{3,102,103}` 으로 갱신하고, golden.jsonl 의 X 계열 전량을 순회해 등록 노드에 없는 Node ID 가 있으면 실패하는 회귀 테스트 `test_injection_targets_are_registered_nodes_f145` 를 추가(값을 하드코딩하지 않고 골든과 다시 대조 — F-080 원칙). **결함 주입 검증**: node_id 를 101로 되돌리자 새 테스트 2건이 정확히 실패(`assert 3 in {101,102,103}`)하는 것을 확인한 뒤 복원, 재확인 통과. **live 통합 검증**: `VirtualNodeServer`+`SiapNodeLink` 를 실제 simulate 링크로 기동하고 제어 채널로 X06·X07·X08 을 순서대로 주입 → 실측 `msg_id=55 violations=['INVALID_DATA_TYPE']`, `msg_id=56 violations=['INVALID_DATA_SUBTYPE']`, `msg_id=57 violations=[] nec=7` — 재현 절차가 보고한 오판정(`INVALID_NODE_ID`)이 전부 목표 판정으로 교체됨을 직접 확인. `sim/tests/` 전체·`tools/mode_verify.py` 재통과 |
