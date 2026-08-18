"""sim/_wire.py 검증 — 독립 인코더가 골든 벡터와 바이트 단위로 일치하는지
(교차검증, "독립 입력" 원칙) 및 왕복·오류 처리.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim import _wire as wire

GOLDEN_PATH = Path(__file__).resolve().parent.parent.parent / "contracts" / "vectors" / "golden.jsonl"


def _golden(vid: str) -> dict:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            v = json.loads(line)
            if v["id"] == vid:
                return v
    raise KeyError(vid)


def test_build_req_set_connection_matches_golden_n01():
    v = _golden("N01")
    b = wire.build_req_set_connection(msg_id=1, gcg_id=1, node_id=3)
    assert b.hex().upper() == v["hex"].upper()


def test_build_noti_device_value_matches_golden_n34():
    v = _golden("N34")
    dmis = [
        wire.WireDMI(1, wire.DEV_SENSOR, 1, wire.VT_FLOAT, 1103783526),
        wire.WireDMI(2, wire.DEV_SENSOR, 2, wire.VT_FLOAT, 1114898432),
    ]
    b = wire.build_noti_device_value(msg_id=34, gcg_id=1, node_id=3, dmis=dmis)
    assert b.hex().upper() == v["hex"].upper()


def test_header_round_trip():
    h = wire.WireHeader(version=0x12, msg_type=0x0C, trans_type=0, msg_id=42,
                         payload_len=7, gcg_id=1, node_id=3)
    encoded = wire.encode_header(h)
    assert len(encoded) == wire.HEADER_BYTES
    decoded = wire.decode_header(encoded)
    assert decoded == h


def test_dmi_round_trip():
    d = wire.WireDMI(device_id=5, dev_type=wire.DEV_ACTUATOR, subtype=0x85,
                      value_type=wire.VT_UINT, value=1)
    encoded = wire.encode_dmi(d)
    assert len(encoded) == wire.DMI_BYTES
    decoded = wire.decode_dmi(encoded)
    assert decoded == d


def test_float_raw_round_trip():
    raw = wire.float_to_raw(25.4)
    assert abs(wire.raw_to_float(raw) - 25.4) < 1e-5


def test_writer_rejects_out_of_range_value():
    w = wire._Writer()
    with pytest.raises(ValueError):
        w.put(256, 8)


def test_reader_rejects_overrun():
    r = wire._Reader(b"\x00")
    with pytest.raises(ValueError):
        r.get(16)


def test_decode_header_rejects_short_buffer():
    with pytest.raises(ValueError):
        wire.decode_header(b"\x00" * 5)


def test_decode_req_set_device_control_round_trip():
    dmis = [wire.WireDMI(2, wire.DEV_ACTUATOR, 0x85, wire.VT_UINT, 0)]
    payload = b"".join(wire.encode_dmi(d) for d in dmis)
    decoded = wire.decode_req_set_device_control(payload)
    assert decoded == dmis


def test_decode_req_set_device_control_rejects_misaligned_payload():
    with pytest.raises(ValueError):
        wire.decode_req_set_device_control(b"\x00" * 10)   # 7의 배수가 아님


def test_decode_res_set_connection_reads_rsc_byte():
    assert wire.decode_res_set_connection(bytes([0x00, 0xFF])) == 0x00
    assert wire.decode_res_set_connection(bytes([0x03])) == 0x03


def test_decode_res_set_connection_rejects_empty_payload():
    with pytest.raises(ValueError):
        wire.decode_res_set_connection(b"")


def test_build_res_set_device_control_msg_id_matches_request():
    """ 원칙(요청의 msg_id 를 그대로 복사) — 가상 노드도 같은 규칙을 따른다."""
    b = wire.build_res_set_device_control(msg_id=99, gcg_id=1, node_id=3)
    h = wire.decode_header(b)
    assert h.msg_id == 99
    assert h.msg_type == wire.MT_RES_SET_DEVICE_CONTROL
    assert b[wire.HEADER_BYTES] == wire.RSC_SUCCESS
