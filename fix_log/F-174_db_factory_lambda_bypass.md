# F-174 · lambda 연결 팩토리가 DB 검증기를 우회

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:150` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3 및 아키텍처 설계서 §4.4에 따라 모든 DB 연결은 `backend/db.py`에서 만들고 연결마다 `PRAGMA foreign_keys=ON`을 적용해야 한다.

개발 착수 지시서 §3.7은 `tools/db_live_verify.py`가 모든 연결에서 이를 검사하도록 요구한다.

## 현상

F-172 수정은 대입 별칭을 공유 해석하도록 고쳤지만, `_db_factory_functions()`는 여전히 모듈 최상위의 `ast.FunctionDef`만 연결 팩토리 후보로 수집한다.

`unsafe_connect = lambda db_path: sqlite3.connect(str(db_path))`처럼 팩토리를 lambda 대입으로 만들면 AST 안의 실제 연결 호출이 후보에서 빠진다. 다른 우회 검사는 `db.py` 자체를 제외하므로 전체 검증이 이 경로를 보지 않는다.

## 영향

FK가 꺼진 연결 팩토리를 `backend/db.py`에 추가한 잘못된 코드가 단계 5 신설 검증기 15/15를 통과한다. 그 연결을 쓰는 런타임 경로에서는 참조 무결성이 조용히 무효화된다.

## 재현

실제 `backend/db.py`의 임시 사본 끝에 아래 lambda를 추가하고 `db_live_verify.main()` 전체를 실행했다.

```python
unsafe_connect = lambda db_path: sqlite3.connect(str(db_path))
```

```text
LAMBDA_MUTANT_DETECTED_FUNCTIONS=['connect', 'init_db']
15/15 통과
FULL_VERIFIER_EXIT=0
UNSAFE_CONNECT_FK=0
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — `_db_factory_functions()`가 `tree.body`에서 `ast.FunctionDef`만 후보로 순회해, `unsafe_connect = lambda db_path: sqlite3.connect(str(db_path))`처럼 모듈 최상위 대입으로 만든 lambda 팩토리는 애초에 순회 대상에서 빠짐을 확인. F-172 리팩터로 별칭 해석(`_collect_sqlite_connect_aliases`)은 공유됐지만, "무엇을 함수 후보로 볼 것인가"(node 종류 판정)는 여전히 `ast.FunctionDef` 하나로 고정돼 있었다 |
| 2026-08-11 | 수정완료 | `_db_factory_functions()`에서 `tree.body`를 순회할 때 `ast.FunctionDef` 외에 `ast.Assign`/`ast.AnnAssign`의 값이 `ast.Lambda`인 경우도 같은 자격으로 검사하도록 확장 — 그 lambda 본문(`ast.walk`)에 `sqlite3.connect` 호출(별칭 포함)이 있으면 대입 대상 이름을 팩토리 함수 목록에 추가한다. `_function_sets_fk_pragma()`는 고치지 않았다 — 파이썬 lambda는 표현식 하나만 담을 수 있어 `con.execute("PRAGMA...")`처럼 별도 문장을 포함할 수 없으므로, 이 함수가 이런 이름에 대해 항상 `False`를 내는 기존 동작 자체가 이미 올바른 판정이었다(별도 분기 불필요) |
| 2026-08-11 | 결함 주입 재검증 | 재현과 동일한 `unsafe_connect = lambda db_path: sqlite3.connect(str(db_path))`를 담은 임시 `db.py`로 `_db_factory_functions`가 `['connect','unsafe_connect']`를 탐지하고 `_function_sets_fk_pragma(...,'unsafe_connect')`가 `False`로 판정함을 확인 |
| 2026-08-11 | 회귀테스트 | `tools/tests/test_db_live_verify.py::test_f174_lambda_connect_factory_in_db_py_is_detected` 신설(13→**14**). `python tools/db_live_verify.py` **15/15**(항목 수 불변), `python tools/tests/test_db_live_verify.py` **14/14**, `python -m pytest tools/tests/` **21/21**, `python tools/run_all.py` **15/15** 재확인 |
