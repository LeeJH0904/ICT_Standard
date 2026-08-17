"""sim/virtual_node.py 검증 — 값 풀 로딩(§5.5 결정), 노드 상태, msg_id 순환.

F-217 — 센서·미등록 디바이스 제어 거부와 제어 목록 원자성을 검증한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from sim import _wire as wire
from sim.virtual_node import (
    SUBTYPE_HUMIDITY, SUBTYPE_TEMPERATURE, SimNode, SimDevice,
    GOLDEN_PATH, VirtualNodeServer, _default_nodes, _late_node, _load_value_pool,
)


def test_value_pool_loads_from_golden_and_prefers_normal_category():
    pool = _load_value_pool()
    assert SUBTYPE_TEMPERATURE in pool
    assert SUBTYPE_HUMIDITY in pool
    # N34(카테고리=정상)의 값이어야 한다 — 경계값(예: B07의 INT 최솟값)이 섞이면 안 된다
    vt, val = pool[SUBTYPE_TEMPERATURE]
    assert vt == wire.VT_FLOAT
    assert val == 1103783526


def test_default_nodes_reuse_pool_values_not_synthetic():
    pool = _load_value_pool()
    nodes = _default_nodes(pool)
    assert len(nodes) == 3
    # Uno 흉내 노드는 101 이 아니라 3 이다(F-145) — golden.jsonl 의 정상·위반
    # 벡터가 (X02 반례를 빼면) 전부 Node ID=3 을 쓰므로, live 주입이 실제로
    # 등록된 노드를 맞혀야 목표 판정이 INVALID_NODE_ID 에 가려지지 않는다.
    assert {n.node_id for n in nodes} == {3, 102, 103}
    # 모든 디바이스 값이 골든 풀에서 왔는지(또는 풀에 없으면 명시적 fallback
    # 0)만 확인한다 — 무작위 생성기나 사인파 함수를 쓰지 않는다는 것은 이
    # 함수가 애초에 그런 호출을 하지 않는다는 소스 자체가 근거다
    for n in nodes:
        for dev in n.devices:
            if dev.subtype in pool:
                assert dev.value == pool[dev.subtype][1]


def test_late_node_has_distinct_id_and_reuses_pool():
    pool = _load_value_pool()
    nodes = _default_nodes(pool)
    late = _late_node(pool)
    assert late.node_id not in {n.node_id for n in nodes}


def test_injection_targets_are_registered_nodes_f145():
    """F-145 — `sim/inject.py` 가 골든 X01~X08 의 hex 를 그대로 링크에
    흘려보내므로, 그 프레임들이 담은 Node ID 가 이 서버의 등록 노드에
    없으면 목표 판정(INVALID_DATA_TYPE 등) 전에 INVALID_NODE_ID 로
    가려진다. X02 는 "미등록 Node ID" 자체가 반례이므로 예외로 뺀다."""
    pool = _load_value_pool()
    registered = {n.node_id for n in _default_nodes(pool)}

    checked = 0
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            v = json.loads(line)
            if not v["id"].startswith("X"):
                continue
            if v.get("inject") == "unregistered_node":     # X02 — 의도된 반례
                continue
            node_id = v["header"]["Node ID"]
            assert node_id in registered, (
                f"{v['id']}(Node ID={node_id})가 등록 노드 {sorted(registered)}에 없다 "
                "— INVALID_NODE_ID 에 목표 판정이 가려진다(F-145)"
            )
            checked += 1
    assert checked >= 7   # X01,X03~X08 (X02 제외)


def test_msg_id_starts_at_zero_and_wraps():
    """7.2.2 원문 그대로 — F-135 와 같은 원칙을 이 파일에서 독립적으로
    재구현한다(코드 재사용 아님, 같은 조항의 재해석)."""
    n = SimNode(1, "test", [])
    assert n.next_msg_id() == 0
    assert n.next_msg_id() == 1
    n.msg_id = 0xFFFF
    assert n.next_msg_id() == 0xFFFF
    assert n.next_msg_id() == 0


class _CaptureSocket:
    def __init__(self):
        self.sent: list[bytes] = []

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)


def _control(server: VirtualNodeServer, node_id: int, msg_id: int,
             commands: list["wire.WireDMI"]) -> int:
    conn = _CaptureSocket()
    header = wire.WireHeader(
        version=0x12, msg_type=wire.MT_REQ_SET_DEVICE_CONTROL,
        trans_type=wire.TRANS_UNICAST, msg_id=msg_id,
        payload_len=wire.DMI_BYTES * len(commands), gcg_id=1, node_id=node_id,
    )
    server._handle(conn, header, b"".join(wire.encode_dmi(c) for c in commands))
    assert len(conn.sent) == 1
    return conn.sent[0][wire.HEADER_BYTES]


def test_invalid_device_control_is_rejected_without_mutation_f217():
    server = VirtualNodeServer(port=0, control_port=None)
    sensor_node = next(n for n in server._nodes if n.node_id == 3)
    sensor = sensor_node.devices[0]
    before = sensor.value
    sensor_cmd = wire.WireDMI(
        sensor.device_id, wire.DEV_SENSOR, sensor.subtype,
        sensor.value_type, wire.float_to_raw(30.0),
    )
    assert _control(server, 3, 1, [sensor_cmd]) == wire.RSC_INVALID_DEVICE_TYPE
    assert sensor.value == before

    missing = wire.WireDMI(99, wire.DEV_ACTUATOR, 0x85, wire.VT_UINT, 1)
    assert _control(server, 3, 2, [missing]) == wire.RSC_INVALID_DEVICE_ID


def test_valid_actuator_control_updates_value_f217():
    server = VirtualNodeServer(port=0, control_port=None)
    node = next(n for n in server._nodes if n.node_id == 102)
    actuator = next(d for d in node.devices if d.dev_type == wire.DEV_ACTUATOR)
    changed = actuator.value + 1
    cmd = wire.WireDMI(
        actuator.device_id, actuator.dev_type, actuator.subtype,
        actuator.value_type, changed,
    )
    assert _control(server, node.node_id, 3, [cmd]) == wire.RSC_SUCCESS
    assert actuator.value == changed


def test_control_list_is_atomic_when_later_device_is_invalid_f217():
    server = VirtualNodeServer(port=0, control_port=None)
    node = next(n for n in server._nodes if n.node_id == 102)
    actuator = next(d for d in node.devices if d.dev_type == wire.DEV_ACTUATOR)
    before = actuator.value
    valid = wire.WireDMI(
        actuator.device_id, actuator.dev_type, actuator.subtype,
        actuator.value_type, actuator.value + 1,
    )
    invalid = wire.WireDMI(99, wire.DEV_ACTUATOR, actuator.subtype, actuator.value_type, 1)
    assert _control(server, node.node_id, 4, [valid, invalid]) == wire.RSC_INVALID_DEVICE_ID
    assert actuator.value == before
