# F-046 · 대기 요청과 Response 종류를 매칭하지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md:184-194,220-225` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

0943 §7.2.2 — "Response, ACK 메시지에 대한 매칭을 수행하기 위한 메시지 식별자"

0943 표 7-2·7-3은 Request와 Response를 같은 기능명 및 코드 `+0x0400`의 14쌍으로 정의한다.

## 현상

`_match_pending()`은 `(Node ID, Message Identifier)`가 같은지만 확인하고, 수신 종류가 원 요청의 `RESPONSE_OF[request.kind]`인지 검사하지 않는다. 또한 Request만 `_pending`에 저장하면서 ACK도 완료 신호로 허용한다. 그 결과 `REQ_GET_DEVICE_VALUE` 대기 중 동일 번호의 `RES_SET_REBOOT` 또는 ACK가 들어오면 정상 응답처럼 대기 항목을 `pop`하고 `Event.set()`한다.

## 영향

다른 요청의 지연·중복 Response나 우연히 같은 번호의 ACK가 현재 호출의 결과로 반환된다. 호출자는 잘못된 응답을 정상 왕복 결과로 받을 수 있으며 진짜 Response는 이후 미매칭 프레임으로 버려진다.

## 재현

```text
pending request = REQ_GET_DEVICE_VALUE, node=3, msg_id=7
incoming        = RES_SET_REBOOT,       node=3, msg_id=7

현재 조건: reply_kind(RES_SET_REBOOT) is None + 이름이 RES_ + 키 일치
결과: pending 제거 및 Event.set() — 대응 Response는 RES_GET_DEVICE_VALUE여야 함
```

## 제안

대기 항목에 기대 Response 종류를 저장하고 Node ID·Message Identifier·Message Type을 모두 확인한 뒤에만 제거한다. Request 대기 항목은 ACK로 완료하지 않는다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 타당. `_match_pending()` 은 `(Node ID, Message Identifier)` 만 보고 `pop` 한다. `REQ_GET_DEVICE_VALUE` 대기 중 같은 번호의 `RES_SET_REBOOT` 이나 ACK 가 들어오면 정상 응답으로 소비되고, 진짜 `RES_GET_DEVICE_VALUE` 는 미매칭으로 버려진다 |
| 2026-08-03 | 수정완료 | `contracts/frame.py` 에 `expected_reply(kind)` 신설 — `reply_kind()` 의 쌍이다. Request 14종 → 대응 `RES_*`, Notify → `ACK`, `RES_*`·`ACK` → `None`. 대기 항목은 송신 시점에 이 값을 `expect` 로 저장한다 |
| 2026-08-03 | 수정완료 | 매칭 조건을 `Node ID` + `Message Identifier` + **`Message Type`** 셋으로 확정했다. 기대와 다른 프레임은 대기 항목을 **소비하지 않고** 흘려보낸다 — 진짜 Response 가 아직 올 수 있으므로 `pop` 이 아니라 `get` 후 조건 확인이다. 타임아웃 판단은 `_expire_pending()` 단독 책임 |
| 2026-08-03 | 수정완료 | Request 대기가 ACK 로 완료되지 않음을 계약 테스트로 못박았다. 게이트웨이가 보내는 Notify(8.2.1.3·8.2.1.4 양방향)는 반대로 ACK 를 기대한다 — 두 경우를 `expected_reply()` 한 함수가 구분한다. 계약 테스트 7종 추가(46 → 53종) |
