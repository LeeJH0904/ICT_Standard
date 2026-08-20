"""F-251 회귀 — 검증 도구 위치와 저장소 루트 계산을 고정한다."""
from pathlib import Path

from tools import run_all


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_f251_tools_live_at_repository_root():
    assert run_all.REPO_ROOT == REPO_ROOT
    assert run_all.TOOLS_DIR == REPO_ROOT / "tools"
    assert run_all.PROJECT_DOCS_DIR == REPO_ROOT / "project_docs"
    assert (run_all.TOOLS_DIR / "run_all.py").is_file()


def test_f251_discovery_covers_tools_and_project_docs():
    scripts = run_all.discover_scripts()
    relative = {path.relative_to(REPO_ROOT).as_posix() for path in scripts}
    assert "tools/offline_verify.py" in relative
    assert "project_docs/web/web_verify.py" in relative
    assert not any(path.startswith("project_docs/siap/tools/") for path in relative)