# F-132 · ACK가 연결 Request pending을 잘못 해제

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/node_state.c:626-633` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

0943 7.2.2 — 메시지 제어 필드는 Request-Response, Notify-ACK를 결정하는 `Message Type`과 Response, ACK 매칭을 위한 `Message Identifier`를 포함한다. msg_id만 같다고 Request의 응답이 ACK로 바뀌지 않는다.

CLAUDE.md §3.5와 펌웨어 설계서 §6.4 — 응답 매칭 조건은 `Node ID` + `Message Identifier` + `Message Type` 세 개다.

## 현상

`_on_end()`의 `SIAP_ACK` 분기는 pending이 비어 있지 않고 `msg_id`가 같기만 하면 `_pending_clear()`를 호출한다. pending 종류에 대한 `expected_reply(kind)` 검사가 없다.

`CONNECTING`에서 `REQ_SET_CONNECTION` 응답을 기다릴 때 같은 msg_id의 ACK를 주입하자 pending이 해제됐다. 상태는 `CONNECTING`에 남지만 재전송할 pending이 없어 이후 Timeout에도 연결 요청을 다시 보내지 않는다.

## 영향

지연·중복 ACK 또는 msg_id 충돌 하나로 노드가 연결 승인 전 상태에서 영구 정지한다. F-046에서 확정한 3조건 응답 매칭이 C 상태 머신 구현에서 회귀했다.

## 재현

```text
BOOT -> CONNECTING, pending=REQ_SET_CONNECTION, msg_id=1
GCG/Node ID와 msg_id=1인 ACK 주입
기대: pending=REQ_SET_CONNECTION 유지
실제: pending=NONE -> 주입 테스트 FAIL (기존 61개는 모두 PASS)
```

## 제안

ACK 처리 전에 현재 pending의 기대 응답이 ACK인지 확인하고, Request는 대응 `RES_*`만 해제하도록 계약을 강제한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `_on_end()`의 `SIAP_ACK` 분기가 `pending.kind != NONE && rx_hdr.msg_id == pending.msg_id`만 보고 `_pending_clear()`를 호출함을 소스에서 확인 — pending 의 종류(`REQ_SET_CONNECTION`은 ACK 가 아니라 `RES_SET_CONNECTION`을 기대해야 함)를 전혀 안 본다 |
| 2026-08-09 | 수정완료 | F-046 이 정한 3조건(Node ID + Message Identifier + **Message Type**) 중 세 번째를 강제하도록 재작성 — ACK 를 기대하는 pending 종류를 Notify 4종(`NOTI_KEEP_ALIVE`·`NOTI_REBOOT`·`NOTI_ERROR`·`NOTI_DEVICE_VALUE`)으로 명시하고, pending 이 그 중 하나가 아니면(`REQ_SET_CONNECTION` 포함) msg_id 가 같아도 무시한다. 회귀 테스트 `test_ack_does_not_clear_connection_request_pending_F132()` 신설 — 같은 msg_id 의 ACK 주입 후 pending 이 `REQ_SET_CONNECTION` 으로 유지되고 상태도 `CONNECTING` 그대로임을 확인, 이어서 정상 Timeout 재전송 경로도 살아있는지 확인. 결함 주입: 원래 코드(종류 검사 없이 msg_id 만 비교)로 되돌린 사전수정본을 빌드·실행 — 신설 검사 2건이 정확히 실패(87/89)함을 확인, 원복 후 재통과. `test_bitpack`·`test_siap_frame`·`test_status_codes`·`test_golden`·`core_purity_verify.py`·`firmware_verify.py`·`run_all.py` 회귀 전량 통과 확인 |
