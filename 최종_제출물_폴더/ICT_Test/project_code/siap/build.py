"""
siap/build.py — FrameBuilder 구현 (contracts/siap_iface.py 의 Protocol).

두 묶음:
  (1) 게이트웨이발 Request 5종 — `link.send()` 경유. msg_id 는 이 파일이
      발번한다(0943 7.2.2 "0~65535 순환, 송신마다 +1, 65535 다음 0". 초기값
      0 — 0도 유효한 순번이다. 노드 측
      규칙과 대칭이 되도록 게이트웨이 쪽도 같은 규약을 쓴다).
  (2) 노드발 메시지에 대한 즉시 회신 7종 — `ingest.handle()` 의 반환값.
      msg_id·GCG ID·Node ID 를 원본 Frame 에서 그대로 복사한다(7.2.2) — 새로
      발번하지 않는다.

payload_len 은 `contracts/frame.py::LAYOUT` 에서 그대로 유도한다(고정부 +
요소크기×N) — codec.encode_frame() 이 실제 직렬화 시 다시 검증한다.
"""
from __future__ import annotations

import threading

try:                    # 패키지로 import될 때
    from contracts.frame import (
        DeviceMainInfo, DeviceProperty, DevType, Frame, Header, LAYOUT, MsgKind,
        NodeProperty, RSC, RSC_BYTES, Status, TransType, ValueType,
        reply_kind, wire_code,
    )
    from siap.codec import SIAP_VERSION
except ImportError:     # 스크립트로 직접 실행되거나 project_code 가 sys.path 밖일 때
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from contracts.frame import (
        DeviceMainInfo, DeviceProperty, DevType, Frame, Header, LAYOUT, MsgKind,
        NodeProperty, RSC, RSC_BYTES, Status, TransType, ValueType,
        reply_kind, wire_code,
    )
    from siap.codec import SIAP_VERSION


class MsgIdAllocator:
    """0943 7.2.2 원문 — "Message Identifier는 … '0'에서 '65535'까지 사용할
    수 있다. 일련번호는 데이터 전송 시마다 +1을 하며 만료되면 0부터 다시
    시작한다." 0을 건너뛰지 않는다 — 이전 버전은 "0은 미할당
    표시로 예약"이라며 노드 측 결정을 그대로 옮겼지만, 그 예약은
    `pending.kind==SIAP_KIND_NONE` 하나로 이미 충분한 "비어 있음" 판정을
    msg_id 에도 중복 적용한 근거 없는 결정이었다(node_state.c 쪽도로
    같이 고쳤다)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next = 0

    def next(self) -> int:
        with self._lock:
            v = self._next
            self._next = (v + 1) & 0xFFFF
            return v


class FrameBuilderImpl:
    """`FrameBuilder` Protocol 구현. `gcg_id` 는 이 게이트웨이가 대표하는
    GCG ID 하나로 고정한다(생성자 인자) — 프레임마다 다시 묻지 않는다.

    `registry`(선택) — `device_control()` 이 DEVICE_MAIN_INFO 의 dev_type·
    subtype 을 채우려면 대상 디바이스의 실제 종류를 알아야 한다. 넘겨주면
    `siap/registry.py::NodeRegistry.devices()` 에서 조회한다."""

    def __init__(self, gcg_id: int, mode: str = "strict", registry=None) -> None:
        self._gcg_id = gcg_id
        self._mode = mode
        self._registry = registry
        self._msg_id = MsgIdAllocator()

    def _wire(self, kind: MsgKind) -> int:
        return wire_code(kind, self._mode)

    def _header(self, kind: MsgKind, node_id: int, payload_len: int,
                trans_type: int = int(TransType.UNICAST)) -> Header:
        return Header(version=SIAP_VERSION, msg_type=self._wire(kind),
                      trans_type=trans_type, msg_id=self._msg_id.next(),
                      payload_len=payload_len, gcg_id=self._gcg_id, node_id=node_id)

    def _reply_header(self, req: Frame, kind: MsgKind, payload_len: int) -> Header:
        """msg_id·GCG ID·Node ID 를 원본에서 복사한다(7.2.2). 새로
        발번하면 노드가 중복 요청으로 처리한다(표준 미규정 → 자체 결정)."""
        if req.header is None:
            raise ValueError("header 가 없는 불완전 Frame 에는 회신할 수 없다")
        return Header(version=SIAP_VERSION, msg_type=self._wire(kind),
                      trans_type=req.header.trans_type, msg_id=req.header.msg_id,
                      payload_len=payload_len, gcg_id=req.header.gcg_id,
                      node_id=req.header.node_id)

    def _lookup_device_kind(self, node_id: int, device_id: int) -> tuple[DevType, int]:
        """`device_control()` 의 Protocol 시그니처는 `(device_id, value,
        value_type)` 만 받는다 — DEVICE_MAIN_INFO(표 7-14)는 `Type`·`Subtype`
        도 요구하는데 그 둘을 전달할 통로가 시그니처에 없다(발견 사항 —
        `contracts/siap_iface.py::FrameBuilder.device_control()` 이 애초에
        갖고 있던 간극이며, 이 파일에서 새로 만든 것이 아니다. 절차 대상
        여부는 사용자 보고 예정). `registry` 에서 그 노드의 실제
        DEVICE_MAIN_INFO 를 device_id 로 찾아 채운다.

        이전에는 registry 가 없거나 조회에 실패하면 `ACTUATOR +
        WINDOW_OPENER` 로 조용히 대체했다. 실제로 존재하지 않거나 확인 못 한
        디바이스 종류를 지어내 제어 프레임에 실으면, 엉뚱한 종류로 해석하는
        노드에 잘못된 제어값이 전달될 수 있다. registry 가 없거나 그 노드에
        `device_id` 가 없으면 조용히 넘어가지 않고 실패시킨다."""
        if self._registry is None:
            raise ValueError(
                f"device_control(node_id={node_id}): registry 가 주입되지 않아 "
                f"device_id={device_id} 의 실제 Type/Subtype 을 확인할 수 없다"
            )
        for dmi in self._registry.devices(node_id):
            if dmi.device_id == device_id:
                return dmi.dev_type, dmi.subtype
        raise ValueError(
            f"device_control(node_id={node_id}): device_id={device_id} 가 "
            f"registry 에 등록되어 있지 않다 — 임의 Type/Subtype 으로 대체하지 않는다"
        )

    # ── (1) 게이트웨이발 Request ──────────────────────────────
    def device_control(self, node_id: int,
                        commands: list[tuple[int, float, ValueType]]) -> Frame:
        infos = []
        for device_id, value, value_type in commands:
            dev_type, subtype = self._lookup_device_kind(node_id, device_id)
            infos.append(DeviceMainInfo(device_id=device_id, dev_type=dev_type,
                                         subtype=subtype, value_type=value_type,
                                         value=value))
        fixed, elem = LAYOUT[MsgKind.REQ_SET_DEVICE_CONTROL]
        header = self._header(MsgKind.REQ_SET_DEVICE_CONTROL, node_id,
                               fixed + elem * len(infos))
        return Frame(header=header, kind=MsgKind.REQ_SET_DEVICE_CONTROL,
                     device_main_infos=tuple(infos))

    def get_device_value(self, node_id: int, device_ids: list[int]) -> Frame:
        fixed, elem = LAYOUT[MsgKind.REQ_GET_DEVICE_VALUE]
        header = self._header(MsgKind.REQ_GET_DEVICE_VALUE, node_id,
                               fixed + elem * len(device_ids))
        return Frame(header=header, kind=MsgKind.REQ_GET_DEVICE_VALUE,
                     device_ids=tuple(device_ids))

    def get_node_property(self, node_id: int) -> Frame:
        header = self._header(MsgKind.REQ_GET_NODE_PROPERTY, node_id, 0)
        return Frame(header=header, kind=MsgKind.REQ_GET_NODE_PROPERTY)

    def set_device_property(self, node_id: int,
                             props: list[DeviceProperty]) -> Frame:
        fixed, elem = LAYOUT[MsgKind.REQ_SET_DEVICE_PROPERTY]
        header = self._header(MsgKind.REQ_SET_DEVICE_PROPERTY, node_id,
                               fixed + elem * len(props))
        return Frame(header=header, kind=MsgKind.REQ_SET_DEVICE_PROPERTY,
                     device_properties=tuple(props))

    def reboot(self, node_id: int) -> Frame:
        header = self._header(MsgKind.REQ_SET_REBOOT, node_id, 0)
        return Frame(header=header, kind=MsgKind.REQ_SET_REBOOT)

    # ── (2) 노드발 메시지에 대한 즉시 회신 ─────────────────────
    def res_set_connection(self, req: Frame, rsc: RSC,
                            node: NodeProperty | None = None,
                            devices: tuple[DeviceProperty, ...] = ()) -> Frame:
        if req.header is None:
            raise ValueError("header 가 없는 불완전 Frame 에는 회신할 수 없다")
        if rsc == RSC.SUCCESS:
            if node is None:
                raise ValueError("RSC.SUCCESS 인 RES_SET_CONNECTION 은 NodeProperty 가 필요하다")
            use_node, use_devices = node, tuple(devices)
        else:
            # 표준은 실패 시 페이로드 형태를 규정하지 않는다(표준 미규정). 이
            # 구현은 LAYOUT(고정부=RSC+NODE_PROPERTY, "N=0 허용")을 그대로
            # 따르고 자리표시 NodeProperty(N=0)를 채운다. "RSC 만 싣는다"는
            # "실제 디바이스 데이터를 담지 않는다"는
            # 뜻으로 해석했다. LAYOUT 자체를 바꾸지 않는 한 RES_SET_CONNECTION
            # 은 항상 RSC+NODE_PROPERTY(9byte) 고정부를 갖는다.
            use_node = NodeProperty(sw_version=0, gcg_id=req.header.gcg_id,
                                     node_id=req.header.node_id, status=Status.UNKNOWN,
                                     num_devices=0)
            use_devices = ()
        fixed, elem = LAYOUT[MsgKind.RES_SET_CONNECTION]
        header = self._reply_header(req, MsgKind.RES_SET_CONNECTION,
                                     fixed + elem * len(use_devices))
        return Frame(header=header, kind=MsgKind.RES_SET_CONNECTION, rsc=rsc,
                     node_property=use_node, device_properties=use_devices)

    def _rsc_only_reply(self, req: Frame, kind: MsgKind, rsc: RSC) -> Frame:
        header = self._reply_header(req, kind, RSC_BYTES)
        return Frame(header=header, kind=kind, rsc=rsc)

    def res_set_node_property(self, req: Frame, rsc: RSC) -> Frame:
        return self._rsc_only_reply(req, MsgKind.RES_SET_NODE_PROPERTY, rsc)

    def res_set_device_property(self, req: Frame, rsc: RSC) -> Frame:
        return self._rsc_only_reply(req, MsgKind.RES_SET_DEVICE_PROPERTY, rsc)

    def res_set_node_device_property_all(self, req: Frame, rsc: RSC) -> Frame:
        return self._rsc_only_reply(req, MsgKind.RES_SET_NODE_DEVICE_PROPERTY_ALL, rsc)

    def res_set_msg_flow_control_profile(self, req: Frame, rsc: RSC) -> Frame:
        return self._rsc_only_reply(req, MsgKind.RES_SET_MSG_FLOW_CONTROL_PROFILE, rsc)

    def error_response(self, req: Frame, rsc: RSC) -> Frame | None:
        rk = reply_kind(req.kind)
        if rk is None:
            return None                                   # 해석 불가 msg_type — 어떤 Response 인지 못 정한다
        if rk is MsgKind.ACK:
            return None                                    # ACK 는 헤더뿐 — 오류를 실을 수단이 없다
        if rk is MsgKind.RES_SET_CONNECTION:
            return self.res_set_connection(req, rsc)
        if rk is MsgKind.RES_SET_NODE_PROPERTY:
            return self.res_set_node_property(req, rsc)
        if rk is MsgKind.RES_SET_DEVICE_PROPERTY:
            return self.res_set_device_property(req, rsc)
        if rk is MsgKind.RES_SET_NODE_DEVICE_PROPERTY_ALL:
            return self.res_set_node_device_property_all(req, rsc)
        if rk is MsgKind.RES_SET_MSG_FLOW_CONTROL_PROFILE:
            return self.res_set_msg_flow_control_profile(req, rsc)
        return None

    def ack(self, req: Frame) -> Frame:
        header = self._reply_header(req, MsgKind.ACK, 0)
        return Frame(header=header, kind=MsgKind.ACK)
