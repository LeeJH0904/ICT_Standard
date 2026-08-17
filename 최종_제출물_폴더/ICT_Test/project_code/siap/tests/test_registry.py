"""siap/registry.py 검증 — 노드 세션 bookkeeping."""
from __future__ import annotations

from contracts.frame import (
    DevType, DeviceMainInfo, DeviceProperty, NodeProperty, Status, Subtype,
    TransferMode, ValueType,
)
from siap.registry import NodeRegistry


def _node(node_id=3, num_devices=0):
    return NodeProperty(sw_version=1, gcg_id=1, node_id=node_id,
                         status=Status.NORMAL, num_devices=num_devices)


def _dp(device_id=5):
    main = DeviceMainInfo(device_id=device_id, dev_type=DevType.SENSOR,
                           subtype=int(Subtype.TEMPERATURE), value_type=ValueType.FLOAT,
                           value=25.3)
    return DeviceProperty(main=main, transfer_mode=TransferMode.PERIODIC, period=60,
                           lower_value=-10.0, upper_value=50.0, lower_limit=-40.0,
                           upper_limit=80.0, precision=0.1, status=Status.NORMAL)


def test_unknown_node_is_not_known():
    reg = NodeRegistry()
    assert reg.is_known(3) is False
    assert reg.registry() == {}
    assert reg.devices(3) == ()


def test_register_then_known():
    reg = NodeRegistry()
    node = _node()
    dp = _dp()
    reg.register(node, (dp,))
    assert reg.is_known(3) is True
    assert reg.registry() == {3: node}
    assert reg.devices(3) == (dp.main,)
    assert reg.device_properties(3) == (dp,)
    assert len(reg) == 1


def test_unregister_removes_all_traces():
    reg = NodeRegistry()
    reg.register(_node(), (_dp(),))
    reg.unregister(3)
    assert reg.is_known(3) is False
    assert reg.devices(3) == ()
    assert reg.device_properties(3) == ()
    assert len(reg) == 0


def test_update_node_ignores_unregistered():
    """미등록 노드는 조용히 무시한다 — 그 판정은 codec.decode_frame() 몫이다."""
    reg = NodeRegistry()
    reg.update_node(_node(node_id=99))
    assert reg.is_known(99) is False


def test_update_node_updates_registered():
    reg = NodeRegistry()
    reg.register(_node(num_devices=0))
    updated = _node(num_devices=3)
    reg.update_node(updated)
    assert reg.registry()[3].num_devices == 3


def test_replace_node_and_device_properties_updates_both_f213():
    reg = NodeRegistry()
    reg.register(_node(), (_dp(device_id=5),))
    updated = NodeProperty(sw_version=9, gcg_id=1, node_id=3,
                           status=Status.NORMAL, num_devices=1)
    replacement = _dp(device_id=7)
    reg.replace_node_and_device_properties(updated, (replacement,))
    assert reg.registry()[3] == updated
    assert reg.devices(3) == (replacement.main,)
    assert reg.device_properties(3) == (replacement,)


def test_registry_returns_copy_not_live_reference():
    reg = NodeRegistry()
    reg.register(_node())
    snapshot = reg.registry()
    snapshot[999] = _node(node_id=999)
    assert 999 not in reg.registry()
