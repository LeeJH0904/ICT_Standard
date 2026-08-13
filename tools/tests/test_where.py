"""F-121 회귀 테스트 — tools/where.py 의 단계 2c 판정이 test_node_state 부재를
놓치고 통과시키던 버그를 다시 만들지 않는지 확인한다.

배경: 개발_착수_지시서 §3.4 출구 ①은 "./test_node_state" 다. 이전 구현은 이
항목을 "재빌드 후 전수 실행 결과 목록에 자연히 포함될 것"이라고 가정했는데,
node_state.c/.h·test_node_state.c 가 없으면 Makefile 의 TARGETS 자체에서
test_node_state 가 빠져 `make` 가 그대로 성공하고 2a·2b 산출물 4종만 도는
채로 "통과"가 나왔다(F-121).

실행: python tools/tests/test_where.py   (저장소 루트에서, pytest 없이도 동작)
      또는 pytest tools/tests/test_where.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import where as where_mod  # noqa: E402


def _make_fake_repo(tmp_path: Path, *, with_sources: bool, makefile_has_target: bool) -> Path:
    """check_stage_2c() 가 파일 존재 검사에 쓰는 최소 디렉터리 골격만 만든다."""
    core_dir = tmp_path / "project_code" / "firmware" / "core"
    tests_dir = tmp_path / "project_code" / "firmware" / "tests"
    core_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    if with_sources:
        (core_dir / "node_state.c").write_text("/* stub */\n", encoding="utf-8")
        (core_dir / "node_state.h").write_text("/* stub */\n", encoding="utf-8")
        (tests_dir / "test_node_state.c").write_text("/* stub */\n", encoding="utf-8")

    makefile_body = "TARGETS := test_bitpack test_siap_frame test_status_codes test_golden"
    if makefile_has_target:
        makefile_body += " test_node_state"
    (tests_dir / "Makefile").write_text(makefile_body + "\n", encoding="utf-8")
    return tmp_path


def test_stage_2c_fails_when_node_state_sources_missing_f121(monkeypatch):
    """소스가 전혀 없으면(현재 F-121 재현 상태) 단계 2c 는 통과할 수 없어야 한다."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        fake_root = _make_fake_repo(Path(tmp), with_sources=False, makefile_has_target=False)
        monkeypatch.setattr(where_mod, "REPO_ROOT", fake_root)

        results = where_mod.check_stage_2c()

        statuses = [ok for _, ok, _ in results]
        assert any(s is False for s in statuses), (
            "F-121 재발: node_state 소스가 없는데도 단계 2c 의 모든 항목이 실패 없이 통과했다"
        )
        # 첫 항목이 소스 부재를 명확히 짚어야 한다 — "어쩌다 실패"가 아니라
        # "무엇이 없어서 실패"인지가 출구 판정의 요구사항이다(개발_착수_지시서 §1.2).
        desc0, ok0, detail0 = results[0]
        assert ok0 is False
        assert "node_state" in desc0
        assert "node_state.c" in detail0 and "test_node_state.c" in detail0


def test_stage_2c_fails_when_makefile_missing_target_f121(monkeypatch):
    """소스는 있어도 Makefile TARGETS 에 test_node_state 가 없으면 실패해야 한다."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        fake_root = _make_fake_repo(Path(tmp), with_sources=True, makefile_has_target=False)
        monkeypatch.setattr(where_mod, "REPO_ROOT", fake_root)

        results = where_mod.check_stage_2c()

        statuses = [ok for _, ok, _ in results]
        assert any(s is False for s in statuses)
        desc0, ok0, _ = results[0]
        assert ok0 is False
        assert "Makefile" in desc0


def test_stage_2c_catches_silent_rebuild_without_node_state_f121(monkeypatch):
    """F-121 의 정확한 재현 경로: 소스·Makefile 등록은 있는데, 재빌드 결과에
    test_node_state 실행이 실제로는 빠진 경우(예: 빌드 산출물 이름 불일치·
    조건부 컴파일 누락)도 잡아야 한다 — 존재 검사만으로는 부족하다."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        fake_root = _make_fake_repo(Path(tmp), with_sources=True, makefile_has_target=True)
        monkeypatch.setattr(where_mod, "REPO_ROOT", fake_root)

        # 버그가 실제로 낸 증상을 그대로 재현: 재빌드 결과가 옛 4종만 담겨 있다.
        def fake_rebuild(stage_label: str) -> list[where_mod.CheckResult]:
            return [
                (f"{stage_label}: make (firmware/tests 전체 재빌드)", True, ""),
                ("./test_bitpack", True, ""),
                ("./test_siap_frame", True, ""),
                ("./test_status_codes", True, ""),
                ("./test_golden", True, ""),
            ]

        monkeypatch.setattr(where_mod, "_rebuild_and_run_all_tests", fake_rebuild)
        monkeypatch.setattr(where_mod, "_run_py", lambda *a, **k: ("stub", True, ""))

        results = where_mod.check_stage_2c()

        statuses = [ok for _, ok, _ in results]
        assert any(s is False for s in statuses), (
            "F-121 재발: test_node_state 가 실행 목록에 없는데도 단계 2c 가 전부 통과했다"
        )
        names = [desc for desc, _, _ in results]
        assert any("test_node_state" in n and "실행됨" in n for n in names)


def test_stage_0_does_not_require_no_구현_output_f144(monkeypatch):
    """F-144 회귀(F-149 — 이 회귀 테스트가 없어 `meta_verify.py`의 "수정완료
    코드버그에 대응 회귀 테스트 존재" 검사가 실패했었다. 이 파일 자체가 그
    결함의 수정이다). check_stage_0() 은 `run.py --mode simulate` 출력에
    '미구현' 문구가 있어야 통과하던 옛 단언을 여전히 요구하면 안 된다.
    check_stage_4() 는 반대로 단계 4 완료 후 그 문구가 사라져야 한다고
    요구하므로(§3.6, "단계 4부터는 '미구현' 문구가 사라져야 한다"), 두 검사가
    같은 명령의 출력에 대해 정반대를 단언하면 단계 4 완료 직후 check_stage_0()
    이 영구히 깨져 `main()`(첫 실패 단계에서 멈춤)의 '현재 단계' 판정이 0으로
    후퇴한다(실측: 단계 1~4 전부 통과해도 '현재 단계: 0'). exit 0 이면서
    '미구현' 문구가 없는(=단계 4 완료 후의 정상 상태) 출력을 흉내내 통과하는지
    직접 확인한다."""
    def fake_run(cmd, cwd=None, timeout=180):
        if cmd and len(cmd) >= 2 and cmd[1].endswith("run.py"):
            # 단계 4 완료 후의 실제 출력 형태 — '미구현' 문구가 전혀 없다.
            return True, "[run.py] 종료 — 등록 노드 3개, rx=12 tx=12 위반=0"
        return True, ""

    monkeypatch.setattr(where_mod, "_run", fake_run)
    monkeypatch.setattr(where_mod, "_exists",
                         lambda rel: (f"{rel} 존재", True, ""))
    monkeypatch.setattr(where_mod, "_pip_offline_install_check",
                         lambda: ("오프라인 설치(표본: win_amd64/py311)", True, ""))
    monkeypatch.setattr(where_mod, "_run_py",
                         lambda rel, args=None, cwd=None: (f"python {rel}", True, ""))

    results = where_mod.check_stage_0()

    by_desc = {desc: (ok, detail) for desc, ok, detail in results}
    ok, detail = by_desc["run.py --mode simulate 가 정상 종료(exit 0)한다"]
    assert ok is True, (
        f"F-144 재발: exit 0 이지만 '미구현' 문구가 없는 정상 출력인데도 단계 0 이 실패로 판정했다 ({detail})"
    )
    assert all(ok for _, ok, _ in results), (
        f"단계 0 전체가 통과해야 하는 입력인데 일부 실패: {results}"
    )


if __name__ == "__main__":
    # pytest 없이도 직접 실행 가능하게 — monkeypatch 를 손으로 흉내낸다.
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
    fns = (
        test_stage_2c_fails_when_node_state_sources_missing_f121,
        test_stage_2c_fails_when_makefile_missing_target_f121,
        test_stage_2c_catches_silent_rebuild_without_node_state_f121,
        test_stage_0_does_not_require_no_구현_output_f144,
    )
    for fn in fns:
        mp = _FakeMonkeypatch()
        try:
            fn(mp)
            print(f"[OK] {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"[FAIL] {fn.__name__}: {exc}")
        finally:
            mp.undo()

    print(f"\n=== {len(fns) - failures}/{len(fns)} 통과 ===")
    sys.exit(1 if failures else 0)
