# F-244 · 최종 제출본 DMS에 수집 데이터 수정·삭제 능력이 없다

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 문서불일치 |
| 대상 | 제출본 `README.md:17` · `project_code/backend/services/dms.py:38` · `project_code/backend/api.py:720` |
| 발견일 | 2026-08-18 |
| 상태 | 신규 |

## 근거

TTAK.KO-10.0937 6.2 — "수집된 데이터를 데이터베이스에 등록, 연결, 수정,
삭제할 수 있어야 한다."

## 현상

`dms.py`는 `public_data_source`를 시드 전용으로 두고 "등록 API는 후속 과제"라고
명시한다. 제출 API의 publicdata 경로는 sources와 records GET뿐이다. 수집 데이터의
등록·조회 흐름은 있지만 수정·삭제 진입점은 없다. 개발 대조표에는 6.2-3 `⚠ 부분`으로
기록되어 있으나 최종 제출본에는 그 범위 설명이 없다.

## 영향

현재 DMS는 수집·조회 참조 구현이며 6.2가 요구하는 데이터 생명주기 전체를 제공하지
않는다. 불변 감사 이력을 택한 설계 결정과 표준 준수 주장이 구분되지 않는다.

## 재현

```powershell
rg -n '@app\.(get|post|patch|put|delete).*publicdata' project_code/backend/api.py
# GET /sources, GET /records만 존재
```

## 제안

표준 능력을 구현하려면 감사 원본과 정정/논리 삭제 레이어를 분리한다. 구현하지 않을
경우 최종 README에 6.2-3 수정·삭제 제외를 명시한다.

---

## 작업자 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
|  |  |  |
