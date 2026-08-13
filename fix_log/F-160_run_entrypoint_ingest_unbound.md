# F-160 · 실제 진입점의 ingest 콜백 미결속

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/run.py:89` · `project_code/run.py:139` · `project_code/run.py:177` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

0943 6.2.2 — *ACK 메시지는 온실통합제어기로부터 알림 메시지를 정상적으로 수신했을 경우 이에 대한 응답메시지로서 노드로 전송*한다. 8.2.1.1은 `NOTI_ERROR`가 오류 정보를 온실통합제어기로 알리는 기능이라고 규정한다. CLAUDE.md §3.5는 정상 NEC의 alert 저장과 ACK 회신을 함께 요구한다.

## 현상

F-154에서 `ingest.bind(conn)`은 생겼지만 `run.py`의 세 경로는 모두 `link.start(...)`에 `on_frame`을 넘기지 않는다. 실제 실행은 ACK만 만들고 DB 저장은 호출하지 않는다.

## 영향

정상 NEC가 격리되지는 않아도 실제 실행 경로에서 alert가 사라진다. F-060·F-154의 alert 저장 + ACK 회신 주장이 성립하지 않는다.

## 재현

```text
정상 NOTI_ERROR를 _dispatch()에 입력:
on_frame 미설정(run.py와 동일): reply=ACK, alert COUNT=0
on_frame=ingest.bind(conn):      reply=ACK, alert COUNT=1
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | `run.py`의 세 실행 경로(`_run_simulate`/`_run_replay`/`_run_hardware`)를 직접 읽어 확인 — 셋 다 `link.start(...)`에 `on_frame`을 넘기지 않았다. 재현 그대로 `python run.py --mode replay`를 실제로 실행해 확인 — `frame_log`·`alert` 등 어떤 테이블에도 행이 생기지 않았다(DB 파일 자체가 없었다) |
| 2026-08-10 | 수정완료 | 아키텍처 설계서 §9.2 "2. DB 준비"를 채운다: `_prepare_db_path()`(파일 없으면 `init_db`, 있으면 그대로 연다) + `_make_on_frame(db_path)`를 세 실행 경로 모두에 연결. **스레드 버그 발견·수정**: 처음에는 메인 스레드에서 연 연결을 그대로 `bind()`에 넘겼는데, 실제로 `run.py --mode replay`를 돌려보니 SIAP I/O 스레드(`link._io_loop`, 별도 스레드) 안에서 그 연결을 쓰다 `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`로 죽었다(아키텍처 설계서 §4.1 "스레드별 연결" 위반) — `_make_on_frame()`이 첫 호출 시점에 **그 스레드 안에서** 지연 연결하도록 다시 설계해 해소. `backend/ingest.py::bind()`에도 이 스레드 제약을 문서화 |
| 2026-08-10 | 확산 반영 | `.gitignore`에 런타임 DB 파일(`project_code/backend/runtime.db*`) 제외 추가 |
| 2026-08-10 | 회귀테스트 | `backend/tests/test_run_entrypoint.py` 신설 — `_prepare_db_path()`가 스키마+시드를 실제로 적용하는지, 재실행 시 재시드하지 않는지, 그리고 핵심으로 `_make_on_frame()`의 콜백을 실제 별도 스레드에서 호출해도(재현 조건과 동일) 죽지 않고 DB에 반영되는지 확인(`test_on_frame_callback_survives_cross_thread_invocation_f160`). `pytest siap/tests/ backend/tests/` **251/251**(신규 4건). `python run.py --mode replay --db backend/runtime.db` 실제 실행 재확인 — `frame_log` 6행, `alert` 2행 기록됨 |
