"""Frame 계약 검증"""
import sys, struct
from frame import *

# 한국어 Windows 기본 콘솔은 CP949 다. 표현 불가 문자 하나로 검증이
#         중단되면 재현성이 깨진다. 출력 문자는 CP949 안에서 고르는 것이 원칙이고
#         이 가드는 중단만은 막는 2중 방어다.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

R=[]
def t(name, cond, note=""):
    R.append((bool(cond), name, note))

# 1. MsgKind ↔ 명세서 34종
t("MsgKind 34종", len(list(MsgKind))==34)
t("LAYOUT 34종 전량 정의", set(LAYOUT)==set(MsgKind))
t("WIRE_CODE 34종 전량 정의", set(WIRE_CODE)==set(MsgKind))

# 2. 코드공간 (표 7-2~7-4)
blocks={"REQ":(0x0000,0x03FF),"RES":(0x0400,0x07FF),"NOTI":(0x0800,0x0BFF),"ACK":(0x0C00,0x0FFF)}
bad=[k.name for k,c in WIRE_CODE.items()
     if not (blocks[k.name.split('_')[0]][0] <= c <= blocks[k.name.split('_')[0]][1])]
t("모든 코드가 블록 경계 내", not bad, str(bad))
t("모든 코드가 14bit 이내", all(c < (1<<14) for c in WIRE_CODE.values()))

# 3. Request+0x400 = Response
pairs=[(k, MsgKind["RES_"+k.name[4:]]) for k in MsgKind if k.name.startswith("REQ_")]
t("Req+0x400=Res 14쌍", len(pairs)==14 and
  all(WIRE_CODE[r]-WIRE_CODE[q]==0x400 for q,r in pairs))

# 4. errata: strict 중복 1건 / extended 해소
t("strict 모드 중복 코드 1건 (0x0800)", len(set(WIRE_CODE.values()))==33)
t("extended 모드 중복 없음", len(set(WIRE_CODE_EXT.values()))==34)
t("extended RESERVED 시작 0x0805", max(c for k,c in WIRE_CODE_EXT.items()
                                       if k.name.startswith("NOTI_"))==0x0804)

# 5. resolve_kind — 0x0800 판별
t("0x0800 len=1 → NOTI_ERROR",        resolve_kind(0x0800,1)  is MsgKind.NOTI_ERROR)
t("0x0800 len=7 → NOTI_DEVICE_VALUE", resolve_kind(0x0800,7)  is MsgKind.NOTI_DEVICE_VALUE)
t("0x0800 len=14 → NOTI_DEVICE_VALUE",resolve_kind(0x0800,14) is MsgKind.NOTI_DEVICE_VALUE)
t("0x0800 len=3 → 판별 불가(None)",   resolve_kind(0x0800,3)  is None)
t("0x0800 len=0 → 판별 불가(None)",   resolve_kind(0x0800,0)  is None)
t("extended 0x0801 → NOTI_DEVICE_VALUE",
  resolve_kind(0x0801,7,"extended") is MsgKind.NOTI_DEVICE_VALUE)
t("strict 0x0801 → NOTI_DISCONNECT",  resolve_kind(0x0801,0)  is MsgKind.NOTI_DISCONNECT)
t("미정의 코드 0x000E → None",         resolve_kind(0x000E,0)  is None)

# 6. element_count — N 산출식
cases=[
 (MsgKind.REQ_SET_CONNECTION,               0,   0),
 (MsgKind.REQ_SET_CONNECTION,               1,   None),
 (MsgKind.REQ_GET_DEVICE_VALUE,             3,   3),
 (MsgKind.REQ_SET_DEVICE_CONTROL,           7,   1),
 (MsgKind.REQ_SET_DEVICE_CONTROL,          14,   2),
 (MsgKind.REQ_SET_DEVICE_CONTROL,           8,   None),
 (MsgKind.REQ_SET_DEVICE_PROPERTY,         60,   2),
 (MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL,38,   1),   # 8 + 30
 (MsgKind.RES_SET_CONNECTION,              39,   1),   # 1 + 8 + 30
 (MsgKind.RES_SET_CONNECTION,              69,   2),
 (MsgKind.RES_SET_CONNECTION,               9,   0),
 (MsgKind.RES_SET_CONNECTION,               8,   None),
 (MsgKind.RES_GET_DEVICE_VALUE,            15,   2),   # 1 + 7*2
 (MsgKind.RES_GET_NODE_PROPERTY,            9,   0),
 (MsgKind.RES_GET_MSG_FLOW_CONTROL_PROFILE, 8,   0),   # 1 + 7
 (MsgKind.NOTI_ERROR,                       1,   0),
 (MsgKind.NOTI_DEVICE_VALUE,               21,   3),
 (MsgKind.ACK,                              0,   0),
 # 노드당 디바이스 상한 N=16. 16은 허용,
 # 17은 거부 — 골든 B03(RES_SET_CONNECTION, N=16)·B11(REQ_SET_DEVICE_CONTROL,
 # N=17 거부)과 짝을 이룬다.
 (MsgKind.REQ_SET_DEVICE_CONTROL,          112,  16),   # 7*16
 (MsgKind.REQ_SET_DEVICE_CONTROL,          119,  None), # 7*17 -> 상한 초과
 (MsgKind.RES_SET_CONNECTION,              489,  16),   # 9+30*16 (B03)
 (MsgKind.RES_SET_CONNECTION,              519,  None), # 9+30*17 -> 상한 초과
]
bad=[(k.name,p,element_count(k,p),e) for k,p,e in cases if element_count(k,p)!=e]
t(f"element_count {len(cases)}케이스", not bad, str(bad))

# 7. Subtype
t("Subtype 16종", len(list(Subtype))==16)
t("센서 10 / 액추에이터 6",
  sum(1 for s in Subtype if s.dev_type==DevType.SENSOR)==10 and
  sum(1 for s in Subtype if s.dev_type==DevType.ACTUATOR)==6)
t("Subtype 코드 고유", len(set(s.value for s in Subtype))==16)

# 8. 구조체 크기 상수
t("구조체 크기 상수", (HEADER_BYTES,NP_BYTES,DMI_BYTES,DP_BYTES,MCP_BYTES)==(12,8,7,30,7))

# 9. 열거형 코드값
t("RSC 10종 0x00~0x09", [r.value for r in RSC]==list(range(10)))
t("NEC 10종 0x00~0x09", [n.value for n in NEC]==list(range(10)))

# 10. Frame 불변성 및 기본값
h=Header(0x12, 0x0800, TransType.UNICAST, 1, 14, 1, 3)
f=Frame(header=h, kind=MsgKind.NOTI_DEVICE_VALUE, raw=b"\x12")
t("Frame 기본 valid", f.is_valid)
v=Violation(RSC.INVALID_FORMAT, "INVALID_FORMAT", "7.3.1", "len mismatch")
f2=Frame(header=h, violations=(v,))
t("violations 있으면 invalid", not f2.is_valid)
t("Violation에 조항번호 보존", f2.violations[0].clause=="7.3.1")
f3=Frame(header=None, raw=b"\x12\x00", violations=(v,))
t("불완전 헤더는 합성 없이 None+invalid", f3.header is None and not f3.is_valid)
t("불완전 프레임 원본 보존", f3.raw==b"\x12\x00")
try:
    f.header = h; ok=False
except Exception: ok=True
t("Frame frozen (불변)", ok)

# 11. Header가 미정의 Transmission Type을 보존하는가
h3 = Header(0x12, 0x0800, 3, 1, 14, 1, 3)          # 표 7-6 미정의값 0x03
t("trans_type=0x03 저장 가능", h3.trans_type == 3)
t("미정의값 해석 → None", h3.trans is None)
t("정상값 해석", Header(0x12,0,0,1,0,1,3).trans is TransType.UNICAST)
t("resolve_trans_type 0/1/2 정상",
  [resolve_trans_type(i) for i in (0,1,2)] == [TransType.UNICAST, TransType.MULTICAST, TransType.BROADCAST])
t("msg_type도 raw int 유지", isinstance(h3.msg_type, int) and h3.msg_type == 0x0800)

# 12. USER DEPENDENT 5필드가 int도 허용하는가
dmi_i = DeviceMainInfo(1, DevType.SENSOR, Subtype.CO2, ValueType.UINT, 800)
dp_i = DeviceProperty(dmi_i, TransferMode.PERIODIC, 60, 0, 2000, 0, 5000, 1, Status.NORMAL)
t("INT 디바이스의 경계값이 int로 유지",
  all(isinstance(v, int) for v in (dp_i.lower_value, dp_i.upper_value,
                                    dp_i.lower_limit, dp_i.upper_limit, dp_i.precision)))
dmi_f = DeviceMainInfo(1, DevType.SENSOR, Subtype.TEMPERATURE, ValueType.FLOAT, 25.3)
dp_f = DeviceProperty(dmi_f, TransferMode.PERIODIC, 60, -40.0, 80.0, -40.0, 80.0, 0.1, Status.NORMAL)
t("FLOAT 디바이스의 경계값이 float로 유지", isinstance(dp_f.precision, float))

# 13. siap_iface 가 패키지·스크립트 양쪽에서 import 되는가
import importlib.util as _ilu, pathlib as _pl
_spec = _ilu.spec_from_file_location("_iface", _pl.Path(__file__).resolve().parent / "siap_iface.py")
_m = _ilu.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_m); _ok = hasattr(_m, "SiapLink") and hasattr(_m, "FrameBuilder")
except Exception as _e:
    _ok = False
t("siap_iface import + Protocol 노출", _ok)

# 14. 명세서 예시 프레임과 대조
#     spec_examples.json 은 저장소의 설계 산출물이라 위치가 갈릴 수 있어,
#     고정 상대경로 대신 저장소 루트까지 위로 올라가며 찾는다.
import json
from pathlib import Path
_HERE = Path(__file__).resolve().parent
_SKIP = {"__pycache__", "node_modules", "site-packages", "venv", ".venv", "env", "wheels", "build", "dist"}
def _find(name: str) -> Path | None:
    base = _HERE
    for _ in range(6):
        hits = [q for q in base.rglob(name)
                 if not any(part.startswith(".") or part in _SKIP for part in q.parts)]
        if hits: return hits[0]
        if base.parent == base: break
        base = base.parent
    return None
p = _find("spec_examples.json")
if p is not None and p.exists():
    ex = json.load(open(p, encoding="utf-8"))
    bad=[]
    for e in ex:
        raw=bytes.fromhex(e["hex"])
        mt=int(bin(int.from_bytes(raw[1:5],'big'))[2:].zfill(32)[:14],2)
        pl=int.from_bytes(raw[5:7],'big')
        k=resolve_kind(mt, pl)
        if k is None or k.name!=e["msg"]: bad.append((e["id"], k.name if k else None, e["msg"]))
        if len(raw)-12 != pl: bad.append((e["id"],"payload_len",pl))
    t(f"명세서 예시 {len(ex)}건 kind 해석 일치", not bad, str(bad))

# 15. 방향·회신 표가 표준 8장과 일치하는가
from frame import (NODE_ORIGINATED_REQUESTS, NODE_ORIGINATED_NOTIFIES,
                   RESPONSE_OF, reply_kind, expected_reply)
t("Request 14종 전부에 대응 Response 존재",
  len(RESPONSE_OF) == 14 and all(RESPONSE_OF[r].name == "RES_"+r.name[4:]
                                 for r in RESPONSE_OF))
t("노드발 Request 5종 (8.1.1 + 8.1.3.1~4)",
  len(NODE_ORIGINATED_REQUESTS) == 5 and MsgKind.REQ_SET_CONNECTION in NODE_ORIGINATED_REQUESTS)
t("Notify 5종 전부 ACK 대상 (6.2.2)",
  len(NODE_ORIGINATED_NOTIFIES) == 5
  and all(reply_kind(k) is MsgKind.ACK for k in NODE_ORIGINATED_NOTIFIES))
t("NOTI_REBOOT 누락 없음 (8.2.1.4)",
  reply_kind(MsgKind.NOTI_REBOOT) is MsgKind.ACK)
t("REQ_SET_CONNECTION -> RES_SET_CONNECTION",
  reply_kind(MsgKind.REQ_SET_CONNECTION) is MsgKind.RES_SET_CONNECTION)
t("Response·ACK 수신에는 회신하지 않는다",
  reply_kind(MsgKind.RES_SET_CONNECTION) is None and reply_kind(MsgKind.ACK) is None)
t("게이트웨이발 Request 는 회신 대상이 아니다",
  all(reply_kind(k) is None for k in
      [MsgKind.REQ_SET_DEVICE_CONTROL, MsgKind.REQ_GET_DEVICE_VALUE,
       MsgKind.REQ_SET_REBOOT, MsgKind.REQ_SET_DEVICE_INIT]))
t("해석 불가(None)에는 회신하지 않는다", reply_kind(None) is None)
# FrameBuilder 계약이 회신 빌더를 실제로 노출하는가
_need = ("res_set_connection","res_set_node_property","res_set_device_property",
         "res_set_node_device_property_all","res_set_msg_flow_control_profile",
         "error_response","ack")
# 16. 대기 요청의 응답 매칭이 Message Type 까지 보는가
t("Request -> 대응 Response 를 기대",
  expected_reply(MsgKind.REQ_GET_DEVICE_VALUE) is MsgKind.RES_GET_DEVICE_VALUE)
t("다른 Response 로는 완료되지 않는다",
  expected_reply(MsgKind.REQ_GET_DEVICE_VALUE) is not MsgKind.RES_SET_REBOOT)
t("Request 대기를 ACK 로 완료하지 않는다",
  expected_reply(MsgKind.REQ_GET_DEVICE_VALUE) is not MsgKind.ACK)
t("게이트웨이발 Notify -> ACK 기대 (6.2.2)",
  expected_reply(MsgKind.NOTI_DISCONNECT) is MsgKind.ACK)
t("RES_*/ACK 송신은 회신을 기다리지 않는다",
  expected_reply(MsgKind.RES_SET_REBOOT) is None and expected_reply(MsgKind.ACK) is None)
t("reply_kind 와 expected_reply 는 쌍",
  all(reply_kind(RESPONSE_OF[q]) is None and expected_reply(q) is RESPONSE_OF[q]
      for q in RESPONSE_OF))
t("Request 14종 전부 고유 기대 Response",
  len({expected_reply(q) for q in RESPONSE_OF}) == 14)

t("FrameBuilder 회신 빌더 7종 노출",
  _ok and all(hasattr(_m.FrameBuilder, n) for n in _need),
  str([n for n in _need if not (_ok and hasattr(_m.FrameBuilder, n))]))

# 게이트웨이발 Request 빌더. 설정 API 가 REQ_SET_DEVICE_PROPERTY 를
#         만들 수단이 여기 없으면 PATCH /api/v1/device-property 가 성립하지 않는다.
_tx = ("device_control", "get_device_value", "get_node_property",
       "reboot", "set_device_property")
t("FrameBuilder 게이트웨이발 Request 빌더 5종 노출",
  _ok and all(hasattr(_m.FrameBuilder, n) for n in _tx),
  str([n for n in _tx if not (_ok and hasattr(_m.FrameBuilder, n))]))
t("set_device_property 가 props 목록을 받는다 (표 7-15 x N)",
  _ok and "props" in getattr(_m.FrameBuilder.set_device_property, "__annotations__", {}),
  str(sorted(getattr(_m.FrameBuilder.set_device_property, "__annotations__", {}))))
# 두지 않은 빌더의 사유가 계약 파일에 적혀 있는가 - 없으면 "빠뜨린 것"과 구분되지 않는다
_src = (_pl.Path(__file__).resolve().parent / "siap_iface.py").read_text(encoding="utf-8")
t("두지 않은 게이트웨이발 빌더 8종의 사유가 계약에 적혀 있다",
  "의도적으로 두지 않은 것" in _src
  and all(k in _src for k in ("REQ_SET_DEVICE_INIT", "REQ_SET_NODE_PROPERTY",
                              "REQ_SET_MSG_FLOW_CONTROL_PROFILE", "REQ_GET_DEVICE_PROPERTY")))

# 17. fake_link.FakeSiapLink 가 SiapLink Protocol 을 실제로 만족하는가.
#     "메서드 이름이 hasattr 로 있다"가 아니라 실제 import → 인스턴스화 →
#     최소 정상 입력 호출 → 반환형 확인까지 간다("호출해서 반환값을 본다"
#     원칙). 빈 클래스(`class FakeSiapLink: pass`)나 문법 오류로 교체해도
#     여기서 FAIL 이 나야 한다.
_SIAP_LINK_METHODS = ("start", "stop", "recv", "send", "registry", "devices", "stats")
try:
    _fl_spec = _ilu.spec_from_file_location(
        "_fake_link", _pl.Path(__file__).resolve().parent / "fake_link.py")
    _fl_mod = _ilu.module_from_spec(_fl_spec)
    _fl_spec.loader.exec_module(_fl_mod)
    _FakeLink = getattr(_fl_mod, "FakeSiapLink", None)
    _fl_load_ok = _FakeLink is not None
except Exception as _fl_exc:
    _FakeLink = None
    _fl_load_ok = False
t("fake_link.py 로드 + FakeSiapLink 클래스 노출", _fl_load_ok)

_link = None
if _fl_load_ok:
    try:
        _link = _FakeLink()
    except Exception:
        _link = None
t("FakeSiapLink() 인스턴스화 가능", _link is not None)

_missing = [m for m in _SIAP_LINK_METHODS if not (_link is not None and callable(getattr(_link, m, None)))]
t("SiapLink 메서드 7종이 실제로 존재하고 callable", not _missing, str(_missing))

_call_bad = []
if _link is not None and not _missing:
    def _check(label, fn, ok_type):
        try:
            v = fn()
        except Exception as e:
            _call_bad.append(f"{label}: {type(e).__name__}: {e}")
            return
        if ok_type is not None and not isinstance(v, ok_type):
            _call_bad.append(f"{label} 반환형 {ok_type.__name__} 아님: {type(v).__name__}")

    _check("start()", lambda: _link.start("simulate", proto_mode="strict"), type(None))
    _check("registry()", _link.registry, dict)
    _check("devices()", lambda: _link.devices(1), tuple)
    _check("recv()", lambda: list(_link.recv()), list)
    _req = Frame(header=Header(0x12, WIRE_CODE[MsgKind.REQ_GET_NODE_PROPERTY], 0, 1, 0, 1, 3),
                 kind=MsgKind.REQ_GET_NODE_PROPERTY, raw=b"")
    def _send_ok():
        v = _link.send(_req)
        if v is not None and not isinstance(v, Frame):
            raise TypeError(f"send() 반환형 Frame|None 아님: {type(v).__name__}")
        return None
    _check("send()", _send_ok, type(None))
    _check("stats()", _link.stats, dict)
    _check("stop()", _link.stop, type(None))
t("SiapLink 메서드 7종을 최소 정상 입력으로 호출 (반환형 확인)",
  not _call_bad, "; ".join(_call_bad))

# 18. 앞 검사는 "메서드가 존재하고 최소 입력으로 호출된다"까지만
#     봤다. `start` 에서 `**opts` 를, `send` 에서 `timeout` 을 빼거나 `recv()`
#     가 list 를 그대로 반환해도 그 검사는 그대로 통과였다 — 이름·개수가
#     아니라 파라미터 kind·기본값과 반환 계약(Iterator)까지 대조한다.
import inspect as _inspect
import collections.abc as _cabc


def _sig_params(fn) -> dict[str, tuple]:
    return {n: (p.kind, p.default) for n, p in _inspect.signature(fn).parameters.items()
            if n != "self"}


def _sig_compat(proto_fn, impl_fn) -> list[str]:
    """Protocol 이 요구하는 파라미터(이름·kind·기본값 유무)를 구현이 전부
    갖는가. Protocol 이 요구하지 않는데 구현이 더 갖는 것은 문제 삼지 않는다
    — 여기서 보는 건 "구현이 Protocol 을 만족하는가"이지 그 반대가 아니다."""
    proto_params, impl_params = _sig_params(proto_fn), _sig_params(impl_fn)
    problems = []
    for name, (kind, default) in proto_params.items():
        if name not in impl_params:
            problems.append(f"{name}({kind.name}) 없음")
            continue
        ikind, idefault = impl_params[name]
        if kind is not ikind:
            problems.append(f"{name}: kind {kind.name} != {ikind.name}")
        elif kind not in (_inspect.Parameter.VAR_KEYWORD, _inspect.Parameter.VAR_POSITIONAL):
            has_def, ihas_def = default is not _inspect.Parameter.empty, idefault is not _inspect.Parameter.empty
            if has_def != ihas_def:
                problems.append(f"{name}: 기본값 유무 불일치(Protocol={has_def} 구현={ihas_def})")
    return problems


_sig_bad = []
if _ok and _fl_load_ok and _FakeLink is not None:
    for _mname in _SIAP_LINK_METHODS:
        _proto_fn = getattr(_m.SiapLink, _mname, None)
        _impl_fn = getattr(_FakeLink, _mname, None)
        if _proto_fn is None or _impl_fn is None:
            _sig_bad.append(f"{_mname}(): Protocol 또는 구현에서 못 찾음")
            continue
        _probs = _sig_compat(_proto_fn, _impl_fn)
        if _probs:
            _sig_bad.append(f"{_mname}(): " + "; ".join(_probs))
t("SiapLink 메서드 7종의 파라미터 이름·kind·기본값이 Protocol 과 호환",
  _ok and _fl_load_ok and not _sig_bad, "; ".join(_sig_bad))

_call_bad2 = []
if _link is not None and not _missing:
    try:
        _link.start("simulate", proto_mode="strict", host="127.0.0.1", port=5555)
    except TypeError as _e:
        _call_bad2.append(f"start(..., 임의 키워드) 호출 실패: {_e}")
    _req2 = Frame(header=Header(0x12, WIRE_CODE[MsgKind.REQ_GET_NODE_PROPERTY], 0, 1, 0, 1, 3),
                  kind=MsgKind.REQ_GET_NODE_PROPERTY, raw=b"")
    try:
        _link.send(_req2, timeout=2.0)
    except TypeError as _e:
        _call_bad2.append(f"send(frame, timeout=2.0) 호출 실패: {_e}")
    _recv_result = _link.recv()
    # 핵심 — list(...)로 감싸면 list 도 통과한다. Iterator 계약은
    # `iter(x) is x` (자기 자신을 돌려줌) 또는 collections.abc.Iterator 로 본다.
    if not (isinstance(_recv_result, _cabc.Iterator) or iter(_recv_result) is _recv_result):
        _call_bad2.append(f"recv() 가 Iterator 계약을 만족하지 않음: {type(_recv_result).__name__}")
t("start(**opts)·send(timeout=) 실호출 및 recv() 의 Iterator 계약",
  not _call_bad2, "; ".join(_call_bad2))

w=max(len(n) for _,n,_ in R)
print("Frame 계약 검증\n")
for ok,n,note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
p=sum(1 for o,*_ in R if o)
print(f"\n  {p}/{len(R)} 통과")
sys.exit(0 if p==len(R) else 1)
