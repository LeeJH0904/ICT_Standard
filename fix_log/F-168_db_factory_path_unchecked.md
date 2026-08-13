# F-168 · DB 팩토리 파일 내부의 신규 연결 경로 미검사

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:70` · `project_code/backend/db.py` |
| 발견일 | 2026-08-10 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3 및 아키텍처 설계서 §4.4 — 모든 DB 연결은 `backend/db.py` 팩토리 경로로 만들고 각 연결에서 `PRAGMA foreign_keys=ON`을 적용해야 한다.

## 현상

`db_live_verify.py`의 직접 연결 정적 검사는 `db.py` 전체를 대상에서 제외한다. 런타임 검사는 이미 알려진 `init_db()`와 `connect()`만 호출하므로, 같은 파일에 외래 키를 켜지 않는 새 연결 함수를 추가해도 검사되지 않는다.

## 영향

호출 가능한 FK-OFF 연결 경로가 팩토리 파일에 존재해도 단계 5 검증기가 11/11로 거짓 통과한다. 그 경로를 쓰면 참조 무결성이 연결 단위로 무너진다.

## 재현

임시 `backend/db.py` 사본에 다음 함수를 추가하고 검증기의 `BACKEND_DIR`을 그 사본으로 바꿔 `main()` 전체를 실행했다.

```python
def unsafe_connect(db_path):
    return sqlite3.connect(str(db_path))
```

결과는 **11/11 통과, 종료 코드 0**이었다. 해당 함수를 import해 `unsafe_connect(:memory:)`로 만든 연결의 `PRAGMA foreign_keys` 실측값은 **0**이었다. 기존 검증기 단위 테스트도 **10/10 통과**했다.

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — 재현 코드와 동일한 `unsafe_connect(db_path)`를 임시 `db.py` 사본에 추가하고 `tools/db_live_verify.py`의 기존 ②(런타임)·③(정적) 검사를 그대로 돌리자 둘 다 통과(FK 미확인)함을 확인. 원인은 두 갈래: 런타임 검사가 `backend_db.init_db`/`backend_db.connect` 두 이름만 하드코딩해 호출했고, 정적 우회 스캔(`_find_sqlite_connect_bypasses`)은 `db.py`를 검사 대상에서 정당하게 제외하지만(파일 자체가 팩토리이므로) 그 파일 **안의 개별 함수**가 실제로 PRAGMA를 거는지는 아무도 보지 않았다 |
| 2026-08-11 | 수정완료 | `tools/db_live_verify.py`에 두 헬퍼 추가. ① `_db_factory_functions(db_py_path)` — `db.py` 최상위 함수 중 `sqlite3.connect(`를 직접 호출하는 함수 이름을 AST로 탐지(이름을 나열하지 않는다, F-094). ② `_function_sets_fk_pragma(db_py_path, func_name)` — 그 함수 **자기 본문 소스**(`ast.get_source_segment`)에 `foreign_keys = ON`이 있는지 정적으로 확인(파일 전체가 아니라 함수 단위 — db.py 안 다른 함수의 PRAGMA에 편승해 통과하는 것을 막는다). ③ `_probe_factory_function_runtime()` — 탐지된 함수를 `inspect.signature`로 `seed` 키워드 유무만 보고 실제 호출해 반환 연결의 `PRAGMA foreign_keys` 실측값을 확인(F-091류 — 파일을 읽는 것과 실행 결과를 보는 것은 다르다). `main()`에 새 섹션 ⑤로 편입해 `init_db`/`connect` 두 이름 하드코딩 호출을 대체 |
| 2026-08-11 | 결함 주입 재검증 | 수정된 헬퍼에 재현과 동일한 `unsafe_connect(db_path): return sqlite3.connect(str(db_path))`를 담은 임시 `db.py`를 넣어 `_db_factory_functions`가 `['connect','unsafe_connect']`를 탐지하고 `_function_sets_fk_pragma(...,'unsafe_connect')`가 `False`로 판정함을 확인 — 결함이 실제로 잡힌다 |
| 2026-08-11 | 회귀테스트 | `tools/tests/test_db_live_verify.py`에 `test_f168_new_connect_function_without_pragma_is_detected`·`test_f168_clean_db_py_all_functions_set_pragma` 추가(10→**12**). `python tools/db_live_verify.py` **15/15**(기존 11 + 신설 4: 함수 탐지 1·정적 함수단위 검사 1·`connect()`/`init_db()` 런타임 자동호출 2), `python tools/tests/test_db_live_verify.py` **12/12**, `python -m pytest tools/tests/` **19/19**, `python tools/run_all.py` **15/15**, `python fix_log/meta_verify.py` **97/97** 재확인 |
