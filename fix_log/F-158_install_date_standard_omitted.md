# F-158 · 장치 설치일자 누락

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | `backend/schema.sql:68` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

1369-P1 6.2.5는 장치설치정보에 설치일자가 포함되어야 한다고 요구한다.

## 현상

설계·구현·모델에 설치일자 컬럼이 없다.

## 영향

필수 설정형 데이터와 설치 이력을 잃는다.

## 재현

`PRAGMA table_info(device_install_info)`에 설치일자 컬럼이 없다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 표준 원문(`TTAK.KO-10.1369-Part1.md` 6.2.5) 직접 대조 — "장치설치정보에는 장치식별자, 장치이름, 설치온실, 설치일자, 설치위치 등이 포함되어야 한다"를 확인. `schema.sql`·`DB_스키마_설계서.md`·`models.py` 어디에도 설치일자 컬럼이 없음을 확인. "설치온실"은 관계 엔티티 `device_install`이 이미 표현하므로(§5 불일치 판정 #1과 같은 근거) 컬럼 누락 대상이 아니라고 판정 |
| 2026-08-10 | 수정완료 | `device_install_info`에 `installed_at TEXT NOT NULL` 추가(`device_name` 바로 뒤). `project_docs/db/schema.sql` → `project_code/backend/schema.sql` 동기(F-153 절차와 동일) → `DB_스키마_설계서.md` §8 DDL 블록 동기(바이트 대조로 확인). `models.py::DeviceInstallInfo`·`repository.py::upsert_device_install_info()`(재연결 UPDATE에서는 건드리지 않음 — `created_at`과 같은 부류) 갱신. `openapi.json`의 `Device` 스키마에도 `installed_at` 노출 추가(F-090 "테이블 컬럼 미노출 없음" 위반 해소) |
| 2026-08-10 | 확산 반영 | `project_docs/db/verify.py`에 "장치설치 설치일자 NOT NULL 차단" 케이스 신설(98→**100**, F-159와 함께). 이 김에 `device_install_info`의 raw 위치지정 INSERT 4곳을 컬럼명 명시로 교체(F-024 원칙 재적용 — 이번 결함과 같은 취약점 패턴). `backend/tests/test_schema_conformance.py`를 동일 내용으로 이식, 케이스 수 검사도 100으로 갱신. `개발_착수_지시서.md`·`0937_요구사항_대조표.md`의 "98종" 인용 2곳을 100으로 갱신(당시 수치 시점 표기 포함) |
| 2026-08-10 | 회귀테스트 | `pytest backend/tests/` **136/136**, `project_docs/db/verify.py` **100/100**, `python tools/db_live_verify.py` 11/11(테이블 수 불변, 컬럼 추가는 이 검증기 범위 밖), `python project_docs/api/api_verify.py` 71/71 재확인 |
