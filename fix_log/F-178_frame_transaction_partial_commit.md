# F-178 · 프레임 처리 실패 뒤 부분 저장이 후속 commit으로 확정됨

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/ingest.py:75` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

아키텍처 설계서 §4.4 SQLite 사용 규칙 — “프레임 1건 = 트랜잭션 1건”, 이유는 “부분 반영 방지”다.

TTAK.KO-10.1369-Part1 6.1 — 설정형·측정형 데이터는 “상호 연관성을 가진 상태로 관리되어야 한다.”

## 현상

`handle()`은 성공 끝에서만 `conn.commit()`을 호출하고, 중간 예외를 rollback하는 경계가 없다. 두 요소 중 첫 환경 측정 저장 뒤 두 번째 저장에서 DB 오류를 주입하면 예외가 전파되지만 첫 요소의 INSERT는 열린 트랜잭션에 남는다. 호출자가 같은 연결을 나중에 commit하면 실패한 프레임의 일부가 영구 저장된다.

## 영향

설계가 보장한다고 한 프레임 단위 원자성이 성립하지 않는다. `env_state_data`·`env_measurement`·관계 테이블이 실패 프레임의 일부만 반영된 상태로 남을 수 있다.

## 재현

```text
TEMP와 HUMIDITY 두 요소를 등록
HUMIDITY env_measurement INSERT를 ABORT하는 임시 트리거 추가
두 요소 NOTI_DEVICE_VALUE를 ingest.handle()에 전달
FRAME_EXCEPTION=IntegrityError injected second-element failure
PARTIAL_VISIBLE_BEFORE_COMMIT=1
같은 연결에서 commit 후 재연결
PARTIAL_DURABLE_AFTER_LATER_COMMIT=1
```

## 제안

`handle()` 전체를 명시적 트랜잭션 경계로 감싸고 예외 시 rollback되는 결함 주입 회귀를 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — `handle()`이 성공 경로 끝에서만 `conn.commit()`을 부르고 예외 경로에는 어떤 rollback도 없어, 두 요소 중 두 번째에서 예외가 나면 첫 요소의 INSERT가 열린 트랜잭션에 그대로 남음을 확인. SQLite의 `RAISE(ABORT,...)`는 **현재 문장만** 되돌리고 트랜잭션은 계속 열어 두므로, 이 함수 자신이 명시적으로 rollback하지 않으면 아무도 정리하지 않는다는 것도 함께 확인 |
| 2026-08-11 | 수정완료 | `handle()` 전체(`insert_frame_log`부터 `conn.commit()`까지)를 `try/except Exception`으로 감싸 예외 시 `conn.rollback()`한 뒤 그대로 재전파(`raise`)하도록 고쳤다 — 호출자가 실패를 계속 알 수 있도록 예외를 삼키지 않는다(재전파 안 하면 `run.py`·`siap/link.py::_dispatch()`가 실패를 조용히 놓친다) |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_ingest.py::test_handle_frame_processing_failure_rolls_back_partial_writes` 신설 — 재현과 같은 방식(HUMIDITY INSERT를 막는 임시 `TEMP TRIGGER`)으로 두 요소 프레임 처리 실패 시 ①첫 요소(TEMPERATURE)의 INSERT ②이 프레임 자신의 `frame_log`가 모두 rollback되는지, ③이후 무관한 정상 프레임을 처리·commit해도 흔적이 살아나지 않는지 확인. `cd project_code && python -m pytest backend/tests/` **168/168** 재확인 |
