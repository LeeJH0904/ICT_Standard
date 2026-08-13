"""
SIAP Frame 계약 — TTAK.KO-10.0943 7장 직역
이 파일은 모듈 경계다. 여기 정의된 타입 외에는 계층 간에 오가지 않는다.
변경 시 골든 벡터 재생성 및 양쪽 테스트 재통과가 필요하다.

엔디안      : big-endian (network byte order)   ※ 표준 미규정 → 자체 결정
FLOAT       : IEEE-754 single precision, 4byte  ※ 표준 미규정 → 자체 결정
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import Literal

# ═══════════════════════════════════════════════════════════════
#  1. 메시지 종류
#     표 7-4에서 NOTI_ERROR와 NOTI_DEVICE_VALUE가 동일 코드(0x0800)를
#     갖는다. IntEnum으로 두면 후자가 전자의 별칭이 되어 구분이 소실되므로,
#     "논리적 종류(MsgKind)"와 "전송 코드(WIRE_CODE)"를 분리한다.
# ═══════════════════════════════════════════════════════════════

class MsgKind(Enum):
    # Request (표 7-2)
    REQ_SET_CONNECTION = auto()
    REQ_SET_DEVICE_INIT = auto()
    REQ_SET_DEVICE_INIT_ALL = auto()
    REQ_SET_NODE_PROPERTY = auto()
    REQ_SET_DEVICE_PROPERTY = auto()
    REQ_SET_NODE_DEVICE_PROPERTY_ALL = auto()
    REQ_SET_MSG_FLOW_CONTROL_PROFILE = auto()
    REQ_GET_NODE_PROPERTY = auto()
    REQ_GET_DEVICE_PROPERTY = auto()
    REQ_GET_NODE_DEVICE_PROPERTY_ALL = auto()
    REQ_GET_DEVICE_VALUE = auto()
    REQ_GET_MSG_FLOW_CONTROL_PROFILE = auto()
    REQ_SET_DEVICE_CONTROL = auto()
    REQ_SET_REBOOT = auto()
    # Response (표 7-3)
    RES_SET_CONNECTION = auto()
    RES_SET_DEVICE_INIT = auto()
    RES_SET_DEVICE_INIT_ALL = auto()
    RES_SET_NODE_PROPERTY = auto()
    RES_SET_DEVICE_PROPERTY = auto()
    RES_SET_NODE_DEVICE_PROPERTY_ALL = auto()
    RES_SET_MSG_FLOW_CONTROL_PROFILE = auto()
    RES_GET_NODE_PROPERTY = auto()
    RES_GET_DEVICE_PROPERTY = auto()
    RES_GET_NODE_DEVICE_PROPERTY_ALL = auto()
    RES_GET_DEVICE_VALUE = auto()
    RES_GET_MSG_FLOW_CONTROL_PROFILE = auto()
    RES_SET_DEVICE_CONTROL = auto()
    RES_SET_REBOOT = auto()
    # Notify / ACK (표 7-4)
    NOTI_ERROR = auto()
    NOTI_DEVICE_VALUE = auto()
    NOTI_DISCONNECT = auto()
    NOTI_REBOOT = auto()
    NOTI_KEEP_ALIVE = auto()
    ACK = auto()

Mode = Literal["strict", "extended"]

_REQ = [k for k in MsgKind if k.name.startswith("REQ_")]
_RES = [k for k in MsgKind if k.name.startswith("RES_")]

# strict — 표준 원문 그대로 (0x0800 중복 포함)
WIRE_CODE: dict[MsgKind, int] = {
    **{k: i for i, k in enumerate(_REQ)},
    **{k: 0x0400 + i for i, k in enumerate(_RES)},
    MsgKind.NOTI_ERROR: 0x0800,
    MsgKind.NOTI_DEVICE_VALUE: 0x0800,   # ★ 표준 원문 중복 (표 7-4)
    MsgKind.NOTI_DISCONNECT: 0x0801,
    MsgKind.NOTI_REBOOT: 0x0802,
    MsgKind.NOTI_KEEP_ALIVE: 0x0803,
    MsgKind.ACK: 0x0C00,
}

# extended — 중복 해소 제안안 (표준 개정 제안)
WIRE_CODE_EXT: dict[MsgKind, int] = {
    **WIRE_CODE,
    MsgKind.NOTI_DEVICE_VALUE: 0x0801,
    MsgKind.NOTI_DISCONNECT: 0x0802,
    MsgKind.NOTI_REBOOT: 0x0803,
    MsgKind.NOTI_KEEP_ALIVE: 0x0804,
}

def wire_code(kind: MsgKind, mode: Mode = "strict") -> int:
    return (WIRE_CODE if mode == "strict" else WIRE_CODE_EXT)[kind]

# ═══════════════════════════════════════════════════════════════
#  2. 표준 정의 열거형
# ═══════════════════════════════════════════════════════════════

class TransType(IntEnum):        # 표 7-6
    UNICAST = 0x00; MULTICAST = 0x01; BROADCAST = 0x02

class RSC(IntEnum):              # 표 7-10  ※ 원문 표기는 'SUCESS' (오타)
    SUCCESS = 0x00
    INVALID_VERSION = 0x01
    INVALID_GCG_ID = 0x02
    INVALID_NODE_ID = 0x03
    INVALID_DEVICE_ID = 0x04
    INVALID_DEVICE_TYPE = 0x05
    INVALID_DATA_TYPE = 0x06
    INVALID_DATA_SUBTYPE = 0x07
    INVALID_TRANSMISSION_TYPE = 0x08
    INVALID_FORMAT = 0x09

class NEC(IntEnum):              # 표 7-12
    ERROR_DEVICE_STATUS = 0x00
    ERROR_DEVICE_INTERFACE = 0x01
    ERROR_RECEIVE = 0x02
    ERROR_SW_TIMER = 0x03
    ERROR_HW_TIMER = 0x04
    ERROR_PWR = 0x05
    ERROR_BATTERY = 0x06
    ERROR_BATTERY_LOW = 0x07
    ERROR_BATTERY_OFF = 0x08
    ERROR_UNKNOWN = 0x09

class DevType(IntEnum):          # 표 7-14
    SENSOR = 0x00; ACTUATOR = 0x01

class ValueType(IntEnum):        # 표 7-14
    INT = 0x00; UINT = 0x01; FLOAT = 0x02

class TransferMode(IntEnum):     # 표 7-15
    PERIODIC = 0x00; EVENT = 0x01; BOTH = 0x02

class Status(IntEnum):           # 표 7-13 / 7-15
    NORMAL = 0x00; ABNORMAL = 0x01; UNKNOWN = 0x02

class Subtype(IntEnum):
    """항목 = TTAK.KO-10.1369-Part1 6.3.3 / 6.3.4
       코드값 = [RUCFS-0009] 미확보로 자체 할당 (치환 지점 1/2)"""
    TEMPERATURE = 0x01            # 온도            ℃      1369-P1 6.3.3.2
    HUMIDITY = 0x02               # 습도            %              6.3.3.3
    CO2 = 0x03                    # 이산화탄소      ppm            6.3.3.4
    INSOLATION = 0x04             # 일사            W/㎡           6.3.3.5
    WIND_DIRECTION = 0x05         # 풍향            degree         6.3.3.6
    WIND_SPEED = 0x06             # 풍속            m/s            6.3.3.7
    RAIN_DETECTION = 0x07         # 감우            ON/OFF         6.3.3.8
    SOIL_MOISTURE_TENSION = 0x08  # 토양수분장력    kPa            6.3.3.9
    EC = 0x09                     # 전기전도도      dS/m           6.3.3.10
    PH = 0x0A                     # 수소이온농도    —              6.3.3.11
    WINDOW_OPENER = 0x81          # 창 개폐기       %              6.3.4.2
    INSULATION_COVER = 0x82       # 보온덮개        %              6.3.4.3
    FAN = 0x83                    # 송풍기          ON/OFF         6.3.4.4
    IRRIGATION_PUMP = 0x84        # 관수펌프        ON/OFF+sec     6.3.4.5
    IRRIGATION_VALVE = 0x85       # 관수밸브        ON/OFF or %    6.3.4.6
    COOLING_HEATER = 0x86         # 냉난방기        ON/OFF+℃      6.3.4.7

    @property
    def dev_type(self) -> DevType:
        return DevType.ACTUATOR if self.value & 0x80 else DevType.SENSOR

# ═══════════════════════════════════════════════════════════════
#  3. 구조체 (7.3.3) — 비트 길이는 코덱이 참조하는 정본
# ═══════════════════════════════════════════════════════════════

HEADER_BYTES = 12   # 96 bit  그림 7-1
NP_BYTES     = 8    # 64 bit  표 7-13
DMI_BYTES    = 7    # 56 bit  표 7-14
DP_BYTES     = 30   # 240 bit 표 7-15
MCP_BYTES    = 7    # 56 bit  표 7-18
RSC_BYTES    = 1
NEC_BYTES    = 1
DID_BYTES    = 1

# F-120 — 노드당 디바이스 상한. 표준 미규정(F-065) → 자체 결정(CLAUDE.md §3.5,
# 펌웨어 설계서 §3.2/§9). N=16 은 501 byte 최대 프레임(RSC+NODE_PROPERTY+
# DEVICE_PROPERTY×16)과 Timeout≥2×wire_time 산식(아키텍처 §6.2-a)의
# 전제다. CLAUDE.md §5 절차: ① 근거는 위 각주 ② 2026-08-08 사용자 승인
# (F-118~F-120 일괄 처리 승인) ③ golden 벡터 재생성 + test_contract.py 재통과
# ④ 이력을 이 절에 남김. C 대응은 firmware/core/siap_types.h 의
# SIAP_MAX_DEVICES_PER_NODE.
MAX_DEVICES_PER_NODE = 16

@dataclass(frozen=True)
class Header:
    """전송된 원본 비트값을 그대로 보존한다.

    F-014 — trans_type을 TransType으로 선언하면 표 7-6 미정의값(0x03)을
    담을 수 없어 "예외를 던지지 않는다"는 계약과 충돌한다. msg_type이
    이미 raw int인 것과 같은 원칙으로 trans_type도 raw int로 둔다.
    해석은 resolve_trans_type() 이 담당한다."""
    version: int              # 8   0x12 = v1.2
    msg_type: int             # 14  전송된 원본 코드
    trans_type: int           # 2   전송된 원본값 (0x03 = 표 7-6 미정의)
    msg_id: int               # 16
    payload_len: int          # 16
    gcg_id: int               # 20
    node_id: int              # 20

    @property
    def trans(self) -> "TransType | None":
        """해석된 전송 타입. 미정의값이면 None (→ INVALID_TRANSMISSION_TYPE)."""
        return resolve_trans_type(self.trans_type)


def resolve_trans_type(raw: int) -> "TransType | None":
    """표 7-6. 0x03은 표준 미정의 → None."""
    try:
        return TransType(raw)
    except ValueError:
        return None

@dataclass(frozen=True)
class NodeProperty:           # 표 7-13
    sw_version: int; gcg_id: int; node_id: int
    status: Status; num_devices: int

@dataclass(frozen=True)
class DeviceMainInfo:         # 표 7-14
    device_id: int
    dev_type: DevType
    subtype: int
    value_type: ValueType
    value: float | int

@dataclass(frozen=True)
class DeviceProperty:         # 표 7-15
    """F-022 — 표 7-15는 아래 5개 필드의 타입을 "USER DEPENDENT"로만 규정하고
    선택 규칙을 정하지 않는다. 이들은 main.value 와 같은 물리량의 경계·정밀도
    이므로 **main.value_type 을 따른다**로 결정했다 (구현 결정, 표준 미규정).
    코덱은 반드시 이 규칙으로 인코딩·디코딩한다."""
    main: DeviceMainInfo
    transfer_mode: TransferMode
    period: int
    lower_value: float | int; upper_value: float | int
    lower_limit: float | int; upper_limit: float | int
    precision: float | int
    status: Status

@dataclass(frozen=True)
class MsgControlProfile:      # 표 7-18
    recv_timeout: int; num_retry: int
    noti_error_interval: int; keep_alive_interval: int

# ═══════════════════════════════════════════════════════════════
#  4. 검증 결과 (표준 외 확장 — 기능 2 전용)
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Violation:
    code: int          # RSC 또는 NEC 값
    code_name: str     # 'INVALID_FORMAT'
    clause: str        # '7.3.1'  ← 화면에 그대로 표시
    detail: str = ""

# ═══════════════════════════════════════════════════════════════
#  5. Frame — 계층 간 유일한 통행 타입
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Frame:
    header: Header
    kind: MsgKind | None = None          # 해석된 논리 종류 (0x0800 해소 결과)
    rsc: RSC | None = None
    nec: NEC | None = None
    node_property: NodeProperty | None = None
    device_main_infos: tuple[DeviceMainInfo, ...] = ()
    device_properties: tuple[DeviceProperty, ...] = ()
    device_ids: tuple[int, ...] = ()
    profile: MsgControlProfile | None = None
    raw: bytes = b""
    violations: tuple[Violation, ...] = ()
    t: float = 0.0

    @property
    def is_valid(self) -> bool:
        return len(self.violations) == 0

# ═══════════════════════════════════════════════════════════════
#  6. 페이로드 레이아웃 — N 산출의 정본
#     (fixed_bytes, element_bytes) ; element_bytes=0 이면 가변부 없음
# ═══════════════════════════════════════════════════════════════

LAYOUT: dict[MsgKind, tuple[int, int]] = {
    MsgKind.REQ_SET_CONNECTION:               (0, 0),
    MsgKind.REQ_SET_DEVICE_INIT:              (0, DID_BYTES),
    MsgKind.REQ_SET_DEVICE_INIT_ALL:          (0, 0),
    MsgKind.REQ_SET_NODE_PROPERTY:            (NP_BYTES, 0),
    MsgKind.REQ_SET_DEVICE_PROPERTY:          (0, DP_BYTES),
    MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL: (NP_BYTES, DP_BYTES),
    MsgKind.REQ_SET_MSG_FLOW_CONTROL_PROFILE: (MCP_BYTES, 0),
    MsgKind.REQ_GET_NODE_PROPERTY:            (0, 0),
    MsgKind.REQ_GET_DEVICE_PROPERTY:          (0, DID_BYTES),
    MsgKind.REQ_GET_NODE_DEVICE_PROPERTY_ALL: (0, 0),
    MsgKind.REQ_GET_DEVICE_VALUE:             (0, DID_BYTES),
    MsgKind.REQ_GET_MSG_FLOW_CONTROL_PROFILE: (0, 0),
    MsgKind.REQ_SET_DEVICE_CONTROL:           (0, DMI_BYTES),
    MsgKind.REQ_SET_REBOOT:                   (0, 0),
    MsgKind.RES_SET_CONNECTION:               (RSC_BYTES + NP_BYTES, DP_BYTES),
    MsgKind.RES_SET_DEVICE_INIT:              (RSC_BYTES, 0),
    MsgKind.RES_SET_DEVICE_INIT_ALL:          (RSC_BYTES, 0),
    MsgKind.RES_SET_NODE_PROPERTY:            (RSC_BYTES, 0),
    MsgKind.RES_SET_DEVICE_PROPERTY:          (RSC_BYTES, 0),
    MsgKind.RES_SET_NODE_DEVICE_PROPERTY_ALL: (RSC_BYTES, 0),
    MsgKind.RES_SET_MSG_FLOW_CONTROL_PROFILE: (RSC_BYTES, 0),
    MsgKind.RES_GET_NODE_PROPERTY:            (RSC_BYTES + NP_BYTES, 0),
    MsgKind.RES_GET_DEVICE_PROPERTY:          (RSC_BYTES, DP_BYTES),
    MsgKind.RES_GET_NODE_DEVICE_PROPERTY_ALL: (RSC_BYTES + NP_BYTES, DP_BYTES),
    MsgKind.RES_GET_DEVICE_VALUE:             (RSC_BYTES, DMI_BYTES),
    MsgKind.RES_GET_MSG_FLOW_CONTROL_PROFILE: (RSC_BYTES + MCP_BYTES, 0),
    MsgKind.RES_SET_DEVICE_CONTROL:           (RSC_BYTES, 0),
    MsgKind.RES_SET_REBOOT:                   (RSC_BYTES, 0),
    MsgKind.NOTI_ERROR:                       (NEC_BYTES, 0),
    MsgKind.NOTI_DEVICE_VALUE:                (0, DMI_BYTES),
    MsgKind.NOTI_DISCONNECT:                  (0, 0),
    MsgKind.NOTI_REBOOT:                      (0, 0),
    MsgKind.NOTI_KEEP_ALIVE:                  (0, 0),
    MsgKind.ACK:                              (0, 0),
}

def element_count(kind: MsgKind, payload_len: int) -> int | None:
    """N 산출. 규격에 맞지 않으면 None (→ INVALID_FORMAT, 7.3.1).

    표준 미규정 사항에 대한 구현 결정:
      고정부 없이 가변부만 갖는 메시지(REQ_SET_DEVICE_CONTROL,
      NOTI_DEVICE_VALUE 등)는 N >= 1 을 요구한다. N=0 이면 페이로드가
      비어 있어 '페이로드 없음' 메시지와 구별되지 않고, 의미도 없다.
      고정부가 있는 메시지(RES_SET_CONNECTION 등)는 N=0 을 허용한다
      — 디바이스가 0개인 노드가 실제로 존재할 수 있다."""
    fixed, elem = LAYOUT[kind]
    rest = payload_len - fixed
    if rest < 0:
        return None
    if elem == 0:
        return 0 if rest == 0 else None
    if rest % elem:
        return None
    n = rest // elem
    if n == 0 and fixed == 0:
        return None
    if n > MAX_DEVICES_PER_NODE:      # F-120 — 노드당 디바이스 상한(위 각주)
        return None
    return n

def resolve_kind(msg_type: int, payload_len: int, mode: Mode = "strict") -> MsgKind | None:
    """전송 코드 → 논리 종류. 0x0800 중복은 페이로드 길이로 판별한다.
       NEC는 1byte, DEVICE_MAIN_INFO는 7byte이므로 두 집합은 배타적이다."""
    table = WIRE_CODE if mode == "strict" else WIRE_CODE_EXT
    cands = [k for k, c in table.items() if c == msg_type]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    for k in cands:                                  # 0x0800 (strict)
        if element_count(k, payload_len) is not None:
            return k
    return None

# ═══════════════════════════════════════════════════════════════
#  7. 방향과 회신 — 0943 6.2.2 / 8장 시퀀스 다이어그램
#     F-040: 게이트웨이가 "무엇에 무엇으로 답해야 하는가"의 정본.
#     서비스 계층이 이 표를 다시 만들면 표준 해석이 두 곳에 생긴다(CLAUDE.md §3.4).
# ═══════════════════════════════════════════════════════════════

#: 노드가 보낼 수 있는 Request. 게이트웨이는 대응 Response 를 회신해야 한다.
NODE_ORIGINATED_REQUESTS: frozenset[MsgKind] = frozenset({
    MsgKind.REQ_SET_CONNECTION,                    # 8.1.1   노드→GCG
    MsgKind.REQ_SET_NODE_PROPERTY,                 # 8.1.3.1 양방향
    MsgKind.REQ_SET_DEVICE_PROPERTY,               # 8.1.3.2 양방향
    MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL,      # 8.1.3.3 양방향
    MsgKind.REQ_SET_MSG_FLOW_CONTROL_PROFILE,      # 8.1.3.4 양방향
})

#: 노드가 보낼 수 있는 Notify. 게이트웨이는 ACK 를 회신해야 한다 (6.2.2).
NODE_ORIGINATED_NOTIFIES: frozenset[MsgKind] = frozenset({
    MsgKind.NOTI_ERROR,          # 8.2.1.1
    MsgKind.NOTI_DEVICE_VALUE,   # 8.2.1.2
    MsgKind.NOTI_DISCONNECT,     # 8.2.1.3
    MsgKind.NOTI_REBOOT,         # 8.2.1.4
    MsgKind.NOTI_KEEP_ALIVE,     # 8.2.1.5
})

#: Request → 대응 Response (표 7-2 / 표 7-3, 전송 코드 +0x0400)
RESPONSE_OF: dict[MsgKind, MsgKind] = {
    req: MsgKind[f"RES_{req.name[4:]}"] for req in _REQ
}

def reply_kind(kind: MsgKind | None) -> MsgKind | None:
    """수신 종류에 대해 게이트웨이가 **즉시 회신해야 하는** 종류.
    None 이면 회신하지 않는다 (Response·ACK 수신, 또는 해석 불가).

    위반 프레임에도 이 표를 그대로 적용한다 — 0943 7.3.1 은 요청 처리 실패 시
    Response 에 오류 RSC 를 담아 보내도록 규정한다. 다만 ACK 는 헤더뿐이라
    오류를 실을 수단이 없으므로 **위반 Notify 에는 ACK 를 보내지 않는다**
    (표준 미규정 → 자체 결정, docs/standard-findings.md 참조)."""
    if kind is None:
        return None
    if kind in NODE_ORIGINATED_REQUESTS:
        return RESPONSE_OF[kind]
    if kind in NODE_ORIGINATED_NOTIFIES:
        return MsgKind.ACK
    return None

def expected_reply(kind: MsgKind | None) -> MsgKind | None:
    """게이트웨이가 `kind` 를 보냈을 때 **되돌아와야 하는** 종류. reply_kind() 의 쌍.

    F-046 — 대기 요청의 매칭 기준이다. `Node ID` + `Message Identifier` 만 보면
    다른 요청의 지연·중복 Response 나 우연히 번호가 같은 ACK 가 현재 호출의
    결과로 반환된다. 7.2.2 의 매칭은 '어느 요청의 응답인가'를 가리는 것이므로
    `Message Type` 까지 확인해야 성립한다."""
    if kind is None:
        return None
    if kind in RESPONSE_OF:                      # Request 14종 → 대응 Response
        return RESPONSE_OF[kind]
    if kind.name.startswith("NOTI_"):            # Notify → ACK (6.2.2)
        return MsgKind.ACK
    return None                                  # RES_* · ACK 는 회신을 기다리지 않는다
