"""sim/replayer.py 검증 — F-042 `dir` 필터, 타이밍 정규화, 안전한 종료."""
from __future__ import annotations

import json
import socket
import time

from sim import _wire as wire
from sim.replayer import Replayer

RX_FRAME_1 = wire.build_req_set_connection(msg_id=1, gcg_id=1, node_id=3)
TX_FRAME = wire.build_noti_keep_alive(msg_id=2, gcg_id=1, node_id=3)   # dir=tx 로 표시할 것 — 절대 주입되면 안 됨
RX_FRAME_2 = wire.build_noti_keep_alive(msg_id=3, gcg_id=1, node_id=3)


def _write_log(path, records: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")


def test_replayer_injects_only_rx_records(tmp_path):
    log = tmp_path / "session.jsonl"
    _write_log(log, [
        {"t": 0.0, "dir": "rx", "hex": RX_FRAME_1.hex()},
        {"t": 0.01, "dir": "tx", "hex": TX_FRAME.hex()},     # F-042 — 절대 소켓에 나가면 안 된다
        {"t": 0.02, "dir": "rx", "hex": RX_FRAME_2.hex()},
    ])

    r = Replayer(log, port=0, speed=50.0)
    # 포트 0 은 OS 가 임의 포트를 배정한다 — 실제 배정된 포트를 알아야
    # 클라이언트가 접속할 수 있으므로 미리 소켓을 만들어 bind 하고 넘긴다.
    r._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    r._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    r._srv.bind(("127.0.0.1", 0))
    port = r._srv.getsockname()[1]
    r._srv.listen(1)
    r._srv.settimeout(0.2)
    import threading
    r._thread = threading.Thread(target=r._accept_and_play, name="test-replayer", daemon=True)
    r._thread.start()

    client = socket.create_connection(("127.0.0.1", port), timeout=2.0)
    client.settimeout(2.0)
    client.sendall(TX_FRAME)  # dir=tx 기대 출력 — 주입 입력이 아니라 실제 게이트웨이 송신 대역
    received = b""
    deadline = time.monotonic() + 2.0
    expected_len = len(RX_FRAME_1) + len(RX_FRAME_2)
    while len(received) < expected_len and time.monotonic() < deadline:
        try:
            chunk = client.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        received += chunk
    client.close()
    r.stop()

    assert received == RX_FRAME_1 + RX_FRAME_2, "tx 레코드가 섞여 들어왔거나 rx 순서가 어긋남"
    assert r.stats["skipped_tx"] == 1
    assert r.stats["matched_tx"] == 1
    assert r.error is None
    assert r.stats["sent"] == 2


def test_replayer_normalizes_epoch_timestamps(tmp_path):
    """§5.4 — 첫 레코드의 t 를 빼서 정규화한다. epoch 시각을 그대로 sleep
    하면 재생이 사실상 영원히 끝나지 않는다."""
    log = tmp_path / "session.jsonl"
    big_epoch = 1_700_000_000.0
    _write_log(log, [
        {"t": big_epoch, "dir": "rx", "hex": RX_FRAME_1.hex()},
        {"t": big_epoch + 0.05, "dir": "rx", "hex": RX_FRAME_2.hex()},
    ])
    r = Replayer(log, port=0, speed=100.0)
    r._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    r._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    r._srv.bind(("127.0.0.1", 0))
    port = r._srv.getsockname()[1]
    r._srv.listen(1)
    r._srv.settimeout(0.2)
    import threading
    r._thread = threading.Thread(target=r._accept_and_play, name="test-replayer2", daemon=True)
    r._thread.start()

    client = socket.create_connection(("127.0.0.1", port), timeout=2.0)
    client.settimeout(3.0)
    started = time.monotonic()
    total = b""
    expected_len = len(RX_FRAME_1) + len(RX_FRAME_2)
    while len(total) < expected_len and time.monotonic() - started < 3.0:
        try:
            total += client.recv(4096)
        except socket.timeout:
            break
    elapsed = time.monotonic() - started
    client.close()
    r.stop()

    assert total == RX_FRAME_1 + RX_FRAME_2
    assert elapsed < 2.0, f"epoch 시각을 정규화하지 않으면 몇 년을 기다린다 (실제 {elapsed:.2f}s)"


def test_replayer_detects_tx_mismatch_f218(tmp_path):
    log = tmp_path / "mismatch.jsonl"
    _write_log(log, [
        {"t": 0.0, "dir": "rx", "hex": RX_FRAME_1.hex()},
        {"t": 0.01, "dir": "tx", "hex": TX_FRAME.hex()},
    ])
    r = Replayer(log, port=0, speed=100.0, tx_timeout=0.5)
    r._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    r._srv.bind(("127.0.0.1", 0))
    port = r._srv.getsockname()[1]
    r._srv.listen(1)
    r._srv.settimeout(0.2)
    import threading
    r._thread = threading.Thread(target=r._accept_and_play, daemon=True)
    r._thread.start()

    client = socket.create_connection(("127.0.0.1", port), timeout=2.0)
    client.sendall(b"\xDE" * len(TX_FRAME))
    assert r.done.wait(2.0)
    client.close()
    r.stop()

    assert r.error is not None
    assert "tx 기대 출력 불일치" in str(r.error)
    assert r.stats["matched_tx"] == 0
    assert r.stats["mismatched_tx"] == 1


def test_replayer_worker_error_is_exposed_f219(tmp_path):
    log = tmp_path / "malformed.jsonl"
    log.write_text("{not-json}\n", encoding="utf-8")
    r = Replayer(log, port=0, speed=100.0)
    r.start()
    port = r._srv.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port), timeout=2.0)
    assert r.done.wait(2.0)
    client.close()
    r.stop()

    assert r.error is not None
    assert "malformed.jsonl:1" in str(r.error)


def test_run_replay_returns_nonzero_for_mismatch_and_worker_error_f218_f219(tmp_path):
    import run

    mismatch = tmp_path / "run-mismatch.jsonl"
    _write_log(mismatch, [
        {"t": 0.0, "dir": "rx", "hex": RX_FRAME_1.hex()},
        {"t": 0.01, "dir": "tx", "hex": "DEADBEEF"},
    ])
    assert run.main([
        "--mode", "replay", "--log", str(mismatch), "--db", str(tmp_path / "mismatch.db"),
        "--speed", "100", "--duration", "5",
    ]) == 1

    malformed = tmp_path / "run-malformed.jsonl"
    malformed.write_text("{not-json}\n", encoding="utf-8")
    assert run.main([
        "--mode", "replay", "--log", str(malformed), "--db", str(tmp_path / "malformed.db"),
        "--speed", "100", "--duration", "5",
    ]) == 1


def test_run_replay_default_golden_session_matches_all_tx_f218(tmp_path):
    import run
    from sim import golden_log

    log = golden_log.write(tmp_path / "golden-session.jsonl", interval=0.01)
    assert run.main([
        "--mode", "replay", "--log", str(log), "--db", str(tmp_path / "golden.db"),
        "--speed", "100", "--duration", "5",
    ]) == 0


def test_committed_default_replay_log_matches_generator_f218():
    from sim import golden_log

    actual = [
        json.loads(line)
        for line in golden_log.DEFAULT_OUT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert actual == golden_log.build(), (
        "기본 replay 로그가 생성 규칙과 다르다 — python -m sim.golden_log 재실행 필요"
    )
