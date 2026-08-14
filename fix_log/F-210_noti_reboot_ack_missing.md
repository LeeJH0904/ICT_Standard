# F-210 · 수신 NOTI_REBOOT가 ACK 없이 폐기됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/firmware/core/node_state.c:L716-L768` · `project_code/firmware/tests/test_node_state.c:L483-L499` · F-071 |
| 발견일 | 2026-08-12 |
| 상태 | 수정완료 |

## 근거

0943 §6.1.2는 온실통합제어기가 노드에 보내는 알림으로 연결 해제와 리부팅을 함께 열거하고, “ACK 메시지는 노드가 알림 메시지를 정상적으로 수신했을 경우” 온실통합제어기로 보낸다고 정한다. 표 7-4는 `NOTI_REBOOT` 방향을 N→G와 G→N 모두 허용하고, §8.2.1.4도 목적에 따라 Notify와 ACK가 역방향으로 전송될 수 있다고 명시한다.

`project_docs/firmware/펌웨어_설계서.md` §6.2-a도 HALTED를 제외한 모든 상태에서 `NOTI_DISCONNECT`와 `NOTI_REBOOT`를 받으면 ACK한다고 판정했다. 이 내용은 F-071의 수정완료 근거이기도 하다.

## 현상

`node_state.c::_on_end()`의 수신 Notify 분기는 `SIAP_NOTI_DISCONNECT`만 처리한다. `SIAP_NOTI_REBOOT` case가 없어 정상 디코드 후 switch의 `default`에서 아무 회신 없이 끝난다.

기존 `test_node_state.c`도 수신 Notify를 `NOTI_DISCONNECT` 한 종류만 검사한다. 공식 테스트는 91/91이지만, 해당 프레임 종류만 `NOTI_REBOOT`로 바꾸고 ACK 뒤 상태는 RUNNING 유지로 판정한 독립 반례는 ACK 검사 1건이 실패해 90/91이었다.

## 영향

게이트웨이가 자기 리부팅을 노드에 알리는 표준 방향에서 노드는 유효한 알림을 받았는데도 ACK하지 않는다. 게이트웨이는 ACK를 기다리며 제한 횟수까지 재전송하고, F-071에서 닫았다고 기록한 양방향 Notify-ACK 생명주기가 실제 펌웨어에서는 성립하지 않는다.

## 재현

```text
1. project_code/firmware/tests/test_node_state.c를 임시 복제한다.
2. test_noti_disconnect_ack_then_reconnect_8_2_1_3()의 push_empty 종류만
   SIAP_NOTI_DISCONNECT에서 SIAP_NOTI_REBOOT로 바꾼다.
3. ACK의 msg_id==500을 기대하고, 상태 기대값은 RUNNING 유지로 바꾼다.
4. 현재 node_state.c와 함께 gcc로 빌드해 실행한다.

공식 원본: 91/91 통과
독립 반례: FAIL  6.1.2/8.2.1.4: NOTI_REBOOT 수신 -> 즉시 ACK 회신
             90/91 통과
```

## 제안

정상 수신 `NOTI_REBOOT`를 상태 게이트보다 앞서 ACK하는 분기를 구현하고, HALTED를 제외한 CONNECTING·RUNNING·FAULT·REBOOTING·DISCONNECTED 상태를 각각 회귀 테스트한다. `NOTI_DISCONNECT`의 DISCONNECTED 전이는 별도 동작으로 유지한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-13 | 확인 | 공식 `test_node_state`는 91/91·종료코드 0이었으나, 기존 수신 Notify 테스트의 종류를 `SIAP_NOTI_REBOOT`로 바꾸고 상태 유지 기대를 RUNNING으로 맞춘 독립 반례는 ACK 검사만 실패해 90/91·종료코드 1이었다. `_on_end()`에 `SIAP_NOTI_REBOOT` 수신 분기가 없어 설계서 §6.2-a와 불일치함을 재현했다. |
| 2026-08-13 | 수정완료 | `node_state.c::_on_end()`에 정상 수신 `SIAP_NOTI_REBOOT`의 즉시 ACK 분기를 추가했다. 이 알림은 게이트웨이 자신의 리부팅 통지이므로 노드 상태와 기존 송신 `pending`은 유지하고, 기존 HALTED 선행 가드로 무응답 예외를 보존했다. `test_node_state.c`에 CONNECTING·RUNNING·FAULT·REBOOTING·DISCONNECTED의 ACK wire code·`msg_id`·빈 payload와 상태 보존, HALTED 무응답을 고정했다. 수정 분기 제거 재주입은 다섯 ACK 검사가 실패해 98/103·종료코드 1, 복원 후 103/103이었다. `firmware_verify.py` 51/51, `core_purity_verify.py` 7/7, `tools/run_all.py` 20/20을 통과했다. |
