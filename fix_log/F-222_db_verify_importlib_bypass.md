# F-222 · DB 연결 검사가 importlib 동적 import를 놓침

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:42-207` |
| 발견일 | 2026-08-13 |
| 상태 | 신규 |

## 근거

`CLAUDE.md` §4.3 — “DB 연결은 반드시 `backend/db.py` 팩토리를 통해서만 생성한다”이며, 모든 연결에서 `PRAGMA foreign_keys=ON`을 켜야 한다.

## 현상

`db_live_verify.py`의 AST 별칭 수집기는 `import sqlite3`, `from sqlite3 import connect`, `getattr`, `__import__`, 대입 별칭과 lambda를 인식하지만 `importlib.import_module(sqlite3)`의 반환 모듈은 추적하지 않는다.

현재 backend는 이 우회를 쓰지 않아 직접 연결 검사 15/15가 통과한다. 그러나 아래 코드는 검사기의 동일 판정 함수에서 연결 호출 0건으로 분류되면서 실제 `sqlite3.Connection`을 만든다.

## 영향

향후 backend 파일에 팩토리 우회가 들어와도 출구가 성공한다. SQLite 기본값인 `foreign_keys=0` 연결을 통해 참조 무결성을 우회할 수 있다.

## 재현

```python
import importlib

def unsafe(path):
    return importlib.import_module(sqlite3).connect(path)
```

이 소스를 `ast.parse()`한 뒤 검증기의 `_collect_sqlite_connect_aliases()`와 `_is_sqlite_connect_call()`을 그대로 호출하고, 이어 실제로 실행했다.

```text
verifier_detected_connect_calls=[]
actual_connection_type=sqlite3.Connection
foreign_keys=0
```

## 제안

동적 import 호출을 공통 모듈 별칭 해석에 포함하고, 임시 backend 트리에 이 반례를 넣어 `_find_sqlite_connect_bypasses()` 전체 경로가 실패하는 회귀 테스트를 둔다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| | | |

