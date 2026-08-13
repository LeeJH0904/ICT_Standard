# F-138 · read 오류에서 send 대기 상한이 적용되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/siap/link.py:115` · `project_code/siap/link.py:157` |
| 발견일 | 2026-08-09 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §3.5 및 아키텍처 설계서 §3.1-b — “`send()` 대기 상한 = `Timeout × (Retry Count + 1)`.” F-041은 무수신 상태에서도 송신 큐와 재전송을 매 회 처리하도록 확정했다.

## 현상

`send()`는 제한 없는 `out.get()`으로 I/O 스레드의 pending 등록을 먼저 기다린 뒤에만 제한 시간 `Event.wait()`를 호출한다. `_io_loop()`는 `transport.read()`가 `OSError`를 던지면 `continue`하여 송신 큐 처리와 pending 만료를 모두 건너뛴다. 지속적인 링크 오류에서는 요청이 pending에 등록되지 않아 상한 계산 자체에 도달하지 않는다.

## 영향

링크가 끊긴 가장 필요한 상황에서 API 호출 스레드가 무한 대기한다. F-041의 송신 큐 생존성과 명시된 시간 상한이 구현에서 재발했다.

## 재현

```text
profile: Timeout=1, Retry=1 -> 상한 2초
Transport.read(): 매번 OSError
별도 스레드에서 link.send(REQ_GET_NODE_PROPERTY)
2.36초 뒤에도 스레드 alive, txq=1, pending=0
```

## 제안

read 오류여도 큐·만료 처리를 실행하고, pending 등록 전 대기까지 포함한 `send()` 전체 경로에 동일한 절대 마감시각을 적용한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-09 | 확인 | `send()`가 `out.get()`을 timeout 없이 호출함을 확인. `_io_loop()`의 `except OSError: continue`가 `_drain_txq()`·`_pending.expire()`를 모두 건너뜀을 확인 — read 오류가 지속되면 pending 등록 자체가 무한정 미뤄져 `out.get()`이 영원히 블로킹함을 재현 스크립트로 확인(항상 OSError를 던지는 가짜 Transport 주입 후 `timeout 10 python -m pytest`가 rc=124로 강제 종료됨을 실측 — 실제로 무한 대기함을 확인) |
| 2026-08-09 | 수정완료 | `send()`에 절대 마감시각(`deadline = now + upper`, `upper` = 지정 timeout 또는 `Timeout×(Retry+1)`) 도입 — `out.get(timeout=...)`과 `_pending.wait(timeout=...)` 양쪽에 남은 시간만 넘긴다. `_io_loop()`의 `except OSError`를 `continue` 대신 `chunk = b""`로 바꿔 그 회차의 ②(`_drain_txq`)·③(`_pending.expire`)이 read 오류와 무관하게 항상 돌게 했다. 회귀 테스트 추가: `test_link.py::test_send_bounded_even_when_read_always_errors_f138`(read()가 항상 OSError를 던지는 가짜 Transport를 직접 주입해 `send()`가 표 7-18 상한 안에 None으로 돌아오는지 확인). 결함 주입(옛 `send()`+`_io_loop()` 되돌림) 후 같은 재현 스크립트가 다시 rc=124(10초 타임아웃까지 무한 대기)로 무한 대기를 재현함을 확인하고 원복 — `pytest siap/tests/` 재통과 |
