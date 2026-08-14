"""0937 요구사항 대조표 검증 — 독립 입력 5종과 대조한다

F-080 — 초안은 대조표 한 파일만 읽었다. 그러면 "대조표가 자기 자신과 일치하는가"만
        보게 되어, 요구 문구를 서로 바꾸거나 존재하지 않는 심벌을 근거로 적어도
        전부 통과한다. F-079 회귀 검사도 실제 아키텍처가 아니라 대조표를 다시 읽고
        있었다. 그래서 입력을 넷으로 늘렸다.

  1) 0937_clauses.json  — 원문 종결어미. 강도를 여기서 재산출한다 (F-081)
  2) 아키텍처_설계서.md — handle() 의 실제 서비스 배정 (F-079 회귀)
  3) schema.sql         — 근거로 인용한 테이블·컬럼의 실재 (F-082)
  4) openapi.json       — 근거로 인용한 API 경로의 실재 (F-082)
  5) 실제 Python 소스    — §4.1과 요구 행의 진입점 실재 (F-229)

실행:  python project_docs/services/services_verify.py
       python project_docs/services/services_verify.py --with-source <0937 원문.md>
       (--with-source 는 clauses.json 발췌본을 원문과 대조한다. 원문은 심사자 PC 에
        없으므로 기본 실행에서는 건너뛴다.)
종료코드: 0 = 전부 일치, 1 = 불일치 있음
"""
from __future__ import annotations
import ast, json, re, sys
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

DOC = (HERE / "0937_요구사항_대조표.md").read_text(encoding="utf-8")

# ── 독립 입력 4종 (F-080) ────────────────────────────────────
CLAUSES = json.loads((HERE / "0937_clauses.json").read_text(encoding="utf-8"))["clauses"]
ARCH_P  = find("아키텍처_설계서.md", must="handle(")
SQL_P   = find("schema.sql", must="CREATE TABLE")
API_P   = find("openapi.json", must="openapi")
ARCH = ARCH_P.read_text(encoding="utf-8") if ARCH_P else ""
SQL  = SQL_P.read_text(encoding="utf-8")  if SQL_P  else ""
API  = json.loads(API_P.read_text(encoding="utf-8")) if API_P else {"paths": {}}

# F-229 — 문서의 §4.1 표를 정답으로 다시 읽지 않는다. 실제 구현 소스를
# 독립 입력으로 파싱해 모듈 함수와 클래스 메서드의 완전한 심벌을 만든다.
SOURCE_SPECS = {
    "ems": ("ems.py", "def list_nodes"),
    "dms": ("dms.py", "def fetch_public_data"),
    "mms": ("mms.py", "def run_model"),
    "fms": ("fms.py", "def check_stale_devices"),
    "fcs": ("fcs.py", "def execute"),
    "ingest": ("ingest.py", "def handle"),
    "link": ("link.py", "class SiapNodeLink"),
}
SOURCE_PATHS = {mod: find(name, must=must) for mod, (name, must) in SOURCE_SPECS.items()}

def source_symbols(module: str, path: Path | None) -> set[str]:
    if path is None:
        return set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.add(f"{module}.{node.name}")
        elif isinstance(node, ast.ClassDef):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out.add(f"{module}.{node.name}.{child.name}")
    return out

ACTUAL_SYMBOLS = set().union(
    *(source_symbols(module, path) for module, path in SOURCE_PATHS.items()))

def strength_of(ending: str) -> str:
    """0937 종결어미 -> 강도. 대조표가 아니라 원문 발췌에서 산출한다 (F-081).
       능력 표현을 먼저 본다 - '가능해야 한다' 는 '해야 한다' 로 끝나지만 능력 요구다."""
    if "가능해야 한다" in ending or "할 수 있어야 한다" in ending:
        return "필수(능력)"
    if ending.endswith("해야 한다"):
        return "필수"
    return "선택"

WANT = {c["id"]: strength_of(c["ending"]) for c in CLAUSES}

def cell(x: str) -> str:
    return re.sub(r"[`*]", "", x).strip()

def rows(after: str, cols: int, scope: str = "") -> list[list[str]]:
    src = DOC.split(scope, 1)[1] if scope and scope in DOC else DOC
    seg = src.split(after, 1)[1] if after in src else ""
    out = []
    for line in seg.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if out: break
            continue
        cs = [c.strip() for c in s.strip("|").split("|")]
        if set("".join(cs)) <= set("-: |"): continue
        if len(cs) != cols: break
        out.append(cs)
    return out

# ═══════════════════════════════════════════════════════════════
#  1. 6장 요구사항 표 6종 — 행 수와 번호 연속성
# ═══════════════════════════════════════════════════════════════
SECS = {"6.1": "### 1.1 EMS", "6.2": "### 1.2 DMS", "6.3": "### 1.3 MMS",
        "6.4": "### 1.4 FMS", "6.5": "### 1.5 FCS", "6.6": "### 1.6 FOS"}
REQ: dict[str, list[list[str]]] = {}
for key, scope in SECS.items():
    REQ[key] = rows("| # | 요구사항 | 강도 | 판정 | 구현 |", 5, scope=scope)

counts = {k: len(v) for k, v in REQ.items()}
total = sum(counts.values())
t(f"6장 요구사항 표 6종 파싱 · 합계 {total}건", total == 33 and all(counts.values()),
  str(counts))

m = re.search(r"## 1\. 서비스별 요구사항 대조 — (\d+)건", DOC)
t("제목의 총계가 실제 행 수와 일치", m is not None and int(m.group(1)) == total,
  f"제목={m.group(1) if m else None} 실제={total}")

gap = []
for key, rs in REQ.items():
    ids = [cell(r[0]) for r in rs]
    want = [f"{key}-{i}" for i in range(1, len(rs) + 1)]
    if ids != want: gap.append(f"{key}: {ids}")
t("요구사항 번호가 1부터 빠짐없이 연속", not gap, "; ".join(gap[:2]))

# ═══════════════════════════════════════════════════════════════
#  2. 강도 표기 규약
# ═══════════════════════════════════════════════════════════════
LEVELS = {"필수", "필수(능력)", "선택"}
bad = sorted({cell(r[2]) for rs in REQ.values() for r in rs} - LEVELS)
t("강도 표기가 규약 3종을 벗어나지 않는다", not bad, str(bad))

# ── F-081: 강도를 원문 종결어미에서 재산출해 대조한다 ──────────
t(f"0937_clauses.json 적재 ({len(CLAUSES)}건)", len(CLAUSES) == 33)
drift = []
for rs in REQ.values():
    for r in rs:
        cid = cell(r[0])
        if cid not in WANT: drift.append(f"{cid}: clauses.json 에 없음"); continue
        if cell(r[2]) != WANT[cid]:
            drift.append(f"{cid}: 표={cell(r[2])} 원문={WANT[cid]}")
t("강도가 원문 종결어미에서 재산출한 값과 일치 (F-081)", not drift, "; ".join(drift[:3]))

_ids = {c["id"] for c in CLAUSES}
_doc_ids = {cell(r[0]) for rs in REQ.values() for r in rs}
t("clauses.json 과 대조표의 조항 집합이 같다", _ids == _doc_ids,
  str(sorted(_ids ^ _doc_ids)))

# ── F-080: 요구 문구가 원문 핵심 명사구를 유지하는가 ───────────
#    6.1-1 과 6.2-1 을 서로 바꾸는 식의 교환을 잡는다. 핵심 명사구의
#    어절 중 절반 이상이 요구사항 열에 남아 있어야 한다.
#    대조표의 요구사항 열은 원문의 축약이므로 문자열 일치를 요구할 수 없다.
#    대신 "이 행이 자기 조항에 가장 가까운가" 를 본다 - 두 행을 맞바꾸면
#    최선 매칭이 상대 조항으로 넘어가 즉시 드러난다. 유지보수 조항 5건처럼
#    문구가 같은 경우는 동점이 되므로 argmax 집합에 포함되면 통과다.
def _bg(x: str) -> set[str]:
    x = re.sub(r"[^0-9A-Za-z가-힣]", "", x)
    return {x[i:i+2] for i in range(len(x) - 1)}
def sim(a: str, b: str) -> float:
    A, B = _bg(a), _bg(b)
    return len(A & B) / len(A | B) if A | B else 1.0

swap = []
for rs in REQ.values():
    for r in rs:
        cid, text = cell(r[0]), cell(r[1])
        scores = {c["id"]: sim(c["key"], text) for c in CLAUSES}
        best = max(scores.values())
        # 여유 0.10 - 유지보수 조항 5건처럼 원문이 거의 같은 경우를 허용한다.
        # 실제 교환은 0.5 이상 벌어지므로 이 여유로 놓치지 않는다.
        if scores.get(cid, -1) < best - 0.10:
            top = max(scores, key=lambda k: scores[k])
            swap.append(f"{cid}: 최선매칭={top} ({scores[top]:.2f} > {scores.get(cid,0):.2f})")
t("각 행이 자기 조항에 가장 가깝다 (F-080 문구 교환)", not swap, "; ".join(swap[:2]))

VERDICTS = {"✅", "⚠", "❌"}
badv = sorted({cell(r[3])[0] for rs in REQ.values() for r in rs if cell(r[3])} - VERDICTS)
t("판정 표기가 규약 3종을 벗어나지 않는다", not badv, str(badv))

# ═══════════════════════════════════════════════════════════════
#  3. 집계표 ↔ 실제 행
# ═══════════════════════════════════════════════════════════════
def tally() -> dict[tuple[str, str], int]:
    d: dict[tuple[str, str], int] = {}
    for rs in REQ.values():
        for r in rs:
            k = (cell(r[3])[0], cell(r[2]))
            d[k] = d.get(k, 0) + 1
    return d
T = tally()

SUM = rows("| 판정 \\ 강도 | 필수 | 필수(능력) | 선택 | 계 |", 5)
mismatch = []
for row in SUM:
    v = cell(row[0])
    if v.startswith("계"): continue
    mark = v[0]
    for col, lvl in enumerate(("필수", "필수(능력)", "선택"), start=1):
        stated = int(re.sub(r"\D", "", row[col]) or 0)
        real = T.get((mark, lvl), 0)
        if stated != real: mismatch.append(f"{v[1:].strip() or v}/{lvl}: 표기={stated} 실제={real}")
    stated_tot = int(re.sub(r"\D", "", row[4]) or 0)
    real_tot = sum(T.get((mark, l), 0) for l in ("필수", "필수(능력)", "선택"))
    if stated_tot != real_tot: mismatch.append(f"{v[1:].strip() or v} 계: {stated_tot} != {real_tot}")
t("1.7 집계표가 실제 행 집계와 일치", not mismatch, "; ".join(mismatch[:3]))

_last = next((r for r in SUM if cell(r[0]).startswith("계")), None)
if _last:
    cols = [int(re.sub(r"\D", "", _last[i]) or 0) for i in range(1, 5)]
    lvl_real = [sum(T.get((v, l), 0) for v in VERDICTS)
                for l in ("필수", "필수(능력)", "선택")]
    t("1.7 강도별 열 합계가 실제와 일치 · 총계 33",
      cols[:3] == lvl_real and cols[3] == total, f"표기={cols} 실제={lvl_real + [total]}")
else:
    t("1.7 강도별 열 합계가 실제와 일치 · 총계 33", False, "계 행 없음")

# ═══════════════════════════════════════════════════════════════
#  4. 1.8 판정 내역 — 나열된 조항이 실제 판정과 일치하는가
# ═══════════════════════════════════════════════════════════════
DETAIL = rows("| 판정 | 건수 | 해당 |", 3)
real_by_verdict: dict[str, set[str]] = {v: set() for v in VERDICTS}
for rs in REQ.values():
    for r in rs:
        real_by_verdict[cell(r[3])[0]].add(cell(r[0]))

bad = []
for r in DETAIL:
    v = cell(r[0])
    if v.startswith("합계"): continue
    mark = v[0]
    stated_n = int(re.sub(r"\D", "", r[1]) or 0)
    # 구분자가 절 사이는 '/' 또는 '·', 절 안은 '·' 다. 토큰 단위로 뜯는다.
    listed = set()
    for mm in re.finditer(r"(\d\.\d)-([\d·]+)", cell(r[2])):
        listed |= {f"{mm.group(1)}-{x}" for x in mm.group(2).split("·") if x}
    if stated_n != len(real_by_verdict[mark]):
        bad.append(f"{v[1:].strip() or v}: 건수 {stated_n} != {len(real_by_verdict[mark])}")
    if listed != real_by_verdict[mark]:
        d1 = sorted(real_by_verdict[mark] - listed); d2 = sorted(listed - real_by_verdict[mark])
        bad.append(f"{v[1:].strip() or v}: 누락={d1} 잉여={d2}")
t("1.8 판정 내역이 실제 판정과 정확히 일치", not bad, "; ".join(bad[:2]))

# ═══════════════════════════════════════════════════════════════
#  5. 부정 판정에는 사유가 있어야 한다
# ═══════════════════════════════════════════════════════════════
noreason = []
for rs in REQ.values():
    for r in rs:
        if cell(r[3])[0] in ("⚠", "❌") and len(cell(r[4])) < 10:
            noreason.append(cell(r[0]))
t("부분·범위외 판정에 전부 사유가 적혀 있다", not noreason, str(noreason))

t("범위 외 결정이 별도 절에서 근거와 함께 선언됨",
  all(k in DOC for k in ("## 2. 구현 범위 선언", "### 2.1", "### 2.2", "### 2.3")))

# ═══════════════════════════════════════════════════════════════
#  6. 부속서 A — 시나리오 4종
# ═══════════════════════════════════════════════════════════════
A1 = rows("| # | 세부 요구사항 | 판정 | 구현 |", 4, scope="### 3.1 A.1")
A2 = rows("| # | 세부 요구사항 | 판정 | 구현 |", 4, scope="### 3.2 A.2")
A3 = rows("| # | 세부 요구사항 | 강도 | 판정 | 구현 |", 5, scope="### 3.3 A.3")
A4 = rows("| # | 세부 요구사항 | 강도 |", 3, scope="### 3.4 A.4")
ann = {"A.1": A1, "A.2": A2, "A.3": A3, "A.4": A4}
acount = {k: len(v) for k, v in ann.items()}
atotal = sum(acount.values())
t(f"부속서 A 표 4종 파싱 · 합계 {atotal}건", atotal == 31 and all(acount.values()), str(acount))

m = re.search(r"## 3\. 부속서 A 시나리오 대조 — (\d+)건", DOC)
t("부속서 A 제목의 총계가 실제와 일치", m is not None and int(m.group(1)) == atotal,
  f"제목={m.group(1) if m else None} 실제={atotal}")

ASUM = rows("| 시나리오 | 요구 수 | ✅ | ⚠ | ❌ | 대상 |", 6)
bad = []
for r in ASUM:
    key = cell(r[0]).split()[0]
    if key.startswith("합계") or key.startswith("**"): continue
    n, ok, part, out = (int(re.sub(r"\D", "", r[i]) or 0) for i in range(1, 5))
    if key not in ann: bad.append(f"{key}: 표 없음"); continue
    if n != len(ann[key]): bad.append(f"{key}: 요구 수 {n} != {len(ann[key])}")
    if ok + part + out != n: bad.append(f"{key}: {ok}+{part}+{out} != {n}")
    # A.4 는 강도만 나열(판정 열 없음) — 전량 범위 외로 선언되어야 한다
    if key == "A.4" and out != n: bad.append("A.4: 전량 범위 외가 아니다")
    if key != "A.4":
        vi = 2 if key != "A.3" else 3
        real = [0, 0, 0]
        for rr in ann[key]:
            mark = cell(rr[vi])[0]
            real[["✅", "⚠", "❌"].index(mark)] += 1
        if [ok, part, out] != real: bad.append(f"{key}: 표기={[ok,part,out]} 실제={real}")
t("3.5 부속서 A 집계가 각 표와 일치", not bad, "; ".join(bad[:3]))

t("부속서 A 누적 구조를 명시 (A.1 ⊂ A.2 ⊂ A.3 ⊂ A.4)",
  "⊂" in DOC and "누적 구조" in DOC)

# ═══════════════════════════════════════════════════════════════
#  7. 모듈 배정 — 6.1~6.5 를 빠짐없이 덮는가
# ═══════════════════════════════════════════════════════════════
MOD = rows("| 모듈 | 담당 조항 | 진입점 |", 3)
SVC = [r for r in MOD if cell(r[0]).endswith(".py") and "밖" not in cell(r[0])]
t("services/ 모듈 5종 + 경계 밖 담당 명시",
  len(SVC) == 5 and len(MOD) == 6,
  " ".join(re.sub(r"[^0-9A-Za-z가-힣./ ]", "", cell(r[0])) for r in MOD))

assigned: set[str] = set()
for r in MOD:
    txt = cell(r[1])
    for mm in re.finditer(r"(6\.\d)\s*(전부|[-\d·]+)", txt):
        sec, what = mm.group(1), mm.group(2)
        if what == "전부":
            assigned |= {cell(x[0]) for x in REQ.get(sec, [])}
        else:
            assigned |= {f"{sec}-{x}" for x in re.findall(r"\d+", what)}
need = {cell(r[0]) for k in ("6.1", "6.2", "6.3", "6.4", "6.5") for r in REQ[k]}
# 범위 외로 선언한 것은 담당이 없어도 된다
outof = {cell(r[0]) for rs in REQ.values() for r in rs if cell(r[3])[0] == "❌"}
t("모듈 배정이 6.1~6.5 의 구현 대상 조항을 전부 덮는다",
  (need - outof) <= assigned, str(sorted((need - outof) - assigned)))

# ── F-079 회귀 ① 실제 아키텍처 디스패치를 읽는다 (F-080) ──────
#    초안은 대조표 §4.1 만 다시 읽었다. 그러면 아키텍처를 되돌려도 통과한다.
t("아키텍처_설계서.md 를 찾았다", bool(ARCH), str(ARCH_P.name) if ARCH_P else "없음")
_h = ARCH.split("def handle(", 1)[-1].split("\n```", 1)[0] if "def handle(" in ARCH else ""
t("아키텍처 handle() 본문을 읽었다", len(_h) > 200, f"{len(_h)}자")
_bad_dms = re.findall(r"dms\.on_(?:node|device)_\w+", _h)
t("아키텍처 handle() 에 dms.on_*_property 가 없다 (F-079 회귀)",
  not _bad_dms, str(_bad_dms))
_need_ingest = ("REQ_SET_DEVICE_PROPERTY", "REQ_SET_NODE_DEVICE_PROPERTY_ALL",
                "_handle_device_property")
_miss_ingest = [x for x in _need_ingest if x not in _h]
t("아키텍처 handle() 이 속성 설정 2종을 실제 ingest 등록 함수에 배정 (F-079·F-229)",
  not _miss_ingest, str(_miss_ingest))

# ── F-079 회귀 ② 대조표 배정 ─────────────────────────────────
dms_row = next((r for r in MOD if cell(r[0]).startswith("dms")), None)
t("dms 담당 조항이 6.2 뿐 (F-079 회귀)",
  dms_row is not None and set(re.findall(r"6\.\d", cell(dms_row[1]))) == {"6.2"},
  cell(dms_row[1]) if dms_row else "dms 행 없음")
t("dms 진입점에 노드·디바이스 속성 함수가 없다 (F-079 회귀)",
  dms_row is not None
  and not re.search(r"on_(node|device)_(property|device_all)", cell(dms_row[2])),
  cell(dms_row[2]) if dms_row else "")
ems_row = next((r for r in MOD if cell(r[0]).startswith("ems")), None)
t("EMS 행이 실제 link·ingest·ems 경계를 함께 배정 (0937 6.1, F-079·F-229)",
  ems_row is not None and all(k in cell(ems_row[2]) for k in
      ("link.SiapNodeLink._apply_registry_effects",
       "ingest._handle_device_property", "ems.set_device_property")),
  cell(ems_row[2])[:60] if ems_row else "")
t("F-079 를 문서에 근거와 함께 기록",
  "F-079" in DOC and "### 4.2" in DOC)

# ═══════════════════════════════════════════════════════════════
#  7-a. 근거 심벌이 실제로 존재하는가 (F-082)
#       "테이블이 있으니 충족" 을 막는다. 컬럼·경로·진입점을 실물에서 찾는다.
# ═══════════════════════════════════════════════════════════════
TABLES = set(re.findall(r"CREATE TABLE (\w+)", SQL))
COLS: dict[str, set[str]] = {}
for m in re.finditer(r"CREATE TABLE (\w+)\s*\((.*?)\n\);", SQL, re.S):
    body = re.sub(r"--[^\n]*", "", m.group(2))
    COLS[m.group(1)] = {mm.group(1) for mm in
                        re.finditer(r"^\s{4}(\w+)\s+[A-Z]", body, re.M)}
PATHS = set(API.get("paths", {}))
t("실제 Python 구현 소스 7종 AST 적재 (F-229)",
  all(SOURCE_PATHS.values()) and bool(ACTUAL_SYMBOLS),
  " ".join(f"{m}={p.name if p else '없음'}" for m, p in SOURCE_PATHS.items()))

DOC_ENTRY_REFS = {
    sym for r in MOD
    for sym in re.findall(r"([a-z_][a-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,2})\(\)",
                          cell(r[2]))
}
missing_doc_entry = sorted(DOC_ENTRY_REFS - ACTUAL_SYMBOLS)
t("§4.1 진입점이 실제 Python 함수·메서드에 전부 실재 (F-229)",
  bool(DOC_ENTRY_REFS) and not missing_doc_entry,
  str(missing_doc_entry))

t(f"schema.sql · openapi.json 적재 (테이블 {len(TABLES)} · 경로 {len(PATHS)})",
  len(TABLES) >= 30 and len(PATHS) >= 15)

def check_evidence(text: str) -> list[str]:
    """근거 문자열에서 검사 가능한 심벌만 골라 실재를 확인한다."""
    out = []
    for tok in re.findall(r"`([^`]+)`", text):
        tok = tok.strip()
        # 1) API 경로
        if tok.startswith("/api/") or re.match(r"^(GET|POST|PATCH|DELETE)\s+/api/", tok):
            path = tok.split()[-1]
            if path not in PATHS: out.append(f"경로 {path}")
        # 2) Python 진입점. 문서 표가 아니라 실제 소스 AST와 대조한다(F-229).
        elif re.fullmatch(r"[a-z_][a-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,2}\(\)", tok):
            if tok[:-2] not in ACTUAL_SYMBOLS: out.append(f"진입점 {tok}")
        # 3) 테이블.컬럼
        elif re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", tok):
            tbl, col = tok.split(".", 1)
            if tbl in COLS and col not in COLS[tbl]: out.append(f"컬럼 {tok}")
        # 4) 단독 테이블명
        elif re.fullmatch(r"[a-z][a-z0-9_]{4,}", tok) and tok.endswith(("_info","_data","_log","_rule","_execution","_model","_record","_source")):
            if tok not in TABLES: out.append(f"테이블 {tok}")
    return out

ghost = []
for rs in REQ.values():
    for r in rs:
        if cell(r[3])[0] != "✅": continue
        for g in check_evidence(r[4]): ghost.append(f"{cell(r[0])}: {g}")
t("충족 행의 근거 심벌이 schema.sql·openapi.json·진입점표에 실재 (F-082)",
  not ghost, "; ".join(ghost[:3]))

# ⚠ 행도 인용한 심벌은 실재해야 한다 (사유 서술은 자유롭되 심벌은 사실이어야)
ghost2 = []
for rs in REQ.values():
    for r in rs:
        if cell(r[3])[0] != "⚠": continue
        for g in check_evidence(r[4]):
            ghost2.append(f"{cell(r[0])}: {g}")
t("부분 행이 인용한 심벌도 실재 (F-082)", not ghost2, "; ".join(ghost2[:3]))

# ── 신규 계약 2종이 배정표에도 등재되었는가 ────────────────────
t("4.4 신규 계약 2종이 실제 구현과 4.1 진입점에 모두 실재 (F-082·F-229)",
  {"mms.run_model", "fms.check_stale_devices"} <= ACTUAL_SYMBOLS
  and {"mms.run_model", "fms.check_stale_devices"} <= DOC_ENTRY_REFS,
  f"실제={sorted({'mms.run_model','fms.check_stale_devices'} & ACTUAL_SYMBOLS)}")
t("4.4 절이 두 계약의 시그니처·근거를 적었다",
  "### 4.4" in DOC and "mms.run_model" in DOC and "fms.check_stale_devices" in DOC)

# ── ⚠ 행이 후속 과제와 연결되는가 ─────────────────────────────
FOLLOW = rows("| # | 대상 조항 | 필요한 것 | 파급 | 우선순위 |", 5)
covered = set()
for r in FOLLOW:
    covered |= {x for x in re.findall(r"\d\.\d-\d+", cell(r[1]))}
part_ids = {cell(r[0]) for rs in REQ.values() for r in rs if cell(r[3])[0] == "⚠"}
t("부분 판정이 전부 5절 후속 과제에 연결됨",
  part_ids <= covered, str(sorted(part_ids - covered)))

# ── F-095: 산문 절(§4.5 · §5)의 수치가 본문 집계·실측과 맞는가 ─
#    §1.7·§3.5 의 표는 재산출하면서 그 표를 요약한 산문은 검사하지 않았다.
#    F-094 는 전부 산문에서 나왔다 — `⚠ 7건` · `쓰기 4건` · `76종` · `A.1-5 종결`.
_hist = ("당시", "이전", "한때", "F-094")
_part6 = len(part_ids)                      # 6장 요구사항의 부분 판정
_partA = sum(int(re.sub(r"\D", "", r[3]) or 0) for r in ASUM
             if not cell(r[0]).startswith(("합계", "**")))   # 부속서 A 의 부분 판정
_m45 = re.search(r"### 4\.5 후속 과제로 남긴 것(.*?)(?=\n## )", DOC, re.S)
_txt45 = _m45.group(1) if _m45 else ""
_n45 = [(int(n), ln) for ln in _txt45.splitlines()
        for n in re.findall(r"`?\u26a0`?\s*(\d+)\s*건", ln)
        if not any(h in ln for h in _hist)]
t("4.5 절이 인용한 부분 판정 건수가 집계표와 일치 (F-094 · F-095)",
  all(n in (_part6, _partA) for n, _ in _n45),
  f"4.5 인용={[n for n,_ in _n45]} / 6장={_part6} 부속서A={_partA}")

# 현재 수치 주장은 실측과 맞아야 한다. 과거 값은 '당시'·'이전'·'한때' 로 표시한다.
WRITE_N = sum(1 for item in API.get("paths", {}).values() for m in item
              if m in ("post", "put", "patch", "delete"))
# DB 제약 테스트 건수는 db/verify.py 의 check(...) 호출을 세어 얻는다.
# 문서가 적은 숫자를 믿지 않는다 (F-090 · F-095).
#   소스의 check( 호출 수를 세면 루프·헬퍼 안의 호출을 놓친다. 실제로 돌려 결과를 읽는다.
_dbv = find("verify.py", must="표준 유래 제약")
DB_CHECKS = -1
if _dbv:
    import subprocess
    _r = subprocess.run([sys.executable, str(_dbv)], capture_output=True)
    _mm = re.search(r"(\d+)/(\d+)", _r.stdout.decode("utf-8", "replace").splitlines()[-1])
    if _mm and _mm.group(1) == _mm.group(2): DB_CHECKS = int(_mm.group(2))
t("db/verify.py 를 실행해 제약 테스트 건수를 재산출 (F-095)", DB_CHECKS > 80, f"{DB_CHECKS}종 전량 통과")
def _prose_claims(pattern, actual, label):
    bad = []
    for ln in DOC.splitlines():
        for hit in re.finditer(pattern, ln):
            if int(hit.group(1)) != actual and not any(h in ln for h in _hist):
                bad.append(f"{label}={hit.group(1)}: {ln.strip()[:44]}")
    t(f"산문의 '{label}' 주장이 실측({actual})과 일치하거나 시점이 붙어 있다 (F-095)",
      not bad, "; ".join(bad[:2]))
_prose_claims(r"API 쓰기\s*(\d+)\s*건", WRITE_N, "API 쓰기")
_prose_claims(r"제약 테스트\s*\*?\*?(\d+)\s*종", DB_CHECKS, "DB 제약 테스트")

# A.1-5 를 '닫혔다'고 적으면서 판정은 부분으로 두는 자기모순을 막는다
_a15 = [l for l in DOC.splitlines() if l.startswith("| A.1-5 |")]
_a15_part = bool(_a15) and cell(_a15[0].split("|")[3])[0] == "\u26a0"
_claim_closed = re.search(r"A\.1-3 . A\.1-5 세 건이 사라졌다", DOC) is not None
t("A.1-5 를 부분으로 두면서 종결됐다고 적지 않는다 (F-087 회귀)",
  not (_a15_part and _claim_closed),
  f"A.1-5 부분={_a15_part} / 종결 문장={_claim_closed}")

# ═══════════════════════════════════════════════════════════════
#  8. 계층 규칙 재확인 · 금지 패턴
# ═══════════════════════════════════════════════════════════════
LAYER = rows("| 규칙 | 근거 |", 2, scope="### 4.3 계층 규칙")
t("계층 규칙 4종을 재확인 표로 명시", len(LAYER) == 4, f"{len(LAYER)}행")

SECRET  = re.compile(r"api[_-]?key|password|passwd|@author", re.I)
PRIVATE = re.compile(r"[A-Za-z]:\\Users\\|/home/[a-z]+/|/Users/[a-z]+/", re.I)
SYNTH   = re.compile(r"random\.(uniform|randint|gauss)\(|np\.random\.")
hits = [f"{i}: {l.strip()[:44]}" for i, l in enumerate(DOC.splitlines(), 1)
        if SECRET.search(l) or PRIVATE.search(l) or SYNTH.search(l)]
t("대조표에 비밀정보·개인경로·합성데이터 패턴 없음 (CLAUDE.md 1)", not hits, str(hits[:2]))

# 조항 인용 밀도 — 표준 활용성의 근거 문서다
clauses = set(re.findall(r"\b6\.\d(?:-\d+)?\b", DOC)) | set(re.findall(r"표 7-\d+", DOC))
t(f"표준 조항 인용 {len(clauses)}종", len(clauses) >= 30, " ".join(sorted(clauses)[:6]) + " ...")

# ═══════════════════════════════════════════════════════════════
#  9. --with-source : 발췌본을 표준 원문과 대조한다 (개발자 전용)
#     원문은 심사자 PC 에 없다. 기본 실행에서는 건너뛰고, 개발자가
#     발췌본이 정본에서 파생되었음을 확인할 때만 쓴다.
# ═══════════════════════════════════════════════════════════════
if "--with-source" in sys.argv:
    i = sys.argv.index("--with-source")
    src_p = Path(sys.argv[i + 1]) if i + 1 < len(sys.argv) else None
    if src_p is None or not src_p.exists():
        t("--with-source 경로가 유효하다", False, str(src_p))
    else:
        raw = src_p.read_text(encoding="utf-8", errors="replace")
        body = raw.split("## 6   클라우드 기반 스마트팜 서비스 요구사항", 1)[-1]
        body = body.split("## 부 속 서 A", 1)[0]
        # 원문 md 는 PDF 추출물이라 한 문장이 목록 기호·쉼표와 함께 줄바꿈으로
        # 쪼개져 있다("지원할 수 있\n- , / 다."). 공백만 지우면 붙지 않으므로
        # 목록 기호와 흩어진 구두점도 함께 제거한 뒤 포함 여부를 본다.
        flat = re.sub(r"[\s\-,/·]+", "", body)
        miss_end = [c["id"] for c in CLAUSES
                    if re.sub(r"\s+", "", c["ending"]) not in flat]
        t(f"발췌 종결어미 {len(CLAUSES)}건이 원문 6장에 존재", not miss_end, str(miss_end[:4]))
        # 핵심 명사구의 어절이 원문에 남아 있는가 (원문 OCR 의 공백 깨짐을 흡수)
        weak = []
        for c in CLAUSES:
            ws = [w for w in re.split(r"\s+", c["key"]) if len(w) >= 2]
            hit = sum(1 for w in ws if re.sub(r"[\s\-,/·]+", "", w) in flat)
            if ws and hit * 2 < len(ws): weak.append(f"{c['id']}({hit}/{len(ws)})")
        t("발췌 핵심 명사구가 원문 6장에 남아 있다", not weak, "; ".join(weak[:3]))

# ═══════════════════════════════════════════════════════════════
w = max(len(n) for _, n, _ in R)
print("0937 요구사항 대조표 검증  (집계 / 커버리지 / 모듈 배정)\n")
for ok, n, note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
p = sum(1 for o, *_ in R if o)
print(f"\n  {p}/{len(R)} 통과")
sys.exit(0 if p == len(R) else 1)
