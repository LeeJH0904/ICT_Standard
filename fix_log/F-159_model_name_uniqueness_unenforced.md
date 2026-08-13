# F-159 · model_name 유일성 미강제

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | DB 설계서 §8 · `backend/schema.sql:56` · `repository.py:56` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

1369-P1 7.2.2.4는 모델명이 모든 스마트 온실 서비스에서 장치를 고유하게 식별한다고 한다.

## 현상

`model_name`은 `TEXT NOT NULL`일 뿐 `UNIQUE`가 아니다. 같은 `MODEL-X`로 ID가 다른 두 행을 실제 INSERT하자 모두 커밋됐다.

## 영향

repository의 전역 식별·재사용 전제와 DDL 정본이 갈린다.

## 재현

`device_info`에 같은 `model_name`인 두 행을 INSERT하면 COUNT가 2다. DB 검증 98/98은 통과한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 표준 원문(`TTAK.KO-10.1369-Part1.md` 7.2.2.4) 직접 대조 — "모델명은... 모든 스마트 온실 서비스에서 장치를 고유하게 식별하며, 공용으로 사용되는 속성값을 가진다"를 확인. `schema.sql`의 `device_info.model_name`이 `TEXT NOT NULL`뿐이고 `UNIQUE`가 없음을 확인. 보고된 재현대로 같은 `model_name`, 다른 `id`인 두 행을 실제 INSERT해 둘 다 커밋됨을 확인 |
| 2026-08-10 | 수정완료 | `device_info.model_name`에 `UNIQUE` 추가. `project_docs/db/schema.sql` → `project_code/backend/schema.sql` 동기(F-153 절차) → `DB_스키마_설계서.md` §8 DDL 블록 동기(바이트 대조로 확인). `repository.py::get_or_create_device_info()`는 이미 SELECT-후-INSERT로 중복을 스스로 피하고 있었으므로 코드 변경은 불필요 — 그 전제가 DDL로 뒷받침되지 않았던 것이 이 결함의 본질이었다 |
| 2026-08-10 | 확산 반영 | `project_docs/db/verify.py`에 "device_info.model_name 전역 유일성 (중복 차단)" 케이스 신설(99→**100**, F-158과 합쳐 98→100). `backend/tests/test_schema_conformance.py`에 동일 이식 |
| 2026-08-10 | 회귀테스트 | `project_docs/db/verify.py` **100/100**, `pytest backend/tests/` **136/136**(`test_get_or_create_device_info_reuses_by_model_name`이 이미 이 불변식을 앱 계층에서 확인 중이었고, 이번엔 DDL 자체가 뒷받침함) |
