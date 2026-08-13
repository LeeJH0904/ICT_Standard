"""개발용 대역 SiapLink — Frame_구조_명세서.md §7 "다음 단계" 1항.

실제 게이트웨이(siap/link.py, 단계 3에서 구현)가 아직 없어도 backend/·web/이
`SiapLink` Protocol(contracts/siap_iface.py)에 기대어 작성·단위테스트될 수 있게
하는 대역체다. 서비스 계층은 이 파일이 아니라 Protocol만 참조해야 하며(계층
규칙, CLAUDE.md §2.2), 이 파일은 그 Protocol을 구조적으로 만족하는 예시일 뿐
production 경로에 배선되지 않는다.

CLAUDE.md §1-1 — project_code/ 전체에서 합성 데이터(난수·주기함수로 만든 가짜
수치)를 금지한다. 이 대역체는 상태를 갖지 않는 빈 registry로 시작하며, 어떤
수치도 꾸며내지 않는다. 실제 프레임 흐름 검증은 골든 벡터를 재생하는
sim/replayer.py(단계 4)의 몫이다.

단계 6 — `FakeFrameBuilder`를 추가했다. `FrameBuilder` Protocol도
`contracts/siap_iface.py`에 있어(§2.2가 backend/에 허용하는 두 참조 대상 중
하나) `backend/tests/`·`tools/gate_e2e.py`·`tools/route_verify.py`가 실제
`siap/build.py`(FrameBuilderImpl) 없이도 `services/fcs.py`·`services/ems.py`를
단위테스트할 수 있다.
"""
from __future__ import annotations

from typing import Iterator

try:                    # F-025 — 패키지로 import될 때
    from .frame import (
        DeviceMainInfo, DeviceProperty, DevType, Frame, Header, LAYOUT, Mode,
        MsgKind, MsgControlProfile, NodeProperty, RSC, RESPONSE_OF, Status,
        TransType, ValueType, reply_kind,
    )
except ImportError:     # 스크립트로 직접 실행될 때
    from frame import (
        DeviceMainInfo, DeviceProperty, DevType, Frame, Header, LAYOUT, Mode,
        MsgKind, MsgControlProfile, NodeProperty, RSC, RESPONSE_OF, Status,
        TransType, ValueType, reply_kind,
    )

RunMode = str  # siap_iface.RunMode 와 동일한 리터럴 집합. 순환 import 회피용 별칭.


class FakeSiapLink:
    """`SiapLink` Protocol 을 만족하는 개발용 대역.

    duck typing 으로 만족한다 — `Protocol`을 상속하지 않아도 메서드 시그니처가
    같으면 구조적으로 호환된다(PEP 544). 등록 노드·디바이스는 항상 빈 상태로
    시작한다: 이 파일의 역할은 "인터페이스가 호출 가능하다"이지 "그럴듯한 데이터를
    보여준다"가 아니다."""

    def __init__(self) -> None:
        self._started = False
        self._proto_mode: Mode = "strict"
        self._registry: dict[int, NodeProperty] = {}
        self._devices: dict[int, tuple[DeviceMainInfo, ...]] = {}
        self._stats: dict[str, int | float] = {
            "rx": 0, "tx": 0, "violations": 0, "retries": 0, "uptime": 0.0,
        }

    # ── SiapLink ────────────────────────────────────────────────
    def start(self, run_mode: RunMode, *, proto_mode: Mode = "strict", **opts) -> None:
        self._started = True
        self._proto_mode = proto_mode

    def stop(self) -> None:
        self._started = False

    def recv(self) -> Iterator[Frame]:
        """대역체는 능동적으로 프레임을 만들어내지 않는다 — 빈 스트림.
        노드 시뮬레이션이 필요하면 sim/virtual_node.py(단계 4)를 쓴다."""
        return iter(())

    def send(self, frame: Frame, timeout: float | None = None) -> Frame | None:
        """대응 관계만 흉내낸다: 등록된 Request 에는 즉시 SUCCESS Response,
        Notify 에는 None. 페이로드는 만들지 않는다 — RSC 뿐이다."""
        self._stats["tx"] += 1
        res_kind = RESPONSE_OF.get(frame.kind) if frame.kind else None
        if res_kind is None:
            return None
        from dataclasses import replace
        header = replace(
            frame.header,
            msg_type=0,   # 실제 코드 배정은 siap/build.py(단계 3)의 몫
            payload_len=1,
        )
        return Frame(header=header, kind=res_kind, rsc=RSC.SUCCESS, raw=b"")

    def registry(self) -> dict[int, NodeProperty]:
        return dict(self._registry)

    def devices(self, node_id: int) -> tuple[DeviceMainInfo, ...]:
        return self._devices.get(node_id, ())

    def stats(self) -> dict:
        return dict(self._stats)


class FakeFrameBuilder:
    """`FrameBuilder` Protocol 을 만족하는 개발용/테스트용 대역.

    실제 SIAP 인코딩 규칙(siap/build.py::FrameBuilderImpl)을 흉내내지
    않는다 — `siap.codec.SIAP_VERSION` 등 siap/ 내부 심볼은 여기서 참조할
    수 없다(계층 규칙, CLAUDE.md §2.2). 대신 `Frame` 객체의 형태(header.msg_id
    발번, kind 채우기)만 맞춰 `services/`·`api.py` 가 실제 프로토콜 계층 없이
    단위테스트되게 한다.

    `device_control()` — 실물 `FrameBuilderImpl`은 대상 (node_id, device_id)의
    실제 Type/Subtype 을 `NodeRegistry` 에서 찾아 채운다(F-137, 임의 종류로
    대체하지 않는다). 이 대역체도 같은 원칙을 지킨다 — `device_kinds`에
    미리 등록해 두지 않은 (node_id, device_id) 로 호출하면 예외를 낸다."""

    def __init__(self, gcg_id: int = 1) -> None:
        self._gcg_id = gcg_id
        self._msg_id = 0
        #: 테스트가 채운다: (node_id, device_id) -> (dev_type, subtype)
        self.device_kinds: dict[tuple[int, int], tuple[DevType, int]] = {}

    def _next_id(self) -> int:
        v = self._msg_id
        self._msg_id = (v + 1) & 0xFFFF
        return v

    def _header(self, kind: MsgKind, node_id: int, payload_len: int) -> Header:
        # msg_type 은 실제 전송 코드가 아니라 자리표시(0) — 실제 배정은
        # siap/build.py(단계 3)의 몫이다. FakeSiapLink.send() 와 같은 원칙.
        return Header(version=0x12, msg_type=0, trans_type=int(TransType.UNICAST),
                      msg_id=self._next_id(), payload_len=payload_len,
                      gcg_id=self._gcg_id, node_id=node_id)

    def _reply_header(self, req: Frame, payload_len: int) -> Header:
        return Header(version=0x12, msg_type=0, trans_type=req.header.trans_type,
                      msg_id=req.header.msg_id, payload_len=payload_len,
                      gcg_id=req.header.gcg_id, node_id=req.header.node_id)

    # ── (1) 게이트웨이발 Request ──────────────────────────────
    def device_control(self, node_id: int,
                        commands: list[tuple[int, float, ValueType]]) -> Frame:
        infos = []
        for device_id, value, value_type in commands:
            kind = self.device_kinds.get((node_id, device_id))
            if kind is None:
                raise ValueError(
                    f"FakeFrameBuilder.device_control(node_id={node_id}): "
                    f"device_id={device_id} 가 device_kinds 에 없다 — 테스트가 먼저 등록해야 한다 (F-137과 같은 원칙)"
                )
            dev_type, subtype = kind
            infos.append(DeviceMainInfo(device_id=device_id, dev_type=dev_type,
                                         subtype=subtype, value_type=value_type, value=value))
        fixed, elem = LAYOUT[MsgKind.REQ_SET_DEVICE_CONTROL]
        header = self._header(MsgKind.REQ_SET_DEVICE_CONTROL, node_id, fixed + elem * len(infos))
        return Frame(header=header, kind=MsgKind.REQ_SET_DEVICE_CONTROL,
                     device_main_infos=tuple(infos))

    def get_device_value(self, node_id: int, device_ids: list[int]) -> Frame:
        fixed, elem = LAYOUT[MsgKind.REQ_GET_DEVICE_VALUE]
        header = self._header(MsgKind.REQ_GET_DEVICE_VALUE, node_id, fixed + elem * len(device_ids))
        return Frame(header=header, kind=MsgKind.REQ_GET_DEVICE_VALUE, device_ids=tuple(device_ids))

    def get_node_property(self, node_id: int) -> Frame:
        header = self._header(MsgKind.REQ_GET_NODE_PROPERTY, node_id, 0)
        return Frame(header=header, kind=MsgKind.REQ_GET_NODE_PROPERTY)

    def set_device_property(self, node_id: int, props: list[DeviceProperty]) -> Frame:
        fixed, elem = LAYOUT[MsgKind.REQ_SET_DEVICE_PROPERTY]
        header = self._header(MsgKind.REQ_SET_DEVICE_PROPERTY, node_id, fixed + elem * len(props))
        return Frame(header=header, kind=MsgKind.REQ_SET_DEVICE_PROPERTY,
                     device_properties=tuple(props))

    def reboot(self, node_id: int) -> Frame:
        header = self._header(MsgKind.REQ_SET_REBOOT, node_id, 0)
        return Frame(header=header, kind=MsgKind.REQ_SET_REBOOT)

    # ── (2) 노드발 메시지에 대한 즉시 회신 ─────────────────────
    def res_set_connection(self, req: Frame, rsc: RSC,
                            node: NodeProperty | None = None,
                            devices: tuple[DeviceProperty, ...] = ()) -> Frame:
        use_node = node or NodeProperty(sw_version=0, gcg_id=req.header.gcg_id,
                                         node_id=req.header.node_id, status=Status.UNKNOWN,
                                         num_devices=0)
        fixed, elem = LAYOUT[MsgKind.RES_SET_CONNECTION]
        header = self._reply_header(req, fixed + elem * len(devices))
        return Frame(header=header, kind=MsgKind.RES_SET_CONNECTION, rsc=rsc,
                     node_property=use_node, device_properties=tuple(devices))

    def _rsc_only_reply(self, req: Frame, kind: MsgKind, rsc: RSC) -> Frame:
        header = self._reply_header(req, 1)
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
        if rk is None or rk is MsgKind.ACK:
            return None
        if rk is MsgKind.RES_SET_CONNECTION:
            return self.res_set_connection(req, rsc)
        return self._rsc_only_reply(req, rk, rsc)

    def ack(self, req: Frame) -> Frame:
        header = self._reply_header(req, 0)
        return Frame(header=header, kind=MsgKind.ACK)
