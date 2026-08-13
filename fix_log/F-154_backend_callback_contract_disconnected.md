# F-154 · backend 콜백 계약 단절

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/run.py:11` · `project_code/siap/link.py:217` · `project_code/backend/ingest.py:60` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

0943 8.2.1.1은 정상 Notify에 대한 ACK를 요구하고, CLAUDE.md §3.5는 정상 NEC의 alert 저장과 ACK 회신을 함께 요구한다.

## 현상

`_dispatch()`는 콜백을 인자 하나로 호출하지만 `ingest.handle`은 `(frame, conn) -> None`이다.

## 영향

F-060 수정이 실제 실행 경로에서 성립하지 않는다.

## 재현

`link._dispatch(valid_NOTI_ERROR)`는 `TypeError: handle() missing conn`으로 끝난다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | `siap/link.py::_dispatch()`를 직접 읽어 재현 — `on_frame`이 설정되면 `_default_reply()`를 완전히 대신했다(`self._on_frame(frame)`을 그대로 반환). `backend/ingest.handle(frame, conn)`을 그 자리에 꽂으면 인자 부족으로 TypeError, 설령 시그니처를 맞춰도 회신 Frame을 만들지 않아 등록·ACK가 전부 사라짐을 확인 |
| 2026-08-10 | 수정완료 | 기존 `siap/tests/test_link.py::test_on_frame_success_still_registers_f137`(F-137)을 재검토한 결과, "`on_frame`이 스스로 완결된 회신을 만든다"는 전제 자체가 `backend/ingest.py`의 실제 범위(DB 스키마 설계서 §7 — 순수 DB 반영, 회신 없음)와 CLAUDE.md §3.4("표준 해석은 프로토콜 계층에만")를 어기고 있었다. `_dispatch()`를 "회신은 항상 `_default_reply()`가 만들고, `on_frame`은 부수효과로 추가 호출될 뿐(반환값 무시)"으로 변경 — `backend/`가 `siap/build.py` 없이도 동작하게 됐다. `backend/ingest.py`에 `bind(conn) -> Callable[[Frame], None]` 어댑터를 추가해 `link.start(..., on_frame=backend.ingest.bind(conn))`로 연결할 수 있게 했다. `run.py` 독스트링의 잘못된 참조(`on_frame=backend.ingest.handle`)도 갱신 |
| 2026-08-10 | 회귀테스트 | `siap/tests/test_link.py::test_on_frame_is_side_effect_only_f154` 신설 — `on_frame`이 항상 `None`을 반환해도 노드가 정상 `RES_SET_CONNECTION`을 받고 `registry()`가 갱신되며 `on_frame`이 실제로 호출됨을 확인. 기존 F-137 테스트도 독스트링을 갱신해 새 계약을 명시하고 재통과 확인(276/276, siap 101종 포함). `backend/tests/test_ingest.py::test_bind_produces_single_arg_callable_that_persists` 신설 |
