"""web/ 화면 설계서 검증 — 화면↔API↔골든 벡터를 대조한다

CLAUDE.md 6.2 — 검증기는 검증 대상 파일 하나만 읽지 않는다(F-080). 독립 입력 셋을 본다.

  1) openapi.json      — 화면이 쓴다고 적은 오퍼레이션이 실재하는가
  2) golden.jsonl      — 주입 8종이 X01~X08 과 1:1 이고 기대 출력이 실측과 같은가
  3) 시연_시나리오.md  — 영상 컷의 화면 배정과 일치하는가

구현 후에는 web/*.html 을 파싱해 접근성 8항목과 금지 패턴을 실물로 검사한다.
지금은 설계서의 선언만 검사하며, 실물 검사는 파일이 생기면 자동으로 켜진다.

실행:  python project_docs/web/web_verify.py
종료코드: 0 = 전부 일치, 1 = 불일치 있음
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS_DIR = HERE.parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
from web_source_checks import (
    approved_has_execute_path,
    bit_unpack_sources,
    external_css_references,
    extract_inline_scripts,
    numeric_korean_map_sources,
    pending_execute_paths,
    recovery_cursor_issues,
    recovery_pagination_issues,
    status_cue_issues,
)

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

DOC = (HERE / "화면_설계서.md").read_text(encoding="utf-8")

API_P  = find("openapi.json", must="openapi")
GOLD_P = find("golden.jsonl")
DEMO_P = find("시연_시나리오.md")
APIVF_P = find("api_verify.py", must="WRITE_ALLOWED")
API  = json.loads(API_P.read_text(encoding="utf-8")) if API_P else {"paths": {}}
GOLD = [json.loads(l) for l in GOLD_P.read_text(encoding="utf-8").splitlines() if l.strip()] if GOLD_P else []
DEMO = DEMO_P.read_text(encoding="utf-8") if DEMO_P else ""
APIVF = APIVF_P.read_text(encoding="utf-8") if APIVF_P else ""

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

t("독립 입력 3종 적재 (openapi · golden · 시연)",
  bool(API.get("paths")) and len(GOLD) == 53 and bool(DEMO),  # F-120: B11 추가로 52 -> 53
  f"경로 {len(API.get('paths', {}))} · 벡터 {len(GOLD)} · 시연 {len(DEMO)}자")

OPS: dict[str, tuple[str, str]] = {}          # operationId -> (METHOD, path)
for p, ms in API.get("paths", {}).items():
    for m, o in ms.items():
        if m in ("get", "post", "put", "patch", "delete"):
            OPS[o["operationId"]] = (m.upper(), p)

# ═══════════════════════════════════════════════════════════════
#  1. 화면 4종 — 담당 조항 · 배점 · 영상 컷
# ═══════════════════════════════════════════════════════════════
SCREENS = rows("| 화면 | 기능 | 담당 조항 | 배점 항목 | 영상 |", 5)
names = [cell(r[0]) for r in SCREENS]
t(f"화면 4종 선언 ({names})", len(SCREENS) == 4
  and set(names) == {"index.html", "verify.html", "rules.html", "settings.html"})

nocl = [cell(r[0]) for r in SCREENS if not re.search(r"(0937|0943|1369)", r[2])]
t("모든 화면이 담당 표준 조항을 갖는다", not nocl, str(nocl))
nosc = [cell(r[0]) for r in SCREENS if not re.search(r"\d+", r[3])]
t("모든 화면이 배점 항목을 갖는다", not nosc, str(nosc))

# ── 시연 시나리오의 컷 배정과 일치하는가 ──────────────────────
cut_of = {cell(r[0]): re.findall(r"S\d", r[4]) for r in SCREENS}
bad = []
for scr, cuts in cut_of.items():
    for c in cuts:
        if c not in DEMO: bad.append(f"{scr}:{c}")
t("설계서가 지목한 영상 컷이 시연 시나리오에 존재", not bad, str(bad))
t("verify.html 이 S4 를 담당한다 (배점 최대 항목)",
  "S4" in cut_of.get("verify.html", []) and "30" in SCREENS[1][3],
  str(cut_of.get("verify.html")))
t("settings.html 은 영상에 넣지 않는다 (117초 결정 유지)",
  not cut_of.get("settings.html") and "영상에 넣지 않는다" in DOC)

# ═══════════════════════════════════════════════════════════════
#  2. 화면 ↔ API 대응이 openapi.json 과 맞는가
# ═══════════════════════════════════════════════════════════════
MAP = rows("| 화면 | 읽기 | 쓰기 |", 3)
t("화면-API 대응표 4행", len(MAP) == 4, str([cell(r[0]) for r in MAP]))

used_read: dict[str, set[str]] = {}
used_write: dict[str, set[str]] = {}
for r in MAP:
    scr = cell(r[0])
    used_read[scr]  = set(re.findall(r"`(\w+)`", r[1]))
    used_write[scr] = set(re.findall(r"`(\w+)`", r[2]))

ghost = sorted({o for s in list(used_read.values()) + list(used_write.values())
                for o in s} - set(OPS))
t("화면이 참조한 operationId 가 전부 openapi.json 에 실재", not ghost, str(ghost))

wrong = []
for scr, ops in used_write.items():
    for o in ops:
        if o in OPS and OPS[o][0] == "GET": wrong.append(f"{scr}:{o}")
for scr, ops in used_read.items():
    for o in ops:
        if o in OPS and OPS[o][0] != "GET": wrong.append(f"{scr}:{o}(읽기칸)")
t("읽기·쓰기 칸의 메서드가 openapi.json 과 일치", not wrong, str(wrong))

# F-084 — verify.html 은 "읽기 전용" 이 아니라 "운영 상태를 바꾸지 않는다" 이다.
#         주입은 수신 경로에 바이트를 넣을 뿐이므로 허용하되, 그것 하나로 제한한다.
OBSERVE_EXEMPT = {"verify.html": {"injectVector"}}
bad_w = []
for scr in ("index.html", "verify.html"):
    extra = used_write.get(scr, set()) - OBSERVE_EXEMPT.get(scr, set())
    if extra: bad_w.append(f"{scr}:{sorted(extra)}")
t("관측 화면(1·2)이 운영 상태를 바꾸지 않는다 (주입만 예외)",
  not bad_w, "; ".join(bad_w))
t("주입 예외의 근거가 설계서에 있다 (F-084)",
  "운영 상태를 바꾸지 않는다" in DOC and "5.3-a" in DOC and "409" in DOC)

# ── api_verify.py 의 WRITE_ALLOWED 와 정확히 일치하는가 ────────
allowed = {(m, p) for m, p in re.findall(r'\("(GET|POST|PATCH|PUT|DELETE)",\s*"([^"]+)"\)', APIVF)}
screen_writes = {OPS[o] for s in used_write.values() for o in s if o in OPS}
t("화면의 쓰기 경로가 api_verify.py 의 WRITE_ALLOWED 와 일치",
  bool(allowed) and screen_writes == allowed,
  f"화면밖 {sorted(screen_writes - allowed)} 미사용 {sorted(allowed - screen_writes)}")

# ═══════════════════════════════════════════════════════════════
#  3. 주입 8종 ↔ 골든 X01~X08
# ═══════════════════════════════════════════════════════════════
INJ = rows("| # | 라벨 | 골든 | 기대 출력 |", 4)
ids = [cell(r[2]) for r in INJ]
xs = sorted([v for v in GOLD if v["category"] == "위반"], key=lambda v: v["id"])
t("주입 8종이 골든 X01~X08 과 1:1", ids == [v["id"] for v in xs], str(ids))

bad = []
for r in INJ:
    xid = cell(r[2])
    v = next((v for v in xs if v["id"] == xid), None)
    if v is None: bad.append(f"{xid}: 벡터 없음"); continue
    c = v["violations"][0] if v["violations"] else v.get("nec_alert")
    if not c: bad.append(f"{xid}: 판정 없음"); continue
    if c["code_name"] not in r[3]: bad.append(f"{xid}: {c['code_name']} 없음")
    if c["clause"] not in r[3]:    bad.append(f"{xid}: 조항 {c['clause']} 없음")
t("주입표의 기대 출력이 골든 실측(코드명·조항)과 일치", not bad, "; ".join(bad[:3]))

x08 = next((r for r in INJ if cell(r[2]) == "X08"), None)
t("X08 이 위반이 아니라 알림으로 선언됨 (F-060)",
  x08 is not None and "위반 아님" in x08[3] and "알림" in x08[3],
  re.sub(r"[^0-9A-Za-z가-힣.· ]", " ", cell(x08[3]))[-26:] if x08 else "")
t("화면이 판정 3종(violation/alert/normal)을 구분해 표기",
  all(k in DOC for k in ("위반", "알림", "정상")) and "다른 색·다른 아이콘" in DOC)
t("주입 바이트를 화면이 만들지 않는다 (골든에서 온다)",
  "golden.jsonl" in DOC and "진위" in DOC)

# ═══════════════════════════════════════════════════════════════
#  4. 접근성 계약
# ═══════════════════════════════════════════════════════════════
A11Y = rows("| # | 항목 | WCAG | 검사 방법 |", 4)
t("접근성 8항목이 검사 방법과 함께 선언됨",
  len(A11Y) == 8 and all(len(cell(r[3])) >= 4 for r in A11Y), f"{len(A11Y)}항목")
wc = [cell(r[2]) for r in A11Y]
t("각 항목이 WCAG 성공기준 번호를 인용",
  all(re.fullmatch(r"\d\.\d\.\d", x) for x in wc), str(wc))

COLOR = rows("| 의미 | 색 | 함께 주는 것 |", 3)
t("색 의존 금지표가 상태 6종을 덮는다", len(COLOR) == 6, f"{len(COLOR)}종")
nocolor = [cell(r[0]) for r in COLOR if len(cell(r[2])) < 3]
t("모든 상태가 색 외 표기를 함께 갖는다", not nocolor, str(nocolor))
t("색 의존이 기능 2 의 성립 조건임을 근거로 적었다",
  "색각 이상" in DOC and "기능 자체가" in DOC)

KEY = rows("| 화면 | 키보드만으로 가능해야 하는 것 |", 2)
t("키보드 조작 요건이 3화면에 선언됨", len(KEY) == 3, f"{len(KEY)}행")
t("주입 8종이 키보드로 실행 가능하다고 선언",
  any("주입" in cell(r[1]) for r in KEY))

# ═══════════════════════════════════════════════════════════════
#  5. 화면이 하지 않는 것 — 계층 규칙
# ═══════════════════════════════════════════════════════════════
NOT = rows("| 금지 | 이유 | 검사 |", 3)
t("금지표 6종", len(NOT) == 6, f"{len(NOT)}종")
nocheck = [cell(r[0])[:14] for r in NOT if len(cell(r[2])) < 4]
t("모든 금지 항목이 검사 방법을 갖는다", not nocheck, str(nocheck))
t("표준 해석·Subtype 매핑·디코딩 금지가 명시됨",
  all(k in "".join(cell(r[0]) for r in NOT) for k in ("한국어 문구 매핑", "종류명 매핑", "디코딩")))
t("localStorage 금지 (재현성)", "localStorage" in DOC)

# ═══════════════════════════════════════════════════════════════
#  6. 신규 API — 승인 게이트 우회 차단
# ═══════════════════════════════════════════════════════════════
NEWP = "/api/v1/device-property"
t("신규 경로가 openapi.json 에 실재", NEWP in API.get("paths", {}))
_op = API.get("paths", {}).get(NEWP, {}).get("patch", {})
t("신규 경로가 setDeviceProperty · PATCH", _op.get("operationId") == "setDeviceProperty")
_sch = API.get("components", {}).get("schemas", {}).get("DevicePropertyPatch", {})
_props = set(_sch.get("properties", {}))
t("신규 경로가 표 7-15 사용자 지정 4필드만 받는다",
  _props == {"transfer_mode", "period_sec", "lower_value", "upper_value"}, str(sorted(_props)))
t("신규 경로에 제어값(Value) 필드가 없다 (CLAUDE.md 1-7)",
  "value" not in _props and _sch.get("additionalProperties") is False)
t("설계서가 표 7-15 8필드의 쓰기·읽기 구분을 표로 선언",  # 화면 축소로 3열→4열(화면/API 구분), 4행→5행
  len(rows("| 표 7-15 필드 | 화면 | API(`DevicePropertyPatch`) | 이유 |", 4)) == 5)
t("쓰기 경로 증가를 근거와 함께 적었다", "검증 표면" in DOC)

# ═══════════════════════════════════════════════════════════════
#  7. 빌드 없음 · 오프라인
# ═══════════════════════════════════════════════════════════════
CON = rows("| 제약 | 출처 | 결과 |", 3)
t("빌드 없음 제약 4종이 출처와 함께 선언", len(CON) == 4)
t("파일 구조에 번들러·node_modules 흔적 없음",
  not re.search(r"node_modules|webpack|vite|rollup|package\.json", DOC.split("```")[1] if "```" in DOC else ""),
  "")
t("외부 CDN 참조 금지가 금지표에 있다",
  any("CDN" in cell(r[0]) for r in NOT))

# ── 구현 후: web/*.html 실물이 있으면 자동으로 켜진다 ──────────
# F-196 — 실제 구현은 project_code/web/ 인데(CLAUDE.md §2 디렉터리 구조),
# 예전 후보 두 개(저장소 루트 web/, project_docs/web/web/)는 어느 쪽도
# 그 경로가 아니라 항상 미발견 → "설계 단계이므로 건너뛴다"로 조용히
# 빠지고, 화면 실물 검사(접근성 8항목 · 금지 패턴)가 한 번도 실행되지
# 않았다. project_code/web/ 을 첫 후보로 둔다.
WEB_DIR = None
for cand in (HERE.parent.parent / "project_code" / "web", HERE.parent.parent / "web", HERE.parent / "web"):
    if cand.is_dir() and list(cand.glob("*.html")): WEB_DIR = cand; break
if WEB_DIR:
    htmls = sorted(WEB_DIR.glob("*.html"))
    txt = {p.name: p.read_text(encoding="utf-8") for p in htmls}
    static_dir = WEB_DIR / "static"
    js_txt = {p.name: p.read_text(encoding="utf-8")
              for p in sorted(static_dir.glob("*.js"))} if static_dir.is_dir() else {}
    css_txt = {p.name: p.read_text(encoding="utf-8")
               for p in sorted(static_dir.glob("*.css"))} if static_dir.is_dir() else {}
    script_txt = {**js_txt, **extract_inline_scripts(txt)}
    t(f"web/ 실물 {len(htmls)}종 발견 - 실물 검사 수행", len(htmls) == 4, str(list(txt)))
    t("모든 페이지에 lang=ko (WCAG 3.1.1)",
      all(re.search(r'<html[^>]*lang="ko"', v) for v in txt.values()))
    t("모든 페이지에 main·nav·header 랜드마크 (1.3.1)",
      all(all(f"<{k}" in v for k in ("main", "nav", "header")) for v in txt.values()))
    t("모든 페이지에 건너뛰기 링크 (2.4.1)",
      all('class="skip"' in v for v in txt.values()))
    external_refs = [name for name, source in txt.items()
                     if re.search(r'(src|href)\s*=\s*["\']https?://', source)]
    external_refs.extend(external_css_references(css_txt))
    t("외부 리소스·CSS CDN 참조 0건 (오프라인, F-230)",
      not external_refs, str(external_refs))
    t("localStorage 사용 0건",
      not any("localStorage" in v or "sessionStorage" in v for v in txt.values()))
    js = "".join(js_txt.values())
    t("화면 코드에 RSC·NEC·Subtype 상수 없음 (CLAUDE.md 3.4 · 1-6)",
      not any(re.search(r"INVALID_(VERSION|FORMAT|NODE_ID)|ERROR_BATTERY|0x8[0-9A-F]\b", source)
              for source in script_txt.values()))
    bit_hits = bit_unpack_sources(script_txt)
    t("정적·인라인 화면 스크립트에 비트 언팩 없음 (F-231)",
      not bit_hits, str(bit_hits))
    numeric_map_hits = numeric_korean_map_sources(script_txt)
    t("화면 스크립트에 숫자 코드→한국어 매핑 객체 없음 (F-231)",
      not numeric_map_hits, str(numeric_map_hits))
    rules_html = txt.get("rules.html", "")
    pending_exec = pending_execute_paths(rules_html)
    t("미승인 카드가 헬퍼를 거쳐서도 실행 경로를 렌더하지 않음 (F-204)",
      not pending_exec, str(pending_exec))
    t("승인 카드에는 실행 경로가 존재 (F-204)",
      approved_has_execute_path(rules_html))
    status_issues = status_cue_issues(txt.get("verify.html", ""))
    t("프레임 상태가 색 외 아이콘·문자를 함께 제공 (F-232)",
      not status_issues, str(status_issues))
    recovery_issues = recovery_pagination_issues(
        js_txt.get("api.js", ""), txt.get("verify.html", ""))
    t("SSE 재연결 누락 복구가 100건 초과 페이지를 모두 소비 (F-205)",
      not recovery_issues, str(recovery_issues))
    cursor_issues = recovery_cursor_issues(
        js_txt.get("stream.js", ""), txt.get("verify.html", ""))
    t("폴링이 최초 SSE 단절의 연속 커서를 덮지 않음 (F-233)",
      not cursor_issues, str(cursor_issues))
else:
    t("web/ 실물 없음 - 설계 단계이므로 실물 검사는 건너뛴다", True, "구현 후 자동 활성")

# ═══════════════════════════════════════════════════════════════
#  7-a. F-089 — 문서가 적은 수치·심벌이 실제 입력과 맞는가
#       초안 검증기는 "operationId 가 존재하는가" 만 보고 40/40 을 냈다.
#       경로 수를 21 로 잘못 적고, 없는 파일을 로드한다고 쓰고,
#       스키마에 없는 필드명을 예시 코드에 넣어도 전부 통과했다.
# ═══════════════════════════════════════════════════════════════
N_PATH = len(API.get("paths", {}))
N_OP   = len(OPS)
N_WR   = sum(1 for m, _ in OPS.values() if m != "GET")
m = re.search(r"경로\s*(\d+)\s*·\s*오퍼레이션\s*(\d+)\s*·\s*쓰기\s*(\d+)", DOC)
t("설계서의 경로·오퍼레이션·쓰기 수가 openapi.json 실측과 일치 (F-089)",
  m is not None and [int(x) for x in m.groups()] == [N_PATH, N_OP, N_WR],
  f"실측 {N_PATH}/{N_OP}/{N_WR} 문서 {m.groups() if m else None}")

# ── 파일 구조에 없는 파일을 로드한다고 적지 않았는가 ──────────
_tree = DOC.split("```", 2)[1] if DOC.count("```") >= 2 else ""
_files = set(re.findall(r"([\w.]+\.(?:js|css|html))", _tree))
_loaded = set(re.findall(r'src="static/([\w.]+\.js)"', DOC))
t("설계서가 로드한다고 적은 스크립트가 파일 구조에 실재 (F-089)",
  _loaded <= _files, f"없는 파일 {sorted(_loaded - _files)}")
t("파일 구조를 파싱했다", len(_files) >= 8, str(sorted(_files)))

# ── 예시 코드가 참조한 응답 필드가 스키마에 실재하는가 ────────
SCH = API.get("components", {}).get("schemas", {})
FIELDS = {n: set(v.get("properties", {})) for n, v in SCH.items()}
VARS = {"dev": "Device", "frame": "Frame", "rule": "Rule", "alert": "Alert"}
ghostf = []
for var, sch in VARS.items():
    for f in re.findall(rf"\b{var}\.(\w+)", DOC):
        if sch in FIELDS and f not in FIELDS[sch]: ghostf.append(f"{var}.{f}")
t("예시 코드가 참조한 응답 필드가 스키마에 실재 (F-089)",
  not ghostf, str(sorted(set(ghostf))))

# ── 화면이 선언한 동작에 호출 가능한 오퍼레이션이 있는가 ──────
NEED_OP = [
    ("기능 2 주입 버튼",        "injectVector",     "5.3-a"),
    ("기능 3 초안 생성",        "createRuleDraft",  "6.1-a"),
    ("기능 3 승인",             "approveRule",      "6.2"),
    ("기능 3 거부",             "rejectRule",       "6.2"),
    ("기능 3 실행",             "executeRule",      "6.1"),
    ("설정 적용",               "setDeviceProperty","7.2"),
]
miss_op = [f"{n}({o})" for n, o, _ in NEED_OP if o not in OPS]
t("화면이 선언한 동작 6종에 호출 가능한 오퍼레이션이 있다 (F-089)",
  not miss_op, str(miss_op))
unused = [f"{n}({o})" for n, o, _ in NEED_OP
          if not any(o in v for v in list(used_write.values()) + list(used_read.values()))]
t("그 오퍼레이션이 화면-API 대응표에도 적혀 있다", not unused, str(unused))

# ── 검증 뷰가 필요로 하는 응답 필드가 계약에 있는가 (F-085) ───
_fr = FIELDS.get("Frame", set())
t("Frame 계약에 fields·judgement 가 있다 (검증 뷰 성립 조건, F-085)",
  {"fields", "judgement"} <= _fr, str(sorted(_fr)))
_fs = SCH.get("FieldSlice", {}).get("required", [])
t("FieldSlice 가 비트 오프셋·폭을 제공한다 (F-085)",
  {"bit_offset", "bit_width"} <= set(_fs), str(_fs))
t("Alert 이 원인 프레임을 가리킨다 (X08 결속, F-085)",
  "frame_id" in FIELDS.get("Alert", set()))

# ── 설정 화면이 프로토콜 빌더를 갖는가 (F-086) ────────────────
IFACE_P = find("siap_iface.py", must="FrameBuilder")
IFACE = IFACE_P.read_text(encoding="utf-8") if IFACE_P else ""
t("설정 API 가 쓸 FrameBuilder 빌더가 계약에 있다 (F-086)",
  "def set_device_property(" in IFACE,
  IFACE_P.name if IFACE_P else "siap_iface.py 없음")
t("두지 않은 게이트웨이발 빌더의 사유가 계약에 적혀 있다 (F-086)",
  "의도적으로 두지 않은 것" in IFACE)

# ── 기능 3 초안이 서버 생성인가 (F-083) ───────────────────────
_rdr = SCH.get("RuleDraftRequest", {})
t("초안 요청이 model_id·inputs 를 받는다 (F-083)",
  {"model_id", "inputs"} <= set(_rdr.get("properties", {})))
t("Rule 이 generation·거부 3필드를 노출한다 (F-083)",
  {"generation", "rejected_at", "rejected_by", "reject_reason"} <= FIELDS.get("Rule", set()))
t("설계서가 origin 과 generation 의 차이를 설명한다 (F-083)",
  "origin` 은 요청자의 **의도**" in DOC or "요청자의 **의도**" in DOC)

# ── F-095: '필드가 있다' 와 '값이 반드시 온다' 는 다르다 ───────
#    F-091·F-092 는 속성 존재만 보는 검사를 전부 통과했다. 화면이 생성 경로와
#    거부 사유, 알림의 원본 프레임을 '받는다'고 선언했으면 required 여야 한다.
def _req(name): return set(SCH.get(name, {}).get("required", []))
t("Rule 응답이 생성경로·거부 증거를 required 로 보장 (F-091 · F-095)",
  {"generation", "rejected_at", "rejected_by", "reject_reason"} <= _req("Rule"),
  str(sorted(_req("Rule"))))
t("Alert 응답이 frame_id 를 required 로 보장 (F-092 · F-095)",
  {"frame_id", "siap_nec"} <= _req("Alert"), str(sorted(_req("Alert"))))
t("NEC 알림이면 frame_id 가 non-null 이다 (X08 결속의 실제 강제, F-092)",
  any(b.get("if", {}).get("properties", {}).get("siap_nec", {}).get("type") == "integer"
      and b.get("then", {}).get("properties", {}).get("frame_id", {}).get("type") == "string"
      for b in SCH.get("Alert", {}).get("allOf", [])))
t("선택자 필드가 non-nullable 이다 (설정 화면의 대상 확정, F-093)",
  not [k for k, v in SCH.get("DevicePropertySelector", {}).get("properties", {}).items()
       if "null" in (v.get("type") if isinstance(v.get("type"), list) else [v.get("type")])])

# ── F-094 · F-095: 판정은 대조표가 정본이다. 화면 설계서가 다르게 적으면 실패 ─
MAT_P = find("0937_요구사항_대조표.md", must="부속서 A")
MAT = MAT_P.read_text(encoding="utf-8") if MAT_P else ""
# 판정 기호는 CP949 밖이라 출력하지 않는다(F-045). 라벨로 바꿔 비교한다.
def _verdict(cell: str) -> str:
    if "\u26a0" in cell: return "부분"
    if "\u2705" in cell: return "충족"
    if "\u274c" in cell: return "미충족"
    return "불명"
_a15 = [l for l in MAT.splitlines() if l.startswith("| A.1-5 |")]
_a15_verdict = _verdict(_a15[0].split("|")[3]) if _a15 else "없음"
t("대조표에서 A.1-5 판정을 읽어낸다 (정본 참조, F-094)",
  _a15_verdict in ("부분", "충족", "미충족"), f"대조표 A.1-5 = {_a15_verdict}")
# 화면 설계서가 '닫힌다'고 적었는데 대조표는 아직 부분이면 F-087 이 되돌아간 것이다
_closed = "A.1-5 가 닫힌다" in DOC
t("화면 설계서의 A.1-5 종결 주장이 대조표와 어긋나지 않는다 (F-087 · F-094)",
  (not _closed) or _a15_verdict == "충족",
  f"설계서 종결주장={_closed} / 대조표={_a15_verdict}")
import re as _re
_m = _re.search(r"부속서 A 집계는[^`]*`\s*.?\s*(\d+)\s*/\s*.?\s*(\d+)\s*/\s*.?\s*(\d+)\s*`", DOC)
_mm = _re.search(r"\|\s*\*\*합계\*\*\s*\|\s*\*\*31\*\*\s*\|\s*\*\*(\d+)\*\*\s*\|\s*\*\*(\d+)\*\*\s*\|\s*\*\*(\d+)\*\*", MAT)
t("화면 설계서의 부속서 A 집계가 대조표 합계와 일치 (F-094)",
  (_m is None) or (_mm is not None and _m.groups() == _mm.groups()),
  f"설계서={_m.groups() if _m else None} 대조표={_mm.groups() if _mm else None}")

# ═══════════════════════════════════════════════════════════════
#  8. 금지 패턴 · 조항 인용
# ═══════════════════════════════════════════════════════════════
SECRET  = re.compile(r"api[_-]?key|password|passwd|@author", re.I)
PRIVATE = re.compile(r"[A-Za-z]:\\Users\\|/home/[a-z]+/|/Users/[a-z]+/", re.I)
SYNTH   = re.compile(r"random\.(uniform|randint|gauss)\(|np\.random\.")
hits = [f"{i}" for i, l in enumerate(DOC.splitlines(), 1)
        if SECRET.search(l) or PRIVATE.search(l) or SYNTH.search(l)]
t("설계서에 비밀정보·개인경로·합성데이터 패턴 없음", not hits, str(hits[:3]))

clauses = set(re.findall(r"표 7-\d+", DOC)) | set(re.findall(r"\b(?:8|7|6)\.\d(?:\.\d)*", DOC))
t(f"표준 조항 인용 {len(clauses)}종", len(clauses) >= 12,
  " ".join(sorted(clauses)[:6]) + " ...")

# ═══════════════════════════════════════════════════════════════
w = max(len(n) for _, n, _ in R)
print("web/ 화면 설계서 검증  (openapi / golden / 시연 시나리오 대조)\n")
for ok, n, note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
p = sum(1 for o, *_ in R if o)
print(f"\n  {p}/{len(R)} 통과")
sys.exit(0 if p == len(R) else 1)
