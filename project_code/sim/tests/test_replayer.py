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
