"""F-155 회귀 테스트 — tools/db_live_verify.py 의 sqlite3.connect() 우회 탐지가
별칭 import 를 놓치고 통과시키던 버그를 다시 만들지 않는지 확인한다.

배경: CLAUDE.md §4.3 은 DB 연결이 backend/db.py 팩토리에서만 만들어지길
요구한다. 이전 검사는 `node.func.value.id == "sqlite3"` 리터럴만 봐서
`import sqlite3 as sql; sql.connect(...)` 같은 별칭 우회를 11/11 로 거짓
통과시켰다.

실행: python tools/tests/test_db_live_verify.py   (저장소 루트에서)
      또는 pytest tools/tests/test_db_live_verify.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.db_live_verify import (  # noqa: E402
    _db_factory_functions,
    _find_sqlite_connect_bypasses,
    _function_sets_fk_pragma,
)

F179_GETATTR_ASSIGN_POC = """\
import sqlite3

def unsafe_connect():
    opener = getattr(sqlite3, "connect")
    return opener(':memory:')
"""

F179_GETATTR_DIRECT_POC = """\
import sqlite3

def unsafe_connect():
    return getattr(sqlite3, "connect")(':memory:')
"""

F155_MODULE_ALIAS_POC = """\
import sqlite3 as sql

def unsafe_connect():
    return sql.connect(':memory:')
"""

F155_FUNC_ALIAS_POC = """\
from sqlite3 import connect as go

def unsafe_connect():
    return go(':memory:')
"""

CLEAN_POC = """\
def helper(x):
    return x + 1
"""

# F-161 — 모듈 별칭의 .connect 를 다른 이름에 대입한 뒤 그 이름으로 부른다.
F161_ASSIGNMENT_ALIAS_POC = """\
import sqlite3 as sql

open_db = sql.connect

def unsafe_connect():
    return open_db(':memory:')
"""

# F-161 변형 — 대입 사슬(별칭의 별칭). 두 단계 모두 함수 별칭으로 전파돼야 한다.
F161_CHAINED_ASSIGNMENT_ALIAS_POC = """\
import sqlite3 as sql

_raw = sql.connect
open_db = _raw

def unsafe_connect():
    return open_db(':memory:')
"""

# F-161 변형 — from import 별칭을 다시 대입.
F161_FROM_IMPORT_REASSIGN_POC = """\
from sqlite3 import connect as go

open_db = go

def unsafe_connect():
    return open_db(':memory:')
"""

# F-165 — 타입 주석이 붙은 대입(ast.AnnAssign)은 ast.Assign 과 다른 노드다.
F165_ANNOTATED_ASSIGNMENT_ALIAS_POC = """\
import sqlite3 as sql

open_db: object = sql.connect

def unsafe_connect():
    return open_db(':memory:')
"""

# F-165 변형 — 주석 대입 뒤 다시 일반 대입으로 이어지는 사슬.
F165_ANNOTATED_CHAIN_POC = """\
import sqlite3 as sql

_raw: object = sql.connect
open_db = _raw

def unsafe_connect():
    return open_db(':memory:')
"""


def test_f155_module_alias_import_is_caught():
    """F-155 재현 그대로: `import sqlite3 as sql` 뒤 `sql.connect()`."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault.py").write_text(F155_MODULE_ALIAS_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-155 재발: 모듈 별칭(import sqlite3 as sql)을 통한 connect() 우회를 놓쳤다"


def test_f155_from_import_connect_alias_is_caught():
    """F-155 변형: `from sqlite3 import connect as go` 뒤 `go()`."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault2.py").write_text(F155_FUNC_ALIAS_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-155 재발: 함수 별칭(from sqlite3 import connect as go)을 통한 우회를 놓쳤다"


def test_literal_sqlite3_connect_still_caught():
    """기존에 잡던 리터럴 형태(`sqlite3.connect(...)`)가 새 구현에서도 계속 잡혀야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault3.py").write_text(
            "import sqlite3\n\ndef bad():\n    return sqlite3.connect('x.db')\n", encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found


def test_db_py_itself_is_excluded():
    """db.py 는 정당한 팩토리 위치이므로 검사 대상에서 제외된다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "db.py").write_text(
            "import sqlite3\n\ndef connect(p):\n    return sqlite3.connect(p)\n", encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found == []


def test_clean_files_pass():
    """sqlite3 를 전혀 쓰지 않는 정상 파일은 오탐이 없어야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "clean.py").write_text(CLEAN_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found == []


def test_f161_assignment_alias_is_caught():
    """F-161 재현 그대로: `open_db = sql.connect` 뒤 `open_db()`."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault4.py").write_text(F161_ASSIGNMENT_ALIAS_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-161 재발: 대입 별칭(open_db = sql.connect)을 통한 connect() 우회를 놓쳤다"


def test_f161_chained_assignment_alias_is_caught():
    """F-161 변형: 대입 사슬(`_raw = sql.connect; open_db = _raw`)도 잡아야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault5.py").write_text(F161_CHAINED_ASSIGNMENT_ALIAS_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-161 재발: 대입 사슬(별칭의 별칭)을 통한 우회를 놓쳤다"


def test_f161_from_import_reassignment_is_caught():
    """F-161 변형: `from sqlite3 import connect as go` 뒤 `open_db = go`."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault6.py").write_text(F161_FROM_IMPORT_REASSIGN_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-161 재발: from-import 별칭의 재대입을 통한 우회를 놓쳤다"


def test_f165_annotated_assignment_alias_is_caught():
    """F-165 재현 그대로: `open_db: object = sql.connect` (ast.AnnAssign)."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault7.py").write_text(F165_ANNOTATED_ASSIGNMENT_ALIAS_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-165 재발: 타입 주석 대입(ast.AnnAssign)을 통한 connect() 우회를 놓쳤다"


def test_f165_annotated_then_plain_assignment_chain_is_caught():
    """F-165 변형: 주석 대입 뒤 일반 대입으로 이어지는 사슬도 잡아야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault8.py").write_text(F165_ANNOTATED_CHAIN_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-165 재발: 주석 대입 → 일반 대입으로 이어지는 사슬을 놓쳤다"


# F-168 — db.py 안에서 새 연결 함수(PRAGMA 없이 sqlite3.connect만 하는)를
# 추가해도 잡혀야 한다. 재현 그대로: 팩토리 파일 자체는 우회 스캔에서
# 정당하게 제외되므로(test_db_py_itself_is_excluded), 함수 단위 정적 검사가
# 이 구멍을 메운다.
F168_DB_PY_POC = """\
import sqlite3
from pathlib import Path

def connect(db_path):
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")
    return con

def unsafe_connect(db_path):
    return sqlite3.connect(str(db_path))
"""


def test_f168_new_connect_function_without_pragma_is_detected():
    """F-168 재현: `unsafe_connect()`가 AST로 탐지되고, 자기 본문에
    `foreign_keys=ON`이 없다는 것도 잡혀야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_py = Path(tmp) / "db.py"
        db_py.write_text(F168_DB_PY_POC, encoding="utf-8")
        funcs = _db_factory_functions(db_py)
        assert "unsafe_connect" in funcs, "F-168 재발: 새 연결 함수가 AST 탐지에서 빠졌다"
        assert "connect" in funcs
        assert _function_sets_fk_pragma(db_py, "connect") is True
        assert _function_sets_fk_pragma(db_py, "unsafe_connect") is False, (
            "F-168 재발: PRAGMA 없는 연결 함수가 함수 단위 검사를 통과했다"
        )


def test_f168_clean_db_py_all_functions_set_pragma():
    """정상 db.py — 탐지된 함수 전부가 자기 본문 안에서 PRAGMA를 건다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_py = Path(tmp) / "db.py"
        db_py.write_text(
            "import sqlite3\n\n"
            "def connect(p):\n"
            "    con = sqlite3.connect(str(p))\n"
            "    con.execute('PRAGMA foreign_keys = ON')\n"
            "    return con\n",
            encoding="utf-8",
        )
        funcs = _db_factory_functions(db_py)
        assert funcs == ["connect"]
        assert all(_function_sets_fk_pragma(db_py, f) for f in funcs)


# F-172 — `_db_factory_functions`가 리터럴 `sqlite3.connect(` 판정만 써서
# 대입 별칭(`_open = sqlite3.connect`)으로 부르는 함수를 놓쳤다. 재현 그대로.
F172_DB_PY_POC = """\
import sqlite3

def connect(db_path):
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")
    return con

_open_without_fk = sqlite3.connect

def unsafe_connect(db_path):
    return _open_without_fk(str(db_path))
"""


def test_f172_alias_connect_function_in_db_py_is_detected():
    """F-172 재현: `_open = sqlite3.connect` 대입 별칭으로 부르는
    `unsafe_connect()`가 AST 탐지 목록에 들어와야 하고, PRAGMA 없음도
    잡혀야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_py = Path(tmp) / "db.py"
        db_py.write_text(F172_DB_PY_POC, encoding="utf-8")
        funcs = _db_factory_functions(db_py)
        assert "unsafe_connect" in funcs, "F-172 재발: 대입 별칭으로 부르는 연결 함수를 탐지하지 못했다"
        assert _function_sets_fk_pragma(db_py, "unsafe_connect") is False


# F-174 — `_db_factory_functions`가 `ast.FunctionDef`만 후보로 봐서 모듈
# 최상위 lambda 대입 팩토리를 놓쳤다. 재현 그대로.
F174_DB_PY_POC = """\
import sqlite3

def connect(db_path):
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON")
    return con

unsafe_connect = lambda db_path: sqlite3.connect(str(db_path))
"""


def test_f179_getattr_connect_bypass_is_caught():
    """F-179 재현: `getattr(sqlite3, "connect")` 별칭 대입 뒤 호출하는 우회가
    `_find_sqlite_connect_bypasses`(backend/ 일반 파일 검사)에서 잡혀야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault9.py").write_text(F179_GETATTR_ASSIGN_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-179 재발: getattr(sqlite3, 'connect') 대입 별칭을 통한 우회를 놓쳤다"


def test_f179_getattr_connect_direct_call_bypass_is_caught():
    """F-179 변형: 대입 없이 `getattr(sqlite3, "connect")(...)`로 바로 부르는
    형태도 잡혀야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault10.py").write_text(F179_GETATTR_DIRECT_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-179 재발: getattr(sqlite3, 'connect')(...) 직접 호출을 통한 우회를 놓쳤다"


def test_f179_getattr_connect_factory_in_db_py_is_detected():
    """F-179 재현 그대로: db.py 안에서 `getattr(sqlite3, "connect")` 별칭으로
    부르는 연결 함수도 `_db_factory_functions`가 탐지해야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_py = Path(tmp) / "db.py"
        db_py.write_text(
            "import sqlite3\n\n"
            "def connect(p):\n"
            "    con = sqlite3.connect(str(p))\n"
            "    con.execute('PRAGMA foreign_keys = ON')\n"
            "    return con\n\n"
            "def unsafe_connect(p):\n"
            "    opener = getattr(sqlite3, 'connect')\n"
            "    return opener(str(p))\n",
            encoding="utf-8",
        )
        funcs = _db_factory_functions(db_py)
        assert "unsafe_connect" in funcs, "F-179 재발: db.py 안의 getattr 별칭 연결 함수를 탐지하지 못했다"
        assert _function_sets_fk_pragma(db_py, "unsafe_connect") is False


def test_f174_lambda_connect_factory_in_db_py_is_detected():
    """F-174 재현: `unsafe_connect = lambda p: sqlite3.connect(...)`가 AST
    탐지 목록에 들어와야 한다. 람다는 문 하나도 못 담으므로 PRAGMA 를
    자기 본문에 걸 수 없다 — `_function_sets_fk_pragma`가 항상 False를
    내는 것 자체가 올바른 판정임을 함께 확인한다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_py = Path(tmp) / "db.py"
        db_py.write_text(F174_DB_PY_POC, encoding="utf-8")
        funcs = _db_factory_functions(db_py)
        assert "unsafe_connect" in funcs, "F-174 재발: lambda 대입 연결 팩토리를 탐지하지 못했다"
        assert _function_sets_fk_pragma(db_py, "unsafe_connect") is False


F181_DUNDER_IMPORT_DIRECT_POC = """\
def unsafe_connect(p):
    return __import__('sqlite3').connect(p)
"""

F181_DUNDER_IMPORT_MODULE_ALIAS_POC = """\
def unsafe_connect(p):
    db = __import__('sqlite3')
    return db.connect(p)
"""

F181_DUNDER_IMPORT_GETATTR_POC = """\
def unsafe_connect(p):
    opener = getattr(__import__('sqlite3'), 'connect')
    return opener(p)
"""

F222_IMPORTLIB_DIRECT_POC = """\
import importlib

def unsafe_connect(path):
    return importlib.import_module("sqlite3").connect(path)
"""

F222_IMPORTLIB_ALIAS_CHAIN_POC = """\
import importlib as loader_module

loader = loader_module.import_module
db_module = loader("sqlite3")
open_db = db_module.connect

def unsafe_connect(path):
    return open_db(path)
"""

F222_IMPORTLIB_GETATTR_POC = """\
from importlib import import_module as load

def unsafe_connect(path):
    return getattr(load(name="sqlite3"), "connect")(path)
"""


def test_f181_dunder_import_direct_call_bypass_is_caught():
    """F-181 재현: `__import__('sqlite3').connect(...)`는 `sqlite3`를 이름에
    묶지 않아 `module_aliases`(ast.Import 로만 채운다)에 전혀 안 걸렸다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault11.py").write_text(F181_DUNDER_IMPORT_DIRECT_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-181 재발: __import__('sqlite3').connect(...) 직접 호출을 통한 우회를 놓쳤다"


def test_f181_dunder_import_module_alias_bypass_is_caught():
    """F-181 변형: `db = __import__('sqlite3')`로 모듈을 이름에 묶은 뒤
    `db.connect(...)`로 부르는 형태(`import sqlite3 as db`와 같은 자격)."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault12.py").write_text(F181_DUNDER_IMPORT_MODULE_ALIAS_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-181 재발: __import__('sqlite3') 대입 별칭을 통한 우회를 놓쳤다"


def test_f181_dunder_import_getattr_bypass_is_caught():
    """F-181 변형: `getattr(__import__('sqlite3'), 'connect')` — F-179와
    F-181 두 우회가 겹친 형태도 잡혀야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault13.py").write_text(F181_DUNDER_IMPORT_GETATTR_POC, encoding="utf-8")
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-181 재발: getattr(__import__('sqlite3'), 'connect') 우회를 놓쳤다"


def test_f181_dunder_import_factory_in_db_py_is_detected():
    """F-181 재현 그대로: db.py 안에서 `__import__('sqlite3').connect(...)`로
    부르는 연결 함수도 `_db_factory_functions`가 탐지해야 한다(재현 시나리오
    그대로 - 임시 backend 사본에 이 함수를 넣으면 전체 15/15로 거짓 통과했다)."""
    with tempfile.TemporaryDirectory() as tmp:
        db_py = Path(tmp) / "db.py"
        db_py.write_text(
            "import sqlite3\n\n"
            "def connect(p):\n"
            "    con = sqlite3.connect(str(p))\n"
            "    con.execute('PRAGMA foreign_keys = ON')\n"
            "    return con\n\n"
            "def unsafe(p):\n"
            "    return __import__('sqlite3').connect(p)\n",
            encoding="utf-8",
        )
        funcs = _db_factory_functions(db_py)
        assert "unsafe" in funcs, "F-181 재발: db.py 안의 __import__('sqlite3') 연결 함수를 탐지하지 못했다"
        assert _function_sets_fk_pragma(db_py, "unsafe") is False


def test_f222_importlib_bypass_and_actual_fk_off_connection_are_caught():
    """F-222 재현: 검증기가 임시 backend 우회를 잡고, 반례 자체가 실제로
    `foreign_keys=0` 연결을 만드는 실행 가능한 코드임을 독립 실측한다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault14.py").write_text(
            F222_IMPORTLIB_DIRECT_POC, encoding="utf-8"
        )
        found = _find_sqlite_connect_bypasses(backend_dir)
        assert found, "F-222 재발: importlib.import_module('sqlite3') 직접 우회를 놓쳤다"

        namespace: dict[str, object] = {}
        exec(compile(F222_IMPORTLIB_DIRECT_POC, "<F-222>", "exec"), namespace)
        con = namespace["unsafe_connect"](Path(tmp) / "fk_off.db")
        try:
            assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        finally:
            con.close()


def test_f222_importlib_module_and_function_alias_chain_is_caught():
    """`importlib as X`와 `loader = X.import_module` 뒤 모듈·connect를 다시
    대입하는 전이적 별칭 사슬도 고정점 추적 대상이다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault15.py").write_text(
            F222_IMPORTLIB_ALIAS_CHAIN_POC, encoding="utf-8"
        )
        assert _find_sqlite_connect_bypasses(backend_dir)


def test_f222_from_import_keyword_and_getattr_bypass_is_caught():
    """from-import 함수 별칭·name 키워드·getattr가 겹친 변형도 잡는다."""
    with tempfile.TemporaryDirectory() as tmp:
        backend_dir = Path(tmp) / "backend"
        backend_dir.mkdir()
        (backend_dir / "_fault16.py").write_text(
            F222_IMPORTLIB_GETATTR_POC, encoding="utf-8"
        )
        assert _find_sqlite_connect_bypasses(backend_dir)


def test_f222_importlib_factory_in_db_py_is_detected():
    """동일 공통 판정이 db.py 내부 연결 함수 자동 탐지에도 적용돼야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        db_py = Path(tmp) / "db.py"
        db_py.write_text(
            "import importlib\n\n"
            "def unsafe_connect(path):\n"
            "    return importlib.import_module('sqlite3').connect(path)\n",
            encoding="utf-8",
        )
        funcs = _db_factory_functions(db_py)
        assert funcs == ["unsafe_connect"]
        assert _function_sets_fk_pragma(db_py, "unsafe_connect") is False


if __name__ == "__main__":
    failures = 0
    for fn in (
        test_f155_module_alias_import_is_caught,
        test_f155_from_import_connect_alias_is_caught,
        test_literal_sqlite3_connect_still_caught,
        test_db_py_itself_is_excluded,
        test_clean_files_pass,
        test_f161_assignment_alias_is_caught,
        test_f161_chained_assignment_alias_is_caught,
        test_f161_from_import_reassignment_is_caught,
        test_f165_annotated_assignment_alias_is_caught,
        test_f165_annotated_then_plain_assignment_chain_is_caught,
        test_f168_new_connect_function_without_pragma_is_detected,
        test_f168_clean_db_py_all_functions_set_pragma,
        test_f172_alias_connect_function_in_db_py_is_detected,
        test_f174_lambda_connect_factory_in_db_py_is_detected,
        test_f179_getattr_connect_bypass_is_caught,
        test_f179_getattr_connect_direct_call_bypass_is_caught,
        test_f179_getattr_connect_factory_in_db_py_is_detected,
        test_f181_dunder_import_direct_call_bypass_is_caught,
        test_f181_dunder_import_module_alias_bypass_is_caught,
        test_f181_dunder_import_getattr_bypass_is_caught,
        test_f181_dunder_import_factory_in_db_py_is_detected,
        test_f222_importlib_bypass_and_actual_fk_off_connection_are_caught,
        test_f222_importlib_module_and_function_alias_chain_is_caught,
        test_f222_from_import_keyword_and_getattr_bypass_is_caught,
        test_f222_importlib_factory_in_db_py_is_detected,
    ):
        try:
            fn()
            print(f"[OK] {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"[FAIL] {fn.__name__}: {exc}")

    total = 25
    print(f"\n=== {total - failures}/{total} 통과 ===")
    sys.exit(1 if failures else 0)
