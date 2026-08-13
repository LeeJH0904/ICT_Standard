# F-024 · DB 검증기의 실행 위치 의존과 예외 오판

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `project_docs/db/verify.py:5-33` |
| 발견일 | 2026-08-03 |
| 상태 | 수정완료 |

## 근거

공고문 소스코드 제출 안내 — "제출물만으로 실제 실행(재현)이 가능한 전체 소스코드"

`CLAUDE.md` §4.1 — "파일 인코딩 UTF-8, 개행 LF" 및 검증 재현성 원칙

## 현상

`fresh()`가 `open("schema.sql")`을 현재 작업 폴더 기준으로 호출하므로 DB 폴더 밖에서 검증기를 실행하면 `FileNotFoundError`가 발생한다. 또한 `check()`는 차단 기대 테스트에서 예외 종류를 검사하지 않고 모든 `Exception`을 성공으로 판정한다. SQL 오타나 `NameError`도 무결성 제약이 작동한 것처럼 PASS가 될 수 있다.

## 영향

현재 56건은 실제 실행에서 모두 `IntegrityError`였지만, 향후 회귀 시 테스트 자체의 결함을 제약 통과로 오인할 수 있다. 검증 명령의 실행 위치도 암묵적이어서 제출 재현성이 낮아진다.

## 재현

```powershell
cd <저장소 루트>
python -B project_docs\db\verify.py
# FileNotFoundError: schema.sql
```

`check(..., lambda c,i: 1/0)`처럼 제약과 무관한 예외를 넣어도 `expect_fail=True`이면 PASS로 집계되는 구조다.

## 제안

`Path(__file__)` 기준으로 스키마를 읽고, 차단 기대 테스트는 `sqlite3.IntegrityError`만 성공으로 인정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-03 | 확인 | 저장소 루트에서 실행 시 `FileNotFoundError` 재현. `except Exception` 이 모든 예외를 차단 성공으로 집계함을 확인 |
| 2026-08-03 | 수정완료 | `HERE = Path(__file__).resolve().parent` 도입. `check()`가 **`sqlite3.IntegrityError` 만** 성공으로 인정하고, 그 외 예외는 `!! NameError: ...` 형태로 **FAIL** 처리하도록 변경. 의도적 `NameError` 주입으로 검출 동작 확인 |
| 2026-08-03 | 수정완료 | 부수 조치 — 시드와 테스트의 위치 기반 `INSERT`를 전부 명명 컬럼으로 전환. 스키마에 컬럼이 추가돼도 테스트가 깨지지 않는다 (F-032의 `crop` 추가에서 실제로 깨졌다) || | | |
