# F-223 · 실행 결과 UPDATE 소유자 정정이 본문에 반영되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/arch/아키텍처_설계서.md:386` · `project_docs/arch/아키텍처_설계서.md:398` · F-186 |
| 발견일 | 2026-08-13 |
| 상태 | 수정완료 |

## 근거

아키텍처 §4.4-a 표 — `control_execution.result_rsc`·`responded_at` UPDATE는 API 스레드가 `SiapLink.send()`의 동기 반환 직후 수행한다고 F-186으로 정정했다.

`contracts/siap_iface.py::SiapLink.send()`는 Request에 대해 Response `Frame`을 호출자에게 반환하는 동기 계약이다.

## 현상

같은 절의 표는 API 스레드가 UPDATE한다고 올바르게 고쳤지만, 아래 요약 본문은 여전히 “I/O 스레드가 나중에 응답 필드만 UPDATE”한다고 적는다. 현재 `backend/services/fcs.py` 구현은 표와 계약대로 API 스레드가 UPDATE한다.

## 영향

F-186의 수정완료 상태와 문서 내부가 불일치한다. 후속 구현자가 요약 본문을 따르면 존재하지 않는 I/O 매칭 배선을 다시 만들거나, 현재 API 쓰기를 계층 위반으로 오판할 수 있다.

## 제안

§4.4-a 요약 문장을 표·동기 `send()` 계약·현재 구현과 일치시키고, 같은 절 안에서 소유자명이 서로 다른지 메타 검증한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-14 | 확인 | 아키텍처 §4.4-a 표는 API 스레드가 동기 `SiapLink.send()` 반환 직후 UPDATE한다고 적고 `backend/services/fcs.py::_send_and_finalize()`도 같은 호출 스레드에서 `result_rsc`·`responded_at`을 갱신한다. 같은 절 F-186 요약만 “I/O 스레드가 나중에 UPDATE”로 남은 내부 모순을 확인했다. |
| 2026-08-14 | 수정완료 | §4.4-a 요약을 API 스레드가 INSERT하고 같은 요청 안에서 동기 `send()` 반환 직후 UPDATE하는 실제 생애로 정정했다. 표·요약·`fcs.py`를 함께 대조하는 meta 검사를 추가했으며, 옛 I/O UPDATE 문구 재주입 시 FAIL을 확인했다. |
