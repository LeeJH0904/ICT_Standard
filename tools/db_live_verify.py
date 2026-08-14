"""tools/db_live_verify.py - 구현(backend/)이 설계(project_docs/db/)와 같은가.

개발 착수 지시서 §3.7(단계 5) 신설 검증기. `project_docs/**/*_verify.py`가
설계 문서 자체를 본다면, 이 파일은 **실행 중인 DB**와 **소스 파일 2종**을
서로 대조한다 - 자기 자신과만 비교하지 않는다(F-080):

  ① backend/schema.sql  ↔  project_docs/db/schema.sql   (파일 동기, F-153)
  ② 실행 중 DB의 sqlite_master  ↔  backend/schema.sql 정적 파싱 결과
     (테이블 31 · 트리거 37 · 인덱스 8, DB 스키마 설계서 §6.1)
  ③ `PRAGMA foreign_keys=ON`이 backend/db.py 팩토리 단일 경로에서만 켜지는가
     - 다른 파일이 sqlite3.connect()를 직접 부르지 않는가(CLAUDE.md §4.3)
  ④ 실제 연결에서 foreign_keys가 실제로 ON인가(런타임 확인 - 파일을 읽는 것과
     실행 결과를 보는 것은 다르다, F-091류)

실행:  python tools/db_live_verify.py   (저장소 루트에서)
종료코드: 0 = 전부 통과, 1 = 하나라도 실패
"""
from __future__ import annotations

import ast
import inspect
import re
import sys
import tempfile
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
PROJECT_CODE = ROOT / "project_code"
BACKEND_DIR = PROJECT_CODE / "backend"
IMPL_SCHEMA = BACKEND_DIR / "schema.sql"
DESIGN_SCHEMA = ROOT / "project_docs" / "db" / "schema.sql"

sys.path.insert(0, str(PROJECT_CODE))


def _collect_sqlite_connect_aliases(
        tree: ast.AST,
) -> tuple[set[str], set[str], set[str], set[str]]:
    """`sqlite3.connect`를 가리킬 수 있는 모든 이름을 고정점까지 모은다 —
    `module_aliases`(그 이름.connect() 형태로 쓰는 모듈 바인딩, 리터럴
    `sqlite3` 자신도 포함)와 `func_aliases`(그 이름() 만으로 바로 호출하는
    함수 바인딩). `_find_sqlite_connect_bypasses`(다른 파일의 우회 탐지,
    F-155/F-161/F-165)와 `_db_factory_functions`(db.py 자신의 연결 함수
    탐지, F-168)가 **이 하나의 판정을 공유**한다 — 따로 두면 한쪽만 고치고
    다른 쪽의 별칭 인식이 낡는 사고가 난다(F-172: `_db_factory_functions`가
    자체 리터럴 판정만 쓰다가 `_open = sqlite3.connect; _open(...)` 같은
    대입 별칭을 놓쳤다).

    F-155 — `import sqlite3 as sql` 처럼 별칭을 쓴 연결도 잡는다. `sqlite3`
    모듈 자체를 가리키는 로컬 바인딩(모듈 별칭)과 `sqlite3.connect` 함수
    자체를 가리키는 바인딩(`from sqlite3 import connect as X`)을 먼저 모은
    뒤 그 이름들로의 호출을 우회로 판정한다 — tools/layer_verify.py의 별칭
    해석 원칙(F-109)과 같다.

    F-161 — import 별칭만으로는 부족했다. `open_db = sqlite3.connect` 처럼
    **대입으로 만든 별칭**은 `func_aliases`에 들어가지 않아 `open_db(...)`
    호출이 우회로 잡히지 않았다. 대입 우변이 (a) 이미 알려진 모듈 별칭의
    `.connect` 속성이거나 (b) 이미 알려진 함수 별칭 자체인 단순
    `이름 = 표현식` 대입을 고정점(fixed point)까지 반복 수집한다 —
    `a = b = sqlite3.connect` 같은 다중 대입, `y = x`(별칭의 별칭) 형태의
    전이적 대입까지 잡는다.

    F-165 — `ast.Assign`만 보면 부족했다. **타입 주석이 붙은 대입**
    (`open_db: object = sql.connect`)은 파이썬 문법상 별개의 노드
    `ast.AnnAssign`이라 `ast.Assign`을 찾는 순회에 전혀 걸리지 않았다.
    `ast.Assign`은 `targets`(리스트) + `value`, `ast.AnnAssign`은
    `target`(단일) + `value`(값 없는 순수 선언 `x: int`는 `value`가 `None`
    이라 대상에서 제외)로 구조가 달라 별도로 순회하되, 같은 고정점 루프
    안에서 함께 판정한다.

    F-179 — `.connect` 속성 접근(`ast.Attribute`)만 보면 부족했다.
    `getattr(sqlite3, "connect")`는 **문자열 리터럴로 같은 속성을 얻는
    별개의 표현식**(`ast.Call`)이라 `isinstance(value, ast.Attribute)` 판정에
    전혀 걸리지 않았다 — `opener = getattr(sqlite3, "connect"); opener(...)`
    가 대입 별칭 목록에 들어가지 않았고, `getattr(sqlite3, "connect")(...)`
    처럼 대입 없이 바로 부르는 형태도 `_is_sqlite_connect_call`이 놓쳤다.
    `_is_getattr_connect()`로 두 자리(대입 우변 판정 · 직접 호출 판정)
    모두에서 같은 패턴을 인식한다.

    F-181 — `module_aliases`는 `ast.Import`로 만든 **이름 바인딩**만 모은다.
    `__import__('sqlite3').connect(...)`는 `sqlite3` 모듈을 아예 이름에
    묶지 않고 그 자리에서 바로 속성에 접근한다 — `.connect`의 `value`가
    `ast.Name`이 아니라 `ast.Call`(`__import__(...)`)이라 기존 판정
    (`isinstance(fn.value, ast.Name) and fn.value.id in module_aliases`)에
    전혀 걸리지 않았다. `_is_dunder_import_sqlite()`로 이 표현식 자체를
    인식하고, ① `.connect` 속성 판정(대입 우변·직접 호출 양쪽) ②
    `getattr(__import__('sqlite3'), "connect")`의 첫 인자 ③
    `x = __import__('sqlite3')` 뒤 `x.connect(...)`(대입으로 모듈 별칭이
    되는 경우, `import sqlite3 as x`와 같은 자격) 세 자리 모두에 반영한다.

    F-222 — `importlib.import_module("sqlite3")`도 `sqlite3` 모듈을 반환하지만
    기존 수집기는 반환 모듈을 추적하지 못했다. `importlib` 모듈 별칭과
    `import_module` 함수 별칭, 그 대입 사슬도 고정점까지 추적한다."""
    module_aliases: set[str] = set()
    func_aliases: set[str] = set()
    importlib_aliases: set[str] = set()
    import_module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sqlite3":
                    module_aliases.add(alias.asname or alias.name)
                elif alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "sqlite3":
                for alias in node.names:
                    if alias.name == "connect":
                        func_aliases.add(alias.asname or alias.name)
            elif node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        import_module_aliases.add(alias.asname or alias.name)

    # F-161/F-165/F-181 — 대입 별칭(모듈 별칭·함수 별칭 둘 다)을 고정점까지
    # 전파한다. 매 라운드마다 새로 잡히는 이름이 없을 때까지 반복 —
    # 별칭 사슬(`a=b=c=sqlite3.connect`)의 길이를 미리 가정하지 않는다.
    assign_pairs: list[tuple[list[ast.expr], ast.expr | None]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            assign_pairs.append((n.targets, n.value))
        elif isinstance(n, ast.AnnAssign):
            assign_pairs.append(([n.target], n.value))   # value 는 None 일 수 있다 (순수 선언)
    changed = True
    while changed:
        changed = False
        for targets, value in assign_pairs:
            if value is None:
                continue
            is_func_alias_value = (
                (isinstance(value, ast.Attribute) and value.attr == "connect"
                 and (
                     (isinstance(value.value, ast.Name) and value.value.id in module_aliases)
                     or _is_dunder_import_sqlite(value.value)   # F-181
                     or _is_import_module_sqlite(
                         value.value, importlib_aliases, import_module_aliases
                     )   # F-222
                 ))
                or (isinstance(value, ast.Name) and value.id in func_aliases)
                or _is_getattr_connect(
                    value, module_aliases, importlib_aliases, import_module_aliases
                )   # F-179/F-222
            )
            # F-181 — `x = __import__('sqlite3')` 자체는 `.connect`가 아니라
            # 모듈 자신을 가리킨다. `import sqlite3 as x`와 같은 자격의
            # 모듈 별칭으로 취급해야 이후 `x.connect(...)`가 잡힌다.
            is_module_alias_value = (
                _is_dunder_import_sqlite(value)
                or _is_import_module_sqlite(
                    value, importlib_aliases, import_module_aliases
                )
            )
            is_import_module_alias_value = (
                (isinstance(value, ast.Attribute) and value.attr == "import_module"
                 and isinstance(value.value, ast.Name)
                 and value.value.id in importlib_aliases)
                or (isinstance(value, ast.Name) and value.id in import_module_aliases)
            )
            if not (is_func_alias_value or is_module_alias_value
                    or is_import_module_alias_value):
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if is_func_alias_value and target.id not in func_aliases:
                    func_aliases.add(target.id)
                    changed = True
                if is_module_alias_value and target.id not in module_aliases:
                    module_aliases.add(target.id)
                    changed = True
                if (is_import_module_alias_value
                        and target.id not in import_module_aliases):
                    import_module_aliases.add(target.id)
                    changed = True
    return module_aliases, func_aliases, importlib_aliases, import_module_aliases


def _is_dunder_import_sqlite(node: ast.expr) -> bool:
    """F-181 — `__import__('sqlite3')`가 `sqlite3` 모듈 자신을 가리키는
    표현식인가. `import sqlite3`와 같은 모듈을 얻지만 이름에 묶이지 않고
    그 자리에서 바로 쓰일 수 있다(`__import__('sqlite3').connect(...)`)."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "__import__"
        and len(node.args) >= 1
        and isinstance(node.args[0], ast.Constant) and node.args[0].value == "sqlite3"
    )


def _is_import_module_sqlite(
        node: ast.expr,
        importlib_aliases: set[str],
        import_module_aliases: set[str],
) -> bool:
    """F-222 — `importlib.import_module("sqlite3")` 또는 그 별칭 호출인가.
    실제 sqlite3 모듈을 반환하는 리터럴 입력만 인정해 다른 동적 import를
    연결 모듈로 오탐하지 않는다."""
    if not isinstance(node, ast.Call):
        return False
    fn = node.func
    calls_import_module = (
        (isinstance(fn, ast.Attribute) and fn.attr == "import_module"
         and isinstance(fn.value, ast.Name) and fn.value.id in importlib_aliases)
        or (isinstance(fn, ast.Name) and fn.id in import_module_aliases)
    )
    if not calls_import_module:
        return False
    name_arg: ast.expr | None = node.args[0] if node.args else None
    if name_arg is None:
        name_arg = next((kw.value for kw in node.keywords if kw.arg == "name"), None)
    return isinstance(name_arg, ast.Constant) and name_arg.value == "sqlite3"


def _is_getattr_connect(
        node: ast.expr,
        module_aliases: set[str],
        importlib_aliases: set[str],
        import_module_aliases: set[str],
) -> bool:
    """F-179 — `getattr(<module_aliases 중 하나 또는 __import__('sqlite3')>,
    "connect")` 형태인가. `sqlite3.connect`와 같은 값을 가리키지만
    `ast.Attribute`가 아니라 `ast.Call`이라 별도로 판정해야 한다."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name) and node.func.id == "getattr"
        and len(node.args) >= 2
        and (
            (isinstance(node.args[0], ast.Name) and node.args[0].id in module_aliases)
            or _is_dunder_import_sqlite(node.args[0])   # F-181
            or _is_import_module_sqlite(
                node.args[0], importlib_aliases, import_module_aliases
            )   # F-222
        )
        and isinstance(node.args[1], ast.Constant) and node.args[1].value == "connect"
    )


def _is_sqlite_connect_call(
        node: ast.Call,
        module_aliases: set[str],
        func_aliases: set[str],
        importlib_aliases: set[str],
        import_module_aliases: set[str],
) -> bool:
    """`node`가 (별칭을 포함해) `sqlite3.connect(...)`를 부르는 호출인가."""
    fn = node.func
    return (
        (isinstance(fn, ast.Attribute) and fn.attr == "connect"
         and (
             (isinstance(fn.value, ast.Name) and fn.value.id in module_aliases)
             or _is_dunder_import_sqlite(fn.value)   # F-181 — __import__('sqlite3').connect(...)
             or _is_import_module_sqlite(
                 fn.value, importlib_aliases, import_module_aliases
             )   # F-222
         ))
        or (isinstance(fn, ast.Name) and fn.id in func_aliases)
        or _is_getattr_connect(
            fn, module_aliases, importlib_aliases, import_module_aliases
        )   # F-179/F-222
    )


def _find_sqlite_connect_bypasses(backend_dir: Path) -> list[str]:
    """`backend/`(팩토리 `db.py` 제외) 안에서 `sqlite3.connect()`를 (별칭을
    포함해) 직접 부르는 파일을 찾는다 — CLAUDE.md §4.3, 연결은 `db.py`
    팩토리에서만 만든다."""
    found: list[str] = []
    for f in sorted(backend_dir.rglob("*.py")):
        if "__pycache__" in f.parts or "tests" in f.parts or f.name == "db.py":
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        except SyntaxError:
            continue
        (module_aliases, func_aliases,
         importlib_aliases, import_module_aliases) = _collect_sqlite_connect_aliases(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and _is_sqlite_connect_call(
                        node, module_aliases, func_aliases,
                        importlib_aliases, import_module_aliases
                    )):
                try:
                    found.append(str(f.relative_to(ROOT)))
                except ValueError:
                    # 테스트가 저장소 밖 임시 디렉터리를 backend_dir 로 넘길 때
                    # (tools/tests/test_db_live_verify.py) — 절대경로로 대체한다.
                    found.append(str(f))
                break
    return found


def _db_factory_functions(db_py_path: Path) -> list[str]:
    """F-168 — `db.py` 안에서 (별칭을 포함해) `sqlite3.connect()`를 호출하는
    최상위 함수 이름 전부. 이전에는 런타임 검사가 `init_db()`·`connect()`
    두 이름을 하드코딩해 불렀다 — 같은 파일에 새 연결 함수(예: 결함 주입
    재현의 `unsafe_connect()`)를 추가해도 그 이름이 호출 목록에 없어
    검사되지 않고 조용히 통과했다. 이름을 나열하지 않고 AST 로 **탐지**
    한다(F-094 "목록 고정 금지" 원칙과 동일).

    F-172 — 리터럴 `sqlite3.connect(` 판정만으로는 부족했다.
    `_open = sqlite3.connect` 처럼 대입 별칭을 쓴 뒤 `_open(...)`으로 부르는
    함수는 탐지되지 않아 F-168의 신설 검사가 15/15로 거짓 통과했다 —
    `_find_sqlite_connect_bypasses`와 같은 별칭 해석(`_collect_sqlite_
    connect_aliases`)을 이 파일 자신에도 그대로 적용한다.

    F-174 — `ast.FunctionDef`만 후보로 봐서 `unsafe_connect = lambda
    db_path: sqlite3.connect(str(db_path))`처럼 **모듈 최상위 대입으로 만든
    lambda 팩토리**를 놓쳤다(재현: F-172와 같은 15/15 거짓 통과).
    `ast.Assign`/`ast.AnnAssign`의 값이 `ast.Lambda`인 경우도 같은 자격으로
    본다 — 람다는 표현식 하나뿐이라 `PRAGMA foreign_keys=ON`을 자기 본문에
    걸 수 없으므로(파이썬 문법상 불가능), `_function_sets_fk_pragma()`가
    이런 이름에 대해 항상 `False`를 내는 것 자체가 올바른 판정이다 —
    별도 분기를 추가하지 않는다."""
    tree = ast.parse(db_py_path.read_text(encoding="utf-8"), filename=str(db_py_path))
    (module_aliases, func_aliases,
     importlib_aliases, import_module_aliases) = _collect_sqlite_connect_aliases(tree)

    def _calls_sqlite_connect(subtree: ast.AST) -> bool:
        return any(isinstance(sub, ast.Call) and _is_sqlite_connect_call(
                       sub, module_aliases, func_aliases,
                       importlib_aliases, import_module_aliases
                   )
                   for sub in ast.walk(subtree))

    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if _calls_sqlite_connect(node):
                names.append(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Lambda):
            if not _calls_sqlite_connect(node.value):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
    return names


def _function_sets_fk_pragma(db_py_path: Path, func_name: str) -> bool:
    """F-168 — `func_name` **자기 본문 안**에 `foreign_keys`를 `ON`으로 켜는
    문자열이 있는가(정적). 기존 ③ 검사(파일 전체에 "foreign_keys" 문자열이
    있는가)는 db.py 안 다른 함수에 PRAGMA가 있으면 새로 추가된 연결 함수도
    검사 없이 통과시켰다 — 이번엔 **그 함수 자신**의 소스만 본다."""
    tree = ast.parse(db_py_path.read_text(encoding="utf-8"), filename=str(db_py_path))
    full_src = db_py_path.read_text(encoding="utf-8")
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            src = ast.get_source_segment(full_src, node) or ""
            return bool(re.search(r"foreign_keys\s*=\s*ON", src, re.IGNORECASE))
    return False


def _probe_factory_function_runtime(backend_db, func_name: str, probe_db_path: Path) -> tuple[bool, str]:
    """F-168 — 탐지된 연결 함수를 실제로 호출해 반환 연결의 `PRAGMA
    foreign_keys` 실측값을 본다(파일을 읽는 것과 실행 결과를 보는 것은
    다르다, F-091류). 시그니처를 하드코딩하지 않고 `inspect`로 `seed`
    키워드 유무만 확인해 호출한다 — `init_db()`/`connect()` 뿐 아니라
    새로 추가되는 함수도 같은 방식으로 자동 검사된다."""
    fn = getattr(backend_db, func_name, None)
    if fn is None:
        return False, "backend.db 모듈에 해당 이름의 함수가 없음"
    try:
        sig = inspect.signature(fn)
        kwargs = {"seed": False} if "seed" in sig.parameters else {}
        con = fn(probe_db_path, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 결함 주입 함수는 임의 예외를 낼 수 있다
        return False, f"호출 실패: {exc!r}"
    try:
        ok = con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        return ok, "" if ok else "PRAGMA foreign_keys 실측값이 0"
    finally:
        con.close()


def _parse_ddl_names(sql: str, keyword: str) -> set[str]:
    """`CREATE TABLE x (` / `CREATE TRIGGER x` / `CREATE INDEX x` 이름을
    정적으로 뽑는다. `schema.sql`을 실제로 실행해 보는 것(②)과는 다른
    입력(텍스트 정규식)이라 서로 교차검증이 된다."""
    pat = re.compile(rf"CREATE\s+{keyword}\s+(\w+)", re.IGNORECASE)
    return set(pat.findall(sql))


def main() -> int:
    R: list[tuple[bool, str, str]] = []

    def t(name: str, ok: bool, note: str = "") -> None:
        R.append((bool(ok), name, note))

    # ═══════════════════════════════════════════════════════════
    #  ① 파일 동기 - F-153
    # ═══════════════════════════════════════════════════════════
    impl_exists = IMPL_SCHEMA.exists()
    t("project_code/backend/schema.sql 존재", impl_exists, "" if impl_exists else str(IMPL_SCHEMA))
    design_exists = DESIGN_SCHEMA.exists()
    t("project_docs/db/schema.sql 존재", design_exists, "" if design_exists else str(DESIGN_SCHEMA))

    if not (impl_exists and design_exists):
        _report(R)
        return 1

    impl_sql = IMPL_SCHEMA.read_text(encoding="utf-8")
    design_sql = DESIGN_SCHEMA.read_text(encoding="utf-8")
    synced = impl_sql.strip() == design_sql.strip()
    t("backend/schema.sql == project_docs/db/schema.sql (바이트 동일)", synced,
      "" if synced else "이관 후 정본이 갈렸다 - project_docs/db/schema.sql 을 다시 복사할 것")

    # ═══════════════════════════════════════════════════════════
    #  ② 실행 중 DB ↔ 정적 파싱 대조 - 테이블 31 · 트리거 37 · 인덱스 8
    # ═══════════════════════════════════════════════════════════
    from backend import db as backend_db  # noqa: E402 - sys.path 설정 후 import

    static_tables = _parse_ddl_names(impl_sql, "TABLE")
    static_triggers = _parse_ddl_names(impl_sql, "TRIGGER")
    static_indexes = _parse_ddl_names(impl_sql, "INDEX")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "live_verify.db"
        con = backend_db.init_db(db_path, seed=False)
        try:
            live_tables = set(backend_db.table_names(con))
            live_triggers = set(backend_db.trigger_names(con))
            live_indexes = set(backend_db.index_names(con))

            t(f"테이블 31개 (실행={len(live_tables)}, 정적파싱={len(static_tables)})",
              len(live_tables) == 31 == len(static_tables) and live_tables == static_tables,
              "" if live_tables == static_tables else f"차집합: {live_tables ^ static_tables}")
            t(f"트리거 37개 (실행={len(live_triggers)}, 정적파싱={len(static_triggers)})",
              len(live_triggers) == 37 == len(static_triggers) and live_triggers == static_triggers,
              "" if live_triggers == static_triggers else f"차집합: {live_triggers ^ static_triggers}")
            t(f"인덱스 8개 (실행={len(live_indexes)}, 정적파싱={len(static_indexes)})",
              len(live_indexes) == 8 == len(static_indexes) and live_indexes == static_indexes,
              "" if live_indexes == static_indexes else f"차집합: {live_indexes ^ static_indexes}")

            # ── ④ 런타임 foreign_keys 실제 확인 ──────────────────
            fk_on_init = con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            t("init_db() 연결에서 foreign_keys=ON (실측)", fk_on_init, "")
        finally:
            con.close()

        con2 = backend_db.connect(db_path)
        try:
            fk_on_connect = con2.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            t("connect() 재연결에서도 foreign_keys=ON (매 연결마다 켠다, 아키텍처 §4.4)",
              fk_on_connect, "")
            # 결함 주입 판정 대상 - FK 가 실제로 강제되는가(실행 결과, 파일을 읽는 것과 다르다)
            try:
                con2.execute(
                    "INSERT INTO device_install_info(id,created_at,updated_at,device_name,device_info_id)"
                    " VALUES('x','t','t','X','no-such-device-info-id')"
                )
                con2.commit()
                fk_enforced = False
            except Exception:
                fk_enforced = True
                con2.rollback()
            t("FK 위반 INSERT 가 실제로 거부된다 (PRAGMA 값이 아니라 동작으로 확인)",
              fk_enforced, "")
        finally:
            con2.close()

        # ═══════════════════════════════════════════════════════════
        #  ⑤ db.py 안의 연결 함수 자동 탐지 + 함수 단위 검사 - F-168
        #     이전에는 init_db()·connect() 두 이름만 하드코딩해 호출했다 —
        #     같은 파일에 새 연결 함수가 추가돼도 이름을 나열하지 않으므로
        #     AST 로 직접 찾는다(F-094).
        # ═══════════════════════════════════════════════════════════
        factory_funcs = _db_factory_functions(BACKEND_DIR / "db.py")
        t(f"db.py 연결 함수 탐지 (AST, {len(factory_funcs)}개): {factory_funcs}",
          len(factory_funcs) > 0, "")
        missing_pragma = [fn for fn in factory_funcs
                           if not _function_sets_fk_pragma(BACKEND_DIR / "db.py", fn)]
        t("db.py 의 연결 함수 전부가 자기 본문 안에서 foreign_keys=ON 을 건다 (함수 단위 정적 검사)",
          not missing_pragma, "; ".join(missing_pragma))

        for fn_name in factory_funcs:
            probe_path = Path(tmp) / f"live_verify_probe_{fn_name}.db"
            ok, note = _probe_factory_function_runtime(backend_db, fn_name, probe_path)
            t(f"{fn_name}() 런타임 호출 결과 foreign_keys=ON (자동 탐지·자동 호출, F-168)", ok, note)

    # ═══════════════════════════════════════════════════════════
    #  ③ PRAGMA foreign_keys 는 db.py 팩토리 단일 경로에서만 (CLAUDE.md §4.3)
    # ═══════════════════════════════════════════════════════════
    pragma_files = []
    for f in sorted(BACKEND_DIR.rglob("*.py")):
        if "__pycache__" in f.parts or f.parts[-2:] == ("tests", f.name):
            continue
        src = f.read_text(encoding="utf-8", errors="replace")
        if "foreign_keys" in src and f.name != "db.py":
            pragma_files.append(str(f.relative_to(ROOT)))
    t("PRAGMA foreign_keys 설정은 backend/db.py 하나뿐", not pragma_files,
      "; ".join(pragma_files))

    connect_files = _find_sqlite_connect_bypasses(BACKEND_DIR)
    t("backend/ 안에서 sqlite3.connect() 를 직접 부르는 곳이 db.py 뿐 (연결은 db.py 팩토리에서만)",
      not connect_files, "; ".join(connect_files))

    return _report(R)


def _report(R: list[tuple[bool, str, str]]) -> int:
    w = max((len(n) for _, n, _ in R), default=0)
    print("DB 실행 대조 검증 - schema.sql 동기 · 실행 DB ↔ 정적 파싱 · foreign_keys 단일 경로\n")
    for ok, n, note in R:
        print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
    p = sum(1 for o, *_ in R if o)
    print(f"\n  {p}/{len(R)} 통과")
    return 0 if p == len(R) else 1


if __name__ == "__main__":
    sys.exit(main())
