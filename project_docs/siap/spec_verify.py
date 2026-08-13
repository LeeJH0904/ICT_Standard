"""TTAK.KO-10.0943 (SIAP) 메시지 명세 검증 및 예시 프레임 생성"""
import struct, json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent   # F-013: 실행 위치 무관

# F-045 — 한국어 Windows 기본 콘솔은 CP949 다. 표현 불가 문자 하나로
#         검증 스크립트 전체가 UnicodeEncodeError 로 중단되면 재현성이 깨진다.
#         출력 문자는 CP949 안에서 고르는 것이 원칙이고(회귀 테스트로 강제),
#         이 가드는 새 문자가 섞여도 중단만은 막는 2중 방어다.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

# ── 비트 패킹 ────────────────────────────────────────────────
class BitWriter:
    def __init__(self): self.bits=[]
    def w(self, val, n):
        assert 0 <= val < (1<<n), f"value {val} overflows {n} bits"
        for i in range(n-1,-1,-1): self.bits.append((val>>i)&1)
        return self
    def wf(self, val):                      # IEEE-754 single, big-endian
        return self.w(struct.unpack('>I', struct.pack('>f', val))[0], 32)
    def bytes(self):
        assert len(self.bits)%8==0, f"not byte aligned: {len(self.bits)} bits"
        return bytes(int("".join(map(str,self.bits[i:i+8])),2) for i in range(0,len(self.bits),8))

class BitReader:
    def __init__(self, b): self.bits="".join(f"{x:08b}" for x in b); self.p=0
    def r(self, n):
        v=int(self.bits[self.p:self.p+n],2); self.p+=n; return v
    def rf(self):
        return struct.unpack('>f', struct.pack('>I', self.r(32)))[0]

# ── 구조체 (7.3.3) ───────────────────────────────────────────
def header(version, msg_type, trans_type, msg_id, plen, gcg, node):
    return BitWriter().w(version,8).w(msg_type,14).w(trans_type,2).w(msg_id,16)\
                      .w(plen,16).w(gcg,20).w(node,20).bytes()          # 96bit=12B

def node_property(sw, gcg, node, status, ndev):
    return BitWriter().w(sw,8).w(gcg,20).w(node,20).w(status,8).w(ndev,8).bytes()  # 64bit=8B

# ── Value(32bit) 패킹 — 표 7-14 Value Type ───────────────────
# 0=INT, 1=UNSIGNED INT, 2=FLOAT, 3=Reserved
INT32_MIN, INT32_MAX = -(1 << 31), (1 << 31) - 1
UINT32_MAX = (1 << 32) - 1
# F-055 — IEEE-754 single precision 의 최대 유한값. 이 범위를 넘으면 패킹 자체가 불가능하다.
#         struct 는 반올림 경계(약 3.40282357e38)까지 받아주지만, 명세는 표현 가능한
#         최대 유한값을 상한으로 삼는다 — 더 좁고 설명하기 쉬운 쪽을 고른다.
FLOAT32_MAX = 3.4028234663852886e38

class ValueRangeError(ValueError):
    """F-044 — 32bit 범위를 벗어난 값. 마스킹으로 조용히 래핑하지 않는다."""

def pack_value(b: "BitWriter", vtype: int, value) -> "BitWriter":
    """표 7-14 Value(32bit)를 Value Type 에 따라 패킹한다.
    F-044 — `int(v)&0xFFFFFFFF` 는 UINT 음수·2^32 이상, INT 범위 밖을
    오류 없이 다른 값으로 바꾼다. 골든 벡터의 정답이 오염되므로 실패시킨다."""
    if vtype == 2:                                    # FLOAT
        # F-058 — 변환 단계의 예외도 정규화한다. 10**400 은 float() 에서 OverflowError,
        #         "abc" 는 ValueError, None 은 TypeError 를 던져 계약이 입력 형태에 따라
        #         깨진다. 호출자는 ValueRangeError 하나만 잡으면 된다.
        try:
            fv = float(value)
        except (OverflowError, ValueError, TypeError) as e:
            raise ValueRangeError(
                f"FLOAT 로 변환할 수 없다: {value!r} ({type(e).__name__})") from e
        # F-055 — struct.pack 의 OverflowError 로 새어나가지 않게 여기서 판정한다.
        if fv != fv or fv in (float("inf"), float("-inf")):
            raise ValueRangeError(f"FLOAT 은 유한값만 담는다: {value!r}")
        if abs(fv) > FLOAT32_MAX:
            raise ValueRangeError(f"IEEE-754 single 범위 초과: {fv!r}")
        return b.wf(fv)
    if vtype == 3:                                    # 표 7-14 Reserved
        raise ValueRangeError("Value Type=0x03 은 표 7-14 Reserved")
    # F-058 — 정수 경로도 같은 누출이 있다. int(float('inf')) 는 OverflowError,
    #         int("abc") 는 ValueError, int(None) 은 TypeError 다.
    #         지적은 FLOAT 만 짚었으나 원인이 같으므로 함께 정규화한다.
    try:
        iv = int(value)
    except (OverflowError, ValueError, TypeError) as e:
        raise ValueRangeError(
            f"Value Type={vtype} 로 변환할 수 없다: {value!r} ({type(e).__name__})") from e
    if iv != value:
        raise ValueRangeError(f"Value Type={vtype} 는 정수만 담는다: {value!r}")
    if vtype == 0:                                    # INT — 2의 보수
        if not (INT32_MIN <= iv <= INT32_MAX):
            raise ValueRangeError(f"INT 32bit 범위 초과: {iv}")
        return b.w(iv & 0xFFFFFFFF, 32)
    if vtype == 1:                                    # UNSIGNED INT
        if not (0 <= iv <= UINT32_MAX):
            raise ValueRangeError(f"UINT 32bit 범위 초과: {iv}")
        return b.w(iv, 32)
    raise ValueRangeError(f"알 수 없는 Value Type: {vtype}")

def unpack_value(r: "BitReader", vtype: int):
    """F-044 — INT 는 2의 보수로 복원한다. 왕복이 성립해야 상호운용성이 증명된다.
    F-047 — 디코딩도 Value Type 을 강제한다. 0x03(Reserved)과 2bit 밖의 값을
            그대로 통과시키면 표 7-10 INVALID_DATA_TYPE(0x06) 위반을 놓친다.
            인코딩만 막고 디코딩을 열어두면 기능 2 의 판정 기준이 무너진다."""
    if vtype not in (0, 1, 2):
        raise ValueRangeError(f"Value Type={vtype} 은 표 7-14 정의 밖 (0x03=Reserved)")
    if vtype == 2: return r.rf()
    raw = r.r(32)
    if vtype == 0 and raw >= (1 << 31): raw -= (1 << 32)
    return raw

def device_main_info(did, dtype, subtype, vtype, value):
    b=BitWriter().w(did,8).w(dtype,1).w(subtype,8).w(vtype,2).w(0,5)
    pack_value(b, vtype, value)
    return b.bytes()                                                     # 56bit=7B

def main_value_type(main: bytes) -> int:
    """F-026 — DEVICE_MAIN_INFO(56bit)의 Value Type(offset 17, len 2)을 추출한다.
    별도 인자를 두면 main과 어긋날 수 있으므로 단일 출처에서 도출한다."""
    return (int.from_bytes(main, "big") >> (56 - 17 - 2)) & 0b11

def device_property(main, tmode, period, lo_v, up_v, lo_l, up_l, prec, status):
    """F-022 — 표 7-15의 USER DEPENDENT 5필드는 main.value 와 같은 물리량의
    경계·정밀도이므로 DEVICE_MAIN_INFO.Value Type 을 따른다 (구현 결정).
    F-026 — 타입은 main 바이트에서 직접 도출한다. 중복 인자를 두지 않는다."""
    vt = main_value_type(main)
    b=BitWriter()
    for byte in main: b.w(byte,8)                                        # 56
    b.w(tmode,2).w(period,14)                                            # 16
    for v in (lo_v,up_v,lo_l,up_l,prec):                                 # 160
        pack_value(b, vt, v)                                             # F-044
    b.w(status,8)                                                        # 8
    return b.bytes()                                                     # 240bit=30B

def msg_control_profile(timeout, retry, noti_iv, keep_iv):
    return BitWriter().w(timeout,16).w(retry,8).w(noti_iv,16).w(keep_iv,16).bytes()  # 56bit=7B

# ── 1차 검증: 구조체 크기가 표준 명시값과 일치하는가 ─────────
SIZES = {
    "Header":              (len(header(0x12,0,0,0,0,0,0)),           12, "그림 7-1 (96bit)"),
    "NODE_PROPERTY":       (len(node_property(1,0,0,0,0)),            8, "표 7-13 / 표 7-16 '64'"),
    "DEVICE_MAIN_INFO":    (len(device_main_info(1,0,1,2,0.0)),       7, "표 7-14 / 표 7-15 '56'"),
    "DEVICE_PROPERTY":     (len(device_property(device_main_info(1,0,1,2,0.0),0,0,0,0,0,0,0,0)), 30, "표 7-15 / 표 7-16 'N*240'"),
    "MSG_CONTROL_PROFILE": (len(msg_control_profile(0,0,0,0)),         7, "표 7-18 (56bit)"),
    "RSC":                 (1,                                          1, "표 7-9 (8bit)"),
    "NEC":                 (1,                                          1, "표 7-11 (8bit)"),
    "DEVICE_ID":           (1,                                          1, "표 7-17 (N*8bit)"),
}
print("[1차] 구조체 크기 ↔ 표준 명시값")
ok1=True
for k,(got,exp,src) in SIZES.items():
    m = "OK " if got==exp else "FAIL"
    if got!=exp: ok1=False
    print(f"  {m}  {k:<20} {got:>3}B (기대 {exp:>3}B)  {src}")

# ── 메시지 명세표 ────────────────────────────────────────────
H, RSC, NEC, NP, DMI, DP, DID, MCP = 12,1,1,8,7,30,1,7
# (name, code, dir, payload_expr, fixed, per_n, figure)
MSGS = [
 ("REQ_SET_CONNECTION",              0x0000,"N→G","(없음)",                                    H,   0,  "8-4"),
 ("REQ_SET_DEVICE_INIT",             0x0001,"G→N","DEVICE_ID×N",                               H,   DID,"8-7"),
 ("REQ_SET_DEVICE_INIT_ALL",         0x0002,"G→N","(없음)",                                    H,   0,  "8-10"),
 ("REQ_SET_NODE_PROPERTY",           0x0003,"양방향","NODE_PROPERTY",                          H+NP,0,  "8-13"),
 ("REQ_SET_DEVICE_PROPERTY",         0x0004,"양방향","DEVICE_PROPERTY×N",                      H,   DP, "8-16"),
 ("REQ_SET_NODE_DEVICE_PROPERTY_ALL",0x0005,"양방향","NODE_PROPERTY + DEVICE_PROPERTY×N",      H+NP,DP, "8-19"),
 ("REQ_SET_MSG_FLOW_CONTROL_PROFILE",0x0006,"양방향","MSG_CONTROL_PROFILE",                    H+MCP,0, "8-22"),
 ("REQ_GET_NODE_PROPERTY",           0x0007,"G→N","(없음)",                                    H,   0,  "8-25"),
 ("REQ_GET_DEVICE_PROPERTY",         0x0008,"G→N","DEVICE_ID×N",                               H,   DID,"8-28"),
 ("REQ_GET_NODE_DEVICE_PROPERTY_ALL",0x0009,"G→N","(없음)",                                    H,   0,  "8-31"),
 ("REQ_GET_DEVICE_VALUE",            0x000A,"G→N","DEVICE_ID×N",                               H,   DID,"8-34"),
 ("REQ_GET_MSG_FLOW_CONTROL_PROFILE",0x000B,"G→N","(없음)",                                    H,   0,  "8-37"),
 ("REQ_SET_DEVICE_CONTROL",          0x000C,"G→N","DEVICE_MAIN_INFO×N",                        H,   DMI,"8-40"),
 ("REQ_SET_REBOOT",                  0x000D,"G→N","(없음)",                                    H,   0,  "8-43"),
 ("RES_SET_CONNECTION",              0x0400,"G→N","RSC + NODE_PROPERTY + DEVICE_PROPERTY×N",   H+RSC+NP,DP,"8-5"),
 ("RES_SET_DEVICE_INIT",             0x0401,"N→G","RSC",                                       H+RSC,0,"8-8"),
 ("RES_SET_DEVICE_INIT_ALL",         0x0402,"N→G","RSC",                                       H+RSC,0,"8-11"),
 ("RES_SET_NODE_PROPERTY",           0x0403,"양방향","RSC",                                    H+RSC,0,"8-14"),
 ("RES_SET_DEVICE_PROPERTY",         0x0404,"양방향","RSC",                                    H+RSC,0,"8-17"),
 ("RES_SET_NODE_DEVICE_PROPERTY_ALL",0x0405,"양방향","RSC",                                    H+RSC,0,"8-20"),
 ("RES_SET_MSG_FLOW_CONTROL_PROFILE",0x0406,"양방향","RSC",                                    H+RSC,0,"8-23"),
 ("RES_GET_NODE_PROPERTY",           0x0407,"N→G","RSC + NODE_PROPERTY",                       H+RSC+NP,0,"8-26"),
 ("RES_GET_DEVICE_PROPERTY",         0x0408,"N→G","RSC + DEVICE_PROPERTY×N",                   H+RSC,DP,"8-29"),
 ("RES_GET_NODE_DEVICE_PROPERTY_ALL",0x0409,"N→G","RSC + NODE_PROPERTY + DEVICE_PROPERTY×N",   H+RSC+NP,DP,"8-32"),
 ("RES_GET_DEVICE_VALUE",            0x040A,"N→G","RSC + DEVICE_MAIN_INFO×N",                  H+RSC,DMI,"8-35"),
 ("RES_GET_MSG_FLOW_CONTROL_PROFILE",0x040B,"N→G","RSC + MSG_CONTROL_PROFILE",                 H+RSC+MCP,0,"8-38"),
 ("RES_SET_DEVICE_CONTROL",          0x040C,"N→G","RSC",                                       H+RSC,0,"8-41"),
 ("RES_SET_REBOOT",                  0x040D,"N→G","RSC",                                       H+RSC,0,"8-44"),
 ("NOTI_ERROR",                      0x0800,"N→G","NEC",                                       H+NEC,0,"8-48"),
 ("NOTI_DEVICE_VALUE",               0x0800,"N→G","DEVICE_MAIN_INFO×N",                        H,   DMI,"8-51"),
 ("NOTI_DISCONNECT",                 0x0801,"양방향","(없음)",                                 H,   0,  "8-54"),
 ("NOTI_REBOOT",                     0x0802,"양방향","(없음)",                                 H,   0,  "8-57"),
 ("NOTI_KEEP_ALIVE",                 0x0803,"N→G","(없음)",                                    H,   0,  "8-60"),
 ("ACK",                             0x0C00,"양방향","(없음)",                                 H,   0,  "8-49/52/55/58/61"),
]
print(f"\n[2차] 메시지 명세 {len(MSGS)}종")
# 코드공간 검증
blocks={"REQ":(0x0000,0x03FF),"RES":(0x0400,0x07FF),"NOTI":(0x0800,0x0BFF),"ACK":(0x0C00,0x0FFF)}
ok2=True
for n,c,*_ in MSGS:
    pre = n.split("_")[0]; pre = "REQ" if pre=="REQ" else "RES" if pre=="RES" else "NOTI" if pre=="NOTI" else "ACK"
    lo,hi = blocks[pre]
    if not (lo<=c<=hi): print(f"  FAIL {n} 0x{c:04X} not in {pre} block"); ok2=False
    if c >= 1<<14: print(f"  FAIL {n} exceeds 14-bit Message Type"); ok2=False
print(f"  {'OK  ' if ok2 else 'FAIL'} 모든 코드가 14bit 및 블록 경계 내")
# Request↔Response 대응
reqs={n[4:]:c for n,c,*_ in MSGS if n.startswith("REQ_")}
ress={n[4:]:c for n,c,*_ in MSGS if n.startswith("RES_")}
mism=[k for k in reqs if k in ress and ress[k]-reqs[k]!=0x0400]
print(f"  {'OK  ' if not mism else 'FAIL'} Request+0x0400 = Response ({len(reqs)}쌍){'' if not mism else ' -> '+str(mism)}")
# 코드 중복 (errata)
from collections import Counter
dup=[c for c,k in Counter(c for _,c,*_ in MSGS).items() if k>1]
print(f"  {'주의' if dup else 'OK  '} 중복 코드: {[hex(c) for c in dup]}  ← 표 7-4 errata")

# ── 3차: 예시 프레임 생성 및 왕복 검증 ───────────────────────
print("\n[3차] 예시 프레임 생성 + 왕복 검증")
vectors=[]
def emit(vid, name, code, direction, payload, clause, note):
    h=header(0x12, code, 0x00, len(vectors)+1, len(payload), 0x00001, 0x00003)
    raw=h+payload
    # 왕복: 헤더 재파싱
    r=BitReader(raw)
    got=(r.r(8), r.r(14), r.r(2), r.r(16), r.r(16), r.r(20), r.r(20))
    assert got==(0x12,code,0x00,len(vectors)+1,len(payload),1,3), f"{vid} roundtrip fail"
    assert got[4]==len(raw)-12, f"{vid} payload_len mismatch"
    vectors.append({"id":vid,"msg":name,"dir":direction,"clause":clause,
                    "hex":raw.hex().upper(),"len":len(raw),"note":note})
    print(f"  OK   {vid:<34} {len(raw):>3}B  {raw.hex().upper()[:44]}{'...' if len(raw)>22 else ''}")

# F-068 — COMBINED_PROPERTY(표 7-16)에서 Num. of Devices 는 뒤따르는
#         DEVICE_PROPERTY 개수와 같아야 한다. 아래 예시는 1건이므로 1.
np_ = node_property(0x10, 1, 3, 0x00, 1)
dmi_t = device_main_info(1, 0, 0x01, 2, 25.3)      # 온도 센서 25.3
dmi_h = device_main_info(2, 0, 0x02, 2, 61.0)      # 습도 센서 61%
dmi_v = device_main_info(5, 1, 0x85, 1, 1)         # 관수밸브 ON
dp_   = device_property(dmi_t, 0, 60, -40.0, 80.0, -40.0, 80.0, 0.1, 0x00)
mcp_  = msg_control_profile(2, 3, 30, 60)   # F-033: 전부 sec 단위

emit("REQ_SET_CONNECTION_min","REQ_SET_CONNECTION",0x0000,"노드→GCG", b"", "8.1.1","페이로드 없음")
emit("RES_SET_CONNECTION_1dev","RES_SET_CONNECTION",0x0400,"GCG→노드", bytes([0x00])+np_+dp_, "8.1.1","RSC+NODE_PROPERTY+DEVICE_PROPERTY×1")
emit("NOTI_DEVICE_VALUE_2sensor","NOTI_DEVICE_VALUE",0x0800,"노드→GCG", dmi_t+dmi_h, "8.2.1.2","DEVICE_MAIN_INFO×2")
emit("REQ_SET_DEVICE_CONTROL_valve","REQ_SET_DEVICE_CONTROL",0x000C,"GCG→노드", dmi_v, "8.1.5","관수밸브 ON")
emit("RES_SET_DEVICE_CONTROL_ok","RES_SET_DEVICE_CONTROL",0x040C,"노드→GCG", bytes([0x00]), "8.1.5","RSC=SUCCESS")
emit("NOTI_ERROR_batlow","NOTI_ERROR",0x0800,"노드→GCG", bytes([0x07]), "8.2.1.1","NEC=ERROR_BATTERY_LOW")
emit("REQ_GET_DEVICE_VALUE_3","REQ_GET_DEVICE_VALUE",0x000A,"GCG→노드", bytes([1,2,5]), "8.1.4.4","DEVICE_ID×3")
emit("REQ_SET_MSG_PROFILE","REQ_SET_MSG_FLOW_CONTROL_PROFILE",0x0006,"GCG→노드", mcp_, "8.1.3.4","MSG_CONTROL_PROFILE")
emit("ACK_min","ACK",0x0C00,"양방향", b"", "8.2","헤더만")

# 값 복원 검증
r=BitReader(dmi_t); r.r(8); r.r(1); r.r(8); r.r(2); r.r(5)
v=r.rf()
print(f"\n  OK   DEVICE_MAIN_INFO 값 복원: 25.3 -> {v:.1f}  (IEEE-754 single, big-endian)")

# ── 4차: Value Type 별 범위·왕복 검증 (F-044 회귀) ───────────
print("\n[4차] Value(32bit) 범위 강제 + 실제 바이트 왕복  (표 7-14)")
ok4=True
def _dmi_value(main: bytes):
    """DEVICE_MAIN_INFO 바이트에서 Value Type 에 맞게 Value 를 복원한다."""
    vt = main_value_type(main)
    r = BitReader(main); r.r(8); r.r(1); r.r(8); r.r(2); r.r(5)
    return vt, unpack_value(r, vt)

def t4(name, cond, extra=""):
    global ok4
    if not cond: ok4=False
    print(f"  {'OK  ' if cond else 'FAIL'} {name:<44} {extra}")

# (1) 경계값 왕복 — 실제 바이트를 눈으로 확인한다
ROUNDTRIP = [
    ("INT  최솟값",  0, INT32_MIN, "80000000"),
    ("INT  -1",      0, -1,        "FFFFFFFF"),
    ("INT  최댓값",  0, INT32_MAX, "7FFFFFFF"),
    ("UINT 최솟값",  1, 0,         "00000000"),
    ("UINT 최댓값",  1, UINT32_MAX,"FFFFFFFF"),
    ("FLOAT 25.3",   2, 25.3,      "41CA6666"),
    ("FLOAT 최댓값", 2, FLOAT32_MAX, "7F7FFFFF"),   # F-055 경계
]
for label, vt, val, exp_hex in ROUNDTRIP:
    m = device_main_info(1, 0, 0x01, vt, val)
    got_hex = m.hex().upper()[-8:]
    gvt, gval = _dmi_value(m)
    same = (gvt == vt) and (abs(gval-val) < 1e-4 if vt == 2 else gval == val)
    t4(f"{label} 왕복", same and got_hex == exp_hex, f"{got_hex} -> {gval}")

# (2) 범위 밖은 반드시 실패한다 — 조용한 래핑 금지
OUT_OF_RANGE = [
    ("UINT 음수",        1, -1),
    ("UINT 2^32",        1, 1 << 32),
    ("INT  2^31",        0, 1 << 31),
    ("INT  -2^31-1",     0, -(1 << 31) - 1),
    ("Reserved(0x03)",   3, 0),
    ("INT 에 소수",      0, 1.5),
    ("FLOAT 1e39",       2, 1e39),            # F-055
    ("FLOAT -1e39",      2, -1e39),           # F-055
    ("FLOAT inf",        2, float("inf")),    # F-055
    ("FLOAT nan",        2, float("nan")),    # F-055
    ("FLOAT 10**400",    2, 10 ** 400),       # F-058 float() 변환 단계 OverflowError
    ("FLOAT 문자열",     2, "abc"),           # F-058 ValueError
    ("FLOAT None",       2, None),            # F-058 TypeError
    ("INT   inf",        0, float("inf")),    # F-058 int() 변환 단계 OverflowError
    ("INT   문자열",     0, "abc"),           # F-058 ValueError
    ("UINT  None",       1, None),            # F-058 TypeError
]
for label, vt, val in OUT_OF_RANGE:
    try:
        device_main_info(1, 0, 0x01, vt, val); blocked=False; why="래핑됨(FAIL)"
    except ValueRangeError as e:
        blocked=True; why=str(e)[:44]
    t4(f"{label} 차단", blocked, why)

# (2-a) F-047 — 디코딩도 Value Type 을 강제하는가 (인코딩만 막으면 판정 기준이 무너진다)
for vt in (3, 4, 99):
    try:
        unpack_value(BitReader(b"\x00\x00\x00\x01"), vt); blocked=False; why="수용됨(FAIL)"
    except ValueRangeError as e:
        blocked=True; why=str(e)[:44]
    t4(f"디코딩 Value Type={vt} 차단", blocked, why)

# (3) INT 와 UINT 는 같은 비트열을 다르게 해석한다 — 타입 구분이 실제로 살아있는가
m_i = device_main_info(1,0,0x01,0,-1); m_u = device_main_info(1,0,0x01,1,UINT32_MAX)
t4("동일 비트열 FFFFFFFF 의 타입별 해석 분리",
   _dmi_value(m_i)[1] == -1 and _dmi_value(m_u)[1] == UINT32_MAX,
   f"INT={_dmi_value(m_i)[1]}, UINT={_dmi_value(m_u)[1]}")

# (4) DEVICE_PROPERTY 의 USER DEPENDENT 5필드도 같은 규칙을 따르는가 (F-022·F-026 회귀)
try:
    device_property(device_main_info(1,0,0x01,1,0), 0, 60, 0, UINT32_MAX+1, 0, 0, 1, 0)
    t4("DEVICE_PROPERTY 경계값 범위 강제", False, "래핑됨(FAIL)")
except ValueRangeError as e:
    t4("DEVICE_PROPERTY 경계값 범위 강제", True, str(e)[:44])
dp_u = device_property(device_main_info(1,0,0x01,1,0), 0, 60, 0, UINT32_MAX, 0, 0, 1, 0)
ru = BitReader(dp_u); [ru.r(8) for _ in range(7)]; ru.r(2); ru.r(14)
t4("UINT DEVICE_PROPERTY 경계값 왕복", unpack_value(ru,1) == 0 and unpack_value(ru,1) == UINT32_MAX)

# F-063 — 검증기 기본 동작은 쓰지 않고 대조만 한다(비파괴). 검증 중에 산출물을
#         덮어쓰면 체크인된 파일이 변질돼 있어도 그 사실이 그 자리에서 사라진다.
# F-066 — 이 대조가 실제로 잡은 사례: 생성기를 고치고 산출물을 커밋에 넣지 않아
#         마지막 개행 1바이트가 어긋났다. 생성기를 수정하면 산출물도 같은 커밋에
#         포함해야 한다. 여기서 종료코드 1 로 드러난다.
# F-101 — 예전에는 "--check 를 줘야만" 대조 모드였다. `tools/run_all.py` 는
#         검증기를 인자 없이 돌리므로, 전체 회귀 경로에서는 이 스크립트가 매번
#         쓰기 모드로 실행돼 손상된 spec_examples.json 을 조용히 정상으로
#         되돌려 놓고 통과했다 — F-063 이 막으려던 것과 같은 결함이 회귀
#         경로에서 재발한 것. 이제 기본값이 대조(비파괴)이고, 재생성은 명시적
#         `--write` 를 줘야만 한다.
_out = HERE / "spec_examples.json"
_payload = json.dumps(vectors, ensure_ascii=False, indent=1) + "\n"
ok5 = True
if "--write" in sys.argv:
    _out.write_text(_payload, encoding="utf-8", newline="\n")
    print(f"\n  예시 프레임 {len(vectors)}건 -> spec_examples.json (--write)")
else:
    _cur = _out.read_text(encoding="utf-8") if _out.exists() else ""
    ok5 = _cur == _payload
    print(f"\n  {'OK  ' if ok5 else 'FAIL'} spec_examples.json 이 생성 결과와 일치 "
          f"({len(vectors)}건){'' if ok5 else '  <- 재생성 필요: python spec_verify.py --write'}")
sys.exit(0 if (ok1 and ok2 and ok4 and ok5) else 1)
