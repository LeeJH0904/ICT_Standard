"""
SIAP 계층 인터페이스 — 게이트웨이 아래(프로토콜)와 위(서비스)의 경계.
구현체는 siap/link.py, 개발용 대역은 contracts/fake_link.py.
서비스 계층은 이 Protocol 외의 siap.* 내부 심볼을 참조하지 않는다.
"""
from __future__ import annotations
from typing import Protocol, Iterator, Literal
try:                    # 패키지로 import될 때
    from .frame import (Frame, MsgKind, NodeProperty, DeviceMainInfo,
                        DeviceProperty, MsgControlProfile, RSC,
                        ValueType, Subtype, Mode)
except ImportError:     # 스크립트로 직접 실행될 때
    from frame import (Frame, MsgKind, NodeProperty, DeviceMainInfo,
                       DeviceProperty, MsgControlProfile, RSC,
                       ValueType, Subtype, Mode)

RunMode = Literal["hardware", "replay", "simulate"]

class SiapLink(Protocol):
    def start(self, run_mode: RunMode, *, proto_mode: Mode = "strict", **opts) -> None:
        """전송 계층 개통.
        opts 예: port='/dev/ttyUSB0' | log='logs/session_01.jsonl' | host/port"""

    def stop(self) -> None: ...

    def recv(self) -> Iterator[Frame]:
        """수신 프레임 스트림 (블로킹 제너레이터).
        규격 위반 프레임도 예외 없이 violations가 채워진 Frame으로 나온다."""

    def send(self, frame: Frame, timeout: float | None = None) -> Frame | None:
        """Request → Response Frame 반환 / Notify → None.
        재전송·타임아웃은 MSG_CONTROL_PROFILE(0943 표 7-18)에 따라 내부 처리."""

    def registry(self) -> dict[int, NodeProperty]:
        """등록된 노드 { node_id: NodeProperty }. 0943 8.1.1 절차의 결과."""

    def devices(self, node_id: int) -> tuple[DeviceMainInfo, ...]: ...

    def stats(self) -> dict:
        """{'rx','tx','violations','retries','uptime'}"""


class FrameBuilder(Protocol):
    """서비스 계층이 0943 비트 배치를 몰라도 되게 하는 빌더. siap/build.py가 구현.

    두 묶음으로 나뉜다.
      (1) 게이트웨이발 Request — 화면·서비스가 능동적으로 보낸다. `link.send()` 경유.
      (2) 노드발 Request·Notify 에 대한 즉시 회신 — `siap/link.py` 안에서 만든다.
          회신 빌더는 모두 **원본 Frame(`req`)을 인자로 받는다.** 0943 7.2.2 에 따라
          `Message Identifier` 를 복사해야 하고, 헤더의 `GCG ID`·`Node ID` 도 수신값을
          그대로 되돌려야 노드가 매칭하기 때문이다.

    회신 담당을 `siap/link.py` 안에 둔 이유: `backend/ingest.handle()` 이 회신까지
    반환하면 `backend/` 가 이 `FrameBuilder` 를 알아야 해, "표준 해석은 프로토콜
    계층에만 둔다"는 계층 규칙을 어긴다.
    """

    # ── (1) 게이트웨이발 Request ──────────────────────────────
    def device_control(self, node_id: int,
                       commands: list[tuple[int, float, ValueType]]) -> Frame:
        """REQ_SET_DEVICE_CONTROL (8.1.5). commands=[(device_id, value, value_type)]"""

    def get_device_value(self, node_id: int, device_ids: list[int]) -> Frame:
        """REQ_GET_DEVICE_VALUE (8.1.4.4)"""

    def get_node_property(self, node_id: int) -> Frame:
        """REQ_GET_NODE_PROPERTY (8.1.4.1)"""

    def set_device_property(self, node_id: int,
                            props: list[DeviceProperty]) -> Frame:
        """REQ_SET_DEVICE_PROPERTY (8.1.3.2). DEVICE_PROPERTY x N (표 7-15, 30 byte 씩).

        0943 8.1.3.2 는 이 메시지를 **양방향**으로 규정하고 표 7-15 를 요청 메시지에
        담도록 한다 — 설정 API(`PATCH /api/v1/device-property`)가 프레임을 만드는
        게이트웨이발 경로다(`res_set_device_property()` 는 노드발 역방향 회신이라 이
        자리를 대신하지 못한다).

        `props` 의 각 요소가 대상 디바이스를 `device_main_info.device_id` 로 가리킨다."""

    def reboot(self, node_id: int) -> Frame:
        """REQ_SET_REBOOT (8.1.6)"""

    # ── 게이트웨이발 Request 중 **의도적으로 두지 않은 것** ─────
    #   0943 의 G→N Request 는 13종이다. 위 5종만 두는 이유를 적어 둔다.
    #   빌더가 없다는 것은 "이 프로젝트가 그 절차를 쓰지 않는다"는 선언이다.
    #
    #   REQ_SET_DEVICE_INIT (8.1.2.1) · _ALL (8.1.2.2)
    #       초기화는 노드 부팅 시 스스로 한다. 게이트웨이가 원격 초기화를 지시하는
    #       시나리오가 기능 3종에 없다.
    #   REQ_SET_NODE_PROPERTY (8.1.3.1) · REQ_SET_NODE_DEVICE_PROPERTY_ALL (8.1.3.3)
    #       노드 속성(S/W 버전·Status·Num. of Devices)은 노드가 보고하는 값이다.
    #       게이트웨이가 덮어쓰면 실제 상태와 어긋난다.
    #   REQ_SET_MSG_FLOW_CONTROL_PROFILE (8.1.3.4)
    #       프로파일은 연결 시 RES_SET_CONNECTION 으로 내려간다. 운영 중 변경은
    #       기능 3종 밖이다.
    #   REQ_GET_DEVICE_PROPERTY (8.1.4.2) · _NODE_DEVICE_PROPERTY_ALL (8.1.4.3)
    #   REQ_GET_MSG_FLOW_CONTROL_PROFILE (8.1.4.5)
    #       조회는 DB 가 정본이다. 노드에 되묻지 않는다.

    # ── (2) 노드발 메시지에 대한 즉시 회신 ─────────────────────
    def res_set_connection(self, req: Frame, rsc: RSC,
                           node: NodeProperty | None = None,
                           devices: tuple[DeviceProperty, ...] = ()) -> Frame:
        """RES_SET_CONNECTION (8.1.1). RSC + NODE_PROPERTY + DEVICE_PROPERTY×N.
        rsc != SUCCESS 이면 호출자가 넘긴 node·devices는 사용하지 않지만,
        LAYOUT의 9byte 고정부(RSC + 자리표시 NODE_PROPERTY, N=0)는 유지한다.
        표준에는 오류 RSC에서 응답 구조를 1byte로 줄인다는 규정이 없다."""

    def res_set_node_property(self, req: Frame, rsc: RSC) -> Frame:
        """RES_SET_NODE_PROPERTY (8.1.3.1 역방향). RSC 만."""

    def res_set_device_property(self, req: Frame, rsc: RSC) -> Frame:
        """RES_SET_DEVICE_PROPERTY (8.1.3.2 역방향). RSC 만."""

    def res_set_node_device_property_all(self, req: Frame, rsc: RSC) -> Frame:
        """RES_SET_NODE_DEVICE_PROPERTY_ALL (8.1.3.3 역방향). RSC 만."""

    def res_set_msg_flow_control_profile(self, req: Frame, rsc: RSC) -> Frame:
        """RES_SET_MSG_FLOW_CONTROL_PROFILE (8.1.3.4 역방향). RSC 만."""

    def error_response(self, req: Frame, rsc: RSC) -> Frame | None:
        """위반 Request 에 대한 오류 회신 (7.3.1).
        `frame.reply_kind(req.kind)` 로 대응 Response 종류를 정한다. 일반 응답은
        RSC만 싣고, RES_SET_CONNECTION은 LAYOUT의 9byte 고정부를 유지한다.
        회신 종류를 정할 수 없으면(해석 불가 msg_type, Notify) **None** 을 반환한다 —
        ACK 는 헤더뿐이라 오류를 실을 수단이 없다."""

    def ack(self, req: Frame) -> Frame:
        """ACK (8.2). 헤더만. msg_id·gcg_id·node_id 를 req 에서 복사한다 —
        0943 7.2.2 가 요구하는 복사 대상이 msg_id 하나가 아니므로 원본 Frame 을 받는다."""
