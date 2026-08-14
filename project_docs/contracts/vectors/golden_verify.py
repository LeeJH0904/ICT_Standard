"""골든 벡터 검증 — 손으로 만든 벡터를 독립된 세 출처와 대조한다

규약 6.2 의 "코드로 검증한다" 쪽이다. 검증 대상은 golden.jsonl 이고,
정답의 근거는 **벡터를 만든 코드가 아닌 곳**에서 온다.

  1) 독립 헤더 리더 — 표 7-5 ~ 7-8 오프셋으로 hex 에서 비트를 다시 잘라
     기록된 header 값과 대조한다. 쓰기(golden_layout)와 읽기가 서로를 검산한다.
  2) contracts/frame.py — resolve_kind() · element_count() · RSC/NEC/Subtype 열거.
     계약은 벡터보다 먼저 존재했고 벡터를 참조하지 않는다.
  3) siap/spec_examples.json — spec_verify.py 의 **독립 인코더**가 만든 예시 9건.
     같은 메시지의 페이로드 바이트가 일치해야 한다. 두 번 타이핑한 레이아웃이
     같은 바이트를 내놓는지가 사람 오독을 잡는 유일한 장치다.
  4) CLAUDE.md 6.3 — 위반 케이스 8종 표와 벡터가 정확히 대응하는가.
  5) 골든벡터_명세서.md — 문서가 선언한 총 벡터 수와 판정 분포가 실제와
     일치하는가. 실행 코드만 맞고 심사 기준 문서가 낡는 회귀도 실패시킨다(F-207).

실행:  python project_docs/contracts/vectors/golden_verify.py
종료코드: 0 = 전부 일치, 1 = 불일치 있음
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../contracts/vectors/
ROOT = HERE.parent.parent.parent                # 저장소 루트 (project_docs/ 의 부모)
DOC = (HERE / "골든벡터_명세서.md").read_text(encoding="utf-8")

if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

R: list[tuple[bool, str, str]] = []
def t(name: str, ok: bool, note: str = "") -> None:
    R.append((bool(ok), name, note))

SKIP_DIRS = {"__pycache__", "node_modules", "site-packages", "venv", ".venv",
             "env", "wheels", "build", "dist"}
def _skip(p: Path) -> bool:
    return any(part.startswith(".") or part in SKIP_DIRS for part in p.parts)

def find(name: str) -> Path | None:
    """HERE 에서 위로 올라가며 찾는다. 저장소 배치(project_docs 유무)에 의존하지 않는다."""
    base = HERE
    for _ in range(6):
        hits = [q for q in base.rglob(name) if not _skip(q)]
        if hits: return hits[0]
        if base.parent == base: break
        base = base.parent
    return None

def load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]

GOLD = load(HERE / "golden.jsonl")
EXT = load(HERE / "golden_ext.jsonl")

# ═══════════════════════════════════════════════════════════════
#  0-a. 정본 <-> 생성물 드리프트 (F-063)
#       golden_layout.py 를 __main__ 이 아닌 이름으로 실행한다 -> main() 이 돌지
#       않으므로 **아무 파일도 쓰지 않는다.** 메모리에서 만든 결과와 체크인된
#       파일을 byte 단위로 대조한다. 정본만 고치고 재생성을 안 하면 여기서 걸린다.
# ═══════════════════════════════════════════════════════════════
_lay = HERE / "golden_layout.py"
_ns: dict = {"__name__": "golden_layout", "__file__": str(_lay)}
exec(compile(_lay.read_text(encoding="utf-8"), str(_lay), "exec"), _ns)
_drift = []
for _fname, _key in (("golden.jsonl", "VECTORS"), ("golden_ext.jsonl", "EXT")):
    _want = "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in _ns[_key])
    _have = (HERE / _fname).read_text(encoding="utf-8")
    if _want != _have:
        _drift.append(f"{_fname}: 정본 {len(_ns[_key])}건과 다름")
t("생성물이 정본(golden_layout.py)과 byte 단위 일치 (F-063)", not _drift, "; ".join(_drift))

# ═══════════════════════════════════════════════════════════════
#  1. 구성
# ═══════════════════════════════════════════════════════════════
cat = {}
for v in GOLD: cat[v["category"]] = cat.get(v["category"], 0) + 1
t(f"골든 벡터 53건 · 구성 {cat}", len(GOLD) == 53 and cat == {"정상": 34, "경계": 11, "위반": 8})  # F-120: 52 -> 53 (B11)
t("벡터 ID 고유", len({v["id"] for v in GOLD}) == len(GOLD))
t("extended 벡터 5건", len(EXT) == 5)

# F-207 — 명세서 §6의 독립 헤더 리더 총계도 실물 두 파일에서 재산출한다.
# 검증기가 자기 코드의 53/5만 확인하면 문서가 57건으로 낡아도 계속 통과한다.
_doc_total = re.search(r"독립 헤더 리더[^\n]*?\|\s*(\d+)건\s*×\s*7필드", DOC)
t("명세서 §6 독립 헤더 리더 건수 = golden + extended (F-207)",
  bool(_doc_total) and int(_doc_total.group(1)) == len(GOLD) + len(EXT),
  f"문서={_doc_total.group(1) if _doc_total else '?'} 실제={len(GOLD) + len(EXT)}")

badhex = [v["id"] for v in GOLD + EXT
          if not re.fullmatch(r"[0-9A-F]*", v["hex"]) or len(v["hex"]) != v["len"] * 2]
t("hex 표기·길이 일치", not badhex, str(badhex))

# ═══════════════════════════════════════════════════════════════
#  2. 독립 헤더 리더 — 표 7-5 ~ 7-8 오프셋을 여기서 다시 적는다
# ═══════════════════════════════════════════════════════════════
HDR_LAYOUT = [("Version", 0, 8), ("Message Type", 8, 14), ("Transmission Type", 22, 2),
              ("Message Identifier", 24, 16), ("Payload Length", 40, 16),
              ("GCG ID", 56, 20), ("Node ID", 76, 20)]

def read_header(raw: bytes) -> dict:
    """12 byte 를 정수 하나로 보고 오프셋·길이로 잘라낸다."""
    word = int.from_bytes(raw[:12], "big")
    return {name: (word >> (96 - off - ln)) & ((1 << ln) - 1)
            for name, off, ln in HDR_LAYOUT}

drift = []
for v in GOLD + EXT:
    raw = bytes.fromhex(v["hex"])
    if len(raw) < 12:
        drift.append(f"{v['id']}: 12byte 미만"); continue
    got = read_header(raw)
    for k, want in v["header"].items():
        if got.get(k) != want:
            drift.append(f"{v['id']}.{k}: 기록={want} 재판독={got.get(k)}")
t(f"독립 헤더 리더 대조 ({len(GOLD)+len(EXT)}건 x 7필드)", not drift, "; ".join(drift[:4]))

# Payload Length 표기 = 실제 (의도적으로 어긋낸 위반 케이스만 예외)
plen_bad, plen_intended = [], []
for v in GOLD:
    declared, actual = v["header"]["Payload Length"], v["len"] - 12
    if declared == actual: continue
    (plen_intended if v["category"] == "위반" else plen_bad).append(
        f"{v['id']}: 표기={declared} 실제={actual}")
t("Payload Length 표기 = 실제 byte (위반 케이스 제외)", not plen_bad, str(plen_bad))
t("Payload Length 불일치는 위반 케이스에만 존재", len(plen_intended) == 1, str(plen_intended))

# ═══════════════════════════════════════════════════════════════
#  3. contracts/frame.py 와 대조
# ═══════════════════════════════════════════════════════════════
frame_py = find("frame.py")
ns: dict = {}
exec(compile(frame_py.read_text(encoding="utf-8"), str(frame_py), "exec"), ns)
need = ("MsgKind", "RSC", "NEC", "Subtype", "resolve_kind", "element_count",
        "WIRE_CODE", "WIRE_CODE_EXT")
missing = [k for k in need if k not in ns]
if missing:
    print(f"  FAIL  계약 파일을 잘못 찾았다: {frame_py} (없는 심볼 {missing})")
    sys.exit(1)
MsgKind, RSC, NEC, Subtype = ns["MsgKind"], ns["RSC"], ns["NEC"], ns["Subtype"]
resolve_kind, element_count = ns["resolve_kind"], ns["element_count"]
WIRE_CODE, WIRE_CODE_EXT = ns["WIRE_CODE"], ns["WIRE_CODE_EXT"]

kind_bad, n_bad, code_bad = [], [], []
for v in GOLD:
    mt, plen = v["header"]["Message Type"], v["header"]["Payload Length"]
    got = resolve_kind(mt, plen)
    want = v["kind"]
    if (got.name if got else None) != want:
        kind_bad.append(f"{v['id']}: 기대={want} 계약={got.name if got else None}")
    if got is not None:
        gn = element_count(got, plen)
        if gn != v["n"]:
            n_bad.append(f"{v['id']}: 기대 N={v['n']} 계약={gn}")
    # 메시지명이 MsgKind 에 실재하는가
    if v["msg"] is not None and v["msg"] not in MsgKind.__members__:
        code_bad.append(f"{v['id']}: {v['msg']}")
t("resolve_kind() 판정이 기대와 일치", not kind_bad, "; ".join(kind_bad[:4]))
t("element_count() N 산출이 기대와 일치", not n_bad, "; ".join(n_bad[:4]))
t("벡터의 메시지명이 MsgKind 에 실재", not code_bad, str(code_bad))

# 전송 코드가 WIRE_CODE 와 같은가 (손으로 적은 코드값 검산)
wire_bad = [f"{v['id']}: {v['msg']} 0x{v['header']['Message Type']:04X}"
            for v in GOLD if v["msg"] in MsgKind.__members__
            and WIRE_CODE[MsgKind[v["msg"]]] != v["header"]["Message Type"]]
t("손으로 적은 Message Type = WIRE_CODE (strict)", not wire_bad, str(wire_bad[:4]))

ext_bad = [f"{v['id']}: {v['msg']} 0x{v['header']['Message Type']:04X}"
           for v in EXT if WIRE_CODE_EXT[MsgKind[v["msg"]]] != v["header"]["Message Type"]]
t("extended 벡터의 Message Type = WIRE_CODE_EXT", not ext_bad, str(ext_bad))

# F-061 — 개정 제안은 **코드만** 바꾼다. 방향(표 7-4)까지 바꾸면 제안의 범위를 넘는다.
STRICT_DIR = {v["msg"]: v["dir"] for v in GOLD if v["category"] == "정상"}
dir_bad = [f"{v['id']}({v['msg']}): extended={v['dir']} strict={STRICT_DIR.get(v['msg'])}"
           for v in EXT if STRICT_DIR.get(v["msg"]) != v["dir"]]
t("extended 벡터의 방향이 strict 와 동일 (F-061)", not dir_bad, "; ".join(dir_bad))

# ── F-068 COMBINED_PROPERTY 의 Num. of Devices = DEVICE_PROPERTY 개수 ──
#   표 7-16 은 NODE_PROPERTY + DEVICE_PROPERTY x N 이고, 7.3.3.4 는 "노드 속성과
#   해당 노드에 연결된 N개 디바이스의 속성 정보"라고 한다. 한 페이로드가 디바이스
#   수를 두 값으로 주장하면 그 프레임은 자기모순이다. 세 구현이 이런 정답을 쓰면
#   연결 응답에서 개수 불일치를 정상으로 받아들이게 된다.
DP_BYTES = ns["DP_BYTES"]
LAYOUT = ns["LAYOUT"]
MAX_DEVICES_PER_NODE = ns["MAX_DEVICES_PER_NODE"]   # F-120
comb_bad, comb_n = [], 0
for v in GOLD:
    if v["kind"] is None or v["kind"] not in MsgKind.__members__:
        continue
    fixed, elem = LAYOUT[MsgKind[v["kind"]]]
    names = [f["name"] for f in v.get("fields", [])]
    # 고정부에 NODE_PROPERTY 가 있고 가변 요소가 DEVICE_PROPERTY 인 메시지만 해당
    if elem != DP_BYTES or "Num. of Devices" not in names:
        continue
    comb_n += 1
    nd = next(f["value"] for f in v["fields"] if f["name"] == "Num. of Devices")
    if nd != v["n"]:
        comb_bad.append(f"{v['id']}({v['kind']}): Num. of Devices={nd} N={v['n']}")
t(f"COMBINED_PROPERTY 의 Num. of Devices = N ({comb_n}건, F-068)",
  not comb_bad and comb_n >= 4, "; ".join(comb_bad))

# ═══════════════════════════════════════════════════════════════
#  4. 위반 케이스 — 코드값·조항이 표준 열거와 맞는가
# ═══════════════════════════════════════════════════════════════
SUB_VALUES = {sub.value for sub in Subtype}
RSC_BY_NAME = {r.name: r.value for r in RSC}
NEC_BY_NAME = {n.name: n.value for n in NEC}
vio_bad = []
for v in GOLD:
    for w in v["violations"]:
        table = RSC_BY_NAME if w["code_name"] in RSC_BY_NAME else NEC_BY_NAME
        if table.get(w["code_name"]) != w["code"]:
            vio_bad.append(f"{v['id']}: {w['code_name']}=0x{w['code']:02X} 불일치")
        if not w.get("clause") or not w.get("detail"):
            vio_bad.append(f"{v['id']}: clause/detail 비어 있음")
t("위반 코드값이 표 7-10 / 표 7-12 열거와 일치", not vio_bad, "; ".join(vio_bad[:4]))

# F-060 — 프로토콜 위반과 노드 오류 알림을 갈라 둔다.
#   violations 가 차 있으면 Frame.is_valid 가 false 가 되고 ingest.handle() 이
#   격리 후 반환한다. 정상 NOTI_ERROR 를 거기 넣으면 alert 저장과 ACK 가 사라진다.
byjudge = {}
for v in GOLD: byjudge.setdefault(v["judgement"], []).append(v["id"])
# F-116 — B02(N=0 거부, 명세서 4절)도 violation 으로 판정되어 violation 7 -> 8,
# normal 44 -> 43 이 됐다. F-120 — B11(N=17, 상한 초과)이 violation 8 -> 9 를
# 더한다. X01~X08 은 category="위반"(CLAUDE.md 6.3의 8종)이고 B02·B11 은
# category="경계"이면서 judgement="violation"인 추가 사례다 — 두 축은 서로
# 다른 것을 센다(category=시험표 분류, judgement=실제 판정 결과).
t("판정 분류: violation 9 / alert 1 / normal 43 (F-060, F-116, F-120)",
  len(byjudge.get("violation", [])) == 9 and len(byjudge.get("alert", [])) == 1
  and len(byjudge.get("normal", [])) == 43,
  {k: len(v) for k, v in byjudge.items()})

# F-207 — §3.1 표와 §6 요약을 각각 읽는다. 두 곳 중 하나만 고쳐도 실패한다.
_actual_j = {k: len(byjudge.get(k, [])) for k in ("violation", "alert", "normal")}
_doc_table_j = {k: int(n) for k, n in
                re.findall(r"^\|\s*`(violation|alert|normal)`\s*\|\s*(\d+)\s*\|", DOC, re.M)}
_doc_summary = re.search(
    r"판정 분리 \(F-060\).*?`violation`\s*(\d+)\s*/\s*"
    r"`alert`\s*(\d+)\s*/\s*`normal`\s*(\d+)", DOC)
_doc_summary_j = ({"violation": int(_doc_summary.group(1)),
                   "alert": int(_doc_summary.group(2)),
                   "normal": int(_doc_summary.group(3))}
                  if _doc_summary else {})
t("명세서 §3.1 판정 건수 = 실제 JSONL 판정 (F-207)",
  _doc_table_j == _actual_j, f"문서={_doc_table_j} 실제={_actual_j}")
t("명세서 §6 판정 요약 = 실제 JSONL 판정 (F-207)",
  _doc_summary_j == _actual_j, f"문서={_doc_summary_j} 실제={_actual_j}")

# F-116 — n=None(가변부만 있는 메시지에서 element_count() 가 형식 오류로 판정한
# 것) 인데 judgement 가 normal/alert 이면 그 자체로 모순이다("N을 못 구했다"와
# "정상"은 동시에 참일 수 없다). B02 가 이 결함의 실례였다 — 같은 종류가 다시
# 생겨도 여기서 잡는다.
none_n_bad = [v["id"] for v in GOLD if v["n"] is None and v["judgement"] in ("normal", "alert")]
t("n is None 인 벡터는 normal/alert 일 수 없다 (F-116)", not none_n_bad, str(none_n_bad))

nec_only = [v["id"] for v in GOLD if v.get("nec_alert") and v["violations"]]
t("NEC 알림 벡터에 violations 가 비어 있음 (격리되지 않는다)", not nec_only, str(nec_only))

t("violations 에는 INVALID_* 만 들어간다",
  all(w["code_name"].startswith("INVALID_") for v in GOLD for w in v["violations"]),
  str([w["code_name"] for v in GOLD for w in v["violations"]
       if not w["code_name"].startswith("INVALID_")]))

viol_ids = [v["id"] for v in GOLD if v["judgement"] == "violation"]
t(f"프로토콜 위반 판정 {len(viol_ids)}건에 전부 violations 기재 (F-116: 7->8 B02, F-120: 8->9 B11)",
  len(viol_ids) == 9
  and all(next(x for x in GOLD if x["id"] == i)["violations"] for i in viol_ids), str(viol_ids))

# ── F-062 ① 주입 라벨 <-> 기대 코드 1:1 ────────────────────────
#   "위반 8종이 다 있다"만 보면 X01 과 X02 의 기대를 서로 바꿔도 통과한다.
#   어떤 주입에 어떤 코드가 붙었는지를 본다.
INJECT_EXPECT = {
    "version":            (0x01, "INVALID_VERSION",           "7.3.1"),
    "unregistered_node":  (0x03, "INVALID_NODE_ID",           "7.3.1"),
    "payload_length":     (0x09, "INVALID_FORMAT",            "7.3.1"),
    "message_type":       (0x09, "INVALID_FORMAT",            "표 7-2"),
    "transmission_type":  (0x08, "INVALID_TRANSMISSION_TYPE", "표 7-6"),
    "value_type":         (0x06, "INVALID_DATA_TYPE",         "표 7-14"),
    "subtype":            (0x07, "INVALID_DATA_SUBTYPE",      "표 7-14"),
    "nec_battery_low":    (0x07, "ERROR_BATTERY_LOW",         "7.3.2"),
}
map_bad = []
for v in GOLD:
    if v["category"] != "위반": continue
    lab = v.get("inject")
    if lab not in INJECT_EXPECT:
        map_bad.append(f"{v['id']}: 주입 라벨 없음/미정의 ({lab})"); continue
    judged = v["violations"] or ([v["nec_alert"]] if v.get("nec_alert") else [])
    if len(judged) != 1:
        map_bad.append(f"{v['id']}: 기대 1건이어야 하는데 {len(judged)}건"); continue
    got = (judged[0]["code"], judged[0]["code_name"], judged[0]["clause"])
    if got != INJECT_EXPECT[lab]:
        map_bad.append(f"{v['id']}({lab}): {got} != {INJECT_EXPECT[lab]}")
labels = [v.get("inject") for v in GOLD if v["category"] == "위반"]
t("주입 라벨 <-> 기대 코드 1:1 대조 (F-062)",
  not map_bad and sorted(labels) == sorted(INJECT_EXPECT), "; ".join(map_bad[:4]) or str(sorted(labels)))

# ── F-062 ② 바이트에서 재판정 — 벡터에 적힌 기대를 보지 않는다 ──
#   Node ID 등록 여부는 게이트웨이의 런타임 상태라 바이트만으로 판정할 수 없다.
#   나머지 6종은 프레임 내용만으로 결정된다.
DEFINED_MT = set(WIRE_CODE.values())
BYTE_DECIDABLE = {"INVALID_VERSION", "INVALID_FORMAT", "INVALID_TRANSMISSION_TYPE",
                  "INVALID_DATA_TYPE", "INVALID_DATA_SUBTYPE"}

def derive(v: dict) -> set[tuple]:
    h, out = v["header"], set()
    if h["Version"] != 0x12:
        out.add((0x01, "INVALID_VERSION", "7.3.1"))
    if h["Payload Length"] != v["len"] - 12:
        out.add((0x09, "INVALID_FORMAT", "7.3.1"))
    if h["Message Type"] not in DEFINED_MT:
        out.add((0x09, "INVALID_FORMAT", "표 7-2"))
    if h["Transmission Type"] not in (0, 1, 2):
        out.add((0x08, "INVALID_TRANSMISSION_TYPE", "표 7-6"))
    # F-116 — "선언된 Payload Length가 실제 수신 byte와 같다"와 "그 길이가
    # 이 메시지 코드의 어떤 후보 레이아웃에도 구조적으로 맞지 않는다"는
    # 서로 다른 원인이다. B02(REQ_SET_DEVICE_CONTROL, plen=0)는 선언=실제가
    # 정확히 맞는데도(위 검사를 안 거친다) 가변부만 있는 메시지가 N=0이라
    # element_count()의 N>=1 규칙(Frame 구조 명세서 §4.1)에 걸린다. 여기서
    # 독립적으로 다시 판정한다 — resolve_kind()/element_count() 를 부르지
    # 않고 LAYOUT 표만으로 같은 결론에 도달해야 진짜 교차검증이다.
    cands = [k for k, code in WIRE_CODE.items() if code == h["Message Type"]]
    if cands:
        def _fits(k) -> bool:
            fixed, elem = LAYOUT[k]
            rest = h["Payload Length"] - fixed
            if rest < 0:
                return False
            if elem == 0:
                return rest == 0
            if rest % elem:
                return False
            n = rest // elem
            if n == 0 and fixed == 0:
                return False
            if n > MAX_DEVICES_PER_NODE:   # F-120 — 노드당 디바이스 상한(B11)
                return False
            return True
        if not any(_fits(k) for k in cands):
            out.add((0x09, "INVALID_FORMAT", "7.3.1"))
    for f in v.get("fields", []):
        if f["name"] == "Value Type" and f["value"] == 3:
            out.add((0x06, "INVALID_DATA_TYPE", "표 7-14"))
        if f["name"] == "Subtype" and f["value"] not in SUB_VALUES:
            out.add((0x07, "INVALID_DATA_SUBTYPE", "표 7-14"))
    return out

derive_bad = []
for v in GOLD:
    got = derive(v)
    rec = {(w["code"], w["code_name"], w["clause"]) for w in v["violations"]
           if w["code_name"] in BYTE_DECIDABLE}
    if got != rec:
        derive_bad.append(f"{v['id']}: 바이트 재판정={sorted(got)} 기록={sorted(rec)}")
t("바이트에서 재판정한 위반이 기록과 일치 (정상·경계는 무위반)",
  not derive_bad, "; ".join(derive_bad[:3]))

# ── CLAUDE.md 6.3 표와 대응하는가 ──────────────────────────────
claude = find("CLAUDE.md")
claude_txt = claude.read_text(encoding="utf-8") if claude else ""
sec = claude_txt.partition("### 6.3")[2].partition("\n---")[0]
want_codes = re.findall(r"`(INVALID_\w+|ERROR_\w+)`", sec)
have_codes = [w["code_name"] for v in GOLD if v["category"] == "위반"
              for w in (v["violations"] or ([v["nec_alert"]] if v.get("nec_alert") else []))]
t("CLAUDE.md 6.3 위반 8종과 벡터가 정확히 대응",
  bool(want_codes) and sorted(want_codes) == sorted(have_codes),
  f"규약={sorted(want_codes)} 벡터={sorted(have_codes)}")

# Subtype 은 레지스트리에 있어야 한다 (미등록 주입 케이스 X07 만 예외)
sub_bad = []
for v in GOLD:
    for f in v.get("fields", []):
        if f["name"] == "Subtype" and f["value"] not in SUB_VALUES:
            if not any(w["code_name"] == "INVALID_DATA_SUBTYPE" for w in v["violations"]):
                sub_bad.append(f"{v['id']}: Subtype=0x{f['value']:02X}")
t("Subtype 이 레지스트리에 존재 (미등록은 위반 케이스뿐)", not sub_bad, str(sub_bad))

# ═══════════════════════════════════════════════════════════════
#  5. 독립 인코더(spec_verify)와의 교차 검증
#     같은 메시지의 **페이로드 바이트**가 일치해야 한다.
#     헤더는 Message Identifier 가 달라 비교 대상이 아니다.
# ═══════════════════════════════════════════════════════════════
ex_path = find("spec_examples.json")
CROSS = {                      # spec_examples id -> golden id
    "REQ_SET_CONNECTION_min":       "N01",
    "ACK_min":                      "N10",
    "RES_SET_DEVICE_CONTROL_ok":    "N17",
    "REQ_SET_MSG_PROFILE":          "N23",
    "REQ_GET_DEVICE_VALUE_3":       "N25",
    "REQ_SET_DEVICE_CONTROL_valve": "N26",
    "RES_SET_CONNECTION_1dev":      "N27",
    "NOTI_DEVICE_VALUE_2sensor":    "N34",
    "NOTI_ERROR_batlow":            "X08",
}
if ex_path and ex_path.exists():
    ex = {e["id"]: e for e in json.load(open(ex_path, encoding="utf-8"))}
    gold_by_id = {v["id"]: v for v in GOLD}
    cross_bad, checked = [], 0
    for ex_id, g_id in CROSS.items():
        if ex_id not in ex or g_id not in gold_by_id:
            cross_bad.append(f"{ex_id}/{g_id} 없음"); continue
        a = bytes.fromhex(ex[ex_id]["hex"])[12:]
        b = bytes.fromhex(gold_by_id[g_id]["hex"])[12:]
        checked += 1
        if a != b:
            cross_bad.append(f"{ex_id} vs {g_id}: {a.hex().upper()} != {b.hex().upper()}")
    t(f"독립 인코더와 페이로드 바이트 일치 ({checked}건 교차)", not cross_bad, "; ".join(cross_bad[:3]))
else:
    t("독립 인코더와 페이로드 바이트 일치", False, "spec_examples.json 없음")

# ═══════════════════════════════════════════════════════════════
#  6. 커버리지
# ═══════════════════════════════════════════════════════════════
normal = {v["msg"] for v in GOLD if v["category"] == "정상"}
t("정상 벡터가 메시지 34종 전량을 덮음",
  normal == set(MsgKind.__members__), str(sorted(set(MsgKind.__members__) - normal)))

t("0x0800 중복이 길이로 갈린다 (NOTI_ERROR / NOTI_DEVICE_VALUE 둘 다 존재)",
  {"NOTI_ERROR", "NOTI_DEVICE_VALUE"} <= normal
  and resolve_kind(0x0800, 1) is MsgKind.NOTI_ERROR
  and resolve_kind(0x0800, 14) is MsgKind.NOTI_DEVICE_VALUE)

bound = [v for v in GOLD if v["category"] == "경계"]
axes = {v["axis"] for v in bound}
# F-120 — B11(N 상한 초과) 추가로 경계 10 -> 11, 축 7 -> 8종("N 상한 초과").
t(f"경계 벡터 11건 · 축 {len(axes)}종", len(bound) == 11 and None not in axes and len(axes) >= 6,
  " · ".join(sorted(a for a in axes if a)))

# N 산출 불가(가변부만 + 빈 페이로드)는 형식 오류다 — 명세서 4절.
# F-116 — 이전에는 n/element_count() 만 보고 "그래서 이게 violation 이어야
# 한다"는 연결은 검사하지 않아, judgement=normal/violations=[] 로 생성된
# 모순을 그냥 통과시켰다. 이제 그 연결까지 명시적으로 검사한다.
b02 = next((v for v in GOLD if v["id"] == "B02"), None)
t("N=0 거부 경계가 element_count() 로 판정된다 (명세서 4절)",
  b02 is not None and b02["n"] is None
  and element_count(MsgKind[b02["kind"]], 0) is None)
t("B02: n=None 이 실제로 judgement=violation/INVALID_FORMAT(7.3.1) 로 이어진다 (F-116)",
  b02 is not None and b02["judgement"] == "violation"
  and any(w["code_name"] == "INVALID_FORMAT" and w["clause"] == "7.3.1" for w in b02["violations"]))

# ═══════════════════════════════════════════════════════════════
w = max(len(n) for _, n, _ in R)
print("골든 벡터 검증  (독립 헤더 리더 / frame.py / spec_examples / CLAUDE.md)\n")
for ok, n, note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
p = sum(1 for o, *_ in R if o)
print(f"\n  {p}/{len(R)} 통과")
sys.exit(0 if p == len(R) else 1)
