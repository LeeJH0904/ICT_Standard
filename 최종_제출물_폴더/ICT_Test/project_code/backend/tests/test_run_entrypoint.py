"""backend/tests/test_run_entrypoint.py — 실제 진입점(`run.py`)의 DB 결속.

이 파일은 예외적으로 `run.py`(→ `siap.link`)를 import한다 — `backend/`가
`siap/` 내부 심볼을 import하지 않는다는 계약은 애플리케이션
코드에 대한 것이고, `run.py` 자신이 "SiapLink 호출만" 하는 유일한 교차
지점이다. 이 파일은 그 교차 지점이 실제로 결선돼 있는가만
검증한다 — `backend/`나 `siap/` 어디에도 새 계층 위반을 추가하지 않는다.

GPT 검증이 실제 `run.py`의 세 실행 경로(`--mode simulate/replay/
hardware`) 모두 `link.start(...)`에 `on_frame`을 넘기지 않아이
문서로만 성립하고 실행 경로에서는 DB 저장이 일어나지 않음을 지적했다.
회귀 가드는 두 갈래다:
  1. `_prepare_db_path()`가 실제로 스키마+시드를 적용한 DB 파일을 만드는가
     ("2. DB 준비").
  2. `_make_on_frame()`이 만든 콜백을 **SIAP I/O 스레드가 아닌 임의의
     스레드**에서 호출해도(즉 실제 운용과 같은 조건) 프레임이 DB에 반영되는가.
     최초 구현은 메인 스레드에서 연 연결을 그대로 넘겨 `sqlite3.
     ProgrammingError: SQLite objects created in a thread can only be
     used in that same thread`로 죽었다( 재현, 아래
     `test_on_frame_callback_survives_cross_thread_invocation_f160`가
     그 실패 조건을 재현해 회귀를 막는다)."""
from __future__ import annotations

import importlib
import sqlite3
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]  # project_code/
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

run = importlib.import_module("run")  # project_code/run.py

from contracts.frame import Frame, Header, MsgKind  # noqa: E402


def _keep_alive_frame(node_id: int = 3, msg_id: int = 1) -> Frame:
    header = Header(version=0x12, msg_type=0, trans_type=0, msg_id=msg_id,
                     payload_len=0, gcg_id=1, node_id=node_id)
    return Frame(header=header, kind=MsgKind.NOTI_KEEP_ALIVE, t=1.0)


def _frame_log_count(db_path: Path) -> int:
    con = sqlite3.connect(str(db_path))
    try:
        return con.execute("SELECT COUNT(*) FROM frame_log").fetchone()[0]
    finally:
        con.close()


class _Args:
    def __init__(self, db: str):
        self.db = db


def test_main_loads_env_before_selecting_mode(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(run, "load_env_file", lambda: calls.append("load"))
    monkeypatch.setattr(run, "_run_hardware", lambda args: calls.append("run") or 0)

    assert run.main(["--mode", "hardware", "--port", "COM1"]) == 0
    assert calls == ["load", "run"]


def test_main_reports_env_error_without_exposing_value(monkeypatch, capsys):
    def _fail():
        raise run.EnvFileError(".env:1: 지원하지 않는 환경변수 이름: TYPO_API_KEY")

    monkeypatch.setattr(run, "load_env_file", _fail)

    assert run.main(["--mode", "replay"]) == 2
    output = capsys.readouterr().out
    assert "환경변수 파일 오류" in output
    assert "secret-value" not in output

def test_prepare_db_path_creates_schema_and_seed_f160(tmp_path):
    db_path = tmp_path / "new.db"
    got = run._prepare_db_path(_Args(str(db_path)))
    assert got == db_path
    assert db_path.exists()
    con = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "frame_log" in tables
        # fixtures/seed.sql 의 고정 데이터 ("시드는 고정값")
        assert con.execute("SELECT COUNT(*) FROM greenhouse_info").fetchone()[0] >= 1
    finally:
        con.close()


def test_prepare_db_path_does_not_reseed_existing_file_f160(tmp_path):
    db_path = tmp_path / "existing.db"
    run._prepare_db_path(_Args(str(db_path)))
    before = sqlite3.connect(str(db_path))
    try:
        n_before = before.execute("SELECT COUNT(*) FROM greenhouse_info").fetchone()[0]
    finally:
        before.close()

    run._prepare_db_path(_Args(str(db_path)))  # 두 번째 호출 — 재시드되면 개수가 는다

    after = sqlite3.connect(str(db_path))
    try:
        n_after = after.execute("SELECT COUNT(*) FROM greenhouse_info").fetchone()[0]
    finally:
        after.close()
    assert n_after == n_before


def test_on_frame_callback_survives_cross_thread_invocation_f160(tmp_path):
    """ 핵심 회귀 — SIAP I/O 스레드를 흉내낸 별도 스레드에서 호출해도
    죽지 않고 DB에 반영돼야 한다. 최초 구현(메인 스레드에서 연 연결을
    `bind()`에 넘김)은 여기서 `sqlite3.ProgrammingError`를 던졌다."""
    db_path = tmp_path / "thread.db"
    run._prepare_db_path(_Args(str(db_path)))

    on_frame = run._make_on_frame(db_path)
    frame = _keep_alive_frame()
    error: list[BaseException] = []

    def _worker():
        try:
            on_frame(frame)
        except BaseException as e:  # noqa: BLE001 — 실패 자체가 회귀 증거다
            error.append(e)

    t = threading.Thread(target=_worker, name="fake-siap-io")
    t.start()
    t.join(timeout=5.0)

    assert not error, f"on_frame이 스레드 경계에서 실패했다: {error}"
    assert _frame_log_count(db_path) == 1


def test_on_frame_callback_reuses_connection_within_same_thread_f160(tmp_path):
    """같은(가짜 I/O) 스레드에서 두 번 호출하면 두 번째 호출에서 새 연결을
    또 열지 않고 캐시된 연결을 재사용한다 — 매 프레임마다 연결을 새로
    여는 것은 "트랜잭션은 짧게"와는 별개로 불필요한
    오버헤드이자, `bind()`가 이미 세운 "연결 하나, 여러 프레임" 관례에서
    벗어난다."""
    db_path = tmp_path / "reuse.db"
    run._prepare_db_path(_Args(str(db_path)))

    on_frame = run._make_on_frame(db_path)

    def _worker():
        on_frame(_keep_alive_frame(msg_id=1))
        on_frame(_keep_alive_frame(msg_id=2))

    t = threading.Thread(target=_worker, name="fake-siap-io")
    t.start()
    t.join(timeout=5.0)

    assert _frame_log_count(db_path) == 2
