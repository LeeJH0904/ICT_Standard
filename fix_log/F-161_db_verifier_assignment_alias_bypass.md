# F-161 · DB 검증기의 대입 별칭 연결 우회

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:41` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3과 아키텍처 설계서 §4.4 — DB 연결은 `backend/db.py` 팩토리에서만 만들고 연결마다 `PRAGMA foreign_keys=ON`을 요구한다.

## 현상

F-155 수정은 import 별칭만 추적한다. 모듈 별칭의 `connect`를 다른 변수에 대입하면 호출 대상의 기원을 더 이상 따라가지 않아 우회 연결을 놓친다.

## 영향

`foreign_keys=OFF`인 실제 연결이 backend에 있어도 신설 검증기가 11/11로 거짓 통과한다. 참조 무결성 단일 경로 주장의 회귀 가드가 닫히지 않았다.

## 재현

```python
import sqlite3 as sql
open_db = sql.connect
def unsafe_connect():
    return open_db(':memory:')
```

임시 backend 사본에 위 파일을 추가한 전체 `db_live_verify` 결과는 **11/11 통과**, 위 연결의 `PRAGMA foreign_keys` 실측값은 **0**이었다. 추가된 단위 테스트 5종도 모두 통과한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 재현 그대로 `open_db = sql.connect; open_db(':memory:')` 를 임시 `backend/` 사본에 주입해 `_find_sqlite_connect_bypasses()` 가 11/11 로 거짓 통과함을 확인 — `func_aliases` 가 import 별칭만 모으고 대입(`ast.Assign`) 은 전혀 보지 않았다 |
| 2026-08-10 | 수정완료 | 대입 우변이 (a) 이미 알려진 모듈 별칭의 `.connect` 속성이거나 (b) 이미 알려진 함수 별칭 자체인 단순 대입을 **고정점(fixed point)까지 반복 수집**하도록 `_find_sqlite_connect_bypasses()` 확장 — `a = b = sqlite3.connect` 다중 대입, `y = x`(별칭의 별칭) 전이적 대입까지 잡는다. 대입 사슬 길이를 미리 가정하지 않는다 |
| 2026-08-10 | 회귀테스트 | `tools/tests/test_db_live_verify.py` 에 F-161 케이스 3종 추가(단순 대입 별칭 / 대입 사슬 / from-import 별칭의 재대입) — 8/8 통과. `python tools/db_live_verify.py` 재확인 11/11(회귀 없음) |
