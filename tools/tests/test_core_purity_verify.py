"""F-122·F-128 회귀 테스트 — tools/core_purity_verify.py 가 보드 매크로 우회를
놓치고 통과시키던 버그를 다시 만들지 않는지 확인한다.

배경: CLAUDE.md §1-5·개발_착수_지시서 §3.3 은 `core/`에 보드 판별 매크로·
플랫폼 헤더 include 가 0개임을 기계로 판정하라고 요구한다.

F-122 — "보드 매크로가 전혀 정의되지 않은 상태"로만 검사해, 아래처럼 자체
매크로로 간접화한 코드를 6/6 · exit 0 으로 통과시켰다.

    #define SIAP_BOARD ARDUINO
    #define SIAP_PLATFORM_HEADER <Arduino.h>
    #if SIAP_BOARD
    #include SIAP_PLATFORM_HEADER
    ...

F-128 — F-122 보완 후에도 "알려진 보드 이름 목록"이라는 전제가 남아 있어서,
빌드 플래그로 정의하는 임의 이름은 여전히 통과했다.

    #if SIAP_PLATFORM
    ...
    #endif

실행: python tools/tests/test_core_purity_verify.py   (저장소 루트에서)
      또는 pytest tools/tests/test_core_purity_verify.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import core_purity_verify as cpv  # noqa: E402

F122_POC = """\
#define SIAP_BOARD ARDUINO
#define SIAP_PLATFORM_HEADER <Arduino.h>
#if SIAP_BOARD
#include SIAP_PLATFORM_HEADER
int siap_board_specific = 1;
#else
int siap_board_specific = 0;
#endif
"""


def test_f122_indirect_board_macro_is_caught(monkeypatch):
    """F-122 재현 그대로: 자체 매크로로 감싼 보드 판별·헤더 include 가
    셋 중 하나 이상의 검사에서 반드시 잡혀야 한다."""
    with tempfile.TemporaryDirectory() as tmp:
        core_dir = Path(tmp) / "core"
        core_dir.mkdir()
        (core_dir / "poc.c").write_text(F122_POC, encoding="utf-8")
        monkeypatch.setattr(cpv, "ROOT", Path(tmp))
        monkeypatch.setattr(cpv, "CORE_DIR", core_dir)

        files = cpv._source_files()
        assert len(files) == 1

        bad_text = cpv._check_includes_textual(files)
        bad_cc, unknown_cc = cpv._check_includes_compiler(files)
        bad_macro = cpv._check_board_macros(files)

        assert bad_text or bad_cc or bad_macro, (
            "F-122 재발: 간접 보드 매크로 PoC 가 텍스트 스캔·gcc 전처리·매크로 "
            "조건 검사 어디에서도 잡히지 않았다"
        )
        # 세 겹 방어 중 최소 두 겹(치환 목록 텍스트 스캔·gcc 매크로 조합)은
        # gcc 유무와 무관하게 항상 잡아야 한다 — 텍스트 계층은 gcc 없이도 동작.
        assert bad_text, "F-122 재발: #define 치환 목록에 대한 텍스트 스캔이 놓쳤다"
        assert bad_macro, "F-122 재발: #define 치환 목록의 보드 매크로 이름을 놓쳤다"


F128_POC = """\
#if SIAP_PLATFORM
int siap_board_specific_branch = 1;
#else
int siap_board_specific_branch = 0;
#endif
"""


def test_f128_arbitrary_macro_name_is_caught(monkeypatch):
    """F-128 재현 그대로: 알려진 보드 이름 목록에 없는 임의 이름 매크로 조건도
    화이트리스트 검사(c)가 잡아야 한다 — (a)/(b)는 이름을 모르므로 못 잡는다."""
    with tempfile.TemporaryDirectory() as tmp:
        core_dir = Path(tmp) / "core"
        core_dir.mkdir()
        (core_dir / "poc.c").write_text(F128_POC, encoding="utf-8")
        monkeypatch.setattr(cpv, "ROOT", Path(tmp))
        monkeypatch.setattr(cpv, "CORE_DIR", core_dir)

        files = cpv._source_files()
        bad_macro = cpv._check_board_macros(files)
        bad_whitelist = cpv._check_conditional_whitelist(files)

        assert not bad_macro, (
            "이 반례는 정의상 알려진 보드 이름 블랙리스트로는 잡히지 않아야 한다 "
            "(잡힌다면 테스트 반례 자체가 F-128을 재현하지 못한 것)"
        )
        assert bad_whitelist, (
            "F-128 재발: 임의 이름 매크로 조건부 컴파일이 화이트리스트 검사에서도 놓쳤다"
        )


def test_clean_core_files_still_pass(monkeypatch):
    """정상적인(간접화 없는) 순수 코드는 여전히 위반 0건이어야 한다 — 오탐 방지.
    include guard 형태와 실제 bitpack.h 의 `#if defined(__GNUC__)` 패턴 둘 다 넣는다."""
    with tempfile.TemporaryDirectory() as tmp:
        core_dir = Path(tmp) / "core"
        core_dir.mkdir()
        (core_dir / "clean.c").write_text(
            "#include \"clean.h\"\nint x = 1;\n", encoding="utf-8"
        )
        (core_dir / "clean.h").write_text(
            "#ifndef CLEAN_H\n#define CLEAN_H\n"
            "#if defined(__GNUC__)\n"
            "#  define ATTR __attribute__((warn_unused_result))\n"
            "#else\n"
            "#  define ATTR\n"
            "#endif\n"
            "void f(void);\n#endif\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(cpv, "ROOT", Path(tmp))
        monkeypatch.setattr(cpv, "CORE_DIR", core_dir)

        files = cpv._source_files()
        assert cpv._check_includes_textual(files) == []
        assert cpv._check_board_macros(files) == []
        assert cpv._check_conditional_whitelist(files) == []
        bad_cc, unknown_cc = cpv._check_includes_compiler(files)
        assert bad_cc == []


if __name__ == "__main__":
    class _FakeMonkeypatch:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, value):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, value)

        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)

    failures = 0
    for fn in (
        test_f122_indirect_board_macro_is_caught,
        test_f128_arbitrary_macro_name_is_caught,
        test_clean_core_files_still_pass,
    ):
        mp = _FakeMonkeypatch()
        try:
            fn(mp)
            print(f"[OK] {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"[FAIL] {fn.__name__}: {exc}")
        finally:
            mp.undo()

    print(f"\n=== {3 - failures}/3 통과 ===")
    sys.exit(1 if failures else 0)
