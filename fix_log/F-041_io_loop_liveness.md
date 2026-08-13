# F-041 · I/O 루프의 송신 큐 기아와 응답 매칭 누락

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md:113-120,167-175`, `siap_iface.py:24-26` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

Frame 구조 명세서 §5 — `SiapLink.send()`는 Request를 보내고 대응 Response Frame을 반환한다.

아키텍처 §4.2 — API가 송신 큐에 넣고 I/O 스레드가 응답 시 `Event.set()`을 호출한다.

## 현상

의사코드는 블로킹 `for frame in codec.decode_stream(port)` 안에서 프레임을 한 건 받은 뒤에만 `_drain_request_queue()`를 호출한다. 수신 프레임이 없으면 API의 첫 송신 요청이 포트로 나가지 않는다. 또한 수신된 `RES_*`를 `control.py`가 소비한다고 서술하지만 루프에는 `Message Identifier` 매칭이나 대기 결과칸 저장, `Event.set()` 호출이 없다.

## 영향

무수신 상태에서 제어·조회 Request가 영구 대기할 수 있고, 전송되더라도 Response가 `link.send()` 호출자에게 돌아오지 않는다. 기능 3 제어 왕복과 재전송 계약이 성립하지 않는다.

## 제안

유한 read timeout/selector와 송신 큐를 같은 I/O 이벤트 루프에서 매회 처리하고, Response 매칭·Event 완료·재전송 타이머의 정확한 순서를 의사코드로 확정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 타당. `for frame in codec.decode_stream(port)` 는 무한 블로킹이므로 수신이 없으면 `_drain_request_queue()` 에 도달하지 못한다. Response 매칭·`Event.set()`·재전송 타이머도 의사코드에 없었다 |
| 2026-08-03 | 수정완료 | 아키텍처 §3.1-b 신설. read timeout 50ms 의 유한 루프에서 ①수신·②송신큐·③재전송 만료를 매 회 처리한다. `_match_pending()`(키 = Node ID + Message Identifier) · `_drain_request_queue()` · `_expire_pending()` 세 함수를 의사코드로 확정했다 |
| 2026-08-03 | 수정완료 | `ingest.handle()` 을 매칭보다 **먼저** 호출하도록 순서를 못박았다 — RES·ACK 도 `frame_log` 에 남아야 기능 2 가 성립한다. 재전송 시 msg_id 유지, `send()` 대기 상한 = Timeout×(Retry+1) 를 표 7-18 에서 유도해 표로 기록 |
