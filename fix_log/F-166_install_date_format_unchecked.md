# F-166 · 설치일자 형식 미검증

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_code/backend/schema.sql:83` · `project_docs/api/openapi.json:1447` · `project_docs/api/api_verify.py:78` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

1369-P1 6.1 — “시간 데이터는 연, 월, 일, 시, 분, 초 단위로 관리될 수 있어야 한다. 또한, 시간을 다루는 일관된 형식의 표기가 지정되어야 한다.” 6.2.5 — “장치설치정보에는 … 설치일자 … 등이 포함되어야 한다.” DB 스키마 설계서 §1-3과 API 명세서 §1은 그 형식을 ISO 8601로 결정했다.

## 현상

F-162 수정은 DB에서 빈 문자열만 막고 OpenAPI에 `format: date-time`을 적었지만 실제 검증기는 `format`을 평가하지 않는다. 따라서 `installed_at='not-a-date'`가 DB에 저장되고, 같은 값을 가진 Device 응답도 프로젝트 자체 평가기와 `Draft202012Validator` 기본 설정에서 유효하다. `FormatChecker`를 켰을 때만 거부된다.

## 영향

필드가 존재한다는 사실만 보장할 뿐 설치일자나 프로젝트가 결정한 ISO 8601 시간 표기를 보장하지 않는다. DB 101/101과 API 71/71이 잘못된 날짜 값을 모두 통과시킨다.

## 재현

```text
1. 임시 DB의 device_install_info.installed_at에 'not-a-date' INSERT: 커밋 성공.
2. Device.installed_at='not-a-date'를 Draft202012Validator로 검사: 오류 0건.
3. 동일 스키마에 FormatChecker를 지정해 검사: 오류 1건.
4. project_docs/db/verify.py 101/101, project_docs/api/api_verify.py 71/71 통과.
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 재현 그대로 확인 — `installed_at='not-a-date'` INSERT가 커밋되고, 자체 평가기(`js_valid`)와 기본 설정 `Draft202012Validator` 양쪽 모두 `format` 키워드를 검사하지 않아 유효로 판정됨을 확인. `FormatChecker`를 붙였을 때만 jsonschema가 거부한다는 재현도 실측 일치 — JSON Schema 표준 자체가 `format`을 기본 주석(annotation)으로만 다루는 사양임을 확인(버그가 아니라 사양이므로, 검증기가 이를 스스로 채워야 하는 문제) |
| 2026-08-10 | 수정완료 | ① `js_valid()`에 `format: date-time` 지원 추가(RFC 3339 정규식 `_DATE_TIME_RE`, jsonschema 구현을 보지 않고 표준 형식을 직접 옮겨 §7 교차검증의 독립성을 유지). ② §7 교차검증 호출부에 `jsonschema.FormatChecker()`를 명시로 붙여 표준 구현도 실제로 format을 보게 함(안 붙이면 양쪽 다 통과시켜 "일치"만 확인되고 버그가 숨는다). ③ DDL에 `CHECK(installed_at GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*')` 추가 — 최소 조건(YYYY-MM-DD 시작)만 강제하고 시각·오프셋 세부 형식은 API 계층(RFC 3339 전체 검사)에 맡긴다(SQLite에 정규식이 없어 과한 GLOB을 쓰면 그 자체가 새 표준 미규정 해석이 되기 때문) |
| 2026-08-10 | 확산 반영 | `project_docs/db/verify.py`에 형식 위반 차단·오프셋 표기 허용 2건 신설(101→**103**), `backend/tests/test_schema_conformance.py` 동일 이식. `api_verify.py` 매트릭스에 Device 2건 추가(47→**49**). 카운트 101→103 파급으로 `DB_스키마_설계서.md`(§0·§6.2)·`개발_착수_지시서.md`·`0937_요구사항_대조표.md`의 "101종" 인용 및 `DB_스키마_설계서.md` 자체 분량(개발_착수_지시서 인용 45,000→50,513자)을 갱신 |
| 2026-08-10 | 회귀테스트 | `python project_docs/db/verify.py` **103/103**, `pytest backend/tests/` (`test_schema_conformance.py` 104개 함수 포함) 전량 통과, `python project_docs/api/api_verify.py` **71/71**(매트릭스 49종, `FormatChecker` 포함 표준 구현 교차검증 일치), `python project_docs/dev/dev_verify.py` **76/76**, `python project_docs/services/services_verify.py` **42/42** |
