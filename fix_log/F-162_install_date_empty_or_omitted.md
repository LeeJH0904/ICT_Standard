# F-162 · 설치일자 빈 값과 API 생략 허용

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/schema.sql:81` · `project_docs/api/openapi.json:1422` · 검증기 2종 |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

1369-P1 6.2.5 — *장치설치정보에는 장치식별자, 장치이름, 설치온실, 설치일자, 설치위치 등이 포함되어야 한다.*

## 현상

F-158 수정은 `installed_at TEXT NOT NULL`만 추가해 빈 문자열을 설치일자로 허용한다. `openapi.json`의 Device properties에는 필드가 생겼지만 required에는 없어 응답이 설치일자를 통째로 생략해도 유효하다.

## 영향

컬럼 존재만 충족하고 실제 설치일자 보장은 없다. DB 검증 100/100과 API 검증 71/71이 이 반례를 모두 통과한다.

## 재현

```text
1. device_install_info.installed_at을 빈 문자열로 INSERT: 커밋 성공, 조회값도 빈 문자열.
2. Device JSON에서 installed_at을 생략: Draft202012Validator 오류 0건.
3. db/verify.py 100/100, api_verify.py 71/71 통과.
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 재현 그대로 확인 — `device_install_info` 에 `installed_at=''` INSERT가 커밋되고, `openapi.json` 의 Device 스키마에서 `installed_at` 이 `required` 에 없어 필드 생략도 유효로 판정됨을 확인. `repository.py::upsert_device_install_info()` 는 `installed_at or now`(빈 문자열이 falsy라 이미 `now` 로 대체됨) 라 애플리케이션 계층 경유로는 이미 빈 값이 저장될 수 없었지만, DDL·API 계약 자체는 그 전제를 보장하지 않고 있었다 |
| 2026-08-10 | 수정완료 | ① `device_install_info` 에 `CHECK (installed_at <> '')` 추가(`project_docs/db/schema.sql` → `backend/schema.sql` → `DB_스키마_설계서.md` §8, F-153 절차). ② `openapi.json` Device 스키마 — `installed_at` 을 `required` 에 추가하고 `minLength: 1` 부여 |
| 2026-08-10 | 확산 반영 | `project_docs/db/verify.py` 에 "장치설치 설치일자 빈 문자열 차단" 케이스 신설(100→**101**), `backend/tests/test_schema_conformance.py` 동일 이식. `api_verify.py` 의 반례 매트릭스에 Device 4건(정상/생략/빈문자열/null) 추가(43→**47**). 카운트 100→101 파급으로 `DB_스키마_설계서.md`(§0·§6.2 인용, §4.1 미규정 결정 각주 신설) · `개발_착수_지시서.md` · `0937_요구사항_대조표.md` 의 "100종" 인용을 101로 갱신(F-090/F-095 패턴) |
| 2026-08-10 | 회귀테스트 | `python project_docs/db/verify.py` **101/101**, `pytest backend/tests/` (내 `test_schema_conformance.py` 102개 함수 포함) 전량 통과, `python project_docs/api/api_verify.py` **71/71**(매트릭스 47종, 표준 구현 교차검증 일치), `python project_docs/dev/dev_verify.py` **76/76**, `python project_docs/services/services_verify.py` **42/42** |
