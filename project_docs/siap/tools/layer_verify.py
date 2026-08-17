"""계층 import 방향 검증 — CLAUDE.md §2.2

  backend/ · web/ 은 siap/ 내부 심볼을 import 하지 않는다. contracts/ 와
  SiapLink 만 참조한다.
  siap/ 은 backend/ 를 import 하지 않는다.

grep 은 주석·문자열(예: 이 파일 자신의 docstring)을 그대로 잡아 오탐을 낸다
(개발_착수_지시서 §3.1 신설 항목). 그래서 각 .py 파일을 ast.parse() 로 파싱하고
Import / ImportFrom 노드만 판정한다.

실행:  python tools/layer_verify.py   (저장소 루트에서)
종료코드: 0 = 위반 없음, 1 = 위반 있음
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

ROOT = Path(__file__).resolve().parent.parent
PROJECT_CODE = ROOT / "project_code"

SKIP_DIRS = {"__pycache__", "node_modules", "site-packages", "venv", ".venv",
             "env", "wheels", "build", "dist"}


def _skip(p: Path) -> bool:
    return any(part.startswith(".") or part in SKIP_DIRS for part in p.parts)


def _py_files(dir_: Path) -> list[Path]:
    if not dir_.exists():
        return []
    return sorted(p for p in dir_.rglob("*.py") if not _skip(p))


def _package_parts(path: Path) -> list[str]:
    """`path` 가 속한 패키지의 dotted 경로를, PROJECT_CODE 를 최상위 패키지
    루트로 보고 계산한다 (`__package__` 와 같은 값). 예:
      project_code/backend/x.py        -> ['backend']
      project_code/backend/services/y.py -> ['backend', 'services']
      project_code/backend/__init__.py -> ['backend']            (자기 자신이 곧 패키지)
    F-105 — 상대 import 를 해석하려면 "이 파일이 어느 패키지 안에 있는가"가
    있어야 한다. 이전에는 이걸 몰라서 level>0 을 전부 건너뛰었다."""
    stem_parts = list(path.relative_to(PROJECT_CODE).with_suffix("").parts)
    if stem_parts and stem_parts[-1] == "__init__":
        return stem_parts[:-1]
    return stem_parts[:-1]


def _effective_top(parts: list[str]) -> str | None:
    """dotted 이름 구성요소 목록에서 실질적인 최상위 계층 이름을 뽑는다.
    첫 구성요소가 `PROJECT_CODE` 디렉터리 이름 자체(`project_code`)면 —
    저장소 루트가 sys.path 에 있어 `import project_code.siap.codec` 처럼
    쓰는 실행 방식이면 — 그 다음 구성요소가 실제 계층 이름이다(F-109).
    `project_docs.contracts.frame` 처럼 애초에 접두어가 없는 경우는 그대로
    첫 구성요소를 쓴다 — `project_docs` 는 `project_code` 의 형제 디렉터리라
    이 접두어 규칙과 무관하다."""
    if not parts:
        return None
    if parts[0] == PROJECT_CODE.name and len(parts) > 1:
        return parts[1]
    return parts[0]


def _resolve_relative(level: int, package_parts: list[str]) -> list[str]:
    """importlib._bootstrap._resolve_name 과 같은 규칙으로 `from ..x import y`
    류의 상대 import 를 절대 dotted 경로의 앞부분(패키지 base)으로 되돌린다.
    `level - 1` 이 현재 패키지 깊이를 넘으면(top-level 밖으로 나가면) base 를
    빈 목록으로 둔다 — 원래 그 지점에서 ImportError 가 나야 하는 코드이므로
    "안전하다"고 조용히 넘기지 않고, 뒤에 붙는 모듈명을 그대로 최상위 이름
    후보로 취급해 보수적으로(=위반 쪽으로) 판정한다."""
    up = level - 1
    if up <= 0:
        return list(package_parts)
    if up >= len(package_parts):
        return []
    return package_parts[: len(package_parts) - up]


# F-105 — 정적 문자열 인자를 쓰는 동적 import 호출. 변수·f-string 등 실행해야만
# 알 수 있는 인자는 정적 분석의 근본적 한계라 여기서 다루지 않는다(다른
# *_verify.py 들도 같은 한계를 명시적으로 인정하는 원칙, 예: golden_verify.py
# 의 "정본만 고치고 재생성 안 하면 걸린다" 류 — 잡을 수 있는 것만 잡고,
# 못 잡는 부분은 숨기지 않는다).
_DYNAMIC_IMPORT_FUNCS = {"import_module", "__import__"}


def _dynamic_import_aliases(tree: ast.AST) -> set[str]:
    """`from importlib import import_module as load` 처럼 `import_module` 을
    다른 이름으로 들여온 지역 바인딩 전부를 모은다(F-109). `foo.import_module(...)`
    형태(속성 호출)는 기준 객체 이름을 이미 안 보고 잡으므로 — `importlib as il`
    별칭은 손댈 필요가 없다. 별칭이 필요한 쪽은 `Name` 호출(`load(...)`) 뿐이다."""
    aliases = set(_DYNAMIC_IMPORT_FUNCS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _top_level_modules(src: str, path: Path) -> set[str]:
    """파일이 import 하는(정적으로 결정 가능한) 모듈의 최상위 이름 집합
    (예: 'siap.codec' -> 'siap'). 상대 import 는 이 파일의 패키지 위치를
    기준으로 절대 경로로 되돌린 뒤 최상위 이름을 취한다(F-105). 패키지
    접두어(`project_code.siap...`)와 별칭 동적 import(`import_module as load`)
    도 같은 최상위 이름으로 정규화한다(F-109)."""
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:
        # 파싱 실패 자체가 판정 대상은 아니다. 별도 항목으로 보고한다.
        return {f"__syntax_error__:{exc}"}
    package_parts = _package_parts(path)
    dynamic_names = _dynamic_import_aliases(tree)
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = _effective_top(alias.name.split("."))
                if top:
                    mods.add(top)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                base = _resolve_relative(node.level, package_parts)
                if node.module:
                    full = base + node.module.split(".")
                else:
                    # 'from . import x' / 'from .. import x' — x 자체가
                    # base 바로 아래의 이름이다.
                    for alias in node.names:
                        top = _effective_top(base + [alias.name])
                        if top:
                            mods.add(top)
                    continue
            else:
                full = node.module.split(".") if node.module else []
            top = _effective_top(full)
            if top:
                mods.add(top)
        elif isinstance(node, ast.Call):
            fn = node.func
            is_dynamic = (
                (isinstance(fn, ast.Attribute) and fn.attr == "import_module")
                or (isinstance(fn, ast.Name) and fn.id in dynamic_names)
            )
            if is_dynamic and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                top = _effective_top(node.args[0].value.split("."))
                if top:
                    mods.add(top)
    return mods


def _violations(scan_dir: Path, forbidden: str) -> list[str]:
    bad: list[str] = []
    for f in _py_files(scan_dir):
        src = f.read_text(encoding="utf-8", errors="replace")
        mods = _top_level_modules(src, f)
        syntax_err = [m for m in mods if m.startswith("__syntax_error__:")]
        if syntax_err:
            bad.append(f"{f.relative_to(ROOT)}: 파싱 실패 ({syntax_err[0].split(':', 1)[1]})")
            continue
        if forbidden in mods:
            bad.append(f"{f.relative_to(ROOT)}: import {forbidden}")
    return bad


def main() -> int:
    # F-105 Claude 처리 기록 — 이 스크립트를 안전하게 import 해서 내부 함수를
    # 직접 반례로 검증할 수 있어야 meta_verify.py 의 "수정완료 코드버그에
    # 대응 회귀 테스트 존재" 요구를 충족한다(F-043). 이전에는 검사 본문이
    # 모듈 최상위에서 곧장 실행되고 sys.exit() 까지 호출해, import 자체가
    # 프로세스를 죽였다 — where.py·offline_verify.py·run_all.py 와 같은
    # main()+`__main__` 가드 구조로 맞췄다.
    R: list[tuple[bool, str, str]] = []
    def t(name: str, ok: bool, note: str = "") -> None:
        R.append((bool(ok), name, note))

    # ═══════════════════════════════════════════════════════════
    #  backend/ · web/ → siap/ 금지
    # ═══════════════════════════════════════════════════════════
    backend_dir = PROJECT_CODE / "backend"
    web_dir = PROJECT_CODE / "web"
    siap_dir = PROJECT_CODE / "siap"

    backend_files = _py_files(backend_dir)
    web_files = _py_files(web_dir)
    siap_files = _py_files(siap_dir)

    t(f"backend/ 스캔 대상 {len(backend_files)}개 .py 파일 발견", True,
      "0개면 이 단계에서는 위반이 있을 수 없다 — 회귀 가드일 뿐이다" if not backend_files else "")
    t(f"web/ 스캔 대상 {len(web_files)}개 .py 파일 발견", True, "")
    t(f"siap/ 스캔 대상 {len(siap_files)}개 .py 파일 발견", True, "")

    bad_backend = _violations(backend_dir, "siap")
    t("backend/ 가 siap/ 를 import 하지 않는다 (CLAUDE.md §2.2)", not bad_backend, "; ".join(bad_backend))

    bad_web = _violations(web_dir, "siap")
    t("web/ 가 siap/ 를 import 하지 않는다 (CLAUDE.md §2.2)", not bad_web, "; ".join(bad_web))

    bad_siap = _violations(siap_dir, "backend")
    t("siap/ 가 backend/ 를 import 하지 않는다 (CLAUDE.md §2.2)", not bad_siap, "; ".join(bad_siap))

    # ═══════════════════════════════════════════════════════════
    #  project_code/ 전체는 project_docs/ 를 import 하지 않는다 (CLAUDE.md §2.2)
    #  F-206 — 이전 검사는 contracts/ 만 순회해 backend/ · siap/ · sim/ 등
    #  다른 구현 계층에 같은 금지 import 가 들어와도 7/7 로 통과했다.
    # ═══════════════════════════════════════════════════════════
    bad_docs = _violations(PROJECT_CODE, "project_docs")
    t("project_code/ 전체가 project_docs/ 를 import 하지 않는다 (CLAUDE.md §2.2)",
      not bad_docs, "; ".join(bad_docs))

    # ═══════════════════════════════════════════════════════════
    w = max(len(n) for _, n, _ in R)
    print("계층 import 방향 검증  (backend/web -x-> siap, siap -x-> backend, project_code -x-> project_docs)\n")
    for ok, n, note in R:
        print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
    p = sum(1 for o, *_ in R if o)
    print(f"\n  {p}/{len(R)} 통과")
    return 0 if p == len(R) else 1


if __name__ == "__main__":
    sys.exit(main())
