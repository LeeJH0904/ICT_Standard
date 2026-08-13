# F-060 · 정상 NOTI_ERROR를 위반으로 표시해 알림·ACK 경로를 차단함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/contracts/vectors/golden_layout.py:322-326`, `golden.jsonl` X08, 골든벡터 명세서 §3.3, 아키텍처 §3.1 |
| 발견일 | 2026-08-05 |
| 상태 | 수정완료 |

## 근거

0943 7.3.2 — "NEC 필드는 센서-구동기 노드에서 오류가 발생할 시, 이를 온실통합제어기로 알림 메시지를 전달할 때 페이로드에 포함되는 에러코드"다.

0943 8.2.1.1 — `NOTI_ERROR`는 배터리 상태 등 노드 오류를 GCG에 알리는 정상 Notify이며 GCG는 ACK를 전송한다. 표 7-12는 `ERROR_BATTERY_LOW = 0x07`을 정상 정의한다.

## 현상

`N33`의 `ERROR_PWR(0x05)`는 정상 `NOTI_ERROR`로 `violations=[]`인데, 같은 표 7-12 코드인 X08의 `ERROR_BATTERY_LOW(0x07)`는 category=`위반`이고 `violations`에 들어 있다. X08의 note와 명세서도 "프레임 자체는 정상"이라고 인정한다.

그러나 `Frame.is_valid`는 `violations`가 하나라도 있으면 false다. 아키텍처 §3.1의 `ingest.handle()`은 `frame.violations`가 있으면 격리 후 즉시 반환하므로 `fcs.on_node_error()`와 Notify ACK 경로에 도달하지 않는다.

## 영향

골든 벡터를 정답으로 구현하면 정상 배터리 부족 알림이 표준 위반 프레임으로 격리되고, alert 저장과 ACK가 누락된다. 노드는 ACK를 받지 못해 Notify Error Interval마다 재전송하게 된다.

## 제안

X08을 프로토콜 위반과 분리해 정상 `NOTI_ERROR`/알림 시나리오로 표현하고, `violations`에는 `INVALID_*` 판정만 넣는다. NEC 알림의 기대 결과는 별도 필드나 backend 기대값으로 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-05 | 확인 | 타당하며 영향이 크다. `Frame.is_valid` 는 `violations` 가 하나라도 있으면 false 이고, 아키텍처 §3.1 의 `handle()` 은 그 경우 격리 후 즉시 반환한다. X08 을 정답으로 구현하면 **정상 배터리 알림이 격리되어 `fcs.on_node_error()` 도 ACK 도 실행되지 않고**, 노드는 ACK 를 못 받아 Notify Error Interval 마다 재전송한다 |
| 2026-08-05 | 수정완료 | 벡터에 `judgement` 필드를 넣어 셋으로 갈랐다 — `violation`(프레임이 표준을 어김) / `alert`(프레임은 정상, 노드가 오류를 알림) / `normal`. X08 은 `violations=[]` 이고 기대는 새 `nec_alert` 필드에 담는다. 0943 8.2.1.1 은 `NOTI_ERROR` 를 정상 Notify 로 정의하고 GCG 가 ACK 를 보내도록 규정한다 |
| 2026-08-05 | 수정완료 | 검증 3종 추가 — 판정 분류 개수(violation 7 / alert 1 / normal 44) / NEC 알림 벡터의 `violations` 가 비어 있는가 / **`violations` 에는 `INVALID_*` 만 들어가는가**. 마지막 검사가 같은 실수를 구조적으로 막는다 |
| 2026-08-05 | 수정완료 | 명세서 §3.3 과 CLAUDE.md §3.5 에 'NEC 알림은 위반이 아니다' 를 결정으로 명시했다. X08 을 위반으로 되돌리는 변형을 주입해 3개 항목이 동시에 FAIL(25/28, exit 1) 하는 것을 확인 |
