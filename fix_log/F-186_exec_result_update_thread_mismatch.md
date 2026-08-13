# F-186 · control_execution 응답 필드 UPDATE 주체가 실제 SiapLink 계약과 어긋남

| 항목 | 값 |
|---|---|
| 심각도 | 위험 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md` §4.4-a④ · `project_code/contracts/siap_iface.py:30-32` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

아키텍처 설계서 §4.4-a④ — "`result_rsc`·`responded_at` UPDATE: **I/O 스레드** — 노드 응답이 도착해야 알 수 있다."

`contracts/siap_iface.py::SiapLink.send()` — "Request → Response Frame 반환 / Notify → None." (동기 반환 계약)

## 현상

단계 6(`backend/services/fcs.py::execute()`) 구현 중 발견. §4.4-a④는 응답 필드 UPDATE를 I/O 스레드가 "나중에" 수행한다고 서술하지만, 실제로 그 응답을 받는 것은 `link.send(frame, timeout)`을 호출한 **호출자 스레드**다 — `send()`는 큐에 넣고 `Event.wait()`할 뿐이며(`siap/link.py::send()`), 응답 `Frame | None`을 호출자에게 **동기 반환**한다. API 스레드가 `POST /rules/{id}/execute`·`POST /control` 처리 중 이 함수를 호출하므로, 응답을 실제로 손에 쥐는 것은 API 스레드다.

I/O 스레드가 이 UPDATE를 스스로 수행하려면 (a) 어느 `control_execution` 행인지 알 방법과 (b) `siap_msg_id`로 응답을 되짚어 매칭하는 배선이 필요한데, 이는 `siap/link.py`의 `on_frame`이나 `backend/ingest.py`의 `handle()` 어디에도 없다 — RES_SET_DEVICE_CONTROL은 `ingest.handle()`에서 "그 외 ... frame_log만으로 충분하다" 분기로 빠진다.

## 영향

문서대로 구현하면 존재하지 않는 배선(I/O 스레드의 사후 매칭·UPDATE)을 새로 만들어야 하며, 이는 단계 6 범위(`services/`·`api.py`)를 벗어나는 `siap/`·`ingest.py` 변경이다. 방치하면 구현자가 "I/O 스레드가 알아서 채운다"고 오인해 `POST /rules/{id}/execute`·`POST /control`의 `result_rsc`가 항상 `null`로 남는 버그로 이어진다.

## 재현

```python
# contracts/siap_iface.py 의 계약을 그대로 따르면:
resp = link.send(frame, timeout=2.0)   # 이미 여기서 Response Frame 을 동기로 쥔다
# → 이 시점에 이미 호출자(API 스레드)가 전부 알고 있다.
# I/O 스레드가 별도로 알아야 할 이유가 없고, 알 수단도 없다.
```

## 제안

`link.send()`가 응답을 동기 반환하므로, **API 스레드가 `send()` 반환 직후 자신이 이미 연 연결로 `result_rsc`·`responded_at`까지 UPDATE**한다. "스레드별 연결" 원칙(아키텍처 §4.4)을 오히려 더 단순하게 지키며(같은 스레드·같은 커넥션·같은 요청 처리 안에서 INSERT→send→UPDATE), 새 스레드 간 배선이 필요 없다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — `SiapLink.send()`는 `Frame \| None`을 호출자에게 동기 반환하고, I/O 스레드 쪽에는 이 응답을 별도로 매칭·UPDATE할 배선이 없다(`ingest.handle()`의 RES_* 분기는 `frame_log` 기록만 한다). 사용자에게 두 방안(① API 스레드로 확정 ② I/O 스레드 비동기 매칭 신규 구현)을 제시해 ①로 확인받았다(2026-08-11) |
| 2026-08-11 | 수정완료 | `backend/services/fcs.py::execute()`·`manual_control()`이 `link.send()` 반환 직후 같은 함수·같은 커넥션 안에서 `repository.update_execution_result()`를 호출하도록 구현. 아키텍처 설계서 §4.4-a④ 표의 서술을 이 결정에 맞춰 갱신(대상: API 스레드) |
