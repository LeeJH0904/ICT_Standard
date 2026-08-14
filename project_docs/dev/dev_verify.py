"""개발_착수_지시서.md 검증 — 설계 산출물·규약·실측과의 대조

이 스크립트는 지시서 한 파일의 내부 일관성만 보지 않는다(CLAUDE.md 6.2 · F-080).
독립 입력 여섯을 읽어 대조한다.

  1. ROLES.md                       : 작업자·검증자 역할과 권한 분리
  2. CLAUDE.md                      : 성립해야 하는 주장 4개 · 금지 9종 · 디렉터리 트리
  3. project_docs/**                : 지시서가 '읽을 문서'로 지정한 설계서의 실재
  4. 기존 검증기 9종의 실제 실행 결과 : 출구 조건이 인용한 통과 건수
  5. 진행보고서.md                  : 마감일
  6. GPT.md                         : 검증 능력 한계 서술의 정합

실행:  python project_docs/dev/dev_verify.py
종료코드: 0 = 전부 일치, 1 = 불일치 있음
"""
from __future__ import annotations
import os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # project_docs/dev/
ROOT = HERE.parent.parent                       # 저장소 루트

# F-045 — 한국어 Windows 기본 콘솔은 CP949 다. 출력 문자는 그 안에서 고른다.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

R: list[tuple[bool, str, str]] = []
def t(name: str, ok: bool, note: str = "") -> None:
    R.append((bool(ok), name, note))

SKIP_DIRS = {"__pycache__", "node_modules", "site-packages", "venv", ".venv",
             "env", "wheels", "build", "dist", "_to_delete"}
def _skip(p: Path) -> bool:
    return any(part.startswith(".") or part in SKIP_DIRS or part.startswith("_stage")
               for part in p.parts)

def find(name: str, must: str = "") -> Path | None:
    for q in ROOT.rglob(name):
        if _skip(q): continue
        if must and must not in q.read_text(encoding="utf-8", errors="replace"): continue
        return q
    return None

# F-096 — 하위 파이썬 프로세스의 stdout 인코딩은 부모가 물려받은 로케일을 따른다.
# 표준 출력이 실제 콘솔이 아니라 파이프(subprocess capture)면 PEP 528 의 UTF-8
# 콘솔 처리가 적용되지 않고, 한국어 Windows 에서는 cp949 로 인코딩된다. 이 스크립트가
# 그 바이트를 "utf-8" 로 디코딩하면 한글이 U+FFFD 로 깨져 "N/N 통과" 정규식이
# 조용히 실패한다(예외 없이 통과 건수 미검출로만 보인다). 하위 프로세스에게
# PYTHONIOENCODING 을 강제해 심사자의 OS 로케일(cp949·cp1252·cp437 등)과
# 무관하게 항상 UTF-8 로 쓰게 한다.
def _utf8_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env

DOC   = (HERE / "개발_착수_지시서.md").read_text(encoding="utf-8")
_gp   = HERE / "개발_운영_가이드.md"
GUIDE = _gp.read_text(encoding="utf-8") if _gp.exists() else ""
def read(p: Path | None) -> str:
    return p.read_text(encoding="utf-8", errors="replace") if p else ""

ROLES  = read(find("ROLES.md", must="역할 운영 정본"))
CLAUDE = read(find("CLAUDE.md", must="절대 금지"))
idx0   = read(find("bug_fix_list.md"))
GPTMD  = read(find("GPT.md"))
REPORT = read(find("진행보고서.md", must="마감"))

t("ROLES.md 적재", all(k in ROLES for k in ("작업자", "검증자", "역할 분리")), f"{len(ROLES)}자")
t("CLAUDE.md 적재", len(CLAUDE) > 5000, f"{len(CLAUDE)}자")
t("사람용 운영 가이드가 별도 파일로 존재", len(GUIDE) > 2000, f"{len(GUIDE)}자")
t("지시서가 작업자 전용임을 선언",
  "이 문서는 작업자가 읽는다" in DOC and "에이전트는 읽지 않는다" in DOC)
t("가이드가 사람 전용임을 선언",
  "사람" in GUIDE[:400] and "작업자는 읽지 않는다" in GUIDE)
#    분리가 유지되는가 — 운영 판단이 지시서로 되돌아오면 에이전트가 읽을 양이 늘고
#    같은 내용이 두 곳에 생긴다(설계 단계 문서불일치 46건이 전부 그 형태였다).
#    가이드를 가리키는 포인터 줄은 내용이 아니다. 그 줄은 제외하고 본다.
_body = "\n".join(l for l in DOC.splitlines() if "개발_운영_가이드.md" not in l)
_leak = [k for k in ("축소 순서", "가용 17일", "08-21", "지연 신호") if k in _body]
t("일정·축소 순서가 지시서에 남아 있지 않다", not _leak, str(_leak))
_need = [k for k in ("축소", "08-23", "지연") if k not in GUIDE]
t("일정·축소 순서가 가이드에 있다", not _need, str(_need))
t("GPT.md 적재", len(GPTMD) > 1000, f"{len(GPTMD)}자")
# 진행보고서.md 는 저장소 밖(표준 문서 폴더)에 있을 수 있다. 있으면 마감일을
# 교차 검증하고, 없으면 그 사실을 출력에 남긴다 — 조용히 건너뛰지 않는다(F-095).
t("진행보고서.md 적재 (선택 - 저장소 밖일 수 있음)", True,
  f"{len(REPORT)}자" if REPORT else "저장소 안에 없음. 마감 교차 검증 생략")

def rows(header: str, ncol: int, scope: str = "", src: str | None = None) -> list[list[str]]:
    """마크다운 표의 데이터 행을 뽑는다. header 행 자체는 소비된다(F-043 의 off-by-one)."""
    doc = DOC if src is None else src
    body = doc.split(scope, 1)[-1] if scope else doc
    if header not in body: return []
    after = body.split(header, 1)[1]
    out = []
    for ln in after.splitlines()[1:]:          # 구분선 한 줄 건너뜀
        ln = ln.strip()
        if not ln.startswith("|"): break
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) != ncol: continue
        if all(set(c) <= set("-: ") for c in cells): continue   # 구분선
        out.append(cells)
    return out

def cell(s: str) -> str:
    return re.sub(r"[`*]", "", s).strip()

# ═══════════════════════════════════════════════════════════════
#  1. 단계 구조 — 한눈에 표와 상세 절이 같은 집합인가
# ═══════════════════════════════════════════════════════════════
SUMMARY = rows("| # | 단계 | 출구 명령 | 신설 검증기 |", 4)
t(f"2절 단계표 파싱 ({len(SUMMARY)}단계)", len(SUMMARY) == 11, str([r[0] for r in SUMMARY]))

detail_ids = re.findall(r"^### 3\.(\w+) 단계 (\S+) ", DOC, re.M)
_mn = re.search(r"## 2\. 단계 (\d+)개", DOC)
t("2절 제목의 단계 수가 표 행 수와 일치",
  _mn is not None and int(_mn.group(1)) == len(SUMMARY),
  f"제목={_mn.group(1) if _mn else None} 표={len(SUMMARY)}")
t("3절 상세가 단계표와 같은 수", len(detail_ids) == len(SUMMARY), str([d[1] for d in detail_ids]))

sum_ids = [cell(r[0]) for r in SUMMARY]
det_ids = [d[1] for d in detail_ids]
t("단계표와 상세 절의 단계 번호가 같다", sum_ids == det_ids,
  f"표={sum_ids} 상세={det_ids}")

# 상세 절이 전부 같은 구성을 갖는가 — 빠진 칸이 있으면 그 단계는 판정 기준이 없다
missing = []
for _, sid in detail_ids:
    blk = DOC.split(f"### 3.{[d[1] for d in detail_ids].index(sid) and '' or ''}", 1)  # noqa
for sid in det_ids:
    m = re.search(rf"### 3\.\w+ 단계 {re.escape(sid)} .*?(?=\n### |\n## )", DOC, re.S)
    blk = m.group(0) if m else ""
    for key in ("**범위**", "**읽을 문서**", "**출구**", "**검증자 검증**", "**하지 않을 것**"):
        if key not in blk: missing.append(f"{sid}:{key}")
t("상세 절이 전부 범위/읽을문서/출구/검증자검증/하지않을것 을 갖는다",
  not missing, str(missing[:4]))

# ═══════════════════════════════════════════════════════════════
#  2. 신설 검증기 — 단계표 · 누적표 · 회귀 명령이 같은 집합인가
# ═══════════════════════════════════════════════════════════════
TOOLS_SUM = set()
for r in SUMMARY:
    TOOLS_SUM |= set(re.findall(r"tools/(\w+\.py)", r[3]))
CUM = rows("| 검증기 | 신설 단계 | 판정하는 주장 |", 3)
TOOLS_CUM = {m for r in CUM for m in re.findall(r"tools/(\w+\.py)", r[0])}
t(f"신설 검증기 목록이 2절 표와 4절 누적표에서 일치 ({len(TOOLS_CUM)}종)",
  TOOLS_SUM == TOOLS_CUM,
  f"2절만={sorted(TOOLS_SUM - TOOLS_CUM)} 4절만={sorted(TOOLS_CUM - TOOLS_SUM)}")

# 누적표의 '신설 단계' 가 실제 단계 번호인가
bad_stage = [r[1] for r in CUM if cell(r[1]) not in det_ids]
t("누적표의 신설 단계가 전부 실재하는 단계 번호", not bad_stage, str(bad_stage))

# 회귀 명령이 존재하는가 — 등록을 빠뜨리면 회귀가 사라진다
t("전체 회귀 명령(run_all.py)을 지정했다", "tools/run_all.py" in DOC)

# ═══════════════════════════════════════════════════════════════
#  3. CLAUDE.md 대조 — 주장 4개가 전부 기계 판정으로 덮이는가
# ═══════════════════════════════════════════════════════════════
#     지시서가 '주장 N' 이라 쓴 것이 CLAUDE.md 0장 표의 행 수와 맞아야 한다.
_cblk = CLAUDE.split("반드시 성립해야 하는 주장", 1)[-1].split("**적용 표준", 1)[0]
claim_rows = [ln for ln in _cblk.splitlines()
              if ln.startswith("|") and ln.count("|") >= 3
              and not set(ln.replace("|", "")) <= set("-: ")]
n_claims = len(claim_rows)
t(f"CLAUDE.md 0장 주장 표 파싱 ({n_claims}개)", n_claims == 4, str(n_claims))

covered = {int(m) for m in re.findall(r"\*\*주장 (\d)\*\*", DOC)}
t("주장 1~3 이 전부 신설 검증기로 덮인다", {1, 2, 3} <= covered, str(sorted(covered)))
t("주장 4(표준결함)의 근거를 가이드가 밝힌다",
  "standard-findings.md" in GUIDE and "19건" in GUIDE)

# 금지 9종을 인용할 때 번호가 CLAUDE.md 표와 맞는가
FORBID = re.findall(r"^\| (\d+) \| \*\*(.+?)\*\*", CLAUDE.split("절대 금지", 1)[-1], re.M)
t(f"CLAUDE.md 1장 금지 항목 파싱 ({len(FORBID)}종)", len(FORBID) == 9, str(len(FORBID)))
cited = {int(m) for m in re.findall(r"§1-(\d)", DOC)}
ghost = [c for c in cited if not any(int(n) == c for n, _ in FORBID)]
t("지시서가 인용한 금지 번호가 전부 실재", not ghost, str(ghost))

# 축소 대상이 실재하는 설계 요소인가 (F-082 — 존재하지 않는 근거를 적지 않는다)
CUT = rows("| 순서 | 자를 것 | 잃는 것 |", 3, src=GUIDE)
t(f"축소 순서 {len(CUT)}단계를 명시", len(CUT) >= 4, str(len(CUT)))
ghost_cut = []
for r in CUT:
    for sym in re.findall(r"`([^`]+)`", r[1]):
        base = Path(sym.rstrip("/")).name
        if sym.endswith((".jsonl", ".html")) or "/" in sym:
            if base not in CLAUDE and not [q for q in ROOT.rglob(base) if not _skip(q)]:
                ghost_cut.append(sym)
t("축소 대상이 설계에 실재하는 산출물", not ghost_cut, str(ghost_cut))

# ═══════════════════════════════════════════════════════════════
#  4. 출구 조건이 인용한 통과 건수 ↔ 실제 실행 결과 (F-090 · F-095 · F-096)
# ═══════════════════════════════════════════════════════════════
#     회귀 가드 (F-096) — 하위 프로세스 stdout 을 utf-8 로 안전하게 복원하는가.
#     _utf8_env() 를 빼면 이 자리에서 즉시 실패해야 한다(한국어 Windows, cp949 로케일).
_probe = subprocess.run(
    [sys.executable, "-B", "-c", "print('통과')"],
    capture_output=True, timeout=10, env=_utf8_env(),
)
_probe_out = _probe.stdout.decode("utf-8", "replace").strip()
t("하위 프로세스 stdout 을 UTF-8로 안전하게 복원 (F-096, cp949 로케일 회귀 가드)",
  _probe_out == "통과", repr(_probe_out))

#     지시서가 '56/56' 이라 적었는데 실제로 다르면 단계 완료 판정이 틀린다.
EXISTING = {
    "test_contract.py":   "contracts",
    "golden_verify.py":   "contracts/vectors",
    "verify.py":          "db",
    "api_verify.py":      "api",
    "web_verify.py":      "web",
    "firmware_verify.py": "firmware",
}
drift = []
for name, _sub in EXISTING.items():
    p = find(name, must="통과")
    if not p:
        drift.append(f"{name}: 파일 없음"); continue
    r = subprocess.run([sys.executable, "-B", str(p)], capture_output=True,
                       cwd=str(p.parent), timeout=180, env=_utf8_env())
    out = r.stdout.decode("utf-8", "replace")
    m = re.search(r"(\d+)/(\d+) 통과", out)
    if not m:
        drift.append(f"{name}: 통과 수 미출력"); continue
    real = m.group(1)
    # 한 줄에 검증기가 여러 개 나오므로 줄 단위 대조는 짝을 잘못 맞춘다.
    # 이름이 나온 위치부터 '다음 검증기 이름 직전'까지에서 첫 N/N 을 찾는다.
    #   'verify.py' 는 'web_verify.py' 안에도 들어 있다. 단어 경계를 요구한다.
    bnd = lambda n: r"(?<![A-Za-z0-9_])" + re.escape(n)
    others = [o for o in EXISTING if o != name]
    for hit in re.finditer(bnd(name), DOC):
        tail = DOC[hit.end():hit.end() + 400]
        pos = [m.start() for o in others for m in re.finditer(bnd(o), tail)]
        cut = min(pos) if pos else len(tail)
        q = re.search(r"\*\*(\d+)/(\d+)\*\*", tail[:cut])
        if q and q.group(1) != real:
            drift.append(f"{name}: 지시서 {q.group(1)} 실측 {real}")
t("출구 조건이 인용한 통과 건수가 실측과 일치 (F-090)", not drift, str(drift[:3]))

# ═══════════════════════════════════════════════════════════════
#  5. '읽을 문서' 가 실재하는가 (F-082 — 없는 근거를 적지 않는다)
# ═══════════════════════════════════════════════════════════════
#     2.1 경로표가 정본이다. 표에서 이름->경로를 읽고, 그 경로가 실재하는지 본다.
PATHTBL = rows("| 이름 | 경로 | 분량 |", 3)
DOCMAP = {cell(r[0]): cell(r[1]) for r in PATHTBL}
t(f"2.1 설계 문서 경로표 파싱 ({len(DOCMAP)}종)", len(DOCMAP) >= 10, str(len(DOCMAP)))

#     적힌 경로 그대로 존재해야 한다. 다른 위치에서 찾아 주면 새 세션이 문서를 못 찾는
#     상황을 그대로 통과시킨다 — 검사의 목적이 '적힌 대로 따라갈 수 있는가' 이기 때문이다.
absent = [f"{name}->{rel}" for name, rel in DOCMAP.items() if not (ROOT / rel).exists()]
t("경로표의 설계 문서가 적힌 경로에 실재 (F-082)", not absent, str(absent))

ARTI = rows("| 파일 | 무엇의 정본인가 |", 2)
absent2 = [cell(r[0]) for r in ARTI if not (ROOT / cell(r[0])).exists()]
t(f"기계 산출물 {len(ARTI)}종이 적힌 경로에 실재", not absent2, str(absent2))

#     핵심: 3절이 '읽을 문서'로 부른 이름이 전부 경로표에 등재되었는가.
#     이름만 적고 경로가 없으면 새 세션이 그 문서를 찾지 못한다.
unmapped = []
for sid in det_ids:
    m = re.search(rf"### 3\.\w+ 단계 {re.escape(sid)} .*?(?=\n### |\n## )", DOC, re.S)
    mm = re.search(r"\*\*읽을 문서\*\*\s*\|([^|]*)\|", m.group(0) if m else "")
    if not mm: continue
    txt = mm.group(1)
    # 백틱 안(파일명 직접 지정)은 이름 참조가 아니다
    plain = re.sub(r"`[^`]*`", "", txt)
    plain = re.sub(r"\([^)]*\)", "", plain)        # 괄호 안의 · 가 분리자로 오인된다
    for chunk in re.split(r"[,]", plain):
        nm = re.sub(r"§[\d.~ ]*|전체", "", chunk).strip().rstrip("·").strip()
        if len(nm) < 3: continue
        if nm not in DOCMAP: unmapped.append(f"{sid}:{nm}")
t("3절이 인용한 설계 문서 이름이 전부 2.1 경로표에 등재 (새 세션이 찾을 수 있다)",
  not unmapped, str(sorted(set(unmapped))))

# 모든 단계가 읽을 문서를 지정했는가 — 지정 없이 구현하지 않는다(CLAUDE.md 8-2)
noread = []
for sid in det_ids:
    m = re.search(rf"### 3\.\w+ 단계 {re.escape(sid)} .*?(?=\n### |\n## )", DOC, re.S)
    blk = m.group(0) if m else ""
    mm = re.search(r"\*\*읽을 문서\*\*\s*\|([^|]*)\|", blk)
    if not mm or len(mm.group(1).strip()) < 5: noread.append(sid)
t("모든 단계가 읽을 문서를 지정", not noread, str(noread))

# ═══════════════════════════════════════════════════════════════
#  6. 일정 — 마감 안에 들어가고 날짜가 단조 증가인가
# ═══════════════════════════════════════════════════════════════
# 저장소 안의 정본은 지시서 자신이다. 진행보고서가 있으면 그것과 대조한다.
_md = re.search(r"마감 \*\*(\d{4})-(\d{2})-(\d{2}) 23:59\*\*", GUIDE)
t("가이드가 마감일을 명시", _md is not None,
  "-".join(_md.groups()) if _md else "없음")
_mr = re.search(r"마감 \| \*\*(\d+)/(\d+)\([^)]*\) 23:59\*\*", REPORT)
if _mr:
    t("가이드의 마감 표기가 진행보고서와 일치",
      _md is not None and (int(_md.group(2)), int(_md.group(3)))
                          == (int(_mr.group(1)), int(_mr.group(2))),
      f"지시서={_md.groups() if _md else None} 진행보고서={_mr.group(1)}/{_mr.group(2)}")
else:
    t("가이드의 마감 표기가 진행보고서와 일치", True,
      "진행보고서가 저장소 밖 - 대조 생략. 개발 PC 에서는 실행된다")
if _md:
    deadline = (int(_md.group(2)), int(_md.group(3)))
    SCHED = rows("| 날짜 | 단계 | 비고 |", 3, src=GUIDE)
    dates = []
    for r in SCHED:
        dates += [(int(a), int(b)) for a, b in re.findall(r"(\d{2})-(\d{2})", r[0])]
    t(f"일정표 {len(SCHED)}행 파싱", len(SCHED) >= 10, str(len(SCHED)))
    t("일정이 단조 증가", dates == sorted(dates), str(dates[:3]))
    t("일정이 마감을 넘지 않는다", bool(dates) and dates[-1] <= deadline,
      f"마지막={dates[-1] if dates else None} 마감={deadline}")
    #   제출일이 일정표에 있고 마감일과 같은가. 없으면 일정이 조용히 잘려도 통과한다.
    _sub = [r for r in SCHED if "제출" in r[1] or "제출" in r[2]]
    _sd = [(int(a), int(b)) for r in _sub for a, b in re.findall(r"(\d{2})-(\d{2})", r[0])]
    t("일정표에 제출일이 있고 마감일과 같다",
      bool(_sd) and _sd[-1] == deadline, f"제출={_sd} 마감={deadline}")
    # 모든 단계가 일정에 배정되었는가
    sched_ids = {s for r in SCHED for s in re.findall(r"\b(\d[abc]?)\b", r[1])}
    unassigned = [s for s in det_ids if s not in sched_ids]
    t("모든 단계가 일정표에 배정됨", not unassigned, str(unassigned))

# ═══════════════════════════════════════════════════════════════
#  7. 검증자 프로토콜 — 능력 확인이 GPT.md 와 어긋나지 않는가
# ═══════════════════════════════════════════════════════════════
t("가이드가 검증 환경의 능력 확인을 명시 (그림 · 하드웨어 · 렌더링 · C 컴파일)",
  "현재 검증 환경의 능력 확인" in GUIDE and
  all(k in GUIDE for k in ("C 컴파일", "하드웨어 접근", "브라우저 렌더링")))
t("가이드의 이미지 능력 서술이 GPT.md 와 정합",
  "이미지 해석" in GUIDE and "이미지 해석" in GPTMD and "제품명으로 가정하지 마라" in GPTMD)
t("지시서가 제출물에 실행 로그·컴파일 로그를 포함하도록 지정",
  "실행 로그" in DOC and "컴파일 로그" in DOC)
t("가이드가 상태 전이 규약을 재확인 (검증자는 신규만)",
  "신규" in GUIDE and "상태 전이는 작업자" in GUIDE)

# 신설 검증기에 결함 주입을 요구하는가 — 이것이 없으면 F-095 가 재발한다
t("종료 체크리스트가 신설 검증기의 결함 주입을 요구",
  "결함 주입" in DOC.split("### 5.2")[-1])
t("진입 체크리스트가 fix_log 신규 확인을 요구",
  "bug_fix_list" in DOC.split("### 5.1")[-1].split("### 5.2")[0])

# ── 새 세션 단독 실행 가능성 (0.1 · 0.2) ──────────────────────
_m01 = re.search(r"### 0\.1 새 세션이 처음 하는 일(.*?)(?=\n### )", DOC, re.S)
_s01 = _m01.group(1) if _m01 else ""
t("0.1 '새 세션이 처음 하는 일' 절이 있다", len(_s01) > 200, f"{len(_s01)}자")
#     명령 블록 안에 where.py 가 있어야 한다. 본문 어딘가에 이름만 나오는 것으로는 부족하다.
_blk = "\n".join(re.findall(r"```bash\n(.*?)```", _s01, re.S))
t("시작 절차의 명령 블록이 where.py 로 현재 단계를 판정",
  "tools/where.py" in _blk, _blk.strip()[:60].replace("\n", " / "))
t("현재 단계를 파일에 적어 두지 않는다 (상태 드리프트 금지)",
  "상태 파일" in _s01 and not re.search(r"DEV_STATE|STATE\.md|state\.json", DOC),
  "상태 파일 근거 서술 + 상태 파일 참조 0")
t("where.py 가 단계 0 의 범위·누적표에 등재",
  DOC.count("tools/where.py") >= 3, f"{DOC.count('tools/where.py')}회 언급")
t("run_all.py 부트스트랩 순환을 명시 (단계 0 에는 없다)",
  "단계 0 에서는 아직 없다" in DOC)
_rep = rows("| 시점 | 보고 내용 |", 2)
t("0.2 사용자 보고 지점 3종을 명시", len(_rep) >= 3, str(len(_rep)))
_dec = rows("| 시점 | 결정할 것 |", 2, src=GUIDE)
t("가이드가 사람의 판단 지점을 지시서의 보고 지점과 같은 수로 명시",
  len(_dec) == len(_rep), f"가이드={len(_dec)} 지시서={len(_rep)}")
t("실행 위치와 파이썬 실행기를 명시",
  "저장소 루트에서" in DOC and "python3" in DOC)

# 한 단계의 읽기 분량이 예산을 넘지 않는가 — 경로표의 분량을 실제로 더한다
_sz = {}
for r in PATHTBL:
    mm = re.search(r"([\d,]+)자", r[2])
    if mm: _sz[cell(r[0])] = int(mm.group(1).replace(",", ""))
#     예산은 '전체를 읽는 문서' 기준이다. 이름 뒤에 절이 지정된 것은 부분 읽기이므로 세지 않는다.
over = []
for sid in det_ids:
    m = re.search(rf"### 3\.\w+ 단계 {re.escape(sid)} .*?(?=\n### |\n## )", DOC, re.S)
    mm = re.search(r"\*\*읽을 문서\*\*\s*\|([^|]*)\|", m.group(0) if m else "")
    if not mm: continue
    txt = mm.group(1)
    tot = 0
    for k, v in _sz.items():
        for hit in re.finditer(re.escape(k), txt):
            tail = txt[hit.end():hit.end() + 12]
            if not tail.lstrip().startswith("§"): tot += v     # 절 지정 없음 = 전체 읽기
    if tot > 60000: over.append(f"{sid}:{tot}자")
t("단계별 전체 읽기 분량이 6만자 예산 안 (2.1 규칙)", not over, str(over))

# 경로표의 분량 표기가 실측과 크게 어긋나지 않는가 (오차 10%)
drift_sz = []
for name, rel in DOCMAP.items():
    q = ROOT / rel
    if not q.exists():
        q = find(Path(rel).name)
    if not q or name not in _sz: continue
    real = len(q.read_text(encoding="utf-8", errors="replace"))
    if abs(real - _sz[name]) > max(2000, real * 0.10):
        drift_sz.append(f"{name}: 표기 {_sz[name]} 실측 {real}")
t("경로표의 분량 표기가 실측과 일치 (오차 10%)", not drift_sz, str(drift_sz[:3]))

# ═══════════════════════════════════════════════════════════════
#  7-a. 검증자 프롬프트 — 단계 집합·규약 참조가 어긋나지 않는가
# ═══════════════════════════════════════════════════════════════
PROMPT_P = HERE / "검증자_프롬프트.md"
t("검증자 프롬프트가 존재", PROMPT_P.exists(), PROMPT_P.name)
if PROMPT_P.exists():
    PR = PROMPT_P.read_text(encoding="utf-8")
    # 단계별 추가 지시가 지시서의 단계 집합과 같은가
    pr_stages = re.findall(r"^### 단계 (\S+) ", PR, re.M)
    t(f"프롬프트의 단계별 지시가 지시서 단계와 같은 집합 ({len(pr_stages)}개)",
      pr_stages == det_ids, f"프롬프트={pr_stages} 지시서={det_ids}")
    # 검사 대상은 §2 의 붙여넣기 블록이다. 해설 산문에 같은 문구가 있어도
    # 프롬프트에서 빠졌으면 검증자는 그 지시를 받지 못한다.
    _mp = re.search(r"## 2\. 붙여넣기용 프롬프트.*?```text\n(.*?)```", PR, re.S)
    BLK = _mp.group(1) if _mp else ""
    t("붙여넣기용 프롬프트 블록을 찾았다", len(BLK) > 800, f"{len(BLK)}자")
    # 정본 문서를 읽으라고 지정했는가 — 프롬프트가 규약을 다시 쓰면 정본이 둘이 된다
    for must in ("ROLES.md", "GPT.md", "fix_log/README.md", "CLAUDE.md", "개발_착수_지시서.md",
                 "bug_fix_list.md"):
        t(f"프롬프트가 {must} 를 읽게 한다", must in BLK)
    t("프롬프트가 상태를 `신규` 로만 두게 한다", "신규" in BLK and "상태를 바꾸거나" in BLK)
    t("프롬프트가 코드 수정을 금지한다",
      "코드를 고치거나" in BLK and "fix_log/ 외의 파일을 수정하지 마라" in BLK)
    t("프롬프트가 로그를 믿지 말고 직접 실행하게 한다",
      "직접 실행하라" in BLK and "제출된 로그를 믿지 마라" in BLK)
    t("프롬프트가 검증기의 결함을 최우선으로 지시한다 (F-074 · F-080 · F-089 · F-095)",
      "이 검사를 통과하면서 틀린 코드" in BLK)
    t("프롬프트가 이미지 능력·접근 부재 시 추측하지 말라고 지시한다 (GPT.md 3)",
      "이미지" in BLK and "추측" in BLK and "검증 불가" in BLK,
      "이미지+추측+검증 불가 3어가 프롬프트 블록 안에")
    #    표준 원문의 위치를 프롬프트가 정확히 말하는가. 저장소 안으로 옮겨졌으므로
    #    "저장소 밖에 있다"고 적혀 있으면 검증자가 폴더를 따로 찾게 된다.
    _std = [q for q in ROOT.iterdir() if q.is_dir() and q.name.startswith("표준 문서")]
    t("프롬프트가 표준 원문의 위치를 명시", "표준 문서 md 파일" in PR)
    t("표준 원문이 프롬프트가 적은 경로에 실재 (저장소에 있을 때만 검사)",
      (not _std) or _std[0].name == "표준 문서 md 파일",
      _std[0].name if _std else "이 작업 공간에는 없음 - 저장소에서 검사된다")
    t("프롬프트가 표준 원문을 제출 제외 대상으로 적었다",
      "제출물에서는 제외" in PR or "제출물에 있으면 안 된다" in PR)
    # 인용한 발견 번호가 실재하는가
    pf = sorted({f for f in re.findall(r"F-\d{3}", PR) if f not in idx0})
    t(f"프롬프트가 인용한 발견 사항이 전부 인덱스에 실재", not pf, str(pf))
    # F-100 — 기존 발견 건수·마지막 ID·라운드 수를 프롬프트에 숫자로 고정하면
    # bug_fix_list.md 에 정상적으로 한 줄만 추가해도 이 검증이 매번 깨진다.
    # 그래서 숫자를 아예 프롬프트에 두지 않게 하고(회귀 가드), 그 대신
    # "그 자리에서 인덱스를 읽어라"는 동적 지시가 있는지만 검사한다.
    stale_count = re.findall(r"기존 (?:발견 )?\d+건", PR)
    t("프롬프트가 기존 발견 건수를 숫자로 고정하지 않음 (F-100)", not stale_count, str(stale_count))
    stale_range = re.findall(r"F-001~F-\d{3}", PR)
    t("프롬프트가 기존 ID 범위 끝을 숫자로 고정하지 않음 (F-100)", not stale_range, str(stale_range))
    stale_round = re.findall(r"지난 \d+라운드", PR)
    t("프롬프트가 라운드 수를 숫자로 고정하지 않음 (F-100)", not stale_round, str(stale_round))
    t("프롬프트가 다음 ID를 인덱스에서 그 자리에서 읽으라고 지시함 (F-100)",
      "다음 ID" in BLK and "bug_fix_list.md" in BLK)

# ═══════════════════════════════════════════════════════════════
#  8. 금지 패턴 · 조항 인용 (CLAUDE.md 1)
# ═══════════════════════════════════════════════════════════════
SECRET  = re.compile(r"api[_-]?key|password|passwd|@author", re.I)
PRIVATE = re.compile(r"[A-Za-z]:\\Users\\|/home/[a-z]+/|/Users/[a-z]+/", re.I)
SYNTH   = re.compile(r"random\.(uniform|randint|gauss)\(|np\.random\.|math\.sin\(")
hits = [str(i) for i, l in enumerate(DOC.splitlines(), 1)
        if SECRET.search(l) or PRIVATE.search(l) or SYNTH.search(l)]
t("지시서에 비밀정보·개인경로·합성데이터 패턴 없음", not hits, str(hits[:3]))

fids = set(re.findall(r"F-\d{3}", DOC))
idx = idx0
ghost_f = sorted(f for f in fids if f not in idx)
t(f"인용한 발견 사항 {len(fids)}건이 전부 인덱스에 실재", not ghost_f, str(ghost_f))

# ═══════════════════════════════════════════════════════════════
w = max(len(n) for _, n, _ in R)
print("개발 착수 지시서 검증  (CLAUDE.md / 설계서 / 실측 / 진행보고서 대조)\n")
for ok, n, note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
p = sum(1 for o, *_ in R if o)
print(f"\n  {p}/{len(R)} 통과")
sys.exit(0 if p == len(R) else 1)
