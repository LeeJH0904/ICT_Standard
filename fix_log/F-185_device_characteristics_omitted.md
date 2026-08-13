# F-185 · 필수 장치특성 저장 필드가 설계와 구현에 없음

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `project_docs/db/DB_스키마_설계서.md:407` · `project_code/backend/schema.sql:56` · `project_code/backend/models.py:84` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

1369-P1 6.2.4 — 장치정보에는 장치코드, 장치이름, 장치종류, 장치모델, 장치제조사, 장치특성 등이 포함되어야 한다.

## 현상

설계서·두 `schema.sql`의 `device_info`와 `models.DeviceInfo`는 식별자, 시간, 이름, 종류, 모델명, 제조사까지만 가진다. `PRAGMA table_info(device_info)`에도 장치특성을 저장할 컬럼이 없다. 7.2.2.4는 제조사 등의 속성이라고 열어 두므로 장치특성을 금지하지 않는다. 상위 요구사항 6.2.4가 포함을 명시하므로 표준이 옳고 설계·구현이 틀렸다.

## 영향

장치 교체·호환성 판단을 위해 표준이 요구한 특성을 보존할 수 없다.

## 재현

```python
con = db.init_db('case.db', seed=False)
cols = [r[1] for r in con.execute('PRAGMA table_info(device_info)')]
assert cols == ['id', 'created_at', 'updated_at', 'device_name',
                'device_kind', 'model_name', 'manufacturer']
assert 'device_characteristics' not in cols
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | **판정(§11.3): 표준이 옳고 설계·구현이 틀렸다.** 재현 그대로 확인 — `PRAGMA table_info(device_info)`에 장치특성을 저장할 컬럼이 없었다. 6.2.4는 "장치정보에는... 장치특성 등이 포함되어야 한다"로 포함을 명시하고, 7.2.2.4는 제조사 등의 속성을 열어 두므로 장치특성을 금지하지 않는다 — 상위 요구(6.2.4)가 우선한다 |
| 2026-08-11 | 수정완료 | `manufacturer`와 같은 자격(nullable TEXT, 자유 텍스트 — 1369-P1이 세부 구조를 규정하지 않는다)으로 `device_characteristics` 컬럼을 추가했다. ① `backend/schema.sql`(→ `project_docs/db/schema.sql` 재동기) — `device_info`에 컬럼 추가. ② `backend/models.py::DeviceInfo` — 필드·`from_row` 추가. ③ `backend/repository.py::get_or_create_device_info()` — `device_characteristics: str | None = None` 인자 추가, INSERT에 반영. 0943 REQ_SET_CONNECTION은 장치특성을 나르지 않으므로 `ingest.py`의 동적 등록 경로는 이 인자를 넘기지 않는다(`manufacturer`와 동일한 처리) — 컬럼이 nullable이라 기존 호출부는 전부 그대로 동작한다(하위호환) |
| 2026-08-11 | 회귀테스트 | `backend/tests/test_repository.py`에 2건 신설(값 저장·조회, 미지정 시 None 기본값). `project_docs/db/verify.py`·`backend/tests/test_schema_conformance.py`에 재현과 같은 컬럼 존재 검사 1건씩 신설(108→**109**, `test_case_count_matches_design_doc_108`→`_109`로 이름·수치 갱신). `python project_docs/db/verify.py` **109/109**, `cd project_code && python -m pytest backend/tests/` **185/185** 재확인. `DB_스키마_설계서.md` §6·§8(전체 DDL 임베드)을 schema.sql과 재동기(§8은 실제 파일 대조로 바이트 일치 확인) |
