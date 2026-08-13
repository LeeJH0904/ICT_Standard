# F-165 · DB 검증기의 타입 주석 대입 별칭 우회

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:82` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3 및 아키텍처 설계서 §4.4 — DB 연결은 `backend/db.py` 팩토리에서만 만들고 모든 연결에서 `PRAGMA foreign_keys=ON`을 적용해야 한다.

## 현상

F-161 수정은 `ast.Assign`만 별칭 전파 대상으로 모은다. 같은 대입에 타입 주석을 붙인 `ast.AnnAssign`은 보지 않으므로 `open_db: object = sql.connect`를 통한 직접 연결을 놓친다.

## 영향

참조 무결성이 꺼진 실제 연결이 `backend/`에 있어도 단계 5 신설 검증기가 11/11로 거짓 통과한다. F-155·F-161이 보장하려던 DB 팩토리 단일 경로가 다시 우회된다.

## 재현

```python
import sqlite3 as sql
open_db: object = sql.connect

def unsafe_connect():
    return open_db(':memory:')
```

임시 `backend/` 사본에 위 파일을 추가하고 `db_live_verify.main()` 전체를 실행하면 **11/11 통과, 종료 코드 0**이다. `unsafe_connect()`가 만든 연결의 `PRAGMA foreign_keys` 실측값은 **0**이다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-10 | 확인 | 재현 그대로 `open_db: object = sql.connect` 를 임시 `backend/` 사본에 주입해 확인 — F-161이 고친 대입 별칭 추적이 `ast.Assign`만 순회해 타입 주석이 붙은 `ast.AnnAssign`(문법상 별개 노드)은 전혀 보지 않았다. 11/11 거짓 통과 재현 |
| 2026-08-10 | 수정완료 | `ast.Assign`(다중 대입, `targets` 리스트)과 `ast.AnnAssign`(단일 `target`, `value`가 `None`일 수 있음)을 각각의 구조 그대로 `(targets, value)` 쌍으로 정규화해 같은 고정점 루프에서 함께 판정하도록 `_find_sqlite_connect_bypasses()` 재작성 |
| 2026-08-10 | 회귀테스트 | `tools/tests/test_db_live_verify.py` 에 F-165 케이스 2종 추가(단순 주석 대입 / 주석 대입→일반 대입 사슬) — **10/10** 통과. `python tools/db_live_verify.py` 재확인 11/11(회귀 없음) |
