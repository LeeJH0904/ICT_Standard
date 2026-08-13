# F-184 · 설치일자 외 시간 컬럼은 비 ISO 문자열을 허용

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/schema.sql:21` · `project_code/backend/schema.sql:113` · `project_docs/db/verify.py` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

1369-P1 6.1 — 시간을 다루는 일관된 형식의 표기가 지정되어야 한다. DB 설계서 §1-2~3은 표준 유래 무결성을 DDL로 강제하고 시간 형식을 ISO 8601(TEXT)로 결정한다.

## 현상

F-166은 `device_install_info.installed_at`에만 형식 CHECK를 추가했다. 설정형 엔티티의 `created_at`·`updated_at`, 측정시각, 변경시각 등은 `TEXT NOT NULL`뿐이다. `created_at='not-a-time'`, `updated_at='also-not-time'`인 사용자 행이 실행 DB에 삽입됐고 DB 검증 103/103도 통과했다. 설계가 옳고 DDL·검증기가 틀렸다.

## 영향

임의 시간 표기가 섞여 기간 검색·정렬·감사 이력의 의미가 깨질 수 있다.

## 재현

```python
con = db.init_db('case.db', seed=False)
con.execute('INSERT INTO user_info(id,created_at,updated_at,name) VALUES(?,?,?,?)',
            ('id', 'not-a-time', 'also-not-time', 'U'))
con.commit()  # IntegrityError 없음
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | **판정: 설계가 옳고 DDL·검증기가 틀렸다.** 설계서 §1-3 원칙 3("시간은 ISO 8601")과 표준 6.1은 특정 컬럼이 아니라 "시간을 다루는" 모든 표기에 적용된다. F-166은 이 최소 GLOB 형식 검사를 `installed_at` 하나에만 걸었다 — 재현 그대로 확인, `INSERT INTO user_info(...) VALUES(...,'not-a-time','also-not-time',...)`가 IntegrityError 없이 통과했다 |
| 2026-08-11 | 수정완료 | `backend/schema.sql`의 모든 시간(TEXT) 컬럼에 F-166과 동일한 최소 GLOB 검사(`GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'`)를 추가했다 — `farm_info`·`greenhouse_info`·`device_info`·`device_install_info`(created_at/updated_at, installed_at는 F-166 기존)·`user_info`(created_at/updated_at 및 nullable `deleted_at`)·`device_state_data.reported_at`·`env_state_data.measured_at`·`config_change_log.changed_at`·`public_data_source`(registered_at, nullable updated_at)·`public_data_record`(fetched_at, nullable period_from/period_to)·`control_model.created_at`·`control_rule`(created_at, nullable approved_at/rejected_at)·`control_execution`(issued_at, nullable responded_at)·`alert`(raised_at, nullable ack_at). nullable 컬럼은 `col IS NULL OR col GLOB '...'` 패턴(F-166이 아닌 곳에 새로 적용) — SQLite CHECK는 매크로를 못 써서 컬럼마다 반복해 적었다. `project_docs/db/schema.sql`은 하드링크가 Edit 도구의 원자적 쓰기로 끊어져 있었다(별개 파일로 갈라짐, 세션 시작 시점엔 아직 같은 inode였다) — `cp`로 재동기했다 |
| 2026-08-11 | 부수 정리 | 형식 검사를 넓히자 `project_docs/db/verify.py`·`backend/tests/test_schema_conformance.py`의 기존 6개 케이스가 FAIL로 돌아섰다 — 두 파일이 시간 컬럼 자리에 `'t'`/`'t2'` 같은 비-ISO 자리표시자를 광범위하게 썼기 때문(주로 `expect_fail=False`로 "허용돼야 한다"를 주장하는 케이스들: 승인된 규칙 기반 실행 허용·MANUAL 허용·명령 일치 허용·원자적 승인 UPDATE 허용·대상 일치 허용). 스크립트로 두 파일의 시간-컬럼 자리 `'t'`/`\'t\'` 리터럴 전부(파일당 27+8=35개소)를 유효 ISO 8601 값으로 치환 — 대체 전 정확히 6개 FAIL, 대체 후 0개 FAIL로 재확인. `expect_fail=True`(위반 기대) 케이스들은 이전에도 다른 사유로 IntegrityError가 나 우연히 PASS였다는 점은 이 라운드에서 정정하지 않았다(형식 검사 자체가 아니라 그 케이스들이 원래 의도한 위반을 계속 재현하는지는 별개 사안 — 별도 F-ID 대상) |
| 2026-08-11 | 회귀테스트 | 재현 그대로 고정 — `verify.py`·`test_schema_conformance.py` 양쪽에 5건씩 신설(사용자정보 생성시간/갱신시간 형식 위반 차단, 삭제시간(nullable) 형식 위반 차단·NULL 허용, 제어실행 issued_at 형식 위반 차단): 103→**108**. `test_schema_conformance.py`의 자기 케이스수 회귀 가드(`test_case_count_matches_design_doc_103`)도 108로 함께 갱신(F-185에서 109로 재갱신). `python project_docs/db/verify.py` **108/108**(F-185 반영 후 109/109) 재확인. `cd project_code && python -m pytest backend/tests/test_schema_conformance.py` 및 전체 `backend/tests/` 통과 재확인. `DB_스키마_설계서.md`의 §6·§8(전체 DDL 임베드)을 실제 schema.sql과 재동기 |
