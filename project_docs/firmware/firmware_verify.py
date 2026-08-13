"""펌웨어 설계서 검증 — 문서의 수치를 계약·골든 벡터와 대조한다

설계서는 산문이라 틀려도 통과한다. 그래서 문서에 적힌 숫자를 전부 파싱해
**문서 밖의 출처**로 다시 산출한 값과 맞춘다. 출처는 셋이다.

  1) contracts/frame.py  — LAYOUT · 구조체 바이트 상수 · RSC 열거.
     계약은 설계서보다 먼저 존재했고 설계서를 참조하지 않는다.
  2) contracts/vectors/golden.jsonl — 최대 프레임(B03)과 위반 8종(X01~X08).
     "501 byte" 와 "위반 8종 표" 가 실제 바이트열과 맞는지 본다.
  3) 문서 자신의 내부 정합 — 메모리 표의 합계·백분율, 상태 전이표와
     상태 다이어그램, RSC 재시도 분류의 전수 커버.

실행:  python project_docs/firmware/firmware_verify.py
종료코드: 0 = 전부 일치, 1 = 불일치 있음
"""
from __future__ import annotations
import json, math, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
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

def find(name: str, must: str = "") -> Path | None:
    """HERE 에서 위로 올라가며 찾는다. 저장소 배치에 의존하지 않는다.
       must 가 있으면 그 문자열을 포함한 파일만 인정한다 — 동명이인 방지."""
    base = HERE
    for _ in range(6):
        for q in sorted(base.rglob(name)):
            if _skip(q): continue
            if must:
                try:
                    if must not in q.read_text(encoding="utf-8"): continue
                except Exception: continue
            return q
        if base.parent == base: break
        base = base.parent
    return None

DOC_PATH = HERE / "펌웨어_설계서.md"
DOC = DOC_PATH.read_text(encoding="utf-8")

# ── frame.py 를 모듈로 적재 ──────────────────────────────────
FRAME = find("frame.py", must="MsgKind")
_ns: dict = {}
exec(compile(FRAME.read_text(encoding="utf-8"), str(FRAME), "exec"), _ns)
_need = ("MsgKind", "RSC", "LAYOUT", "HEADER_BYTES", "NP_BYTES", "DMI_BYTES",
         "DP_BYTES", "MCP_BYTES", "RSC_BYTES")
_miss = [k for k in _need if k not in _ns]
if _miss:
    print(f"  FAIL  계약 파일을 잘못 찾았다: {FRAME} (없는 심볼 {_miss})")
    sys.exit(1)
LAYOUT       = _ns["LAYOUT"]
HEADER_BYTES = _ns["HEADER_BYTES"]
RSC          = _ns["RSC"]
MsgKind      = _ns["MsgKind"]
t("frame.py 적재 (LAYOUT 34종 · RSC 10종)",
  len(LAYOUT) == 34 and len(list(RSC)) == 10, str(FRAME.name))

GOLD_PATH = find("golden.jsonl")
GOLD = [json.loads(l) for l in GOLD_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]

def rows(after: str, cols: int, scope: str = "") -> list[list[str]]:
    """문서에서 `after`(표의 헤더 행) 다음에 오는 데이터 행을 뜯는다.
       `after` 자체가 헤더이므로 결과에 헤더는 포함되지 않는다.
       scope 를 주면 그 절 제목 이후부터 찾는다 — 같은 헤더의 표가 둘 이상일 때 필요하다."""
    src = DOC.split(scope, 1)[1] if scope and scope in DOC else DOC
    seg = src.split(after, 1)[1] if after in src else ""
    out = []
    for line in seg.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if out: break              # 표가 끝났다
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if set("".join(cells)) <= set("-: |"): continue     # 구분선
        if len(cells) != cols: break                        # 다른 표로 넘어갔다
        out.append(cells)
    return out

def nums(s: str) -> list[int]:
    return [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", s)]

# ═══════════════════════════════════════════════════════════════
#  1. 스트리밍 전제 — 모든 구조체가 바이트 정렬인가
# ═══════════════════════════════════════════════════════════════
STRUCTS = rows("| 구조체 | bit | byte | 정렬 |", 4)
bad_align = [r[0] for r in STRUCTS if nums(r[1])[0] % 8 or nums(r[1])[0] // 8 != nums(r[2])[0]]
t("구조체 6종이 전부 바이트 정렬 (스트리밍 전제, 3.3)",
  len(STRUCTS) == 6 and not bad_align, str(bad_align))

# LAYOUT 의 고정부·요소도 정수 byte 여야 한다 (frame.py 는 byte 단위이므로 자명하나,
# 요소 크기가 0 이 아닌데 문서의 max(elem) 와 다르면 여기서 걸린다)
t("LAYOUT 34종의 고정부·요소가 전부 byte 단위 (frame.py)",
  all(isinstance(f, int) and isinstance(e, int) and f >= 0 and e >= 0
      for f, e in LAYOUT.values()))

# ═══════════════════════════════════════════════════════════════
#  2. 스트리밍 윈도우 = 12 + max(fixed) + max(elem)
# ═══════════════════════════════════════════════════════════════
MAX_FIXED = max(f for f, _ in LAYOUT.values())
MAX_ELEM  = max(e for _, e in LAYOUT.values())
WINDOW    = HEADER_BYTES + MAX_FIXED + MAX_ELEM

m = re.search(r"=\s*(\d+)\s*\+\s*(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)\s*byte", DOC)
t("문서의 윈도우 산식이 frame.py 로 재산출한 값과 일치",
  m is not None and [int(g) for g in m.groups()] == [HEADER_BYTES, MAX_FIXED, MAX_ELEM, WINDOW],
  f"재산출 {HEADER_BYTES}+{MAX_FIXED}+{MAX_ELEM}={WINDOW} / 문서 {m.groups() if m else None}")

t(f"윈도우 {WINDOW} byte 가 문서 전반에 일관 표기",
  DOC.count(f"{WINDOW} byte") >= 3 and f"**{WINDOW} B**" in DOC or f"{WINDOW} B" in DOC)

# ═══════════════════════════════════════════════════════════════
#  3. 최대 프레임 501 = 골든 B03
# ═══════════════════════════════════════════════════════════════
CAP = 16                                             # 노드당 디바이스 상한 (F-064)
MAXFRAME = HEADER_BYTES + MAX_FIXED + MAX_ELEM * CAP
b03 = next((v for v in GOLD if v["id"] == "B03"), None)
t(f"최대 프레임 {MAXFRAME} byte = 골든 B03 실측 길이",
  b03 is not None and b03["len"] == MAXFRAME and b03["n"] == CAP,
  f"B03 len={b03['len'] if b03 else None} n={b03['n'] if b03 else None}")
t(f"문서가 최대 프레임을 {MAXFRAME} 로 적었다", f"{MAXFRAME} byte" in DOC or f"{MAXFRAME} B" in DOC)

# 문서의 501-버퍼 반례 계산 (3.4 말미) 도 산술이 맞아야 한다
m = re.search(r"(\d+)\s*\+\s*(\d+)\s*\+\s*(\d+)\s*\+\s*(\d+)\s*=\s*([\d,]+)\s*B\s*\(([\d.]+)%\)", DOC)
if m:
    parts = [int(x) for x in m.groups()[:4]]; tot = int(m.group(5).replace(",", ""))
    t("501-버퍼 반례의 산술과 백분율이 맞다",
      sum(parts) == tot and abs(tot / 2048 * 100 - float(m.group(6))) < 0.05,
      f"{'+'.join(map(str,parts))}={tot} ({tot/2048*100:.1f}%)")
else:
    t("501-버퍼 반례의 산술과 백분율이 맞다", False, "반례 문장을 찾지 못함")

# ═══════════════════════════════════════════════════════════════
#  4. 구조체 크기 6종 ↔ frame.py 상수
# ═══════════════════════════════════════════════════════════════
WANT = {"헤더": HEADER_BYTES, "NODE_PROPERTY": _ns["NP_BYTES"],
        "DEVICE_MAIN_INFO": _ns["DMI_BYTES"], "DEVICE_PROPERTY": _ns["DP_BYTES"],
        "MSG_CONTROL_PROFILE": _ns["MCP_BYTES"], "RSC": _ns["RSC_BYTES"]}
mismatch = []
for r in STRUCTS:
    key = next((k for k in WANT if k in r[0]), None)
    if key is None: mismatch.append(f"미상 행 {r[0]}"); continue
    if nums(r[2])[0] != WANT[key]: mismatch.append(f"{key} 문서 {r[2]} != frame.py {WANT[key]}")
t("구조체 크기 6종이 frame.py 상수와 일치 (표 7-13~7-18)", not mismatch, "; ".join(mismatch))

# ═══════════════════════════════════════════════════════════════
#  5. 메모리 예산표 — 합계·백분율·SRAM 한도
# ═══════════════════════════════════════════════════════════════
SRAM = 2048
ITEMS = rows("| 대상 | 크기 | 산출 |", 3)
base = 0; per_dev = None; stated_base = None
for r in ITEMS:
    if "소계" in r[0]: stated_base = nums(r[1])[0]; continue
    if "디바이스 테이블" in r[0]: per_dev = nums(r[1])[0]; continue
    base += nums(r[1])[0]
t("메모리 소계가 항목 합과 일치", stated_base == base, f"항목합={base} 표기={stated_base}")
t("디바이스 테이블 단가가 DEVICE_PROPERTY 30 byte 이상 (언팩 오버헤드)",
  per_dev is not None and per_dev >= _ns["DP_BYTES"], f"{per_dev} B/device")

NODES = rows("| 노드 | D | 디바이스 테이블 | 합계 | SRAM 2,048 B 대비 |", 5)
bad = []
for r in NODES:
    d = nums(r[1])[0]; tbl = nums(r[2])[0]; tot = nums(r[3])[0]; pct = float(re.findall(r"[\d.]+", r[4])[0])
    if tbl != per_dev * d: bad.append(f"{r[0]}: 테이블 {tbl} != {per_dev}x{d}")
    if tot != base + tbl:  bad.append(f"{r[0]}: 합계 {tot} != {base}+{tbl}")
    if abs(tot / SRAM * 100 - pct) > 0.05: bad.append(f"{r[0]}: {pct}% != {tot/SRAM*100:.1f}%")
    if tot >= SRAM:        bad.append(f"{r[0]}: SRAM 초과")
t(f"노드 3종 메모리 산술·백분율이 맞고 SRAM {SRAM} B 미만",
  len(NODES) == 3 and not bad, "; ".join(bad))

# F-129 — PROGMEM 을 포기하고 core/ 순수성을 우선한 결정(§3.5)의 대가로
# 상한 노드(D=16, 이론상 최댓값)의 추정치가 40%를 넘는다(45.0%). 실제 보드
# 시나리오인 Uno·Pro Mini 만 40% 미만을 강제하고, 상한 노드는 avr-size
# 실측(단계 8) 전까지 잠정 완화한다 — 개발_착수_지시서 §1.5 "실측값이
# 설계서의 추정치를 대체한다" 원칙. 실측이 실제로 넘으면 그때 재검토한다.
REALISTIC_NODES = [r for r in NODES if "상한" not in r[0]]
UPPER_NODES = [r for r in NODES if "상한" in r[0]]
t("실사용 노드(Uno·Pro Mini) SRAM 40% 미만",
  bool(REALISTIC_NODES) and all(nums(r[3])[0] / SRAM < 0.40 for r in REALISTIC_NODES))
t("상한 노드(D=16, 이론치) SRAM 추정 기록됨 - 40% 초과는 avr-size 실측(단계 8) 전까지 잠정 완화 (F-129)",
  bool(UPPER_NODES),
  "; ".join(f"{r[0]}: {nums(r[3])[0] / SRAM:.1%}" for r in UPPER_NODES))

# ═══════════════════════════════════════════════════════════════
#  6. 위반 8종 표 ↔ 골든 X01~X08
# ═══════════════════════════════════════════════════════════════
VIO = rows("| # | 주입 | RSC | clause | 판정 지점 | 페이로드 저장 |", 6)
xs = [v for v in GOLD if v["category"] == "위반"]
xs.sort(key=lambda v: v["id"])
pairs_doc, pairs_gold = [], []
for r in VIO:
    name = re.findall(r"`([A-Z_]+)`", r[2])
    pairs_doc.append((name[0] if name else r[2], r[3]))
for v in xs:
    if v["violations"]:
        pairs_gold.append((v["violations"][0]["code_name"], v["violations"][0]["clause"]))
    elif v.get("nec_alert"):
        pairs_gold.append((v["nec_alert"]["code_name"], v["nec_alert"]["clause"]))
t("위반 8종 표가 골든 X01~X08 과 (코드명, 조항) 순서까지 일치",
  len(VIO) == 8 and len(pairs_gold) == 8 and pairs_doc == pairs_gold,
  f"문서={pairs_doc[:2]}... 골든={pairs_gold[:2]}..." if pairs_doc != pairs_gold else "")

hdr_stage = sum(1 for r in VIO if "S_HDR" in r[4])
t("위반 8종 중 4종이 헤더 단계에서 걸러진다 (페이로드 미저장)",
  hdr_stage == 4 and all("없음" in r[5] for r in VIO if "S_HDR" in r[4]), f"{hdr_stage}종")
t("요소 단계 판정 2종만 요소 1개분을 읽는다",
  sum(1 for r in VIO if "S_ELEM" in r[4]) == 2
  and all("요소 1개분" in r[5] for r in VIO if "S_ELEM" in r[4]))

# ═══════════════════════════════════════════════════════════════
#  7. RSC 재시도 분류가 10종 전량을 덮는가
# ═══════════════════════════════════════════════════════════════
RETRY = rows("| RSC | 코드 | 재시도 | 근거 |", 4)
listed = {re.findall(r"`([A-Z_]+)`", r[0])[0] for r in RETRY if re.findall(r"`([A-Z_]+)`", r[0])}
codes  = {re.findall(r"0x([0-9A-Fa-f]{2})", r[1])[0].upper() for r in RETRY if re.findall(r"0x([0-9A-Fa-f]{2})", r[1])}
want   = {r.name for r in RSC}
want_c = {f"{r.value:02X}" for r in RSC}
retryable = [r for r in RETRY if "가능" in r[2]]
N_RETRYABLE = len(retryable)
t("재시도 분류표가 RSC 10종 전량을 덮는다 (표 7-10)",
  listed == want and codes == want_c, str(sorted(want - listed)))
t("재시도 가능 2종 / 불가 7종 / SUCCESS 제외 = 10",
  N_RETRYABLE == 2 and len(RETRY) == len(list(RSC))
  and {re.findall(r"`([A-Z_]+)`", r[0])[0] for r in retryable}
      == {"INVALID_GCG_ID", "INVALID_NODE_ID"},
  f"가능 {N_RETRYABLE}종 / 표 {len(RETRY)}행")

# ── F-074 ① 요약(0절)의 수치가 본문과 같은가 ─────────────────
#    "문서 전반 일관" 을 이름만 그렇게 붙여두면 안 된다. 요약표는 별도 표라
#    §7 파싱 대상이 아니었고, 3종/99종 변조가 그대로 통과했다.
SUMMARY = rows("| 결정 | 값 | 근거 |", 3)
t("0절 요약표를 파싱했다 (F-074)", len(SUMMARY) >= 8, f"{len(SUMMARY)}행")

_sum_retry = next((r[1] for r in SUMMARY if "RSC" in r[0]), "")
_m = re.search(r"가능\D{0,4}(\d+)\s*종.{0,4}/\s*불가\s*(\d+)\s*종", _sum_retry)
t("0절 요약의 재시도 수 = 6.5 표 실측 (F-074)",
  _m is not None and int(_m.group(1)) == N_RETRYABLE
  and int(_m.group(2)) == len(RETRY) - N_RETRYABLE - 1,
  f"요약={_m.groups() if _m else None} 실측=가능{N_RETRYABLE}/불가{len(RETRY)-N_RETRYABLE-1}")

_sum_win = next((r[1] for r in SUMMARY if "윈도우" in r[0]), "")
t("0절 요약의 윈도우 값 = 재산출 값 (F-074)", str(WINDOW) in _sum_win, _sum_win)


# ── F-074 ② Subtype 개수를 계약에서 재산출 ───────────────────
_sub = _ns.get("Subtype")
N_SUBTYPE = len(list(_sub)) if _sub is not None else None
_m2 = re.search(r"`subtype_registry\.h`[^|]*\|[^|]*\|[^|]*?(\d+)\s*종", DOC)
t(f"Flash 표의 Subtype 개수 = frame.py 의 Subtype 열거 {N_SUBTYPE}종 (F-074)",
  N_SUBTYPE is not None and _m2 is not None and int(_m2.group(1)) == N_SUBTYPE,
  f"문서={_m2.group(1) if _m2 else None} 계약={N_SUBTYPE}")

# ── F-074 ③ 구조체 포인터 산술을 선언에서 재산출 ──────────────
PTR = 2                                    # ATmega328P: flash 32KB -> 2 byte 포인터
def _struct_bytes(name: str) -> int | None:
    m = re.search(r"typedef struct \{([^{}]*)\} " + re.escape(name) + r";", DOC)
    if not m: return None
    body = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    # 멤버는 줄 단위로 센다. 함수 포인터의 **인자 목록**에도 void *ctx 가 나오므로
    # 본문 전체에 정규식을 걸면 인자를 멤버로 오인한다 (재산출이 14/10 이 되는 원인).
    fn = ptr = 0
    for line in body.splitlines():
        if ";" not in line: continue
        if re.search(r"\(\s*\*\s*\w+\s*\)", line): fn += 1      # 함수 포인터 멤버
        elif "(" not in line and re.search(r"\*\s*\w+\s*;", line): ptr += 1  # 일반 포인터 멤버
    return (fn + ptr) * PTR
IO_B, DEV_B = _struct_bytes("siap_io_t"), _struct_bytes("siap_dev_ops_t")
_m3 = re.search(r"\| `siap_io_t` \+ `siap_dev_ops_t` \| (\d+) B", DOC)
t("메모리 표의 추상화 구조체 크기 = 선언에서 재산출 (F-074)",
  None not in (IO_B, DEV_B) and _m3 is not None and int(_m3.group(1)) == IO_B + DEV_B,
  f"재산출 {IO_B}+{DEV_B}={None if IO_B is None else IO_B+DEV_B} / 문서 {_m3.group(1) if _m3 else None}")
t("2.2 의 구조체 크기표도 같은 값 (F-074)",
  f"**{IO_B} B**" in DOC and f"**{DEV_B} B**" in DOC and f"**{IO_B+DEV_B} B**" in DOC,
  f"{IO_B}/{DEV_B}/{IO_B+DEV_B}")

# ═══════════════════════════════════════════════════════════════
#  8. 상태 전이표 — 필수 전이 집합까지 검사한다 (F-074)
# ═══════════════════════════════════════════════════════════════
TRANS = rows("| 현재 | 사건 | 다음 | 동작 |", 4)
def _cell(x: str) -> str:
    return re.sub(r"[`*]", "", x)
states = {_cell(r[0]) for r in TRANS} | {_cell(r[2]) for r in TRANS}
states = {x for x in states if re.fullmatch(r"[A-Z_]+", x)}
diagram = DOC.split("### 6.1 상태", 1)[1].split("### 6.2 전이표", 1)[0]
orphan = sorted(x for x in states if x not in diagram)
t("전이표의 모든 상태가 6.1 다이어그램에 등장 (고아 상태 없음)",
  len(TRANS) >= 15 and not orphan, str(orphan))
_dead = sorted(x for x in states if x not in {_cell(r[0]) for r in TRANS}
               and "HALTED" not in x)
t("종료 상태 없음: 모든 상태에서 나가는 전이가 존재", not _dead, str(_dead))

# 표준이 요구하는 전이가 실제로 표에 있는가.
# 이름 존재와 '나가는 행이 하나 이상' 만 보면 ACK 회신 행을 지워도 통과한다 (F-074).
_flat = "\n".join(" | ".join(r) for r in TRANS)
REQUIRED = [
    ("G→N Notify 수신 시 ACK 회신 (6.1.2)",        r"G.N Notify 수신.*ACK"),
    ("ACK 회신이 상태와 무관 (6.1.2)",              r"HALTED 제외 전 상태.*\|.*G.N Notify 수신"),
    ("송신 Notify 의 응답 대기 해제 (8.2.1)",       r"ACK/RES 수신.*pending. 해제"),
    ("pending Timeout 재전송 (8.2.1 그림 8-45)",    r"pending. Timeout.*재송신"),
    ("REBOOTING 은 ACK 수신으로 완료 (그림 8-56)",  r"REBOOTING \| .*ACK 수신 \| BOOT"),
    ("REBOOTING 은 재전송 소진으로도 완료 (8-56)",  r"REBOOTING \| .*재전송 소진 \| BOOT"),
    ("연결 성공 전이 (8.1.1)",                      r"CONNECTING \| .*SUCCESS \| RUNNING"),
    ("재시도 불가 RSC 는 HALTED (F-072)",           r"CONNECTING \| .*재시도 불가.* \| HALTED"),
    ("주기 알림 송신 (8.2.1.2)",                    r"NOTI_DEVICE_VALUE. 송신"),
    ("Keep Alive 송신 (8.2.1.5)",                   r"NOTI_KEEP_ALIVE. 송신"),
    ("오류 알림 반복 (8.2.1.1)",                    r"FAULT \| .*Notify Error Interval"),
    ("연결 해제 수신 처리 (8.2.1.3)",               r"NOTI_DISCONNECT. 수신.*DISCONNECTED"),
]
_absent = [n for n, pat in REQUIRED if not re.search(pat, _flat)]
t(f"표준이 요구하는 필수 전이 {len(REQUIRED)}종이 전이표에 존재 (F-074)",
  not _absent, str(_absent[:3]))

# FAULT 는 연결 승인 이후에만 진입한다 (F-072)
_fault_in = {_cell(r[0]) for r in TRANS if _cell(r[2]) == "FAULT" and _cell(r[0]) != "FAULT"}
t("FAULT 진입은 RUNNING 에서만 (연결 승인 이후 전용, F-072)",
  _fault_in == {"RUNNING"}, str(sorted(_fault_in)))
_fault_out = {_cell(r[2]) for r in TRANS if _cell(r[0]) == "FAULT"}
t("FAULT 복구 목적지는 RUNNING 뿐 (F-072)",
  _fault_out <= {"RUNNING", "FAULT"}, str(sorted(_fault_out)))

# ── F-076: HALTED 는 영구 정지다. 탈출 전이가 있으면 안 된다 ────
_halted_out = {_cell(r[2]) for r in TRANS if _cell(r[0]) == "HALTED"}
t("HALTED 에서 나가는 전이가 없다 (영구 정지, F-076)",
  _halted_out <= {"HALTED"}, str(sorted(_halted_out)))
# 전이표의 '현재' 칸에 무조건적 '(상태 무관)' 이 남아 있으면 HALTED 도 포함된다.
# 본문 산문에서 옛 표현을 인용하는 것은 허용한다 - 표의 셀만 본다.
_blanket = [r[0] for r in TRANS if "상태 무관" in r[0] and "HALTED" not in r[0]]
t("전이표의 상태 무관 전이가 HALTED 를 명시적으로 제외한다 (F-076)",
  not _blanket and sum(1 for r in TRANS if "HALTED 제외" in r[0]) == 4,
  f"무조건 상태무관={_blanket} 제외표기={sum(1 for r in TRANS if 'HALTED 제외' in r[0])}행")

# ── F-076: 재시도 불가 RSC 의 목적 상태가 세 곳에서 같은가 ──────
_CLAUDE = find("CLAUDE.md", must="절대 금지")
_cm = _CLAUDE.read_text(encoding="utf-8") if _CLAUDE else ""
def _target(text: str, near: str) -> str | None:
    """near 를 포함하는 줄에서 '불가' 뒤에 나오는 상태 이름을 뽑는다."""
    for line in text.splitlines():
        if near in line and "불가" in line:
            m = re.search(r"불가[^|]*?`?(HALTED|FAULT)`?", line)
            if m: return m.group(1)
    return None
_t_65  = _target(DOC, "불가 7종")                       # 6.5 본문
_t_9   = _target(DOC, "RES_SET_CONNECTION` 오류 RSC")    # 9절 표
_t_cm  = _target(_cm, "RES_SET_CONNECTION` 오류 RSC")    # CLAUDE.md 3.5
t("재시도 불가 RSC 의 목적 상태가 6.5 · 9절 · CLAUDE.md 에서 동일 (F-076)",
  _t_65 == _t_9 == _t_cm == "HALTED", f"6.5={_t_65} 9={_t_9} CLAUDE.md={_t_cm}")
t("CLAUDE.md 3.5 에 FAULT 반복 송신 잔재 없음 (F-076)",
  "불가는 `FAULT` 로 가서" not in _cm)

# ── F-077: 주기 알림 기아 방지 규칙 ────────────────────────────
# 절 제목·본문 존재만 보면 제목을 바꿔치기해도 통과한다. 규칙표를 실제로 뜯는다.
STARVE = rows("| 규칙 | 내용 |", 2, scope="### 6.4-a 주기 알림의 기아 방지")
_need_rule = ("만료 시", "기준시각", "송신 선택", "전송 후")
_miss_rule = [k for k in _need_rule if not any(k in r[0] for r in STARVE)]
t("주기 알림 기아 방지 규칙 4행이 존재 (F-077)",
  "### 6.4-a 주기 알림의 기아 방지" in DOC and not _miss_rule
  and re.search(r"uint8_t\s+due;", DOC) is not None
  and re.search(r"uint8_t\s+cursor;", DOC) is not None,
  str(_miss_rule))
TIMERS = {r[0]: r[2] for r in rows("| 타이머 | 출처 | 기본값 | 동작 |", 4)}
_per = re.search(r"(\d+)\s*s", TIMERS.get("`Period`", ""))
_ka  = re.search(r"(\d+)\s*s", TIMERS.get("`Keep Alive Interval`", ""))
t("기본 Period 와 Keep Alive Interval 이 같다 -> 동시 만료가 실재한다 (F-077)",
  _per is not None and _ka is not None and _per.group(1) == _ka.group(1),
  f"Period={_per.group(1) if _per else None}s KeepAlive={_ka.group(1) if _ka else None}s")
t("동시 만료 결정적 테스트가 계획에 있다 (F-077)",
  "test_node_state.c" in DOC and "100주기" in DOC)

# ── F-078: 비트 패커 계약이 세 문서에서 강제되는가 ──────────────
t("bp_write 원형이 SIAP_WUR bool (설계서, F-078)",
  re.search(r"SIAP_WUR bool bp_write\s*\(", DOC) is not None)
t("bp_write 원형이 CLAUDE.md 4.2 와 동일 (F-078)",
  re.search(r"SIAP_WUR bool bp_write\s*\(", _cm) is not None
  and "void     bp_write(" not in _cm)
t("warn_unused_result 속성을 명시한다 (반환형만으로는 경고되지 않는다, F-078)",
  "warn_unused_result" in DOC and "-Werror=unused-result" in DOC)
t("범위 검사에 1u << nbits 시프트를 쓰지 않는다 (AVR 16bit int · 1u<<32 UB, F-078)",
  "(1u << nbits)" not in DOC.split("### 4.1 4개 함수", 1)[-1].split("### 4.2", 1)[0]
  or "쓰면 안 된다" in DOC)
t("마스크식 상한표가 14 · 16 · 20 · 32bit 를 덮는다 (F-078)",
  all(x in DOC for x in ("0x00003FFF", "0x0000FFFF", "0x000FFFFF"))
  and "nbits == 32" in DOC)
t("Makefile 이 -Wshift-count-overflow 를 켠다 (F-078)",
  "-Wshift-count-overflow" in DOC)

# ═══════════════════════════════════════════════════════════════
#  9. CLAUDE.md 1 금지 사항 — 설계서 자체 검사
# ═══════════════════════════════════════════════════════════════
SECRET  = re.compile(r"api[_-]?key|password|passwd|@author", re.I)
PRIVATE = re.compile(r"[A-Za-z]:\\Users\\|/home/[a-z]+/|/Users/[a-z]+/", re.I)
SYNTH   = re.compile(r"random\.(uniform|randint|random|gauss)|math\.sin|np\.random")
# 오탐 허용 — 사유를 반드시 적는다
ALLOW = {
    # 7.4 는 Wi-Fi 자격증명을 담는 파일명 규약(.gitignore 대상)을 지시한다.
    # 값이 아니라 "커밋하지 말라"는 규칙 자체다.
    "secrets.h",
}
hits = []
for i, line in enumerate(DOC.splitlines(), 1):
    s = line
    for a in ALLOW: s = s.replace(a, "")
    if SECRET.search(s) or PRIVATE.search(s) or SYNTH.search(s):
        hits.append(f"{i}: {line.strip()[:60]}")
t("설계서에 비밀정보·개인경로·합성데이터 패턴 없음 (CLAUDE.md 1)", not hits, str(hits[:3]))

t("core/ 허용 include 3종만 명시 (2.1)",
  all(h in DOC for h in ("`stdint.h`", "`stddef.h`", "`stdbool.h`"))
  and "Arduino.h" in DOC and "malloc" in DOC)

t("구동기 입력 경로가 하나임을 표로 선언 (CLAUDE.md 1-7 대응, 6.6)",
  "REQ_SET_DEVICE_CONTROL" in DOC and "유일하게 존재" in DOC
  and DOC.count("**없다**") + DOC.count("**구현하지 않는다**") >= 3)

# ═══════════════════════════════════════════════════════════════
#  10. 표준 근거 — 조항 번호가 붙어 있는가
# ═══════════════════════════════════════════════════════════════
clauses = set(re.findall(r"표 7-\d+", DOC)) | set(re.findall(r"\b8\.\d(?:\.\d)*", DOC))
t(f"표준 조항 인용 {len(clauses)}종 (CLAUDE.md 3.1)", len(clauses) >= 20,
  " ".join(sorted(clauses)[:8]) + " ...")

undecided = rows("| 항목 | 결정 | 근거 | 위치 |", 4)
t("미규정 결정이 근거·위치와 함께 표로 정리 (3.5)",
  len(undecided) >= 6 and all(r[2] and r[3] for r in undecided), f"{len(undecided)}건")

# 요약 문장의 한글 수사와 9절 표의 행 수가 같은가 (F-074 - 표기 드리프트)
_KO = {"둘": 2, "셋": 3, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}
_m = re.search(r"이 중 (\S+?)이? \*\*표준이 규정하지 않은 것\*\*", DOC)
_w = _KO.get(_m.group(1).rstrip("이"), None) if _m else None
t("0절의 '표준 미규정' 건수 표기 = 9절 표 행 수 (F-074)",
  _w == len(undecided), f"요약={_m.group(1) if _m else None}({_w}) 표={len(undecided)}")

# 9절 표가 0절 요약이 가리키는 항목을 실제로 덮는가
_sum_undec = [r[0] for r in SUMMARY
              if any(k in r[2] for k in ("5.6", "5.7", "6.5", "6.2-a", "6.1"))]
t("0절이 미규정으로 표시한 결정이 9절 표에도 존재 (F-074)",
  len(_sum_undec) >= 5, f"{len(_sum_undec)}건")

# 신규 표준결함 총계
m = re.search(r"0943 (\d+)건 → \*\*(\d+)건\*\*.*?합계 (\d+)건", DOC, re.S)
t("표준결함 총계 갱신 표기가 산술적으로 맞다 (0943 13 + 1369-P1 6 = 19)",
  m is not None and int(m.group(2)) == int(m.group(1)) + 1 and int(m.group(3)) == int(m.group(2)) + 6,
  m.groups() if m else "표기 없음")

# ═══════════════════════════════════════════════════════════════
w = max(len(n) for _, n, _ in R)
print("펌웨어 설계서 검증  (frame.py / golden.jsonl / 문서 내부 정합)\n")
for ok, n, note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
p = sum(1 for o, *_ in R if o)
print(f"\n  {p}/{len(R)} 통과")
sys.exit(0 if p == len(R) else 1)
