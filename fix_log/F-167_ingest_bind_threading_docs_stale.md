# F-167 · ingest 콜백 결선 문서의 스레드 안전성 불일치

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_code/run.py:11` · `project_code/siap/link.py:13` · 아키텍처 설계서 §3.1/§4.2 · Frame 구조 명세서 §5.1 |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3과 아키텍처 설계서 §4.1 — DB 연결은 스레드별로 만들며 `check_same_thread=False`를 금지한다. F-160 실제 구현도 이 제약 때문에 I/O 스레드 안에서 지연 연결하는 `run.py::_make_on_frame()`을 사용한다.

## 현상

F-163 문서 정정 후에도 `run.py` 머리말, `siap/link.py` 머리말, 아키텍처 §3.1·§4.2, Frame 구조 명세서 §5.1은 실제 진입점이 `on_frame=backend.ingest.bind(conn)`으로 결선된다고 서술한다. 실제 세 모드는 모두 `_make_on_frame(db_path)`을 넘기며 `bind(conn)`을 쓰지 않는다. 메인 스레드에서 연 연결을 문서대로 `bind()`해 I/O 스레드에서 호출하면 즉시 `sqlite3.ProgrammingError`가 난다.

## 영향

설계 문서가 F-160 수정 과정에서 이미 반증된 교차 스레드 연결 방식을 다시 정본처럼 지시한다. 후속 단계가 문서를 따르면 실제 진입점이 첫 프레임에서 실패한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 네 대상을 직접 grep — `run.py` 머리말·`siap/link.py` 머리말·아키텍처 설계서 §3.1/§3.1-b/§4.2·Frame 구조 명세서 §5.1 전부가 `on_frame=backend.ingest.bind(conn)`로 결선된다고 서술함을 확인. 실제 세 모드는 `_make_on_frame(db_path)`을 쓰고 `bind()`는 호출되지 않는다. 문서대로 `bind(conn)`을 메인 스레드에서 연 연결로 재현하면 F-160이 이미 실측한 `sqlite3.ProgrammingError`가 그대로 재현됨을 재확인 |
| 2026-08-10 | 수정완료 | `run.py` 머리말에 F-167 문단 신설(`bind(conn)`을 직접 쓰지 않는 이유). `siap/link.py` 머리말의 "`link.start(..., on_frame=backend.ingest.bind(conn))`" 서술을 "`run.py`(단계 5, F-160)가 `_make_on_frame(db_path)`로 연결한다"로 정정하고 스레드 제약 문단 추가. `backend/ingest.py` 머리말에도 `bind()`가 테스트 전용이고 `run.py`는 쓰지 않는다는 문단 추가. 아키텍처 설계서 §3.1(F-154 문단)·`_dispatch()` 의사코드 독스트링·"`_dispatch()`를 먼저 부른다" 문단·§4.2 표 4곳, Frame 구조 명세서 §5.1 1곳을 모두 `run.py::_make_on_frame(db_path)` 기준으로 재작성 |
| 2026-08-10 | 확산 반영 | Frame 구조 명세서 분량 증가로 `개발_착수_지시서.md`의 해당 인용은 이미 F-163 처리 시 갱신해 둔 범위 안에 들었다(재확인, 재갱신 불필요) |
| 2026-08-10 | 회귀테스트 | 문서·주석 정정이라 코드 동작은 바뀌지 않았다 — `pytest siap/tests/ backend/tests/` **253/253**(불변) · `python contracts/test_contract.py` **62/62**(불변)로 확인. `grep -rn "bind(conn)"` 로 남은 다섯 지점이 전부 "직접 쓰지 않는다"는 정정된 문맥인지 육안 재확인 |
