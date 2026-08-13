# F-182 · 동적 설정형 데이터 변경이 변경이력에 기록되지 않음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_code/backend/repository.py:56` · `project_code/backend/repository.py:85` · 아키텍처 §4.4-a |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

1369-P1 6.2.1 — 설정형 데이터는 데이터의 변경(생성, 수정, 삭제)에 대해 이력이 관리되어야 한다.

## 현상

`REQ_SET_CONNECTION`은 `device_info`와 `device_install_info`를 생성하고 재연결 때 후자를 갱신한다. 그러나 `repository.py`에는 `config_change_log` INSERT가 없다. 아키텍처 §4.4-a도 이 테이블을 시드 기록으로만 배정한다. 시드 이력 2건은 정상 등록 뒤에도 2건, 재연결 UPDATE 뒤에도 2건이었다. 표준이 옳고 설계·구현이 틀렸다.

## 영향

Plug & Play 등록과 재연결의 설정 변경을 복원할 수 없다. subtype 재연결 뒤에는 과거 측정이 어떤 설정에서 생성됐는지도 잃는다.

## 재현

```python
con = db.init_db('case.db', seed=True)
before = con.execute('SELECT COUNT(*) FROM config_change_log').fetchone()[0]
_connect_sensor(con); after_create = con.execute('SELECT COUNT(*) FROM config_change_log').fetchone()[0]
_connect_sensor(con); after_update = con.execute('SELECT COUNT(*) FROM config_change_log').fetchone()[0]
assert (before, after_create, after_update) == (2, 2, 2)
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | **판정(§11.3): 표준이 옳고 설계·구현이 틀렸다.** 아키텍처 설계서 §4.4-a가 `config_change_log`를 "시드 로더 전용·런타임 쓰기 금지"로 분류했고(F-176이 `device_manage`에서 이미 밟은 것과 같은 오분류 패턴), `repository.py`에는 이 테이블에 대한 INSERT 함수 자체가 없었다. 재현 그대로 확인 — seed 뒤 정상 REQ_SET_CONNECTION 1건 처리해도 `config_change_log`는 시드 2건 그대로였다 |
| 2026-08-11 | 수정완료 | ① `backend/repository.py`에 `record_config_change()` 신설 — `changes`를 JSON으로 직렬화해 저장, `user_id`는 nullable(이 경로는 사람이 아니라 노드가 유발한 변경이라 항상 None). ② 그 값을 실제로 만드는 두 함수가 CREATE/UPDATE 시점에 직접 호출하도록 결선: `get_or_create_device_info()`는 새 행을 만들 때만(재사용은 변경이 아니므로 이력 없음), `upsert_device_install_info()`는 INSERT 분기·UPDATE 분기 각각에서. `ingest.py`는 이 두 함수를 그대로 부를 뿐이라 수정이 필요 없었다(변경 지점이 이미 그 함수들 안에 있었다). ③ 아키텍처 설계서 §4.4-a — `config_change_log`를 ①(시드 전용, 8개→**7개**)에서 ②(SIAP I/O 스레드, 20개→**21개**)로 이동, `8+20+2+1=31` → `7+21+2+1=31`로 갱신, F-182 설명 각주 추가. ④ `fixtures/seed.sql` 머리말 주석 갱신 |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_repository.py`에 3건 신설(`get_or_create_device_info`의 CREATE 전용 이력·재사용 시 미증가, `upsert_device_install_info`의 CREATE+UPDATE 이력, `record_config_change`의 JSON 직렬화·version 기본값). `backend/tests/test_ingest.py`에 2건 신설(`_handle_connection` 최초 등록 뒤 CREATE 2건, 재연결 뒤 UPDATE 1건). `changed_at`이 초 단위라 같은 초 안의 여러 INSERT가 값이 같을 수 있어(F-184로 이 컬럼에 형식 CHECK가 걸린 뒤에도 유일성과는 무관한 기존 성질), "가장 최근 행"을 보는 assertion은 `ORDER BY changed_at DESC`가 아니라 `ORDER BY rowid DESC`로 고정했다(결함 주입 없이도 실제 실행에서 순서가 갈리는 것을 발견해 즉시 정정). `cd project_code && python -m pytest backend/tests/` **182/182** 재확인 |
