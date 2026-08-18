"""
SIAP 코덱 — bytes ↔ Frame (contracts/frame.py 기준, TTAK.KO-10.0943 7장).

firmware/core/bitpack.c · firmware/core/siap_frame.c 를 Python 으로 옮긴 것이다
("C 를 먼저 쓰고 Python 으로 옮긴다" — 반대 방향은 AVR 제약을
놓친다). 분기 구조를 C 원본과 줄 단위로 대응시킨다 — 여기서
갈리면 C·Python 두 구현이 상호운용성 증거가 되지 못한다.

계약("예외를 던지지 않는다"):
  공개 decode_frame() 은 불완전 입력도 raw 와 INVALID_FORMAT 을 담은 Frame 으로
  반환한다. 헤더 12byte 미달이면 알 수 없는 값을 합성하지 않고 header=None 이다.
  IncompleteFrameError 는 Decoder 가 다음 바이트를 기다리기 위한 내부 신호로만 쓴다.
  encode_frame() 은 ValueRangeError(및 그 하위인 구성 오류)를 던질 수 있다 —
  이건 "우리가 잘못된 Frame 을 만들려 했다"는 프로그래밍 오류이지 수신
  프레임의 표준 위반이 아니므로 예외로 남긴다(호출자는 build.py 뿐이다).

core/ 와 달리 이 파일은 host(CPython) 에서 돈다 — AVR SRAM 제약이 없으므로
51byte 슬라이딩 윈도우 대신 파이썬다운 bytearray 누적을 쓴다("C 를 파이썬답게
다시 쓰지 않는다"는 *분기 구조*를 말하는 것이지, 임베디드
메모리 최적화까지 옮기라는 뜻은 아니다).
"""
from __future__ import annotations

import struct
from typing import Callable, Iterator

try:                    # 패키지로 import될 때
    from contracts.frame import (
        DeviceMainInfo, DeviceProperty, DevType, Frame, Header, Mode, MsgControlProfile,
        MsgKind, NodeProperty, NEC, RSC, Status, Subtype, TransferMode, ValueType,
        Violation, HEADER_BYTES, NP_BYTES, DMI_BYTES, DP_BYTES, MCP_BYTES,
        RSC_BYTES, NEC_BYTES, DID_BYTES, WIRE_CODE, WIRE_CODE_EXT,
        LAYOUT, element_count,
    )
except ImportError:     # 스크립트로 직접 실행되거나 project_code 가 sys.path 밖일 때
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from contracts.frame import (
        DeviceMainInfo, DeviceProperty, DevType, Frame, Header, Mode, MsgControlProfile,
        MsgKind, NodeProperty, NEC, RSC, Status, Subtype, TransferMode, ValueType,
        Violation, HEADER_BYTES, NP_BYTES, DMI_BYTES, DP_BYTES, MCP_BYTES,
        RSC_BYTES, NEC_BYTES, DID_BYTES, WIRE_CODE, WIRE_CODE_EXT,
        LAYOUT, element_count,
    )

SIAP_VERSION = 0x12   # v1.2, 7.2.1 — firmware/core/siap_types.h SIAP_VERSION 과 동일


class IncompleteFrameError(Exception):
    """Decoder 전용 스트리밍 버퍼링 신호.

    공개 decode_frame() 에서는 노출하지 않으며, Decoder.feed() 가 조각을
    위반으로 너무 일찍 방출하지 않도록 내부 디코드 경로에서만 사용한다."""


class ValueRangeError(ValueError):
    """pack_value() 계열이 던지는 유일한 예외.
    이 문장이 참이어야 encode_frame() 의 오류 경로가 단순하게 유지된다."""


# ═══════════════════════════════════════════════════════════════
#  0. 비트 read/write — bitpack.c(bp_write/bp_read/bp_write_f32/bp_read_f32) 포팅
#     MSB-first, big-endian(표준 미규정 → 자체 결정).
# ═══════════════════════════════════════════════════════════════

class BitWriter:
    """bp_write 포팅. 범위 초과 시 아무것도 기록하지 않고 False 를 돌려준다
    (마스킹 래핑 금지) — bitpack.c 의 "실패 시 buf 도 *bitpos 도 바뀌지
    않는다" 계약을 그대로 지킨다(1비트라도 쓴 뒤에 실패하면 이미 쓴 비트를
    되돌린다)."""
    __slots__ = ("buf", "bitpos")

    def __init__(self, capacity_bytes: int):
        self.buf = bytearray(capacity_bytes)
        self.bitpos = 0

    def write(self, val: int, nbits: int) -> bool:
        if nbits <= 0 or nbits > 32:
            return False
        if val < 0:
            return False
        if nbits < 32 and val > (0xFFFFFFFF >> (32 - nbits)):
            return False
        if (self.bitpos + nbits + 7) // 8 > len(self.buf):
            return False
        pos = self.bitpos
        for i in range(nbits):
            bit = (val >> (nbits - 1 - i)) & 1
            byte_idx = pos // 8
            bit_idx = pos % 8
            mask = 0x80 >> bit_idx
            if bit:
                self.buf[byte_idx] |= mask
            else:
                self.buf[byte_idx] &= (~mask & 0xFF)
            pos += 1
        self.bitpos = pos
        return True

    def write_f32(self, val: float) -> bool:
        bits = struct.unpack(">I", struct.pack(">f", val))[0]
        return self.write(bits, 32)

    def bytes_written(self) -> bytes:
        return bytes(self.buf[: (self.bitpos + 7) // 8])


class BitReader:
    """bp_read 포팅. 실패를 표현할 채널이 없다 — 디코더가 payload_len 을
    먼저 검증해 이 자리에 유효 데이터가 있음을 보장한 뒤에만 부른다는
    계약은 C 원본과 동일하다(bitpack.h)."""
    __slots__ = ("buf", "bitpos")

    def __init__(self, data: bytes):
        self.buf = data
        self.bitpos = 0

    def read(self, nbits: int) -> int:
        if nbits <= 0 or nbits > 32:
            return 0
        pos = self.bitpos
        val = 0
        for _ in range(nbits):
            byte_idx = pos // 8
            bit_idx = pos % 8
            mask = 0x80 >> bit_idx
            bit = 1 if (self.buf[byte_idx] & mask) else 0
            val = (val << 1) | bit
            pos += 1
        self.bitpos = pos
        return val

    def read_f32(self) -> float:
        bits = self.read(32)
        return struct.unpack(">f", struct.pack(">I", bits))[0]


# ═══════════════════════════════════════════════════════════════
#  1. Value(32bit) pack/unpack — 표 7-14. siap_value_as_*/siap_raw_from_* 포팅.
#     범위를 검사하지 않고
#     마스킹하면 잘못된 입력이 정상 바이트로 위장한다.
# ═══════════════════════════════════════════════════════════════

FLOAT32_MAX = 3.4028234663852886e38   # IEEE-754 single 표현 가능 최대 유한값


def pack_int(value) -> int:
    """INT -2^31..2^31-1 → 32bit raw(2의 보수). 실패는 전부 ValueRangeError."""
    try:
        v = int(value)
    except (TypeError, ValueError, OverflowError) as e:
        raise ValueRangeError(f"INT 변환 실패: {value!r}") from e
    if v != value:                                           # 1.5를 1로 절삭 금지
        raise ValueRangeError(f"INT 는 정수만 담는다: {value!r}")
    if not (-(2 ** 31) <= v <= 2 ** 31 - 1):
        raise ValueRangeError(f"INT 범위 초과: {v}")
    return struct.unpack(">I", struct.pack(">i", v))[0]


def pack_uint(value) -> int:
    """UINT 0..2^32-1 → 32bit raw."""
    try:
        v = int(value)
    except (TypeError, ValueError, OverflowError) as e:
        raise ValueRangeError(f"UINT 변환 실패: {value!r}") from e
    if v != value:                                           # 소수부 보존 불가 입력 거부
        raise ValueRangeError(f"UINT 는 정수만 담는다: {value!r}")
    if not (0 <= v <= 2 ** 32 - 1):
        raise ValueRangeError(f"UINT 범위 초과: {v}")
    return v


def pack_float(value) -> int:
    """FLOAT → IEEE-754 single 32bit raw. inf/nan/표현 불가 값을 거부한다."""
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError) as e:      # 10**400 등
        raise ValueRangeError(f"FLOAT 변환 실패: {value!r}") from e
    if v != v or v in (float("inf"), float("-inf")):         # nan / inf
        raise ValueRangeError(f"FLOAT 비유한값 거부: {v}")
    if abs(v) > FLOAT32_MAX:
        raise ValueRangeError(f"FLOAT 범위 초과: {v}")
    try:
        return struct.unpack(">I", struct.pack(">f", v))[0]
    except (OverflowError, struct.error) as e:
        raise ValueRangeError(f"FLOAT 인코딩 실패: {v}") from e


def unpack_int(raw: int) -> int:
    return struct.unpack(">i", struct.pack(">I", raw & 0xFFFFFFFF))[0]


def unpack_uint(raw: int) -> int:
    return raw & 0xFFFFFFFF


def unpack_float(raw: int) -> float:
    return struct.unpack(">f", struct.pack(">I", raw & 0xFFFFFFFF))[0]


def pack_value(value, value_type: ValueType) -> int:
    vt = int(value_type)
    if vt == int(ValueType.INT):
        return pack_int(value)
    if vt == int(ValueType.UINT):
        return pack_uint(value)
    if vt == int(ValueType.FLOAT):
        return pack_float(value)
    raise ValueRangeError(f"지원하지 않는 Value Type: {value_type!r}")


def unpack_value(raw: int, value_type: ValueType):
    vt = int(value_type)
    if vt == int(ValueType.INT):
        return unpack_int(raw)
    if vt == int(ValueType.UINT):
        return unpack_uint(raw)
    if vt == int(ValueType.FLOAT):
        return unpack_float(raw)
    raise ValueRangeError(f"지원하지 않는 Value Type: {value_type!r}")


# ═══════════════════════════════════════════════════════════════
#  2. 구조체 인코드/디코드 — siap_encode_*/siap_decode_* 포팅.
#     Header/NODE_PROPERTY/MSG_CONTROL_PROFILE 은 위반이 없으면 그대로 값을,
#     실패하면 None(NODE_PROPERTY) 또는 예외(그 외, encode 쪽)로 알린다.
#     DEVICE_MAIN_INFO/DEVICE_PROPERTY 는 Value Type·Subtype·Reserved 위반이
#     있을 수 있어 (구조체|None, Violation|None) 튜플을 돌려준다.
# ═══════════════════════════════════════════════════════════════

SUBTYPE_CODES = frozenset(int(s) for s in Subtype)

_KIND_HAS_LEADING_RSC = frozenset({
    MsgKind.RES_SET_CONNECTION, MsgKind.RES_SET_DEVICE_INIT, MsgKind.RES_SET_DEVICE_INIT_ALL,
    MsgKind.RES_SET_NODE_PROPERTY, MsgKind.RES_SET_DEVICE_PROPERTY,
    MsgKind.RES_SET_NODE_DEVICE_PROPERTY_ALL, MsgKind.RES_SET_MSG_FLOW_CONTROL_PROFILE,
    MsgKind.RES_GET_NODE_PROPERTY, MsgKind.RES_GET_DEVICE_PROPERTY,
    MsgKind.RES_GET_NODE_DEVICE_PROPERTY_ALL, MsgKind.RES_GET_DEVICE_VALUE,
    MsgKind.RES_GET_MSG_FLOW_CONTROL_PROFILE, MsgKind.RES_SET_DEVICE_CONTROL,
    MsgKind.RES_SET_REBOOT,
})

_MCP_KINDS = frozenset({
    MsgKind.REQ_SET_MSG_FLOW_CONTROL_PROFILE, MsgKind.RES_GET_MSG_FLOW_CONTROL_PROFILE,
})


def _np_offset_in_fixed(kind: MsgKind) -> int | None:
    """고정부에서 NODE_PROPERTY(8byte)가 시작하는 byte 오프셋. 없으면 None.
    RSC(1byte)가 앞에 오면 그만큼 밀린다 — RSC 는 항상 NP 보다 앞이다(7.2).
    siap_frame.c::_np_offset_in_fixed() 포팅."""
    if kind in (MsgKind.REQ_SET_NODE_PROPERTY, MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL):
        return 0
    if kind in (MsgKind.RES_SET_CONNECTION, MsgKind.RES_GET_NODE_PROPERTY,
                MsgKind.RES_GET_NODE_DEVICE_PROPERTY_ALL):
        return RSC_BYTES
    return None


def encode_header(h: Header) -> bytes:
    w = BitWriter(HEADER_BYTES)
    ok = (w.write(h.version, 8) and w.write(h.msg_type, 14) and w.write(h.trans_type, 2)
          and w.write(h.msg_id, 16) and w.write(h.payload_len, 16)
          and w.write(h.gcg_id, 20) and w.write(h.node_id, 20))
    if not ok:
        raise ValueRangeError(f"헤더 필드가 비트 폭을 초과했다: {h!r}")
    return w.bytes_written()


def decode_header(data: bytes) -> Header:
    r = BitReader(data)
    return Header(
        version=r.read(8), msg_type=r.read(14), trans_type=r.read(2),
        msg_id=r.read(16), payload_len=r.read(16),
        gcg_id=r.read(20), node_id=r.read(20),
    )


def encode_np(np: NodeProperty) -> bytes:
    if int(np.status) > int(Status.UNKNOWN):        # 표 7-13 Status Reserved
        raise ValueRangeError(f"NODE_PROPERTY.Status 는 RESERVED: {np.status}")
    w = BitWriter(NP_BYTES)
    ok = (w.write(np.sw_version, 8) and w.write(np.gcg_id, 20) and w.write(np.node_id, 20)
          and w.write(int(np.status), 8) and w.write(np.num_devices, 8))
    if not ok:
        raise ValueRangeError(f"NODE_PROPERTY 필드가 비트 폭을 초과했다: {np!r}")
    return w.bytes_written()


def decode_np(data: bytes) -> NodeProperty | None:
    """Status Reserved(0x03~0xFF)면 None. C 의 siap_decode_np() 자체는
    무검사이지만, 그 검사는 siap_dec_feed() 의 FIXED 상태 처리에서 일어난다
    (_kind_has_leading_rsc/np_offset 사용 지점과 같다) — Python 은 그 검사를
    이 함수 안으로 접어 넣어 decode_frame() 의 분기를 단순하게 유지한다."""
    r = BitReader(data)
    sw = r.read(8)
    gcg = r.read(20)
    node = r.read(20)
    status_raw = r.read(8)
    nd = r.read(8)
    if status_raw > int(Status.UNKNOWN):
        return None
    return NodeProperty(sw_version=sw, gcg_id=gcg, node_id=node,
                         status=Status(status_raw), num_devices=nd)


def encode_dmi(dmi: DeviceMainInfo) -> tuple[bytes | None, Violation | None]:
    """siap_encode_dmi() 포팅 — 인코딩 쪽도 디코딩과 동일 기준으로 거부한다
    (한쪽만 막으면 판정 기준이 무너진다)."""
    if int(dmi.value_type) > int(ValueType.FLOAT):
        return None, Violation(int(RSC.INVALID_DATA_TYPE), "INVALID_DATA_TYPE", "표 7-14",
                                f"Value Type=0x{int(dmi.value_type):02X} 는 RESERVED")
    if int(dmi.subtype) not in SUBTYPE_CODES:
        return None, Violation(int(RSC.INVALID_DATA_SUBTYPE), "INVALID_DATA_SUBTYPE", "표 7-14",
                                f"Subtype=0x{int(dmi.subtype):02X} 는 등록되지 않았다")
    try:
        raw = pack_value(dmi.value, dmi.value_type)
    except ValueRangeError as e:
        return None, Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT", "7.3.1", str(e))
    w = BitWriter(DMI_BYTES)
    ok = (w.write(dmi.device_id, 8) and w.write(int(dmi.dev_type), 1)
          and w.write(int(dmi.subtype), 8) and w.write(int(dmi.value_type), 2)
          and w.write(0, 5)                          # Reserved — 송신 시 0 (표 7-14)
          and w.write(raw, 32))
    if not ok:
        return None, Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT", "7.3.1",
                                "DEVICE_MAIN_INFO 필드가 비트 폭을 초과했다")
    return w.bytes_written(), None


def decode_dmi(data: bytes) -> tuple[DeviceMainInfo | None, Violation | None]:
    """siap_decode_dmi() 포팅. 순서가 결과에 영향을 준다 — Value Type 을
    Subtype 보다 먼저 판정한다."""
    r = BitReader(data)
    device_id = r.read(8)
    dev_type_raw = r.read(1)
    subtype = r.read(8)
    value_type_raw = r.read(2)
    r.read(5)
    raw_value = r.read(32)

    if value_type_raw == 0x03:
        return None, Violation(int(RSC.INVALID_DATA_TYPE), "INVALID_DATA_TYPE", "표 7-14",
                                "Value Type=0x03 는 RESERVED")
    if subtype not in SUBTYPE_CODES:
        return None, Violation(int(RSC.INVALID_DATA_SUBTYPE), "INVALID_DATA_SUBTYPE", "표 7-14",
                                f"Subtype=0x{subtype:02X} 는 등록되지 않았다")
    value_type = ValueType(value_type_raw)
    value = unpack_value(raw_value, value_type)
    dmi = DeviceMainInfo(device_id=device_id, dev_type=DevType(dev_type_raw),
                          subtype=subtype, value_type=value_type, value=value)
    return dmi, None


def encode_dp(dp: DeviceProperty) -> tuple[bytes | None, Violation | None]:
    """siap_encode_dp() 포팅. Transfer Mode·Status 검사가 main 인코딩보다
    먼저다 — 실패 시 main 의 7byte 도 쓰지 않는다(요소는 all-or-nothing)."""
    if int(dp.transfer_mode) > int(TransferMode.BOTH):
        return None, Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT", "7.3.1",
                                f"Transfer Mode=0x{int(dp.transfer_mode):02X} 는 RESERVED")
    if int(dp.status) > int(Status.UNKNOWN):
        return None, Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT", "7.3.1",
                                f"Status=0x{int(dp.status):02X} 는 RESERVED")
    main_bytes, v = encode_dmi(dp.main)
    if main_bytes is None:
        return None, v

    vt = dp.main.value_type                          # USER DEPENDENT 5필드는 main.value_type 을 따른다
    try:
        lower_value = pack_value(dp.lower_value, vt)
        upper_value = pack_value(dp.upper_value, vt)
        lower_limit = pack_value(dp.lower_limit, vt)
        upper_limit = pack_value(dp.upper_limit, vt)
        precision = pack_value(dp.precision, vt)
    except ValueRangeError as e:
        return None, Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT", "7.3.1", str(e))

    w = BitWriter(DP_BYTES)
    w.buf[:DMI_BYTES] = main_bytes
    w.bitpos = DMI_BYTES * 8
    ok = (w.write(int(dp.transfer_mode), 2) and w.write(dp.period, 14)
          and w.write(lower_value, 32) and w.write(upper_value, 32)
          and w.write(lower_limit, 32) and w.write(upper_limit, 32)
          and w.write(precision, 32) and w.write(int(dp.status), 8))
    if not ok:
        return None, Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT", "7.3.1",
                                "DEVICE_PROPERTY 필드가 비트 폭을 초과했다")
    return w.bytes_written(), None


def decode_dp(data: bytes) -> tuple[DeviceProperty | None, Violation | None]:
    """siap_decode_dp() 포팅. main 이 위반이어도 나머지 23byte 는 그대로
    소비한다(bitpos 유지용 — Python 버전은 고정폭 슬라이스라 자동으로
    지켜지지만, 반환 계약은 C 와 동일하게 맞춘다). Transfer Mode·Status 는
    30byte 를 전부 읽은 뒤 판정한다(요소는 자기완결적·고정폭)."""
    main, v = decode_dmi(data[:DMI_BYTES])
    r = BitReader(data)
    r.bitpos = DMI_BYTES * 8
    tm_raw = r.read(2)
    period = r.read(14)
    lv = r.read(32)
    uv = r.read(32)
    ll = r.read(32)
    ul = r.read(32)
    prec = r.read(32)
    status_raw = r.read(8)

    if main is None:
        return None, v

    vt = main.value_type
    lower_value = unpack_value(lv, vt)
    upper_value = unpack_value(uv, vt)
    lower_limit = unpack_value(ll, vt)
    upper_limit = unpack_value(ul, vt)
    precision = unpack_value(prec, vt)

    if tm_raw > int(TransferMode.BOTH):
        return None, Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT", "7.3.1",
                                f"Transfer Mode=0x{tm_raw:02X} 는 RESERVED")
    if status_raw > int(Status.UNKNOWN):
        return None, Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT", "7.3.1",
                                f"Status=0x{status_raw:02X} 는 RESERVED")

    dp = DeviceProperty(main=main, transfer_mode=TransferMode(tm_raw), period=period,
                         lower_value=lower_value, upper_value=upper_value,
                         lower_limit=lower_limit, upper_limit=upper_limit,
                         precision=precision, status=Status(status_raw))
    return dp, None


def encode_mcp(mcp: MsgControlProfile) -> bytes:
    w = BitWriter(MCP_BYTES)
    ok = (w.write(mcp.recv_timeout, 16) and w.write(mcp.num_retry, 8)
          and w.write(mcp.noti_error_interval, 16) and w.write(mcp.keep_alive_interval, 16))
    if not ok:
        raise ValueRangeError(f"MSG_CONTROL_PROFILE 필드가 비트 폭을 초과했다: {mcp!r}")
    return w.bytes_written()


def decode_mcp(data: bytes) -> MsgControlProfile:
    r = BitReader(data)
    return MsgControlProfile(recv_timeout=r.read(16), num_retry=r.read(8),
                              noti_error_interval=r.read(16), keep_alive_interval=r.read(16))


# ═══════════════════════════════════════════════════════════════
#  3. 종류 해석 — siap_resolve_kind() 포팅(clause 구분 포함).
#     contracts/frame.py::resolve_kind() 는 clause 를 구분하지 않으므로 여기서
#     WIRE_CODE 를 직접 재사용해 같은 로직을 재현한다 — 같은 명세서를 다시
#     타이핑해 같은 결과가 나오는지가 교차 검증이다.
# ═══════════════════════════════════════════════════════════════

def _resolve_kind_with_clause(msg_type: int, payload_len: int, mode: Mode):
    table = WIRE_CODE if mode == "strict" else WIRE_CODE_EXT
    cands = [k for k, c in table.items() if c == msg_type]
    if not cands:
        return None, "표 7-2"                         # 코드 자체가 미정의
    if len(cands) == 1:                                # 단일 후보 — element_count 무관하게 확정
        return cands[0], None
    for k in cands:                                    # 다중 후보(0x0800) — 맞는 것을 고른다
        if element_count(k, payload_len) is not None:
            return k, None
    return None, "7.3.1"                                # 아무도 이 Payload Length 를 못 받는다


# ═══════════════════════════════════════════════════════════════
#  4. Frame 전체 인코드/디코드 — siap_dec_feed() 의 비스트리밍(단발) 판.
#     결함 주입 지점 순서는 아래 표를 그대로 따른다:
#       1 Version -> 3 Payload Length -> 4 미정의 Message Type
#       -> 5 Transmission Type -> 2 미등록 Node ID -> 6 Value Type -> 7 Subtype
# ═══════════════════════════════════════════════════════════════

def encode_frame(frame: Frame, mode: Mode = "strict") -> bytes:
    """Frame -> bytes. build.py 가 만든 Frame 을 직렬화한다. C 의
    siap_tx_put_*() 함수들과 같은 필드 순서를 쓴다(RSC/NEC -> NODE_PROPERTY ->
    MSG_CONTROL_PROFILE -> 요소) — C 인코더 출력과 바이트 단위로 일치해야
    한다."""
    if frame.header is None:
        raise ValueRangeError("header 가 없는 불완전 Frame 은 인코딩할 수 없다")
    kind = frame.kind
    if kind is None:
        raise ValueRangeError("kind 가 없는 Frame 은 인코딩할 수 없다")

    body = bytearray()
    if kind in _KIND_HAS_LEADING_RSC:
        if frame.rsc is None:
            raise ValueRangeError(f"{kind.name} 은 RSC 가 필요하다")
        if int(frame.rsc) > int(RSC.INVALID_FORMAT):
            raise ValueRangeError(f"RSC=0x{int(frame.rsc):02X} 는 RESERVED")
        body += bytes([int(frame.rsc)])
    if kind is MsgKind.NOTI_ERROR:
        if frame.nec is None:
            raise ValueRangeError("NOTI_ERROR 는 NEC 가 필요하다")
        if int(frame.nec) > int(NEC.ERROR_UNKNOWN):
            raise ValueRangeError(f"NEC=0x{int(frame.nec):02X} 는 RESERVED")
        body += bytes([int(frame.nec)])
    if _np_offset_in_fixed(kind) is not None:
        if frame.node_property is None:
            raise ValueRangeError(f"{kind.name} 은 NODE_PROPERTY 가 필요하다")
        body += encode_np(frame.node_property)
    if kind in _MCP_KINDS:
        if frame.profile is None:
            raise ValueRangeError(f"{kind.name} 은 MSG_CONTROL_PROFILE 이 필요하다")
        body += encode_mcp(frame.profile)

    fixed_bytes, elem_bytes = LAYOUT[kind]
    if len(body) != fixed_bytes:
        raise ValueRangeError(f"{kind.name} 고정부 길이 불일치: {len(body)} != {fixed_bytes}")

    if elem_bytes == DID_BYTES:
        for did in frame.device_ids:
            if not (0 <= did <= 0xFF):
                raise ValueRangeError(f"DEVICE_ID 범위 초과: {did}")
            body += bytes([did])
    elif elem_bytes == DMI_BYTES:
        for dmi in frame.device_main_infos:
            enc, v = encode_dmi(dmi)
            if enc is None:
                raise ValueRangeError(f"DEVICE_MAIN_INFO 인코딩 실패: {v.detail}")
            body += enc
    elif elem_bytes == DP_BYTES:
        for dp in frame.device_properties:
            enc, v = encode_dp(dp)
            if enc is None:
                raise ValueRangeError(f"DEVICE_PROPERTY 인코딩 실패: {v.detail}")
            body += enc

    if frame.header.payload_len != len(body):
        raise ValueRangeError(
            f"payload_len 불일치: header={frame.header.payload_len}, 실제 본문={len(body)}")

    return encode_header(frame.header) + bytes(body)


def decode_frame(data: bytes, mode: Mode = "strict",
                  node_known: Callable[[int], bool] | None = None) -> Frame:
    """프레임 1건의 바이트열을 Frame 으로 해석한다. 불완전 입력을 포함해
    예외를 던지지 않는다(계약).

    node_known: Node ID 가 등록돼 있는지 확인하는 콜백(위반 2 판정,
    "core/ 는 내 주소를 모른다"와 같은 원칙으로 registry.py 를 여기 import
    하지 않는다. 호출자(link.py)가 registry.py 를 보고 주입한다). None 이면
    이 검사를 생략한다(단독 코덱 테스트·골든 벡터 재생 등)."""
    return _decode_frame(data, mode, node_known, incomplete_as_violation=True)


def _decode_frame(data: bytes, mode: Mode,
                  node_known: Callable[[int], bool] | None,
                  *, incomplete_as_violation: bool) -> Frame:
    """공개 단발 디코드와 스트리밍 디코드의 공통 구현.

    스트리밍 경로만 불완전 입력을 내부 신호로 바꾸어 버퍼를 유지한다."""
    if len(data) < HEADER_BYTES:
        detail = f"헤더 미달: 필요 {HEADER_BYTES}, 보유 {len(data)} byte"
        if not incomplete_as_violation:
            raise IncompleteFrameError(detail)
        return Frame(
            header=None, kind=None, raw=data,
            violations=(Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT",
                                  "7.3.1", detail),),
        )

    h = decode_header(data[:HEADER_BYTES])
    total_len = HEADER_BYTES + h.payload_len

    def _violation(code: RSC, name: str, clause: str, detail: str = "") -> Frame:
        return Frame(header=h, kind=None, raw=data[:min(len(data), total_len)],
                     violations=(Violation(int(code), name, clause, detail),))

    if h.version != SIAP_VERSION:                                          # 위반 1 — 7.3.1
        return _violation(RSC.INVALID_VERSION, "INVALID_VERSION", "7.3.1",
                           f"Version=0x{h.version:02X}, 기대 0x{SIAP_VERSION:02X}")

    kind, clause = _resolve_kind_with_clause(h.msg_type, h.payload_len, mode)
    if kind is None:                                                        # 위반 3(다중후보 전부 실패)·4
        if clause == "표 7-2":
            detail = f"Message Type=0x{h.msg_type:04X} 는 정의되지 않았다"
        else:
            detail = f"Payload Length={h.payload_len}, 이 Message Type 어느 후보에도 유효하지 않다"
        return _violation(RSC.INVALID_FORMAT, "INVALID_FORMAT", clause, detail)

    n = element_count(kind, h.payload_len)
    if n is None:                                                           # 위반 3(단일 후보/B02 류)
        return _violation(RSC.INVALID_FORMAT, "INVALID_FORMAT", "7.3.1",
                           f"Payload Length={h.payload_len}, {kind.name} 에 유효하지 않다")

    if h.trans is None:                                                     # 위반 5 — 표 7-6
        return _violation(RSC.INVALID_TRANSMISSION_TYPE, "INVALID_TRANSMISSION_TYPE", "표 7-6",
                           f"Transmission Type=0x{h.trans_type:02X} 는 정의되지 않았다")

    if (node_known is not None and kind is not MsgKind.REQ_SET_CONNECTION   # 위반 2 — 7.3.1
            and not node_known(h.node_id)):
        return _violation(RSC.INVALID_NODE_ID, "INVALID_NODE_ID", "7.3.1",
                           f"Node ID=0x{h.node_id:05X} 는 등록되지 않았다")

    if len(data) < total_len:
        detail = f"payload 미달: 필요 {total_len}, 보유 {len(data)}"
        if not incomplete_as_violation:
            raise IncompleteFrameError(detail)
        return Frame(
            header=h, kind=kind, raw=data,
            violations=(Violation(int(RSC.INVALID_FORMAT), "INVALID_FORMAT",
                                  "7.3.1", detail),),
        )

    payload = data[HEADER_BYTES:total_len]
    fixed_bytes, elem_bytes = LAYOUT[kind]
    fixed = payload[:fixed_bytes]
    rest = payload[fixed_bytes:]

    rsc = nec = None
    node_property = None
    profile = None
    device_main_infos: list = []
    device_properties: list = []
    device_ids: list = []

    if fixed_bytes:
        if kind in _KIND_HAS_LEADING_RSC:                                   # 표 7-10 RSC Reserved
            rsc_raw = fixed[0]
            if rsc_raw > int(RSC.INVALID_FORMAT):
                return _violation(RSC.INVALID_FORMAT, "INVALID_FORMAT", "7.3.1",
                                   f"RSC=0x{rsc_raw:02X} 는 RESERVED")
            rsc = RSC(rsc_raw)
        if kind is MsgKind.NOTI_ERROR:                                      # 표 7-12 NEC Reserved
            nec_raw = fixed[0]
            if nec_raw > int(NEC.ERROR_UNKNOWN):
                return _violation(RSC.INVALID_FORMAT, "INVALID_FORMAT", "7.3.1",
                                   f"NEC=0x{nec_raw:02X} 는 RESERVED")
            nec = NEC(nec_raw)

        np_off = _np_offset_in_fixed(kind)
        if np_off is not None:
            # COMBINED_PROPERTY 3종: NODE_PROPERTY.Num. of Devices 와
            # Payload Length 역산 N 이 다르면 거부. NP 는 항상 고정부의 마지막 8byte.
            if elem_bytes == DP_BYTES and np_off + NP_BYTES == fixed_bytes:
                num_devices = fixed[fixed_bytes - 1]
                if num_devices != n:
                    return _violation(RSC.INVALID_FORMAT, "INVALID_FORMAT", "7.3.1",
                                       f"Num. of Devices={num_devices} != N(Payload Length 역산)={n}")
            node_property = decode_np(fixed[np_off: np_off + NP_BYTES])
            if node_property is None:                                       # 표 7-13 Status Reserved
                return _violation(RSC.INVALID_FORMAT, "INVALID_FORMAT", "7.3.1",
                                   "NODE_PROPERTY.Status 는 RESERVED")

        if kind in _MCP_KINDS:
            mcp_off = fixed_bytes - MCP_BYTES
            profile = decode_mcp(fixed[mcp_off: mcp_off + MCP_BYTES])

    if elem_bytes and n:
        if elem_bytes == DID_BYTES:
            device_ids = [rest[i] for i in range(n)]
        elif elem_bytes == DMI_BYTES:
            for i in range(n):
                chunk = rest[i * DMI_BYTES:(i + 1) * DMI_BYTES]
                dmi, v = decode_dmi(chunk)
                if dmi is None:                                             # 위반 6·7 — 첫 위반에서 중단
                    return _violation(RSC(v.code), v.code_name, v.clause, v.detail)
                device_main_infos.append(dmi)
        elif elem_bytes == DP_BYTES:
            for i in range(n):
                chunk = rest[i * DP_BYTES:(i + 1) * DP_BYTES]
                dp, v = decode_dp(chunk)
                if dp is None:
                    return _violation(RSC(v.code), v.code_name, v.clause, v.detail)
                device_properties.append(dp)

    return Frame(
        header=h, kind=kind, rsc=rsc, nec=nec,
        node_property=node_property,
        device_main_infos=tuple(device_main_infos),
        device_properties=tuple(device_properties),
        device_ids=tuple(device_ids),
        profile=profile,
        raw=data[:total_len],
        violations=(),
    )


# ═══════════════════════════════════════════════════════════════
#  5. 스트리밍 디코더 — siap_dec_t 포팅.
#     transport.py/link.py 가 바이트를 받는 대로 feed() 에 넘기면 완결된
#     Frame 을 내보낸다. 프레임 경계 구분자가 없는 표준의 결함에
#     대한 자체 대응이 재동기 4조건이다.
#
#     알려진 범위 — 이번 단계는 "정상적으로 이어지는 바이트열에서 프레임을
#     추출"과 "위반 프레임 뒤 재동기 진입"까지를 구현한다. 실제 바이트 유실
#     주입 시나리오(T_gap 경계값 등)의 정밀 검증은 sim/inject.py 의
#     몫이다 — 여기서는 그 훅(on_gap)만 제공한다.
# ═══════════════════════════════════════════════════════════════

class Decoder:
    """siap_dec_t 포팅. 상태는 buf(bytearray 누적) 하나로 충분하다 — host 에는
    AVR 의 51byte 창 제약이 없다."""

    def __init__(self, mode: Mode = "strict",
                 node_known: Callable[[int], bool] | None = None):
        self.mode = mode
        self.node_known = node_known
        self._buf = bytearray()
        self._resync = False

    def feed(self, data: bytes) -> Iterator[Frame]:
        self._buf += data
        while True:
            frame = self._try_extract()
            if frame is None:
                return
            yield frame

    def on_gap(self) -> None:
        """T_gap(20ms) 이상 무입력을 관측했을 때 호출한다. 헤더 대기
        중이 아니면 불완전 프레임을 포기하고 재동기 모드로 되돌아간다."""
        if len(self._buf) >= HEADER_BYTES:
            pass   # 헤더는 이미 있다 — 아래에서 그대로 재동기 후보로 재시도된다
        self._resync = True

    def _resync_check(self) -> bool:
        """게이트웨이(Python) 재동기 후보 판정 — **Version 일치 + 등록된 Node ID**
        둘을 본다.

        펌웨어(C, `siap_frame.c`)의 원안은 Version + resolve_kind +
        Transmission Type + element_count 4조건을 모두 요구한다. 이 파일은
        원래 그 4조건을 그대로 포팅했었지만, `resolve_kind`·Transmission
        Type·element_count 셋은 `decode_frame()` 자신이 검사해 위반으로
        **보고하는 바로 그 항목**이다 — 재동기 게이트에서 먼저 걸러내면
        정확히 그 위반들(예: X03 의 `INVALID_FORMAT`, X05 의
        `INVALID_TRANSMISSION_TYPE`)이 재동기 모드 중에는 "노이즈"로 오인돼
        1byte 씩 삼켜지고 다시는 분류되지 않는다. 위반 프레임 하나를 낸
        직후에는 항상 재동기 모드로 들어가므로, 연속
        주입(X01→X03→X05→X06→X07)에서 두 번째부터는
        전부 유실됐다(실측: msg_id [50,55,56]만 도달, [52,54] 소실).

        **Version 단독 조건의 결함**: 위반 프레임을 헤더
        12byte 만 지우고 재동기에 들어가면, 그 위반 프레임이 선언한
        payload 일부가 버퍼에 남을 수 있다(payload_len 을 신뢰하지 않으므로
        의도적으로 그렇다). 그 잔여 바이트가 우연히 `0x12`(Version)이면
        Version 단독 게이트가 그 지점을 새 헤더로 오인해 수락하고, 뒤따르는
        진짜 정상 프레임의 앞부분을 가짜 헤더 본문으로 삼켜버린다 — 정상
        프레임 하나가 사라진다(재동기 규칙이 막으려던 것과 같은 종류의 사고가
        다른 경로로 재발). Version 1byte 만으로는 오탐률이 1/256 으로,
        노이즈 스캔 중 이 정도 빈도로도 실제 피해(정상 프레임 유실)가
        난다.

        `node_known` 콜백(있으면)을 추가 조건으로 더한다 — 등록된 Node ID
        집합은 보통 수십 개 미만이라 20bit Node ID 공간(약 100만) 대비
        오탐률이 극적으로 낮아진다. X01·X03·X05·X06·
        X07 은 전부 `Node ID=3`(등록된 노드)을 선언하므로 이 조건을 항상
        통과한다 — 앞서 고친 연속 주입 판정은 그대로 유지된다.

        **단, `node_known` 실패를 무조건 거부로 쓰면 X02(미등록 Node ID
        자체가 위반 목표)가 다른 위반 직후에 연쇄 주입될 때 다시 삼켜진다**
        (몽타주 컷에서 실측). X02 는 Node ID 만 미등록이고 나머지(Version·
        resolve_kind·Transmission Type·element_count)는 전부 정상 구조다 —
        "노드를 모른다"와 "이 자리가 헤더가 아니다"는 다른 사실이다. 그래서
        `node_known` 이 실패해도, 나머지 구조(resolve_kind·Transmission
        Type·element_count)가 전부 자기충족적으로 유효하면 후보로 인정한다
        — 우연히 이 세 조건을 전부 만족하면서 Version 까지 맞는 잡음은
        이전 4조건 오탐률(약 2⁻²²)과 동일한 수준으로 낮다.
        `node_known=None`(단독 코덱 테스트·골든 벡터 재생)이면 Node ID
        조건 자체를 생략한다 — `decode_frame()` 자신도 같은 규칙을 쓴다.

        kind·trans·element_count 판정 자체(위반 보고)는 평소와 동일하게
        `decode_frame()` 에 맡긴다 — 이 함수는 재동기 후보를 거를 때만 그
        값들을 재사용한다.

        펌웨어는 UART 물리 케이블 노이즈 복구가 주 목적이라 4조건을 그대로
        유지한다("상대 구현이 다른 규칙을 쓰면
        재동기 시점이 달라진다"는 전제를 따른다)."""
        h = decode_header(bytes(self._buf[:HEADER_BYTES]))
        if h.version != SIAP_VERSION:
            return False
        if self.node_known is None or self.node_known(h.node_id):
            return True
        # Node ID 만 미등록인 X02 류를 구제한다 — 나머지 구조가 전부
        # 자기충족적으로 유효할 때만( 재발 방지, 오탐률을 4조건
        # 수준으로 되돌림).
        if h.trans is None:
            return False
        kind, _ = _resolve_kind_with_clause(h.msg_type, h.payload_len, self.mode)
        if kind is None:
            return False
        return element_count(kind, h.payload_len) is not None

    def _try_extract(self) -> Frame | None:
        while True:
            if len(self._buf) < HEADER_BYTES:
                return None
            if self._resync:
                if not self._resync_check():
                    del self._buf[0]                 # 1byte 슬라이딩 — 잡음 구간 스캔 중
                    continue
                self._resync = False
            try:
                frame = _decode_frame(bytes(self._buf), self.mode, self.node_known,
                                      incomplete_as_violation=False)
            except IncompleteFrameError:
                return None
            if frame.violations:
                # 위반 프레임의 payload_len 은 신뢰할 수 없다. Version
                # 위반(예)은 payload_len 자체를 전혀 검증하지 않은 채 확정되므로,
                # 그 값으로 "12+payload_len" 만큼 버퍼를 지우면 이미 도착해
                # 버퍼에 쌓여 있는 다음 정상 프레임까지 통째로 삼킨다(공격적
                # 이거나 손상된 헤더 하나가 뒤따르는 정상 트래픽 전체를 삼키는
                # 사고). 헤더 12byte 만 지우고 재동기 모드로 들어가 1byte 씩
                # 다시 찾는다 — 느리지만 이미 버퍼에 있는 바이트를 잃지 않는다
                # (4조건 스캔이 원래 하려던 일이다).
                del self._buf[:HEADER_BYTES]
                self._resync = True
                return frame
            assert frame.header is not None
            total = HEADER_BYTES + frame.header.payload_len
            del self._buf[:min(total, len(self._buf))]
            return frame
