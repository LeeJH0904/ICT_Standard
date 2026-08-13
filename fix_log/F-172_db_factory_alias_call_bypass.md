# F-172 · DB 팩토리 내부 별칭 연결 함수가 검증기를 우회

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:117` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3 및 아키텍처 설계서 §4.4 — DB 연결은 `backend/db.py` 팩토리에서만 만들고 모든 연결에서 `PRAGMA foreign_keys=ON`을 적용해야 한다. F-168 수정은 팩토리 안의 연결 함수 전부를 이름 고정 없이 자동 탐지·실행한다고 주장한다.

## 현상

`_db_factory_functions()`는 함수 본문에서 정확히 `sqlite3.connect(...)` 형태로 직접 호출한 최상위 함수만 찾는다. `sqlite3.connect`를 모듈 변수에 대입한 뒤 그 별칭을 호출하는 함수는 탐지 목록에 들어가지 않는다. `_find_sqlite_connect_bypasses()`는 여전히 `db.py` 전체를 제외하므로 다른 검사도 이 경로를 보지 않는다.

## 영향

F-168과 같은 FK-OFF 연결 경로가 이름만 별칭으로 바뀌면 수정된 검증기 전체가 15/15로 거짓 통과한다. 해당 연결을 사용하는 런타임 경로에서는 참조 무결성이 꺼진다.

## 재현

임시 `backend/db.py` 사본에 다음 코드를 추가하고 그 사본을 로드해 `db_live_verify.main()` 전체를 실행했다.

```python
_open_without_fk = sqlite3.connect

def unsafe_connect(db_path):
    return _open_without_fk(str(db_path))
```

실측 결과:

```text
MUTANT_DETECTED_FUNCTIONS=['connect', 'init_db']
15/15 통과
FULL_VERIFIER_EXIT=0
UNSAFE_CONNECT_FK=0
```

즉 새 `unsafe_connect`는 탐지·런타임 호출 대상에서 모두 빠졌다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — F-168의 `_db_factory_functions`가 `isinstance(sub.func, ast.Attribute) and sub.func.attr=="connect" and sub.func.value.id=="sqlite3"` 리터럴 판정만 써서, `_open_without_fk = sqlite3.connect` 뒤 `_open_without_fk(...)`로 부르는 함수를 놓침을 확인. 흥미로운 점은 F-168 처리 당시 이미 `_find_sqlite_connect_bypasses`(F-155/F-161/F-165)에 같은 대입 별칭 해석 로직이 있었는데, `_db_factory_functions`를 새로 쓰면서 그걸 재사용하지 않고 리터럴 판정만 다시 만든 것이 원인 — 로직 두 벌을 따로 유지한 대가였다 |
| 2026-08-11 | 수정완료 | `_find_sqlite_connect_bypasses`의 별칭 해석부(모듈 별칭·함수 별칭 수집 + 대입 고정점 전파)를 `_collect_sqlite_connect_aliases(tree)` + `_is_sqlite_connect_call(node, module_aliases, func_aliases)` 두 공유 헬퍼로 뽑아냈다. `_find_sqlite_connect_bypasses`와 `_db_factory_functions` 양쪽이 이제 이 두 헬퍼만 쓴다 — 판정 로직이 하나뿐이라 한쪽만 고치고 다른 쪽을 잊는 사고(F-172의 원인)가 구조적으로 막힌다 |
| 2026-08-11 | 회귀테스트 | `tools/tests/test_db_live_verify.py::test_f172_alias_connect_function_in_db_py_is_detected` 신설(12→**13**) — 재현과 동일한 PoC로 `unsafe_connect`가 탐지되고 PRAGMA 없음도 잡히는지 확인. `python tools/db_live_verify.py` **15/15**(리팩터 후에도 항목 수 불변 — 판정 결과가 같다는 뜻), `python tools/tests/test_db_live_verify.py` **13/13**, `python -m pytest tools/tests/` **20/20**, `python tools/run_all.py` **15/15** 재확인 |
