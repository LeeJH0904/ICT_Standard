"""
sim/_wire.py — 가상 노드 전용 독립 SIAP 바이트 인코더/디코더.

`sim/virtual_node.py`가 만드는 프레임은 `siap/codec.py`를 재사용하지 않고 이
파일이 독립적으로 만든다 — 같은 코덱을 쓰면 인코더 버그가 서로 상쇄되어 드러나지
않기 때문이다. 그래서 비트 패킹 기법도 의도적으로 다르게 짠다: `codec.py`는 바이트
배열에 비트 포인터를 옮겨가며 쓰지만, 이 파일은 파이썬 big int 누산기 하나에
필드를 왼쪽으로 밀어 넣는다. 결과 바이트는 같아야 하지만 그 결과에 이르는 절차는
다르다(이 동일성 대조 자체가 상호운용성 증거다).

`sim/` 전용이다 — `siap/`·`backend/`는 이 파일을 참조하지 않는다. 인코딩 규칙:
big-endian(network byte order), FLOAT는 IEEE-754 single precision 4byte, 가변
요소 개수 N은 Payload Length 역산.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════
#  wire code — 표 7-2/7-3/7-4 (strict 모드). contracts/frame.py::WIRE_CODE
#  와 값은 같을 수밖에 없다(같은 표준 조항의 결과) — 여기서는 그 표를 import
#  하지 않고 이 파일 안에서 다시 적는다(독립 재기술).
# ═══════════════════════════════════════════════════════════════
MT_REQ_SET_CONNECTION = 0x0000       # 표 7-2, 8.1.1
MT_REQ_SET_NODE_DEVICE_PROPERTY_ALL = 0x0005  # 표 7-2, 8.1.3.3 (노드→GCG)
MT_REQ_SET_DEVICE_CONTROL = 0x000C   # 표 7-2, 8.1.5
MT_RES_SET_CONNECTION = 0x0400       # 표 7-3
MT_RES_SET_NODE_DEVICE_PROPERTY_ALL = 0x0405  # 표 7-3, 8.1.3.3
MT_RES_SET_DEVICE_CONTROL = 0x040C   # 표 7-3
MT_NOTI_DEVICE_VALUE = 0x0800        # 표 7-4 (NOTI_ERROR 와 코드 중복)
MT_NOTI_DISCONNECT = 0x0801          # 표 7-4
MT_NOTI_KEEP_ALIVE = 0x0803          # 표 7-4
MT_ACK = 0x0C00                      # 6.2.2

TRANS_UNICAST = 0x00                 # 표 7-6

RSC_SUCCESS = 0x00                   # 표 7-10
RSC_INVALID_NODE_ID = 0x02           # 표 7-10
RSC_INVALID_DEVICE_ID = 0x04         # 표 7-10
RSC_INVALID_DEVICE_TYPE = 0x05       # 표 7-10

DEV_SENSOR = 0x00                    # 표 7-14
DEV_ACTUATOR = 0x01

VT_INT = 0x00                        # 표 7-14
VT_UINT = 0x01
VT_FLOAT = 0x02

TM_PERIODIC = 0x00                   # 표 7-15 Transfer Mode
TM_EVENT = 0x01
TM_BOTH = 0x02

STATUS_NORMAL = 0x00                 # 표 7-13/7-15 Status

HEADER_BYTES = 12                    # 96bit, 그림 7-1
NP_BYTES = 8                         # 64bit, 표 7-13. REQ_SET_NODE_DEVICE_PROPERTY_ALL 의 고정부.
DMI_BYTES = 7                        # 56bit, 표 7-14
DP_BYTES = 30                        # 240bit, 표 7-15
RSC_BYTES = 1


# ═══════════════════════════════════════════════════════════════
#  비트 누산기 — codec.py 의 바이트배열+포인터 방식과 다른 독립 구현
# ═══════════════════════════════════════════════════════════════
class _Writer:
    __slots__ = ("_acc", "_nbits")

    def __init__(self) -> None:
        self._acc = 0
        self._nbits = 0

    def put(self, value: int, nbits: int) -> "_Writer":
        if value < 0 or value >= (1 << nbits):
            raise ValueError(f"value={value} 가 {nbits}bit 범위를 벗어남")
        self._acc = (self._acc << nbits) | value
        self._nbits += nbits
        return self

    def bytes(self) -> bytes:
        if self._nbits % 8:
            raise ValueError(f"바이트 경계에 정렬되지 않음 (누적 {self._nbits}bit)")
        return self._acc.to_bytes(self._nbits // 8, "big")


class _Reader:
    __slots__ = ("_acc", "_total", "_pos")

    def __init__(self, data: bytes) -> None:
        self._acc = int.from_bytes(data, "big")
        self._total = len(data) * 8
        self._pos = 0

    def get(self, nbits: int) -> int:
        if self._pos + nbits > self._total:
            raise ValueError("버퍼 길이를 넘는 필드 읽기 시도")
        shift = self._total - self._pos - nbits
        val = (self._acc >> shift) & ((1 << nbits) - 1)
        self._pos += nbits
        return val


def float_to_raw(f: float) -> int:
    """IEEE-754 single 비트패턴 → uint32."""
    return struct.unpack(">I", struct.pack(">f", f))[0]


def raw_to_float(raw: int) -> float:
    return struct.unpack(">f", struct.pack(">I", raw & 0xFFFFFFFF))[0]


# ═══════════════════════════════════════════════════════════════
#  헤더 (그림 7-1, 96bit)
# ═══════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class WireHeader:
    version: int
    msg_type: int
    trans_type: int
    msg_id: int
    payload_len: int
    gcg_id: int
    node_id: int


def encode_header(h: WireHeader) -> bytes:
    w = _Writer()
    w.put(h.version, 8).put(h.msg_type, 14).put(h.trans_type, 2)
    w.put(h.msg_id, 16).put(h.payload_len, 16)
    w.put(h.gcg_id, 20).put(h.node_id, 20)
    return w.bytes()


def decode_header(data: bytes) -> WireHeader:
    if len(data) < HEADER_BYTES:
        raise ValueError(f"헤더는 {HEADER_BYTES}byte 필요, 실제 {len(data)}byte")
    r = _Reader(data[:HEADER_BYTES])
    return WireHeader(
        version=r.get(8), msg_type=r.get(14), trans_type=r.get(2),
        msg_id=r.get(16), payload_len=r.get(16),
        gcg_id=r.get(20), node_id=r.get(20),
    )


# ═══════════════════════════════════════════════════════════════
#  DEVICE_MAIN_INFO (표 7-14, 56bit)
# ═══════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class WireDMI:
    device_id: int
    dev_type: int
    subtype: int
    value_type: int
    value: int   # 32bit raw — INT(2의 보수)/UINT/FLOAT 비트패턴을 그대로 담는다


def encode_dmi(d: WireDMI) -> bytes:
    w = _Writer()
    w.put(d.device_id, 8).put(d.dev_type, 1).put(d.subtype, 8)
    w.put(d.value_type, 2).put(0, 5)            # Reserved — 송신 시 0 (표 7-14)
    w.put(d.value & 0xFFFFFFFF, 32)
    return w.bytes()


def decode_dmi(data: bytes) -> WireDMI:
    if len(data) < DMI_BYTES:
        raise ValueError(f"DEVICE_MAIN_INFO 는 {DMI_BYTES}byte 필요, 실제 {len(data)}byte")
    r = _Reader(data[:DMI_BYTES])
    device_id = r.get(8)
    dev_type = r.get(1)
    subtype = r.get(8)
    value_type = r.get(2)
    r.get(5)                                     # Reserved — 수신 시 무시
    value = r.get(32)
    return WireDMI(device_id, dev_type, subtype, value_type, value)


# ═══════════════════════════════════════════════════════════════
#  NODE_PROPERTY (표 7-13, 64bit) · DEVICE_PROPERTY (표 7-15, 240bit)
# ═══════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class WireNP:
    sw_version: int
    gcg_id: int
    node_id: int
    status: int
    num_devices: int


def encode_np(n: WireNP) -> bytes:
    w = _Writer()
    w.put(n.sw_version, 8).put(n.gcg_id, 20).put(n.node_id, 20)
    w.put(n.status, 8).put(n.num_devices, 8)
    return w.bytes()


@dataclass(frozen=True)
class WireDP:
    """USER DEPENDENT 5필드(lower/upper_value·lower/upper_limit·precision)는
    main.value_type 을 따른다. 이 필드들은 이미 그 규칙대로 packing된 32bit raw
    값을 받는다 — WireDMI.value 와 같은 관례(INT 는 2의 보수, FLOAT 는
    `float_to_raw()` 결과를 호출부가 미리 넣는다)."""
    main: WireDMI
    transfer_mode: int      # 2bit — TM_PERIODIC/TM_EVENT/TM_BOTH
    period: int              # 14bit — sec
    lower_value: int         # 32bit raw
    upper_value: int         # 32bit raw
    lower_limit: int         # 32bit raw
    upper_limit: int         # 32bit raw
    precision: int           # 32bit raw
    status: int              # 8bit — STATUS_NORMAL 등


def encode_dp(d: WireDP) -> bytes:
    """siap/codec.py::encode_dp() 와 같은 필드 순서·비트폭이지만 독립 구현이다
    (인코더 버그 상쇄 방지, 이 파일 머리말 참고)."""
    w = _Writer()
    w.put(d.main.device_id, 8).put(d.main.dev_type, 1).put(d.main.subtype, 8)
    w.put(d.main.value_type, 2).put(0, 5)               # Reserved — 송신 시 0
    w.put(d.main.value & 0xFFFFFFFF, 32)
    w.put(d.transfer_mode, 2).put(d.period, 14)
    w.put(d.lower_value & 0xFFFFFFFF, 32).put(d.upper_value & 0xFFFFFFFF, 32)
    w.put(d.lower_limit & 0xFFFFFFFF, 32).put(d.upper_limit & 0xFFFFFFFF, 32)
    w.put(d.precision & 0xFFFFFFFF, 32).put(d.status, 8)
    return w.bytes()


# ═══════════════════════════════════════════════════════════════
#  가상 노드가 실제로 만드는 프레임 5종
# ═══════════════════════════════════════════════════════════════
def build_req_set_connection(msg_id: int, gcg_id: int, node_id: int) -> bytes:
    """8.1.1 — 연결 요청. 페이로드 없음(N01 과 동일 형식)."""
    h = WireHeader(version=0x12, msg_type=MT_REQ_SET_CONNECTION, trans_type=TRANS_UNICAST,
                   msg_id=msg_id, payload_len=0, gcg_id=gcg_id, node_id=node_id)
    return encode_header(h)


def build_req_set_node_device_property_all(msg_id: int, gcg_id: int, node_id: int,
                                            node_property: WireNP, devices: list[WireDP]) -> bytes:
    """8.1.3.3 — 노드→GCG. 노드가 자신의 전체 디바이스 구성(NODE_PROPERTY +
    DEVICE_PROPERTY×N)을 선언한다. `REQ_SET_CONNECTION`은 페이로드가 없어 이
    역할을 할 수 없다 — 연결 성공 직후 세션마다 1회 이 메시지로 선언한다."""
    body = encode_np(node_property) + b"".join(encode_dp(d) for d in devices)
    h = WireHeader(version=0x12, msg_type=MT_REQ_SET_NODE_DEVICE_PROPERTY_ALL,
                   trans_type=TRANS_UNICAST, msg_id=msg_id, payload_len=len(body),
                   gcg_id=gcg_id, node_id=node_id)
    return encode_header(h) + body


def build_noti_device_value(msg_id: int, gcg_id: int, node_id: int, dmis: list[WireDMI]) -> bytes:
    """8.2.1.2 — DEVICE_MAIN_INFO × N (N34 형식과 동일)."""
    body = b"".join(encode_dmi(d) for d in dmis)
    h = WireHeader(version=0x12, msg_type=MT_NOTI_DEVICE_VALUE, trans_type=TRANS_UNICAST,
                   msg_id=msg_id, payload_len=len(body), gcg_id=gcg_id, node_id=node_id)
    return encode_header(h) + body


def build_noti_keep_alive(msg_id: int, gcg_id: int, node_id: int) -> bytes:
    """8.2.1.5 — 페이로드 없음."""
    h = WireHeader(version=0x12, msg_type=MT_NOTI_KEEP_ALIVE, trans_type=TRANS_UNICAST,
                   msg_id=msg_id, payload_len=0, gcg_id=gcg_id, node_id=node_id)
    return encode_header(h)


def build_res_set_device_control(msg_id: int, gcg_id: int, node_id: int, rsc: int = RSC_SUCCESS) -> bytes:
    """8.1.5 — 제어 요청에 대한 응답. RSC 1byte 뿐(REQ 의 msg_id 를 그대로 복사)."""
    body = _Writer().put(rsc, 8).bytes()
    h = WireHeader(version=0x12, msg_type=MT_RES_SET_DEVICE_CONTROL, trans_type=TRANS_UNICAST,
                   msg_id=msg_id, payload_len=len(body), gcg_id=gcg_id, node_id=node_id)
    return encode_header(h) + body


# ═══════════════════════════════════════════════════════════════
#  가상 노드가 실제로 읽는 프레임 4종 — RES_SET_CONNECTION /
#  RES_SET_NODE_DEVICE_PROPERTY_ALL / ACK / REQ_SET_DEVICE_CONTROL
# ═══════════════════════════════════════════════════════════════
def decode_res_set_connection(payload: bytes) -> int:
    """RSC 1byte 만 본다 — 가상 노드는 게이트웨이가 회신한 NODE_PROPERTY 를
    그대로 신뢰할 뿐 재해석하지 않는다(연결 성사 여부만 필요)."""
    if not payload:
        raise ValueError("RES_SET_CONNECTION payload 가 비어 있음(RSC 최소 1byte 필요)")
    return payload[0]


def decode_res_set_node_device_property_all(payload: bytes) -> int:
    """RSC 1byte 만 본다 — `decode_res_set_connection()`과 같은 이유로 그 이상을
    재해석하지 않는다."""
    if not payload:
        raise ValueError("RES_SET_NODE_DEVICE_PROPERTY_ALL payload 가 비어 있음(RSC 최소 1byte 필요)")
    return payload[0]


def decode_req_set_device_control(payload: bytes) -> list[WireDMI]:
    """DEVICE_MAIN_INFO × N (N = payload_len // 7)."""
    if len(payload) % DMI_BYTES:
        raise ValueError(f"REQ_SET_DEVICE_CONTROL payload 길이({len(payload)})가 "
                          f"{DMI_BYTES}의 배수가 아님")
    return [decode_dmi(payload[i:i + DMI_BYTES]) for i in range(0, len(payload), DMI_BYTES)]
