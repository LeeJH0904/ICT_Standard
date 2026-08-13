# F-181 · 동적 import 연결 팩토리를 놓쳐 FK-OFF 코드가 전체 검증 통과

| 항목 | 값 |
|---|---|
| 심각도 | 오류 |
| 분류 | 코드버그 |
| 대상 | `tools/db_live_verify.py:138` · `tools/db_live_verify.py:174` |
| 발견일 | 2026-08-11 |
| 상태 | 수정완료 |

## 근거

CLAUDE.md §4.3 — DB 연결은 `backend/db.py` 팩토리에서만 만들며 `foreign_keys=ON`을 연결마다 켠다.

## 현상

판정기는 `sqlite3.connect`, 별칭, `getattr`만 인식한다. `__import__('sqlite3').connect(...)`는 연결 함수 탐지와 우회 탐지 양쪽에서 빠진다. 임시 `db.py`에 이 FK-OFF 팩토리를 넣자 전체 15/15, 종료 코드 0이었고 실제 연결은 `PRAGMA foreign_keys=0`이었다.

## 영향

참조 무결성이 조용히 무너지는 새 연결 경로가 생겨도 단계 5 출구가 거짓 통과한다.

## 재현

```python
def unsafe(p):
    return __import__('sqlite3').connect(p)
con = unsafe(':memory:')
assert con.execute('PRAGMA foreign_keys').fetchone()[0] == 0
# 이 함수를 원본 db.py 사본에 넣고 임시 BACKEND_DIR로 v.main() 실행: 15/15, exit 0
```

---

## Claude 처리 기록

| 일시 | 상태 | 내용 |
|---|---|---|
| 2026-08-11 | 확인 | 재현 그대로 확인 — `module_aliases`는 `ast.Import`/`ast.ImportFrom`로 만든 **이름 바인딩**만 모은다. `__import__('sqlite3')`는 `sqlite3` 모듈을 이름에 전혀 묶지 않고 그 자리에서 바로 `.connect`에 접근하므로, `.connect` 속성 판정(`isinstance(fn.value, ast.Name) and fn.value.id in module_aliases`)이 요구하는 "이름"이 애초에 존재하지 않아 두 판정(우회 탐지·팩토리 탐지) 모두 걸리지 않음을 확인 |
| 2026-08-11 | 수정완료 | `_is_dunder_import_sqlite(node)` 헬퍼 신설 — `__import__('sqlite3')` 호출 표현식 자체를 인식한다. 세 자리에 반영했다: ① `_is_sqlite_connect_call`의 `.connect` 속성 판정(직접 호출 `__import__('sqlite3').connect(...)`), ② `_collect_sqlite_connect_aliases`의 대입 우변 판정(`opener = getattr(__import__('sqlite3'), 'connect')`, `_is_getattr_connect`의 첫 인자도 함께 확장), ③ 같은 함수의 **모듈 별칭** 판정 신설 — `x = __import__('sqlite3')`는 `import sqlite3 as x`와 같은 자격으로 `module_aliases`에 편입시켜야 `x.connect(...)`가 이후 잡힌다(이전에는 모듈 별칭이 오직 `ast.Import` 문에서만 생겼다). F-172·F-174·F-179와 같은 교훈(한 자리만 고치면 다음 라운드에 다른 형태로 재발) — 대입 별칭·직접 호출 두 형태 모두 확인 |
| 2026-08-11 | 결함 주입 재검증 | 재현과 동일한 세 형태(직접 호출·모듈 별칭 대입·getattr 결합)를 각각 별도 스니펫으로 만들어 `_is_sqlite_connect_call`이 실제로 탐지함을 확인(직접 실행 결과: 세 형태 모두 `True`) |
| 2026-08-11 | 회귀테스트 | `tools/tests/test_db_live_verify.py`에 4건 신설(17→**21**) — 직접 호출, 모듈 별칭 대입, getattr 결합, db.py 자신 안의 연결 함수 탐지 각 1건. `python tools/db_live_verify.py` **15/15**(항목 수 불변, 실제로 15/15 그대로 통과함을 재확인), `python tools/tests/test_db_live_verify.py` **21/21**, `python -m pytest tools/tests/` **28/28** 재확인 |
