"""sim/inject.py 검증 — 골든 벡터 8종만 허용, 바이트가 golden.jsonl 원본과
정확히 일치하는지(시연 시나리오 §3.1 "영상 속 hex 와 제출 golden.jsonl 의
hex 가 같아야 한다")."""
from __future__ import annotations

import json
import socket
import threading

import pytest

from sim import inject


def _golden_hex(vector_id: str) -> str:
    with open(inject.GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            v = json.loads(line)
            if v["id"] == vector_id:
                return v["hex"].upper()
    raise KeyError(vector_id)


@pytest.mark.parametrize("vector_id", sorted(inject.ALLOWED_VECTORS))
def test_vector_bytes_match_golden_exactly(vector_id):
    assert inject.vector_bytes(vector_id).hex().upper() == _golden_hex(vector_id)


def test_rejects_vector_outside_x01_x08():
    """ 와 같은 근거 — 자유 바이트열/임의 ID 를 받으면 "결과가 골든과
    같다"는 판정 근거가 사라진다."""
    with pytest.raises(ValueError):
        inject.load_vector("N01")
    with pytest.raises(ValueError):
        inject.load_vector("X09")
    with pytest.raises(ValueError):
        inject.load_vector("../../etc/hosts")


def test_inject_writes_exact_bytes_to_socket():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.listen(1)

    received = {}

    def server():
        conn, _ = srv.accept()
        conn.settimeout(2.0)
        data = b""
        expected = inject.vector_bytes("X03")
        while len(data) < len(expected):
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        received["data"] = data
        conn.close()

    t = threading.Thread(target=server, daemon=True)
    t.start()

    client = socket.create_connection(("127.0.0.1", port), timeout=2.0)
    sent = inject.inject("X03", client)
    client.close()
    t.join(timeout=2.0)
    srv.close()

    assert sent == inject.vector_bytes("X03")
    assert received["data"] == sent
