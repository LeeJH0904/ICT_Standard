"""시연 시나리오 검증 — 컷 시트와 골든 벡터·공고문 규격을 대조한다

시나리오는 산문이라 틀려도 통과한다. 특히 시간 배분은 손으로 더하다 어긋나기 쉽고,
어긋난 채 촬영에 들어가면 2분을 넘겨 규격 위반이 된다. 그래서 다음을 기계로 본다.

  1) 컷 시트의 산술 — 길이 합 · 시작 시각 연속성 · 120초 상한
  2) 배점 커버리지 — 1차 평가 5개 항목에 담당 컷이 각각 있는가
  3) contracts/vectors/golden.jsonl — 주입 시연 8종이 실제 벡터 X01~X08 과 1:1 이고
     화면에 출력할 (코드명, 조항)이 벡터의 실측값과 같은가
  4) 블라인드 · 폴백 · 금지 패턴

실행:  python project_docs/demo/demo_verify.py
종료코드: 0 = 전부 일치, 1 = 불일치 있음
"""
from __future__ import annotations
import json, re, sys
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

DOC = (HERE / "시연_시나리오.md").read_text(encoding="utf-8")
GOLD_PATH = find("golden.jsonl")
GOLD = [json.loads(l) for l in GOLD_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]

def rows(after: str, cols: int, scope: str = "") -> list[list[str]]:
    src = DOC.split(scope, 1)[1] if scope and scope in DOC else DOC
    seg = src.split(after, 1)[1] if after in src else ""
    out = []
    for line in seg.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            if out: break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if set("".join(cells)) <= set("-: |"): continue
        if len(cells) != cols: break
        out.append(cells)
    return out

def secs(x: str) -> int | None:
    """'14s' / '0:36' / '1:57' -> 초"""
    x = re.sub(r"[*`]", "", x).strip()
    m = re.fullmatch(r"(\d+)s", x)
    if m: return int(m.group(1))
    m = re.fullmatch(r"(\d+):(\d{2})", x)
    if m: return int(m.group(1)) * 60 + int(m.group(2))
    return None

LIMIT = 120                                   # 공고문: 2분 이내

# ═══════════════════════════════════════════════════════════════
#  1. 확정 컷 시트의 산술
# ═══════════════════════════════════════════════════════════════
SHEET = rows("| # | 시작 | 길이 | 화면 |", 4, scope="### 3.2 확정 컷 시트")
cuts = [(r[0], secs(r[1]), secs(r[2])) for r in SHEET if r[0].startswith("S")]
total_row = next((r for r in SHEET if r[0] in ("—", "-")), None)

t(f"확정 컷 시트를 파싱했다 ({len(cuts)}컷)", len(cuts) >= 6, str([c[0] for c in cuts]))
bad = [c[0] for c in cuts if c[1] is None or c[2] is None]
t("모든 컷의 시작·길이를 읽었다", not bad, str(bad))

_sum = sum(c[2] for c in cuts if c[2] is not None)
_stated = secs(total_row[2]) if total_row else None
t(f"컷 길이 합 {_sum}초 = 시트 표기 총계", _stated == _sum, f"표기={_stated}")
t(f"영상 길이 {_sum}초 <= 공고문 상한 {LIMIT}초", _sum <= LIMIT, f"여유 {LIMIT - _sum}초")

drift = []
acc = 0
for name, start, length in cuts:
    if start != acc: drift.append(f"{name}: 시작 {start}s, 기대 {acc}s")
    acc += length or 0
t("컷 시작 시각이 앞 컷의 시작+길이와 연속", not drift, "; ".join(drift[:3]))

_end = secs(total_row[1]) if total_row else None
t("시트 말미의 종료 시각이 누적과 일치", _end == acc, f"표기={_end} 누적={acc}")

# ═══════════════════════════════════════════════════════════════
#  2. 배점 커버리지 — 1차 평가 5개 항목
# ═══════════════════════════════════════════════════════════════
SCORE = rows("| 평가항목 | 배점 | 담당 컷 | 화면에서 무엇이 보이는가 |", 4)
ITEMS = {"표준 활용성": 30, "개발의 참신성": 25, "생성형 AI 활용성": 15,
         "구현완성도": 15, "공공편익": 15}
missing = [k for k in ITEMS if not any(k in r[0] for r in SCORE)]
t("1차 평가 5개 항목 전부에 담당 컷이 있다", not missing, str(missing))

pts = []
for r in SCORE:
    m = re.search(r"(\d+)", re.sub(r"[*]", "", r[1]))
    if m and "가산" not in r[0]: pts.append(int(m.group(1)))
t(f"배점 합 {sum(pts)} = 100 (가산점 제외)", sum(pts) == 100, str(pts))

_no_cut = [r[0] for r in SCORE if not re.search(r"S\d", r[2])]
t("모든 평가항목 행이 실제 컷 번호를 지목한다", not _no_cut, str(_no_cut))

_cut_names = {c[0] for c in cuts}
_ref = {x for r in SCORE for x in re.findall(r"S\d", r[2])}
t("배점표가 지목한 컷이 전부 시트에 존재", _ref <= _cut_names, str(sorted(_ref - _cut_names)))

# ═══════════════════════════════════════════════════════════════
#  3. 기능 2 중심 배분
# ═══════════════════════════════════════════════════════════════
s4 = next((c for c in cuts if c[0] == "S4"), None)
ratio = (s4[2] / _sum * 100) if s4 and _sum else 0
t(f"S4(기능 2) 배분 {ratio:.0f}% >= 40% (기능 2 중심 결정)", ratio >= 40,
  f"{s4[2] if s4 else None}s / {_sum}s")

DETAIL = rows("| 구간 | 길이 | 내용 |", 3, scope="### 3.1 S4 세부")
d_sum = sum(secs(r[1]) or 0 for r in DETAIL)
t(f"S4 세부 구간 합 {d_sum}초 = S4 길이", s4 is not None and d_sum == s4[2],
  f"세부={d_sum} 총괄={s4[2] if s4 else None}")

# ═══════════════════════════════════════════════════════════════
#  4. 주입 시연 ↔ 골든 벡터 X01~X08
# ═══════════════════════════════════════════════════════════════
INJ = rows("| 순서 | 골든 | 주입 | 화면 출력 | 조항 |", 5)
shown = [re.sub(r"[`*]", "", r[1]) for r in INJ]
_mont = re.search(r"몽타주 3종\*\*: (.+?)\.", DOC)
mont = re.findall(r"`(X\d\d)`", _mont.group(1)) if _mont else []

xs = sorted([v for v in GOLD if v["category"] == "위반"], key=lambda v: v["id"])
want = [v["id"] for v in xs]
t(f"위반 벡터 {len(want)}종이 골든에 존재", len(want) == 8, str(want))
t("주입 5종 + 몽타주 3종 = 골든 X01~X08 과 정확히 1:1",
  sorted(shown + mont) == want and len(shown) == 5 and len(mont) == 3,
  f"주입={shown} 몽타주={mont}")

def gold_of(xid: str) -> tuple[str, str] | None:
    v = next((v for v in xs if v["id"] == xid), None)
    if v is None: return None
    c = v["violations"][0] if v["violations"] else v.get("nec_alert")
    return (c["code_name"], c["clause"]) if c else None

bad = []
for r in INJ:
    xid = re.sub(r"[`*]", "", r[1])
    g = gold_of(xid)
    if g is None: bad.append(f"{xid}: 벡터 없음"); continue
    name, clause = g
    if name not in r[3]: bad.append(f"{xid}: 화면출력에 {name} 없음")
    if re.sub(r"[`*]", "", r[4]) != clause: bad.append(f"{xid}: 조항 {r[4]} != {clause}")
t("주입표의 (코드명, 조항)이 골든 실측과 일치", not bad, "; ".join(bad[:3]))

# 골든 hex 를 그대로 흘린다는 규약이 문서에 있는가 (진위·창작성 조항)
t("영상 hex 와 golden.jsonl hex 의 대조 가능성을 명시",
  "golden.jsonl" in DOC and "대조" in DOC and "진위" in DOC)

# ═══════════════════════════════════════════════════════════════
#  5. 핵심 기능 3개가 전부 등장하는가
# ═══════════════════════════════════════════════════════════════
sheet_text = "\n".join(" ".join(r) for r in SHEET)
feat = {"기능 1": "기능 1", "기능 2": "기능 2", "기능 3": "기능 3"}
absent = [k for k, v in feat.items() if v not in sheet_text]
t("컷 시트에 핵심 기능 3개가 전부 등장", not absent, str(absent))

# ═══════════════════════════════════════════════════════════════
#  6. 블라인드 점검 완결성
# ═══════════════════════════════════════════════════════════════
BLIND_SCREEN = rows("| 항목 | 위험 | 조치 |", 3)
BLIND_HW     = rows("| 항목 | 조치 |", 2, scope="### 5.2 하드웨어 촬영")
blind_text = DOC.split("## 5. 블라인드 점검", 1)[-1].split("## 6.", 1)[0]
NEED = ["프롬프트", "경로", "북마크", "배경", "반사", "스티커", "파일명"]
gap = [k for k in NEED if k not in blind_text]
t(f"블라인드 점검이 필수 {len(NEED)}항목을 덮는다", not gap, str(gap))
t("화면·하드웨어 점검표를 둘 다 파싱했다",
  len(BLIND_SCREEN) >= 6 and len(BLIND_HW) >= 4,
  f"화면={len(BLIND_SCREEN)}행 하드웨어={len(BLIND_HW)}행")
t("음성 대신 자막을 쓰기로 결정했다 (특정 가능성 배제)",
  "내레이션 없이 자막만" in DOC)

# ═══════════════════════════════════════════════════════════════
#  7. 폴백 4단계가 실행 모드 3종을 전부 쓰는가
# ═══════════════════════════════════════════════════════════════
FB = rows("| 단계 | 조건 | 전환 |", 3)
fb_text = " ".join(r[2] for r in FB)
modes = [m for m in ("hardware", "simulate", "replay") if m in fb_text]
t("폴백 4단계 · 실행 모드 3종을 전부 사용",
  len(FB) == 4 and len(modes) == 3, f"{len(FB)}단계 / 모드 {modes}")
t("최종 폴백이 제출 영상 재생이다 (PC 자체 실패 대비)",
  any("영상" in r[2] for r in FB))

# 오프라인 전제
t("오프라인 완전 동작을 전제로 선언 (기상청 폴백 · wheels · CDN 없음)",
  all(k in DOC for k in ("fixtures/", "--find-links wheels/", "외부 스크립트를 참조하지 않는다")))

# ═══════════════════════════════════════════════════════════════
#  8. 촬영 순서 — 로그 일관성
# ═══════════════════════════════════════════════════════════════
SHOOT = rows("| 단계 | 작업 | 산출 |", 3)
t(f"촬영 순서 {len(SHOOT)}단계가 정의됨", len(SHOOT) >= 7, f"{len(SHOOT)}단계")
_t3 = next((r for r in SHOOT if r[0] == "T3"), None)
t("화면 시연 3컷을 한 세션에서 연속 녹화한다 (로그 일관성)",
  _t3 is not None and "연속" in _t3[1] and "session_01.jsonl" in _t3[2],
  (_t3[0] + " / " + re.sub(r"[^0-9A-Za-z가-힣 ]", " ", _t3[1])[:40]) if _t3 else "T3 없음")
t("촬영 세션 로그를 그대로 제출한다는 규약이 있다",
  "그대로 제출" in DOC and "spy://" in DOC)
t("합성 데이터 금지를 실격 사유로 명시",
  "합성" in DOC and "실격" in DOC)

# ═══════════════════════════════════════════════════════════════
#  9. CLAUDE.md 1 금지 사항 — 시나리오 자체 검사
# ═══════════════════════════════════════════════════════════════
SECRET  = re.compile(r"api[_-]?key|password|passwd|@author", re.I)
PRIVATE = re.compile(r"[A-Za-z]:\\Users\\|/home/[a-z]+/|/Users/[a-z]+/", re.I)
SYNTH   = re.compile(r"random\.(uniform|randint|random|gauss)\(|np\.random\.")
# 오탐 허용 - 반드시 사유를 적는다.
#   5.1 블라인드 점검표는 "이런 경로가 화면에 나오면 안 된다" 를 보이려고 위험 패턴
#   자체를 인용한다. 인용을 지우면 점검표가 무엇을 막는지 알 수 없다.
ALLOW = ("| 파일 경로 |",)
hits = []
for i, line in enumerate(DOC.splitlines(), 1):
    if any(a in line for a in ALLOW): continue
    if SECRET.search(line) or PRIVATE.search(line) or SYNTH.search(line):
        hits.append(f"{i}: {line.strip()[:50]}")
t("시나리오에 비밀정보·개인경로·합성데이터 패턴 없음 (CLAUDE.md 1)", not hits, str(hits[:3]))

# 촬영용 경로가 개인 경로가 아닌 중립 경로로 지정되었는가
t("촬영용 프로젝트 경로가 중립 경로로 지정됨 (F-070 과 같은 뿌리)",
  "`C:\\demo`" in DOC or "C:\\demo" in DOC)

# ═══════════════════════════════════════════════════════════════
#  10. 제출 규격
# ═══════════════════════════════════════════════════════════════
SPEC = rows("| 항목 | 요구 | 본 계획 |", 3)
t("제출 규격표가 형식·길이·해상도·용량·블라인드·진위 6종을 덮는다",
  len(SPEC) >= 6, f"{len(SPEC)}행")
t("해상도 계획이 FULL HD 이상", "1920" in DOC and "1080" in DOC)

# ═══════════════════════════════════════════════════════════════
w = max(len(n) for _, n, _ in R)
print("시연 시나리오 검증  (컷 산술 / 배점 커버리지 / golden.jsonl 대조)\n")
for ok, n, note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
p = sum(1 for o, *_ in R if o)
print(f"\n  {p}/{len(R)} 통과")
sys.exit(0 if p == len(R) else 1)
