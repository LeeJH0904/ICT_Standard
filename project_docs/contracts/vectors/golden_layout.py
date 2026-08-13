"""골든 테스트 벡터 원본 — 손으로 적은 비트 레이아웃 (CLAUDE.md 6.2)

이 파일이 골든 벡터의 **정본**이다. `golden.jsonl` 은 여기서 생성된 결과물이다.

규약 6.2: "손으로 만들고 코드로 검증한다. 코드로 생성한 것을 정답으로 삼으면
자기 검증 순환이 된다."

그래서 이렇게 한다.
  - 벡터마다 (필드명, 비트폭, 값) 을 **표준 표를 보며 손으로** 적는다.
  - 아래 pack() 은 메시지 구조를 전혀 모른다. 비트를 잇고 바이트 정렬을 확인할 뿐이다.
  - siap/spec_verify.py 의 인코더를 재사용하지 않는다. 같은 명세서에서 **독립적으로**
    다시 타이핑한 것이며, 두 구현이 같은 바이트를 내놓는지가 곧 교차 검증이다.
  - 기대 디코드 결과(kind · N · violations)도 손으로 적는다.
    golden_verify.py 가 contracts/frame.py 로 그 값을 재산출해 대조한다.

레이아웃 출처 (SIAP 메시지 명세서 1~2절 = 0943 그림 7-1, 표 7-13 ~ 7-18):
  헤더               96 bit  Version 8 / Message Type 14 / Transmission Type 2 /
                             Message Identifier 16 / Payload Length 16 / GCG ID 20 / Node ID 20
  NODE_PROPERTY      64 bit  표 7-13
  DEVICE_MAIN_INFO   56 bit  표 7-14
  DEVICE_PROPERTY   240 bit  표 7-15
  MSG_CONTROL_PROFILE 56 bit 표 7-18
  RSC / NEC / DEVICE_ID 각 8 bit  표 7-9 ~ 7-12, 표 7-17

실행:  python project_docs/contracts/vectors/golden_layout.py
       -> golden.jsonl (53건, F-120 B11 포함) / golden_ext.jsonl (5건)
"""
from __future__ import annotations
import json, struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# F-045 — 한국어 Windows 기본 콘솔(CP949)에서 중단되지 않게 한다.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

# ═══════════════════════════════════════════════════════════════
#  0. 범용 비트 결합기 — 메시지 구조를 모른다
# ═══════════════════════════════════════════════════════════════
Field = tuple[str, int, int]          # (필드명, 비트폭, 값)

def F(name: str, bits: int, value: int) -> Field:
    if not (0 <= value < (1 << bits)):
        raise ValueError(f"{name}: {value} 는 {bits}bit 에 담기지 않는다")
    return (name, bits, value)

def pack(fields: list[Field]) -> bytes:
    """(비트폭, 값) 을 MSB 우선으로 잇는다. 구조 지식 0."""
    acc = 0
    total = 0
    for _, bits, value in fields:
        acc = (acc << bits) | value
        total += bits
    if total % 8:
        raise ValueError(f"바이트 정렬 아님: {total} bit")
    return acc.to_bytes(total // 8, "big")

def bitlen(fields: list[Field]) -> int:
    return sum(b for _, b, _ in fields)

# ═══════════════════════════════════════════════════════════════
#  1. IEEE-754 single 상수 — 손으로 계산하고 코드로 확인한다
#     표준은 FLOAT 표현 방식을 규정하지 않는다(F-004). 자체 결정한
#     single precision · big-endian 이 맞는지 여기서 못박는다.
# ═══════════════════════════════════════════════════════════════
FLOATS = {
    "25.3":       0x41CA6666,
    "61.0":       0x42740000,
    "-40.0":      0xC2200000,
    "80.0":       0x42A00000,
    "0.1":        0x3DCCCCCD,
    "FLOAT_MAX":  0x7F7FFFFF,   # 3.4028234663852886e38
    "0.0":        0x00000000,
}
def _check_floats() -> list[str]:
    bad = []
    for label, bits in FLOATS.items():
        got = struct.unpack(">f", struct.pack(">I", bits))[0]
        if label == "FLOAT_MAX":
            ok = got == 3.4028234663852886e38
        else:
            ok = abs(got - float(label)) < max(1e-4, abs(float(label)) * 1e-6)
        if not ok:
            bad.append(f"{label}: 0x{bits:08X} -> {got!r}")
    return bad

# ═══════════════════════════════════════════════════════════════
#  2. 구조체 레이아웃 — 명세서 표를 그대로 옮겼다
# ═══════════════════════════════════════════════════════════════
def header(msg_type: int, msg_id: int, plen: int, *,
           version: int = 0x12, trans: int = 0x00,
           gcg: int = 0x00001, node: int = 0x00003) -> list[Field]:
    """96 bit. 그림 7-1 / 표 7-5 ~ 7-8. 오프셋 순서 그대로."""
    return [F("Version", 8, version),
            F("Message Type", 14, msg_type),
            F("Transmission Type", 2, trans),
            F("Message Identifier", 16, msg_id),
            F("Payload Length", 16, plen),
            F("GCG ID", 20, gcg),
            F("Node ID", 20, node)]

def node_property(sw: int, gcg: int, node: int, status: int, ndev: int) -> list[Field]:
    """64 bit. 표 7-13."""
    return [F("S/W Version", 8, sw), F("GCG ID", 20, gcg), F("Node ID", 20, node),
            F("Status", 8, status), F("Num. of Devices", 8, ndev)]

def dmi(device_id: int, dtype: int, subtype: int, vtype: int, value: int) -> list[Field]:
    """56 bit. 표 7-14. value 는 32bit 원시 비트열 — FLOAT 이면 IEEE-754 패턴."""
    return [F("Device ID", 8, device_id), F("Type", 1, dtype), F("Subtype", 8, subtype),
            F("Value Type", 2, vtype), F("Reserved", 5, 0), F("Value", 32, value)]

def device_property(main: list[Field], tmode: int, period: int,
                    lo_v: int, up_v: int, lo_l: int, up_l: int,
                    prec: int, status: int) -> list[Field]:
    """240 bit. 표 7-15. 앞 56 bit 는 DEVICE_MAIN_INFO."""
    return main + [F("Transfer Mode", 2, tmode), F("Period", 14, period),
                   F("Lower Value", 32, lo_v), F("Upper Value", 32, up_v),
                   F("Lower Limit", 32, lo_l), F("Upper Limit", 32, up_l),
                   F("Precision", 32, prec), F("Status", 8, status)]

def mcp(timeout: int, retry: int, noti_iv: int, keep_iv: int) -> list[Field]:
    """56 bit. 표 7-18. 시간 3필드 전부 sec (F-033 구현 결정)."""
    return [F("Message Receive Timeout", 16, timeout), F("Num. of Retry", 8, retry),
            F("Notify Error Interval", 16, noti_iv), F("Keep Alive Interval", 16, keep_iv)]

def rsc(code: int) -> list[Field]:  return [F("RSC", 8, code)]      # 표 7-9 / 7-10
def nec(code: int) -> list[Field]:  return [F("NEC", 8, code)]      # 표 7-11 / 7-12
def device_ids(*ids: int) -> list[Field]:                           # 표 7-17
    return [F(f"Device ID[{i}]", 8, v) for i, v in enumerate(ids)]

# ── 지원 상한 (F-064) ────────────────────────────────────────
#   표준은 Num. of Devices 를 8bit(최대 255)로 두지만 Timeout 과의 관계를
#   규정하지 않는다. 본 구현의 상한과 그 근거는 아키텍처 6.2 에 있다.
MAX_DEVICES_PER_NODE = 16
BAUD = 9600
def wire_ms(nbytes: int) -> float:
    """8N1 = 10 bit/byte. 전송에 걸리는 시간(ms)."""
    return nbytes * 10 * 1000 / BAUD

# 자주 쓰는 조합 (값은 데모 시드 기준)
# F-068 — COMBINED_PROPERTY(표 7-16 = NODE_PROPERTY + DEVICE_PROPERTY x N)에서
#   NODE_PROPERTY.Num. of Devices 는 뒤따르는 DEVICE_PROPERTY 개수와 같아야 한다.
#   7.3.3.4 "노드 속성과 해당 노드에 연결된 N개 디바이스의 속성 정보".
#   한 페이로드가 디바이스 수를 두 값으로 주장하면 그 프레임은 자기모순이다.
#   그래서 ndev 를 인자로 받는 헬퍼를 쓰고, 상수 재사용을 금지한다.
def NP(ndev: int) -> list[Field]:
    """데모 노드의 NODE_PROPERTY. ndev 만 벡터마다 다르다."""
    return node_property(0x10, 0x00001, 0x00003, 0x00, ndev)

NP_3DEV = NP(3)      # NODE_PROPERTY 단독 메시지용 — 노드의 실제 디바이스 수
DMI_TEMP = dmi(1, 0, 0x01, 2, FLOATS["25.3"])        # 온도 센서 25.3 C
DMI_HUMI = dmi(2, 0, 0x02, 2, FLOATS["61.0"])        # 습도 센서 61.0 %
DMI_VALVE = dmi(5, 1, 0x85, 1, 1)                    # 관수밸브 ON (UINT)
DP_TEMP = device_property(DMI_TEMP, 0, 60,
                          FLOATS["-40.0"], FLOATS["80.0"],
                          FLOATS["-40.0"], FLOATS["80.0"], FLOATS["0.1"], 0x00)
MCP_STD = mcp(2, 3, 30, 60)                          # 전부 sec

# ═══════════════════════════════════════════════════════════════
#  3. 벡터 정의
# ═══════════════════════════════════════════════════════════════
VECTORS: list[dict] = []

def V(vid: str, msg: str, direction: str, clause: str, note: str,
      hdr: list[Field], payload: list[Field] | None = None,
      *, kind: str | None = "SAME", n: int | None = 0,
      violations: list[dict] | None = None, axis: str | None = None,
      inject: str | None = None, nec_alert: dict | None = None,
      category: str = "정상", plen_override: bool = False) -> None:
    """벡터 1건. hdr·payload 는 손으로 적은 필드 목록이다.

    kind="SAME" 이면 msg 와 같다는 뜻. 판별 불가 기대는 None 을 준다.
    plen_override=True 면 Payload Length 를 일부러 어긋나게 둔 것이다(위반 케이스)."""
    payload = payload or []
    declared = dict(hdr)[("Payload Length")] if False else \
        next(v for nm, _, v in hdr if nm == "Payload Length")
    actual = bitlen(payload) // 8
    if not plen_override and declared != actual:
        raise ValueError(f"{vid}: Payload Length 표기 {declared} != 실제 {actual} byte")
    raw = pack(hdr) + pack(payload)
    VECTORS.append({
        "id": vid, "msg": msg, "kind": (msg if kind == "SAME" else kind),
        "dir": direction, "category": category, "clause": clause, "note": note,
        "hex": raw.hex().upper(), "len": len(raw),
        "header": {nm: v for nm, _, v in hdr},
        "n": n, "violations": violations or [], "axis": axis,
        # F-060 — 프로토콜 위반과 노드 오류 알림은 다른 것이다.
        #   violation : 프레임이 표준을 어겼다 -> 격리, 회신 없음
        #   alert     : 프레임은 정상이고 노드가 오류를 알린다 -> alert 저장 + ACK
        "judgement": ("alert" if nec_alert else ("violation" if violations else "normal")),
        "inject": inject, "nec_alert": nec_alert,
        "fields": [{"name": nm, "bits": b, "value": v} for nm, b, v in hdr + payload],
    })

H = header   # 짧게

def VIO(code: int, name: str, clause: str, detail: str) -> list[dict]:
    return [{"code": code, "code_name": name, "clause": clause, "detail": detail}]

# F-116 — 경계값 벡터(B02 등)도 위반으로 판정될 수 있어 VIO 를 V() 바로
# 뒤로 옮겼다. 원래 "3.3 위반 8종" 절 서두에 있던 정의였다.

# ── 3.1 정상 메시지 34종 (표 7-2 ~ 7-4) ─────────────────────────
# 헤더만 (페이로드 없음) 10종
V("N01", "REQ_SET_CONNECTION", "N->G", "8.1.1", "노드 연결 요청. 페이로드 없음",
  H(0x0000, 1, 0))
V("N02", "REQ_SET_DEVICE_INIT_ALL", "G->N", "8.1.2.2", "전체 디바이스 초기화",
  H(0x0002, 2, 0))
V("N03", "REQ_GET_NODE_PROPERTY", "G->N", "8.1.4.1", "노드 속성 조회",
  H(0x0007, 3, 0))
V("N04", "REQ_GET_NODE_DEVICE_PROPERTY_ALL", "G->N", "8.1.4.3", "노드+디바이스 속성 일괄 조회",
  H(0x0009, 4, 0))
V("N05", "REQ_GET_MSG_FLOW_CONTROL_PROFILE", "G->N", "8.1.4.5", "메시지 프로파일 조회",
  H(0x000B, 5, 0))
V("N06", "REQ_SET_REBOOT", "G->N", "8.1.6", "노드 재기동 요청",
  H(0x000D, 6, 0))
V("N07", "NOTI_DISCONNECT", "양방향", "8.2.1.3", "연결 해제 알림",
  H(0x0801, 7, 0))
V("N08", "NOTI_REBOOT", "양방향", "8.2.1.4", "재기동 알림",
  H(0x0802, 8, 0))
V("N09", "NOTI_KEEP_ALIVE", "N->G", "8.2.1.5", "생존 알림",
  H(0x0803, 9, 0))
V("N10", "ACK", "양방향", "8.2", "알림 수신 확인. 헤더만",
  H(0x0C00, 10, 0))

# RSC 1바이트만 8종
V("N11", "RES_SET_DEVICE_INIT", "N->G", "8.1.2.1", "RSC=SUCCESS",
  H(0x0401, 11, 1), rsc(0x00))
V("N12", "RES_SET_DEVICE_INIT_ALL", "N->G", "8.1.2.2", "RSC=SUCCESS",
  H(0x0402, 12, 1), rsc(0x00))
V("N13", "RES_SET_NODE_PROPERTY", "양방향", "8.1.3.1", "RSC=SUCCESS",
  H(0x0403, 13, 1), rsc(0x00))
V("N14", "RES_SET_DEVICE_PROPERTY", "양방향", "8.1.3.2", "RSC=SUCCESS",
  H(0x0404, 14, 1), rsc(0x00))
V("N15", "RES_SET_NODE_DEVICE_PROPERTY_ALL", "양방향", "8.1.3.3", "RSC=SUCCESS",
  H(0x0405, 15, 1), rsc(0x00))
V("N16", "RES_SET_MSG_FLOW_CONTROL_PROFILE", "양방향", "8.1.3.4", "RSC=SUCCESS",
  H(0x0406, 16, 1), rsc(0x00))
V("N17", "RES_SET_DEVICE_CONTROL", "N->G", "8.1.5", "RSC=SUCCESS",
  H(0x040C, 17, 1), rsc(0x00))
V("N18", "RES_SET_REBOOT", "N->G", "8.1.6", "RSC=SUCCESS",
  H(0x040D, 18, 1), rsc(0x00))

# 페이로드 있는 16종
V("N19", "REQ_SET_DEVICE_INIT", "G->N", "8.1.2.1", "DEVICE_ID x 3 (표 7-17)",
  H(0x0001, 19, 3), device_ids(1, 2, 5), n=3)
V("N20", "REQ_SET_NODE_PROPERTY", "양방향", "8.1.3.1", "NODE_PROPERTY (표 7-13)",
  H(0x0003, 20, 8), NP_3DEV, n=0)
V("N21", "REQ_SET_DEVICE_PROPERTY", "양방향", "8.1.3.2", "DEVICE_PROPERTY x 1 (표 7-15)",
  H(0x0004, 21, 30), DP_TEMP, n=1)
V("N22", "REQ_SET_NODE_DEVICE_PROPERTY_ALL", "양방향", "8.1.3.3",
  "NODE_PROPERTY + DEVICE_PROPERTY x 1. Num. of Devices=1 로 개수를 맞춘다 (F-068)",
  H(0x0005, 22, 38), NP(1) + DP_TEMP, n=1)
V("N23", "REQ_SET_MSG_FLOW_CONTROL_PROFILE", "양방향", "8.1.3.4", "MSG_CONTROL_PROFILE (표 7-18)",
  H(0x0006, 23, 7), MCP_STD, n=0)
V("N24", "REQ_GET_DEVICE_PROPERTY", "G->N", "8.1.4.2", "DEVICE_ID x 2",
  H(0x0008, 24, 2), device_ids(1, 2), n=2)
V("N25", "REQ_GET_DEVICE_VALUE", "G->N", "8.1.4.4", "DEVICE_ID x 3",
  H(0x000A, 25, 3), device_ids(1, 2, 5), n=3)
V("N26", "REQ_SET_DEVICE_CONTROL", "G->N", "8.1.5", "관수밸브 ON (DEVICE_MAIN_INFO x 1)",
  H(0x000C, 26, 7), DMI_VALVE, n=1)
V("N27", "RES_SET_CONNECTION", "G->N", "8.1.1",
  "RSC + NODE_PROPERTY + DEVICE_PROPERTY x 1. Num. of Devices=1 (F-068)",
  H(0x0400, 27, 39), rsc(0x00) + NP(1) + DP_TEMP, n=1)
V("N28", "RES_GET_NODE_PROPERTY", "N->G", "8.1.4.1", "RSC + NODE_PROPERTY",
  H(0x0407, 28, 9), rsc(0x00) + NP_3DEV, n=0)
V("N29", "RES_GET_DEVICE_PROPERTY", "N->G", "8.1.4.2", "RSC + DEVICE_PROPERTY x 1",
  H(0x0408, 29, 31), rsc(0x00) + DP_TEMP, n=1)
V("N30", "RES_GET_NODE_DEVICE_PROPERTY_ALL", "N->G", "8.1.4.3",
  "RSC + NODE_PROPERTY + DEVICE_PROPERTY x 1. Num. of Devices=1 (F-068)",
  H(0x0409, 30, 39), rsc(0x00) + NP(1) + DP_TEMP, n=1)
V("N31", "RES_GET_DEVICE_VALUE", "N->G", "8.1.4.4", "RSC + DEVICE_MAIN_INFO x 2",
  H(0x040A, 31, 15), rsc(0x00) + DMI_TEMP + DMI_HUMI, n=2)
V("N32", "RES_GET_MSG_FLOW_CONTROL_PROFILE", "N->G", "8.1.4.5", "RSC + MSG_CONTROL_PROFILE",
  H(0x040B, 32, 8), rsc(0x00) + MCP_STD, n=0)
V("N33", "NOTI_ERROR", "N->G", "8.2.1.1", "NEC=ERROR_PWR (0x05). 0x0800 중복은 길이로 판별",
  H(0x0800, 33, 1), nec(0x05), n=0)
V("N34", "NOTI_DEVICE_VALUE", "N->G", "8.2.1.2", "DEVICE_MAIN_INFO x 2. 0x0800 중복은 길이로 판별",
  H(0x0800, 34, 14), DMI_TEMP + DMI_HUMI, n=2)

# ── 3.2 경계값 10종 ─────────────────────────────────────────────
V("B01", "RES_SET_CONNECTION", "G->N", "명세서 4절",
  "N=0 허용 — **디바이스가 0대인 노드**의 연결 응답. 고정부(RSC+NODE_PROPERTY)가 "
  "있으므로 가변부 0개는 정상이며, Num. of Devices 도 0 이라 자기모순이 없다 (F-068)",
  H(0x0400, 40, 9), rsc(0x00) + NP(0), n=0, axis="N=0 허용", category="경계")
V("B02", "REQ_SET_DEVICE_CONTROL", "G->N", "명세서 4절",
  "N=0 거부 — 가변부만 있는 메시지의 빈 페이로드. 코드는 해석되지만 "
  "element_count() 가 None 을 돌려 INVALID_FORMAT 이 된다",
  H(0x000C, 41, 0), [], n=None, axis="N=0 거부", category="경계",
  # F-116 — note 가 이미 "INVALID_FORMAT 이 된다"고 적어 뒀는데도 violations 인자가
  # 빠져 judgement=normal/violations=[] 로 생성되던 결함. Frame 구조 명세서 §4.1과
  # contracts/frame.py:element_count() (고정부 없이 가변부만 있는 메시지는 N>=1
  # 필요, 아니면 None -> 7.3.1) 가 근거다. 이 한 줄을 추가하면 judgement 는
  # V() 의 파생 규칙(violations 있음 -> "violation")으로 자동 전환된다.
  violations=VIO(0x09, "INVALID_FORMAT", "7.3.1",
                 "Payload Length=0, 가변부만 있는 메시지는 N>=1 필요"))
# F-064 — 지원 상한 N=16 의 최대 프레임. 아키텍처 6.2 의 timeout 근거이자
#   firmware 의 수신 버퍼 크기를 정하는 프레임이다.
#   RSC(1) + NODE_PROPERTY(8) + DEVICE_PROPERTY(30) x 16 = 489 byte payload,
#   헤더 포함 501 byte -> 9600 baud 8N1 에서 0.52 s.
#   표준의 Num. of Devices 는 8bit(최대 255)라 이론상 7,671 byte 까지 가능하지만,
#   기본 프로파일 Timeout 2 s 로는 수용할 수 없다(표준결함 F-065).
V("B03", "RES_SET_CONNECTION", "G->N", "표 7-15 / 표 7-16",
  "지원 상한 최대 프레임 — DEVICE_PROPERTY x 16 (501 byte). "
  "Payload Length 가 255 를 넘어 16bit 필드가 실제로 쓰인다",
  H(0x0400, 42, 489),
  rsc(0x00) + NP(MAX_DEVICES_PER_NODE) + [f for i in range(16) for f in
      device_property(dmi(i + 1, 0, 0x01, 2, FLOATS["25.3"]), 0, 60,
                      FLOATS["-40.0"], FLOATS["80.0"],
                      FLOATS["-40.0"], FLOATS["80.0"], FLOATS["0.1"], 0x00)],
  n=16, axis="지원 상한 최대 프레임", category="경계")
V("B04", "NOTI_KEEP_ALIVE", "N->G", "7.2.2",
  "Message Identifier 최댓값 0xFFFF (랩어라운드 직전)",
  H(0x0803, 0xFFFF, 0), axis="msg_id 랩어라운드", category="경계")
V("B05", "NOTI_KEEP_ALIVE", "N->G", "7.2.2",
  "Message Identifier 0x0000 (랩어라운드 직후)",
  H(0x0803, 0x0000, 0), axis="msg_id 랩어라운드", category="경계")
V("B06", "ACK", "양방향", "7.2.4",
  "GCG ID / Node ID 20bit 최댓값 0xFFFFF — 9번째 바이트를 반씩 나눠 쓰는 경계",
  H(0x0C00, 43, 0, gcg=0xFFFFF, node=0xFFFFF), axis="식별자 20bit 최댓값", category="경계")
V("B07", "NOTI_DEVICE_VALUE", "N->G", "표 7-14",
  "Value INT 최솟값 -2^31 (0x80000000, 2의 보수)",
  H(0x0800, 44, 7), dmi(1, 0, 0x08, 0, 0x80000000), n=1,
  axis="Value 타입별 경계", category="경계")
V("B08", "NOTI_DEVICE_VALUE", "N->G", "표 7-14",
  "Value UINT 최댓값 2^32-1 (0xFFFFFFFF) — INT 로 읽으면 -1 이 되는 같은 비트열",
  H(0x0800, 45, 7), dmi(3, 0, 0x03, 1, 0xFFFFFFFF), n=1,
  axis="Value 타입별 경계", category="경계")
V("B09", "NOTI_DEVICE_VALUE", "N->G", "표 7-14",
  "Value FLOAT 최댓값 0x7F7FFFFF — IEEE-754 single 의 최대 유한값 (F-055)",
  H(0x0800, 46, 7), dmi(1, 0, 0x01, 2, FLOATS["FLOAT_MAX"]), n=1,
  axis="Value 타입별 경계", category="경계")
V("B10", "REQ_SET_DEVICE_PROPERTY", "양방향", "표 7-15",
  "Period 14bit 최댓값 16383 + Transfer Mode=Both(0x02). 2+14 가 한 바이트 경계를 넘는다",
  H(0x0004, 47, 30),
  device_property(DMI_TEMP, 0x02, 16383, FLOATS["-40.0"], FLOATS["80.0"],
                  FLOATS["-40.0"], FLOATS["80.0"], FLOATS["0.1"], 0x00),
  n=1, axis="필드 폭 최댓값", category="경계")
# F-120 — 노드당 디바이스 상한(N=16, CLAUDE.md §3.5/F-064) 을 넘는 프레임의
# 거부. 표준은 이 상한을 규정하지 않지만(F-065) 본 구현은 Timeout·메모리
# 산정의 전제가 깨지므로 N=17 을 INVALID_FORMAT 으로 거부한다 — B03(N=16,
# 상한 자체는 허용)과 짝을 이루는 "상한을 넘으면" 경계다.
V("B11", "REQ_SET_DEVICE_CONTROL", "G->N", "CLAUDE.md 3.5 / F-064 / F-120",
  "노드당 디바이스 상한 N=16 초과 거부 — DEVICE_MAIN_INFO x 17 (119 byte)",
  H(0x000C, 48, 119),
  [f for i in range(17) for f in dmi(i + 1, 1, 0x85, 1, 1)],
  n=None, axis="N 상한 초과", category="경계",
  violations=VIO(0x09, "INVALID_FORMAT", "7.3.1",
                 "N=17, 노드당 디바이스 상한(16) 초과"))

# ── 3.3 위반 8종 (CLAUDE.md 6.3 — 기능 2 주입 시나리오) ──────────
# VIO() 정의는 V() 바로 뒤로 옮겼다 (F-116 — B02 도 VIO 를 참조해야 한다).

# F-062 — 주입 라벨. golden_verify 가 라벨 <-> 기대 코드를 1:1 로 대조한다.
#         "위반 8종이 다 있다"가 아니라 "이 주입에 이 코드가 붙었다"를 본다.

V("X01", "NOTI_KEEP_ALIVE", "N->G", "7.3.1", "Version 조작 (0x12 -> 0x99)",
  H(0x0803, 50, 0, version=0x99), inject="version",
  violations=VIO(0x01, "INVALID_VERSION", "7.3.1", "Version=0x99, 기대 0x12"),
  category="위반")
V("X02", "NOTI_KEEP_ALIVE", "N->G", "7.3.1", "미등록 Node ID (0x00003 -> 0xABCDE)",
  H(0x0803, 51, 0, node=0xABCDE), inject="unregistered_node",
  violations=VIO(0x03, "INVALID_NODE_ID", "7.3.1", "Node ID=0xABCDE 는 등록되지 않았다"),
  category="위반")
V("X03", "NOTI_ERROR", "N->G", "7.3.1", "Payload Length 표기 24, 실제 1 byte",
  H(0x0800, 52, 24), nec(0x00), kind=None, n=None, plen_override=True, inject="payload_length",
  violations=VIO(0x09, "INVALID_FORMAT", "7.3.1", "Payload Length=24, 실제 수신 1byte"),
  category="위반")
V("X04", None, "N->G", "표 7-2", "Message Type=0x000E — 표 7-2 미정의(RESERVED)",
  H(0x000E, 53, 0), kind=None, n=None, inject="message_type",
  violations=VIO(0x09, "INVALID_FORMAT", "표 7-2", "Message Type=0x000E 는 정의되지 않았다"),
  category="위반")
V("X05", "NOTI_KEEP_ALIVE", "N->G", "표 7-6", "Transmission Type=0x03 — 표 7-6 미정의",
  H(0x0803, 54, 0, trans=0x03), inject="transmission_type",
  violations=VIO(0x08, "INVALID_TRANSMISSION_TYPE", "표 7-6", "Transmission Type=0x03 은 정의되지 않았다"),
  category="위반")
V("X06", "NOTI_DEVICE_VALUE", "N->G", "표 7-14", "Value Type=0x03 — 표 7-14 RESERVED",
  H(0x0800, 55, 7), dmi(1, 0, 0x01, 3, 0x00000000), n=1, inject="value_type",
  violations=VIO(0x06, "INVALID_DATA_TYPE", "표 7-14", "Value Type=0x03 은 RESERVED"),
  category="위반")
V("X07", "NOTI_DEVICE_VALUE", "N->G", "표 7-14", "Subtype=0x7F — 레지스트리 미등록",
  H(0x0800, 56, 7), dmi(1, 0, 0x7F, 2, FLOATS["25.3"]), n=1, inject="subtype",
  violations=VIO(0x07, "INVALID_DATA_SUBTYPE", "표 7-14", "Subtype=0x7F 는 레지스트리에 없다"),
  category="위반")
# F-060 — 이 벡터만 성격이 다르다. 앞의 7건은 프레임이 표준을 어긴 것이고,
#   이것은 **프레임이 정상인데 노드가 오류를 알리는 것**이다(0943 8.2.1.1).
#   violations 에 넣으면 Frame.is_valid 가 false 가 되고, ingest.handle() 이
#   격리 후 즉시 반환해 alert 저장과 ACK 회신에 도달하지 못한다. 노드는 ACK 를
#   못 받아 Notify Error Interval 마다 재전송한다. 그래서 violations 는 비우고
#   nec_alert 로 분리한다.
V("X08", "NOTI_ERROR", "N->G", "7.3.2",
  "NEC=ERROR_BATTERY_LOW (0x07) 수신. 프레임은 정상이며 alert 저장 + ACK 회신이 기대 동작이다",
  H(0x0800, 57, 1), nec(0x07), n=0, inject="nec_battery_low",
  nec_alert={"code": 0x07, "code_name": "ERROR_BATTERY_LOW", "clause": "7.3.2",
             "detail": "노드 배터리 부족 알림 (NEC)"},
  category="위반")

# ═══════════════════════════════════════════════════════════════
#  4. extended 모드 — 0x0800 중복 해소 제안안 (별도 파일)
#     strict 는 표준 원문 그대로다. 개정 제안의 바이트 근거를 따로 남긴다.
# ═══════════════════════════════════════════════════════════════
EXT: list[dict] = []
def E(vid: str, msg: str, code: int, direction: str, note: str,
      payload: list[Field] | None = None, n: int = 0) -> None:
    """F-061 — 방향은 메시지마다 다르다. 개정 제안은 **코드만** 바꾸며,
    표 7-4 의 방향(NOTI_DISCONNECT · NOTI_REBOOT 은 양방향)을 건드리지 않는다."""
    payload = payload or []
    hdr = H(code, 60 + len(EXT), bitlen(payload) // 8)
    raw = pack(hdr) + pack(payload)
    EXT.append({"id": vid, "msg": msg, "kind": msg, "dir": direction, "mode": "extended",
                "clause": "표 7-4 (개정 제안)", "note": note,
                "hex": raw.hex().upper(), "len": len(raw),
                "header": {nm: v for nm, _, v in hdr}, "n": n, "violations": []})

E("E01", "NOTI_ERROR", 0x0800, "N->G", "제안안에서도 0x0800 유지", nec(0x05))
E("E02", "NOTI_DEVICE_VALUE", 0x0801, "N->G", "0x0800 -> 0x0801 로 분리. 길이 판별이 불필요해진다",
  DMI_TEMP + DMI_HUMI, n=2)
E("E03", "NOTI_DISCONNECT", 0x0802, "양방향", "0x0801 -> 0x0802. 방향은 표 7-4 그대로 양방향")
E("E04", "NOTI_REBOOT", 0x0803, "양방향", "0x0802 -> 0x0803. 방향은 표 7-4 그대로 양방향")
E("E05", "NOTI_KEEP_ALIVE", 0x0804, "N->G",
  "0x0803 -> 0x0804. RESERVED 시작 0x0805 와 맞물린다 (F-002)")

# ═══════════════════════════════════════════════════════════════
#  5. 생성 + 자체 점검
# ═══════════════════════════════════════════════════════════════
def main(check: bool = False) -> int:
    """check=True 면 **아무것도 쓰지 않고** 체크인된 파일과 대조만 한다 (F-063).
    생성기가 검증 도중에 산출물을 덮어쓰면 드리프트가 그 자리에서 사라진다."""
    ok = True
    print("골든 벡터 생성  (손으로 적은 레이아웃에서)\n")

    bad = _check_floats()
    if bad: ok = False
    print(f"  {'OK  ' if not bad else 'FAIL'} IEEE-754 상수 {len(FLOATS)}종 손계산 확인  {bad or ''}")

    counts = {"정상": 0, "경계": 0, "위반": 0}
    for v in VECTORS: counts[v["category"]] += 1
    exp = {"정상": 34, "경계": 11, "위반": 8}   # F-120 — B11 추가로 경계 10 -> 11
    same = counts == exp
    if not same: ok = False
    print(f"  {'OK  ' if same else 'FAIL'} 구성 {counts} (기대 {exp})")

    b03 = next(v for v in VECTORS if v["id"] == "B03")
    want = 12 + 1 + 8 + 30 * MAX_DEVICES_PER_NODE
    okb = b03["len"] == want
    if not okb: ok = False
    print(f"  {'OK  ' if okb else 'FAIL'} 지원 상한 최대 프레임 {b03['len']}B "
          f"(기대 {want}B, 9600 baud {wire_ms(b03['len']):.0f}ms)")

    # F-068 — COMBINED_PROPERTY 의 Num. of Devices == DEVICE_PROPERTY 개수
    comb_bad = []
    for v in VECTORS:
        names = [f["name"] for f in v["fields"]]
        if "Num. of Devices" not in names or "Transfer Mode" not in names:
            continue
        nd = next(f["value"] for f in v["fields"] if f["name"] == "Num. of Devices")
        if nd != v["n"]:
            comb_bad.append(f"{v['id']}: ndev={nd} N={v['n']}")
    if comb_bad: ok = False
    print(f"  {'OK  ' if not comb_bad else 'FAIL'} COMBINED_PROPERTY 의 Num. of Devices = N"
          f"  {'; '.join(comb_bad)}")

    ids = [v["id"] for v in VECTORS]
    uniq = len(ids) == len(set(ids))
    if not uniq: ok = False
    print(f"  {'OK  ' if uniq else 'FAIL'} 벡터 ID 고유 ({len(ids)}건)")

    # 정상 34종이 메시지 종류를 전부 덮는가
    normal_msgs = {v["msg"] for v in VECTORS if v["category"] == "정상"}
    cover = len(normal_msgs) == 34
    if not cover: ok = False
    print(f"  {'OK  ' if cover else 'FAIL'} 정상 벡터가 메시지 34종을 1건씩 덮음 ({len(normal_msgs)}종)")

    for path, data in ((HERE / "golden.jsonl", VECTORS), (HERE / "golden_ext.jsonl", EXT)):
        payload = "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in data)
        if check:
            cur = path.read_text(encoding="utf-8") if path.exists() else ""
            same = cur == payload
            if not same: ok = False
            print(f"  {'OK  ' if same else 'FAIL'} {path.name} 이 정본과 일치 ({len(data)}건)"
                  f"{'' if same else '  <- 재생성 필요'}")
        else:
            path.write_text(payload, encoding="utf-8", newline="\n")
            print(f"  {'OK  '} {path.name} <- {len(data)}건")

    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
