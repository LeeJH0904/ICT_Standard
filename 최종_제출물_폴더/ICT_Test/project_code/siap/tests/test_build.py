"""siap/build.py 검증 — FrameBuilder Protocol 이행 12종(게이트웨이발 5 + 회신 7),
msg_id 발번(초기값 0, F-135), F-040 회신 복사 규칙, F-137(미등록 디바이스 제어 거부).
"""
from __future__ import annotations

import pytest

from contracts.frame import (
    DeviceProperty, DevType, MsgKind, NodeProperty, RSC, Status, Subtype,
    TransferMode, ValueType,
)
from contracts.fake_link import FakeFrameBuilder
from siap import codec
from siap.build import FrameBuilderImpl, MsgIdAllocator


def test_msg_id_allocator_starts_at_0_and_wraps_to_0_f135():
    """0943 7.2.2 원문 — "0에서 65535까지 사용… 만료되면 0부터 다시
    시작한다." 0을 건너뛰지 않는다(F-135 — 이전에는 "0은 미할당 표시로
    예약"이라며 1부터 시작해 0xFFFF 다음 1로 돌아갔다. 표준 문구와
    직접 어긋났고, 그 예약을 실제로 참조하는 코드도 없었다)."""
    a = MsgIdAllocator()
    assert a.next() == 0
    assert a.next() == 1
    a._next = 0xFFFF
    assert a.next() == 0xFFFF
    assert a.next() == 0                    # 표준 그대로 0으로 순환(1이 아니다)


@pytest.mark.parametrize("kind,build_call", [
    (MsgKind.REQ_GET_DEVICE_VALUE, lambda b: b.get_device_value(3, [5, 6])),
    (MsgKind.REQ_GET_NODE_PROPERTY, lambda b: b.get_node_property(3)),
    (MsgKind.REQ_SET_DEVICE_PROPERTY, lambda b: b.set_device_property(3, [_dp()])),
    (MsgKind.REQ_SET_REBOOT, lambda b: b.reboot(3)),
])
def test_gateway_originated_builders_encode_cleanly(kind, build_call):
    b = FrameBuilderImpl(gcg_id=1)
    frame = build_call(b)
    assert frame.kind is kind
    assert frame.header.node_id == 3
    encoded = codec.encode_frame(frame, "strict")     # 인코딩이 실패 없이 되는가
    redecoded = codec.decode_frame(encoded, "strict", node_known=lambda n: True)
    assert not redecoded.violations
    assert redecoded.kind is kind


def test_device_control_encodes_cleanly_with_registry():
    """REQ_SET_DEVICE_CONTROL 은 registry 조회가 있어야 인코딩된다(F-137) —
    다른 4종과 파라미터화하지 않은 이유가 그것이다."""
    from siap.registry import NodeRegistry

    reg = NodeRegistry()
    reg.register(NodeProperty(sw_version=1, gcg_id=1, node_id=3, status=Status.NORMAL, num_devices=1),
                 (_dp(),))
    b = FrameBuilderImpl(gcg_id=1, registry=reg)
    frame = b.device_control(3, [(5, 1.0, ValueType.UINT)])
    assert frame.kind is MsgKind.REQ_SET_DEVICE_CONTROL
    encoded = codec.encode_frame(frame, "strict")
    redecoded = codec.decode_frame(encoded, "strict", node_known=lambda n: True)
    assert not redecoded.violations
    assert redecoded.kind is MsgKind.REQ_SET_DEVICE_CONTROL


def _dp():
    main = __import__("contracts.frame", fromlist=["DeviceMainInfo"]).DeviceMainInfo(
        device_id=5, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
        value_type=ValueType.FLOAT, value=25.3)
    return DeviceProperty(main=main, transfer_mode=TransferMode.PERIODIC, period=60,
                           lower_value=-10.0, upper_value=50.0, lower_limit=-40.0,
                           upper_limit=80.0, precision=0.1, status=Status.NORMAL)


def test_reply_builders_copy_msg_id_gcg_node_from_request_f040():
    b = FrameBuilderImpl(gcg_id=1)
    req = codec.decode_frame(bytes.fromhex("120000000100000000100003"), node_known=lambda n: True)
    for reply in (
        b.res_set_node_property(req, RSC.SUCCESS),
        b.res_set_device_property(req, RSC.SUCCESS),
        b.res_set_node_device_property_all(req, RSC.SUCCESS),
        b.res_set_msg_flow_control_profile(req, RSC.SUCCESS),
        b.ack(req),
    ):
        assert reply.header.msg_id == req.header.msg_id
        assert reply.header.gcg_id == req.header.gcg_id
        assert reply.header.node_id == req.header.node_id


def test_res_set_connection_success_requires_node_property():
    b = FrameBuilderImpl(gcg_id=1)
    req = codec.decode_frame(bytes.fromhex("120000000100000000100003"), node_known=lambda n: True)
    with pytest.raises(ValueError):
        b.res_set_connection(req, RSC.SUCCESS)          # node=None 인데 SUCCESS


def test_res_set_connection_error_path_is_valid_wire_frame():
    b = FrameBuilderImpl(gcg_id=1)
    req = codec.decode_frame(bytes.fromhex("120000000100000000100003"), node_known=lambda n: True)
    err = b.res_set_connection(req, RSC.INVALID_GCG_ID)
    encoded = codec.encode_frame(err, "strict")
    redecoded = codec.decode_frame(encoded, "strict", node_known=lambda n: True)
    assert not redecoded.violations
    assert redecoded.rsc == RSC.INVALID_GCG_ID


@pytest.mark.parametrize("rsc", [RSC.SUCCESS, RSC.INVALID_NODE_ID])
def test_res_set_connection_fake_and_real_payloads_match_f208(rsc):
    """F-208 — Protocol 설명을 다시 '오류면 RSC 1byte만'으로 바꾸거나
    Fake/실제 빌더 중 하나만 고정부를 줄이면 payload byte 대조가 깨진다."""
    req = codec.decode_frame(
        bytes.fromhex("120000000100000000100003"),
        node_known=lambda n: True,
    )
    node = (NodeProperty(sw_version=7, gcg_id=1, node_id=3,
                         status=Status.NORMAL, num_devices=1)
            if rsc == RSC.SUCCESS else None)
    devices = (_dp(),) if rsc == RSC.SUCCESS else ()
    fake = FakeFrameBuilder(gcg_id=1).res_set_connection(
        req, rsc, node=node, devices=devices)
    real = FrameBuilderImpl(gcg_id=1).res_set_connection(
        req, rsc, node=node, devices=devices)

    expected_len = 9 + 30 * len(devices)
    assert fake.header.payload_len == real.header.payload_len == expected_len
    assert fake.node_property == real.node_property
    assert fake.device_properties == real.device_properties
    assert codec.encode_frame(fake, "strict")[12:] == codec.encode_frame(real, "strict")[12:]


def test_error_response_returns_none_for_notify_f040():
    """위반 Notify 에는 회신하지 않는다 — ACK 는 오류를 실을 수단이 없다."""
    b = FrameBuilderImpl(gcg_id=1)
    # 직접 NOTI_KEEP_ALIVE Frame 을 만들어 kind 만으로 reply_kind() 분기를 확인한다.
    from contracts.frame import Frame, Header
    hdr = Header(version=0x12, msg_type=0x0803, trans_type=0, msg_id=1,
                 payload_len=0, gcg_id=1, node_id=3)
    noti = Frame(header=hdr, kind=MsgKind.NOTI_KEEP_ALIVE)
    assert b.error_response(noti, RSC.INVALID_VERSION) is None


def test_error_response_returns_none_for_unresolved_kind():
    from contracts.frame import Frame, Header
    hdr = Header(version=0x99, msg_type=0x0000, trans_type=0, msg_id=1,
                 payload_len=0, gcg_id=1, node_id=3)
    unresolved = Frame(header=hdr, kind=None)
    b = FrameBuilderImpl(gcg_id=1)
    assert b.error_response(unresolved, RSC.INVALID_VERSION) is None


def test_device_control_looks_up_subtype_from_registry():
    """FrameBuilder.device_control() 시그니처는 dev_type/subtype 을 받지
    않는다 — registry 가 있으면 실제 값을 채워야 한다(발견 사항 코멘트 참조)."""
    from siap.registry import NodeRegistry

    reg = NodeRegistry()
    reg.register(NodeProperty(sw_version=1, gcg_id=1, node_id=3, status=Status.NORMAL, num_devices=1),
                 (_dp(),))                              # _dp() 의 device_id=5, TEMPERATURE, SENSOR

    b = FrameBuilderImpl(gcg_id=1, registry=reg)
    frame = b.device_control(3, [(5, 1.0, ValueType.UINT)])
    dmi = frame.device_main_infos[0]
    assert dmi.dev_type == DevType.SENSOR
    assert dmi.subtype == int(Subtype.TEMPERATURE)


def test_device_control_fails_without_registry_f137():
    """F-137 — registry 가 없으면 ACTUATOR/WINDOW_OPENER 로 조용히 대체하지
    않고 실패한다(합성 데이터로 실제 제어 프레임을 만들지 않는다)."""
    b = FrameBuilderImpl(gcg_id=1)                      # registry=None
    with pytest.raises(ValueError):
        b.device_control(3, [(5, 1.0, ValueType.UINT)])


def test_device_control_fails_for_unregistered_device_f137():
    """F-137 — registry 는 있지만 그 device_id 가 없으면 역시 실패한다."""
    from siap.registry import NodeRegistry

    reg = NodeRegistry()
    reg.register(NodeProperty(sw_version=1, gcg_id=1, node_id=3, status=Status.NORMAL, num_devices=1),
                 (_dp(),))                              # device_id=5 만 등록됨
    b = FrameBuilderImpl(gcg_id=1, registry=reg)
    with pytest.raises(ValueError):
        b.device_control(3, [(99, 1.0, ValueType.UINT)])   # 존재하지 않는 device_id
