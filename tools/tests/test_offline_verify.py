"""F-240·F-250 회귀 — 런타임 산출물이 제출물에 섞이지 않는지 확인한다.

배경: `.gitignore` 가 *.db 를 무시해도 (가) 과거처럼 실수로 커밋되면 무시가
무력화되고 (나) `offline_verify.py` 의 폴더 walk 가 gitignore 를 모른 채 온디스크
DB 를 크기·실행파일 스캔에 포함해, 실제 제출물(git 추적 파일)과 어긋났다(F-240).
이 테스트는 두 가지를 고정한다:
  1) git 이 추적하는 *.db 가 하나라도 있으면 check_no_tracked_databases 가 실패한다.
  2) git 이 무시하는 *.db 는 패키징 walk(_is_excluded)에서 제외된다.

실행: python tools/tests/test_offline_verify.py   (저장소 루트에서, pytest 없이도 동작)
      또는 pytest tools/tests/test_offline_verify.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools import offline_verify as ov  # noqa: E402


def test_no_tracked_databases_on_real_repo() -> None:
    """현 저장소에는 추적 중인 DB 가 없어야 한다 — 하나라도 커밋되면 실패한다."""
    ok, detail = ov.check_no_tracked_databases()
    assert ok, f"런타임 DB 가 git 에 추적되고 있다: {detail}"


def test_gitignored_db_excluded_from_packaging(tmp_db: Path) -> None:
    """gitignore 된 런타임 DB 는 _is_excluded 가 True 로 걸러야 한다(크기 부풀림 방지)."""
    ov._gitignored_files.cache_clear()  # 새로 만든 파일을 git 에 다시 물어보게 한다
    try:
        assert ov._is_excluded(tmp_db), (
            f"{tmp_db.relative_to(REPO_ROOT)} 는 .gitignore(*.db) 대상인데 "
            "패키징 walk 에서 제외되지 않았다"
        )
    finally:
        ov._gitignored_files.cache_clear()


def test_final_submission_scanner_rejects_artifacts_and_personal_path(tmp_path: Path) -> None:
    """F-250 — 실제 staging의 캐시·DB·개인 경로를 모두 실패로 잡는다."""
    omc_file = tmp_path / ".omc" / "state" / "error.json"
    omc_file.parent.mkdir(parents=True)
    omc_file.write_text("{}", encoding="utf-8")
    cache_file = tmp_path / "project_code" / "__pycache__" / "x.pyc"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"cache")
    db_file = tmp_path / "project_code" / "backend" / "runtime.db"
    db_file.parent.mkdir(parents=True)
    db_file.write_bytes(b"SQLite format 3\\x00")
    trace = tmp_path / "trace.txt"
    trace.write_text("C:\\\\Users\\\\contestant\\\\workspace\\\\error.log", encoding="utf-8")

    forbidden = ov._find_forbidden_submission_paths(tmp_path)
    personal = ov._find_personal_paths(tmp_path)
    assert {p.name for p in forbidden} >= {".omc", "__pycache__", "runtime.db"}
    assert personal == [trace]


def test_final_submission_scanner_accepts_clean_tree(tmp_path: Path) -> None:
    good = tmp_path / "project_code" / "README.md"
    good.parent.mkdir(parents=True)
    good.write_text("재현 가능한 소스", encoding="utf-8")
    assert ov._find_forbidden_submission_paths(tmp_path) == []
    assert ov._find_personal_paths(tmp_path) == []


def _make_tmp_db() -> Path:
    """저장소 안에 임시 .db 를 만든다 — .gitignore 의 *.db 규칙에 걸린다."""
    p = REPO_ROOT / "project_code" / "x_offline_verify_regtest.db"
    p.write_bytes(b"SQLite format 3\x00regression")
    return p


# ── pytest fixture (없이 실행할 때는 아래 main 이 대체) ─────────────────
try:
    import pytest

    @pytest.fixture()
    def tmp_db():  # type: ignore[no-redef]
        p = _make_tmp_db()
        try:
            yield p
        finally:
            p.unlink(missing_ok=True)
except ImportError:  # pytest 없이 직접 실행
    pytest = None  # type: ignore[assignment]


def main() -> int:
    failures = 0

    try:
        test_no_tracked_databases_on_real_repo()
        print("[PASS] 추적 중인 런타임 DB 0개")
    except AssertionError as e:
        failures += 1
        print(f"[FAIL] {e}")

    p = _make_tmp_db()
    try:
        test_gitignored_db_excluded_from_packaging(p)
        print("[PASS] gitignore 된 DB 가 패키징 walk 에서 제외됨")
    except AssertionError as e:
        failures += 1
        print(f"[FAIL] {e}")
    finally:
        p.unlink(missing_ok=True)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        try:
            test_final_submission_scanner_rejects_artifacts_and_personal_path(root)
            print("[PASS] 최종 제출 staging의 산출물·개인 경로 탐지")
        except AssertionError as e:
            failures += 1
            print(f"[FAIL] {e}")

    with tempfile.TemporaryDirectory() as td:
        try:
            test_final_submission_scanner_accepts_clean_tree(Path(td))
            print("[PASS] 청결한 최종 제출 staging 허용")
        except AssertionError as e:
            failures += 1
            print(f"[FAIL] {e}")

    print(f"\n{'전체 통과' if failures == 0 else f'실패 {failures}건'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
