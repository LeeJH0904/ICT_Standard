# F-179 · 동적 속성 연결이 DB 검증기를 우회함

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:42` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3 및 아키텍처 설계서 §4.4 — DB 연결은 `backend/db.py` 팩토리에서만 만들고 모든 연결에서 `PRAGMA foreign_keys=ON`을 적용해야 한다.

개발 착수 지시서 §3.7은 `tools/db_live_verify.py`가 모든 연결에서 이 조건을 검사하도록 요구한다.

## 현상

F-155·F-161·F-165·F-172·F-174 수정은 import·대입·타입주석·lambda 별칭을 추적하지만, `getattr(sqlite3, connect)`의 반환값은 `func_aliases`에 넣지 않는다. 임시 backend 사본에 이 직접 연결을 추가해도 전체 검증기는 15/15로 통과했다.

## 영향

실제 `PRAGMA foreign_keys=0`인 팩토리 우회 경로가 있어도 단계 5 출구가 거짓 통과한다. 해당 경로에서는 참조 무결성이 조용히 무너진다.

## 재현

```python
import sqlite3

def unsafe_connect(path):
    opener = getattr(sqlite3, connect)
    return opener(path)
```

```text
GETATTR_BYPASS_DETECTED=[]
GETATTR_BYPASS_FK=0
15/15 통과
FULL_DB_LIVE_VERIFY_EXIT=0
```

## 제안

동적 속성 조회를 포함한 연결 기원 추적을 한 곳에서 처리하고 이 반례를 전체 검증기 회귀로 고정한다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — 공유 헬퍼 `_collect_sqlite_connect_aliases`/`_is_sqlite_connect_call`이 `.connect` **속성 접근**(`ast.Attribute`)과 이름 별칭(`ast.Name`)만 인식하고, `getattr(sqlite3, "connect")`처럼 **문자열 리터럴로 같은 속성을 얻는 별개의 표현식**(`ast.Call`)은 두 판정 어디에도 걸리지 않음을 확인 — F-172·F-174 리팩터로 로직은 하나로 합쳤지만 인식하는 "형태"의 가짓수 자체가 부족했다 |
| 2026-08-11 | 수정완료 | `_is_getattr_connect(node, module_aliases)` 헬퍼 신설 — `getattr(<모듈 별칭>, "connect")` 형태를 판정한다. 이를 두 자리에 연결했다: ① `_collect_sqlite_connect_aliases`의 대입 우변 판정(`opener = getattr(sqlite3, "connect")` 같은 대입 별칭도 `func_aliases`에 들어가게), ② `_is_sqlite_connect_call`의 `node.func` 판정(`getattr(sqlite3, "connect")(...)` 처럼 대입 없이 바로 부르는 형태). 한 곳만 고치면 재발하므로(F-172의 교훈) 두 형태(대입 후 호출 / 직접 호출) 모두 확인 |
| 2026-08-11 | 결함 주입 재검증 | 재현과 동일한 두 형태(대입 별칭, 직접 호출)를 임시 파일에 넣어 `_db_factory_functions`가 실제로 탐지함을 확인 |
| 2026-08-11 | 회귀테스트 | `tools/tests/test_db_live_verify.py`에 3건 신설(14→**17**) — `_find_sqlite_connect_bypasses` 쪽 대입/직접호출 2건, `_db_factory_functions`(db.py 자신) 쪽 1건. `python tools/db_live_verify.py` **15/15**(항목 수 불변), `python tools/tests/test_db_live_verify.py` **17/17**, `python -m pytest tools/tests/` **24/24**, `python tools/run_all.py` **15/15** 재확인 |
