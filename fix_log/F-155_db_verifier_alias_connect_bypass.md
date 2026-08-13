# F-155 · DB 검증기의 별칭 연결 우회

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:141` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3과 아키텍처 §4.4는 모든 연결을 `backend/db.py` 팩토리에서 만들고 연결마다 `foreign_keys=ON`을 요구한다.

## 현상

AST가 수신자 이름 `sqlite3`만 찾는다. 임시 복제본에 `import sqlite3 as sql; sql.connect(':memory:')`를 추가해도 11/11 통과했다. 이 연결은 FK가 기본 OFF다.

## 영향

팩토리 우회 한 곳에서 참조 무결성이 무너지지만 신설 검증기는 거짓 통과한다.

## 재현

```python
import sqlite3 as sql
def unsafe_connect(): return sql.connect(':memory:')
```

위 파일을 `backend/`에 둔 임시 복제본에서 `db_live_verify.py`는 exit 0, 11/11이었다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 보고된 재현 그대로 `backend/`에 `import sqlite3 as sql; sql.connect(':memory:')` 파일을 넣고 `tools/db_live_verify.py`를 실행 — 11/11 거짓 통과 확인 |
| 2026-08-10 | 수정완료 | `_find_sqlite_connect_bypasses()` 신설(`tools/layer_verify.py`의 F-109 별칭 해석 원칙과 동일) — 파일마다 `sqlite3` 모듈을 가리키는 로컬 바인딩(모듈 별칭)과 `sqlite3.connect` 함수 자체를 가리키는 바인딩(`from sqlite3 import connect as X`)을 먼저 모은 뒤 그 이름들로의 호출을 우회로 판정 |
| 2026-08-10 | 회귀테스트 | `tools/tests/test_db_live_verify.py` 신설(5종) — 모듈 별칭·함수 별칭·기존 리터럴 형태가 전부 잡히는지, `db.py` 자신은 제외되는지, 정상 파일은 오탐 없는지 확인. 실제 `project_code/backend/`에 결함을 재주입해 FAIL(10/11)로 정확히 잡히고 제거 후 11/11로 복원됨을 확인 |
