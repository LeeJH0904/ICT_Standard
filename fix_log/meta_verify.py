"""fix_log 메타 검증 — F-043

인덱스(`bug_fix_list.md`)와 개별 상세 파일, 그리고 설계 문서에 적힌 수치가
실제 산출물과 일치하는지 기계적으로 대조한다.

F-043 — 같은 종류의 불일치(상태·심각도·총계·DDL 객체 수)가 두 라운드 연속
        보고되었다. 사람이 세는 한 다시 어긋나므로 검사를 코드로 고정한다.

실행:  python fix_log/meta_verify.py      (저장소 루트 위치 무관)
종료코드: 0 = 전부 일치, 1 = 불일치 있음
"""
from __future__ import annotations
import os, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent          # fix_log/
ROOT = HERE.parent                              # 저장소 루트

# F-045 — 한국어 Windows 기본 콘솔은 CP949 다. 표현 불가 문자 하나로 검증이
#         중단되면 재현성이 깨진다. 출력 문자는 CP949 안에서 고르는 것이 원칙이고
#         (meta_verify.py 가 강제), 이 가드는 중단만은 막는 2중 방어다.
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") != "utf8":
    try: sys.stdout.reconfigure(errors="replace")
    except Exception: pass

R: list[tuple[bool, str, str]] = []
def t(name: str, ok: bool, note: str = "") -> None:
    R.append((bool(ok), name, note))

SKIP_DIRS = {"__pycache__", "node_modules", "site-packages",
             "venv", ".venv", "env", "wheels", "build", "dist"}

def _skip(p) -> bool:
    """숨김 디렉터리(.git/.cache/.venv)와 패키지 캐시를 제외한다.
    제외하지 않으면 가상환경 안의 동명 파일(pandas/core/frame.py 등)을 집는다."""
    return any(part.startswith(".") or part in SKIP_DIRS for part in p.parts)

def find(pattern: str) -> Path | None:
    """저장소 안에서 파일 1개를 이름으로 찾는다. 디렉터리 배치에 의존하지 않는다."""
    hits = [q for q in ROOT.rglob(pattern) if not _skip(q)]
    return hits[0] if hits else None

def read(p: Path | None) -> str:
    return p.read_text(encoding="utf-8") if p and p.exists() else ""

def _cp949_ok(ch: str) -> bool:
    """F-045 — 한국어 Windows 기본 콘솔(CP949)에서 표현 가능한 문자인가."""
    try:
        ch.encode("cp949"); return True
    except (UnicodeEncodeError, LookupError):
        return "cp949" not in str(sys.exc_info()[1])  # 코덱 부재 환경은 검사 생략

def clean(s: str) -> str:
    """표 셀에서 마크다운 강조·링크를 벗겨 순수 값만 남긴다."""
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    return s.replace("*", "").replace("`", "").strip()

# ═══════════════════════════════════════════════════════════════
#  0. 인덱스 파싱
# ═══════════════════════════════════════════════════════════════
INDEX = HERE / "bug_fix_list.md"
idx_text = read(INDEX)
t("인덱스 파일 존재", bool(idx_text), str(INDEX))

rows: dict[str, dict] = {}      # id -> {심각도, 분류, 상태, 상세, 표}
seen: list[str] = []            # 중복 검출용 (dict 는 덮어써서 중복이 소실된다)
for line in idx_text.splitlines():
    if not line.startswith("|"):
        continue
    cells = [clean(c) for c in line.strip().strip("|").split("|")]
    if not cells or not re.fullmatch(r"F-\d{3}", cells[0]):
        continue
    if len(cells) == 6:         # 표준결함 표: ID 심각도 대상 요약 상태 상세
        rows[cells[0]] = {"심각도": cells[1], "분류": "표준결함",
                          "상태": cells[4], "상세": cells[5], "표": "표준결함"}
        seen.append(cells[0])
    elif len(cells) == 7:       # 그 외:      ID 심각도 분류 대상 요약 상태 상세
        rows[cells[0]] = {"심각도": cells[1], "분류": cells[2],
                          "상태": cells[5], "상세": cells[6], "표": "일반"}
        seen.append(cells[0])

t(f"인덱스 행 파싱 ({len(rows)}건)", len(rows) > 0)

# ID 중복 없음
dup = [i for i, c in Counter(seen).items() if c > 1]
t("인덱스 ID 중복 없음", not dup, str(dup))

# '다음 ID' 가 실제 최대값보다 크다
m = re.search(r"다음 ID.*?F-(\d{3})", idx_text)
if m:
    nxt = int(m.group(1))
    mx = max(int(i[2:]) for i in rows) if rows else 0
    t("'다음 ID' 가 최대 ID 보다 큼", nxt > mx, f"다음={nxt}, 최대={mx}")

# ═══════════════════════════════════════════════════════════════
#  1. 인덱스 ↔ 개별 상세 파일 헤더
# ═══════════════════════════════════════════════════════════════
FIELD = re.compile(r"^\|\s*(심각도|분류|상태)\s*\|\s*(.+?)\s*\|\s*$", re.M)

missing, drift = [], []
for fid, row in sorted(rows.items()):
    if row["표"] == "표준결함":
        continue                                   # 상세는 명세서 절 번호를 가리킨다
    cand = list(HERE.glob(f"{fid}_*.md"))
    if not cand:
        missing.append(fid); continue
    body = read(cand[0])
    got = {k: clean(v) for k, v in FIELD.findall(body)}
    for key in ("심각도", "분류", "상태"):
        if key in got and got[key] != row[key]:
            drift.append(f"{fid}.{key}: 인덱스={row[key]} 파일={got[key]}")

t("상세 파일 누락 없음", not missing, str(missing))
t("인덱스 ↔ 상세 헤더 일치 (심각도·분류·상태)", not drift, "; ".join(drift))

# 역방향(F-193) — 인덱스에 없는 상세 파일(고아)이 없는가. 위 검사는
# "인덱스 행 -> 상세 파일 존재"만 보고 반대 방향은 보지 않아, 검증자가 상세
# 파일만 만들고 인덱스 행을 빠뜨려도(또는 행이 실수로 지워져도) 잡지
# 못했다 — F-187·F-188 두 건이 이 틈으로 실제로 누락된 채 102/102를
# 통과했다.
detail_ids: set[str] = set()
for p in HERE.glob("F-*.md"):
    dm = re.match(r"F-\d{3}", p.stem)
    if dm:
        detail_ids.add(dm.group(0))
orphans = sorted(detail_ids - set(rows))
t("상세 파일이 전부 인덱스에 있음 (고아 없음, F-193)", not orphans, str(orphans))

# 처리 기록이 비어 있는 '수정완료·기각·보류' 항목이 없는가
EMPTY_ROW = re.compile(r"^\|\s*(YYYY-MM-DD|\s*)\|", re.M)
no_record = []
for fid, row in sorted(rows.items()):
    if row["표"] == "표준결함" or row["상태"] not in ("수정완료", "기각", "보류"):
        continue
    cand = list(HERE.glob(f"{fid}_*.md"))
    if not cand:
        continue
    # 역할 중립화 이후 신규 파일은 "작업자 처리 기록"을 쓴다. 기존 209개 기록의
    # 역사적 제목 "Claude 처리 기록"도 보존하므로 두 제목을 모두 인식한다.
    tail = re.split(r"^## (?:작업자|Claude) 처리 기록\s*$",
                    read(cand[0]), flags=re.M)[-1]
    dated = re.findall(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|", tail, re.M)
    if not dated:
        no_record.append(fid)
t("종결 항목에 처리 기록 존재", not no_record, str(no_record))

# ═══════════════════════════════════════════════════════════════
#  2. 현황 집계 ↔ 실제 행
# ═══════════════════════════════════════════════════════════════
actual_state = Counter(r["상태"] for r in rows.values())
actual_class = Counter(r["분류"] for r in rows.values())

declared: dict[str, int] = {}
for line in idx_text.splitlines():
    if not line.startswith("|"):
        continue
    cells = [clean(c) for c in line.strip().strip("|").split("|")]
    for a, b in zip(cells, cells[1:]):
        if a in ("신규","확인","수정완료","기각","보류","이관",
                 "요건위반","코드버그","문서불일치","표준결함","합계") and b.isdigit():
            declared[a] = int(b)

mismatch = []
for k, v in declared.items():
    real = len(rows) if k == "합계" else (actual_state.get(k, 0) + actual_class.get(k, 0))
    if real != v:
        mismatch.append(f"{k}: 표기={v} 실제={real}")
t("현황 표 집계가 실제 행과 일치", not mismatch, "; ".join(mismatch))

# ═══════════════════════════════════════════════════════════════
#  3. 표준결함 총계 ↔ CLAUDE.md
# ═══════════════════════════════════════════════════════════════
std_rows = sum(1 for r in rows.values() if r["표"] == "표준결함")
claude = read(ROOT / "CLAUDE.md")

nums = [int(n) for n in re.findall(r"현재까지 \*\*(\d+)건\*\*", claude)]
t("CLAUDE.md §3.6 총계 = 표준결함 행 수",
  bool(nums) and nums[0] == std_rows, f"§3.6={nums[0] if nums else '?'} 행={std_rows}")

mm = re.search(r"0943 (\d+)건 \+ 1369-P1 (\d+)건", claude)
if mm:
    a, b = int(mm.group(1)), int(mm.group(2))
    t("CLAUDE.md 표준별 내역 합 = 총계", a + b == std_rows, f"{a}+{b}={a+b} vs {std_rows}")

ref = re.search(r"표준 실구현 장애 지점 (\d+)건", claude)
t("CLAUDE.md §9 참조표 건수 = 표준결함 행 수",
  bool(ref) and int(ref.group(1)) == std_rows,
  f"§9={ref.group(1) if ref else '?'} 행={std_rows}")

# F-125 — '이관' 상태는 README §5 정의상 "docs/standard-findings.md 로 옮겼다"는
# 뜻이다. 그 파일이 실제로 없거나 특정 F-ID 를 담지 않으면 상태와 산출물이
# 모순인데, 지금까지는 이 모순을 아무 검증기도 잡지 않았다(F-125). 표준결함
# 행 전부가 그 파일에 F-ID 로 실제 등장하는지 대조한다 — 존재 여부(파일이
# 있다)와 값 보장(그 F-ID 가 그 안에 있다)은 다르다(CLAUDE.md §6.2 F-091 원칙).
findings_doc = ROOT / "docs" / "standard-findings.md"
findings_text = read(findings_doc)
t("docs/standard-findings.md 존재 (CLAUDE.md §0 핵심 주장 4 근거)",
  findings_doc.exists(), str(findings_doc))

migrated = [fid for fid, r in rows.items() if r["표"] == "표준결함" and r["상태"] == "이관"]
absent_in_findings = sorted(fid for fid in migrated if fid not in findings_text)
t("'이관' 표준결함 전 건이 docs/standard-findings.md 에 F-ID 로 실재",
  not absent_in_findings, str(absent_in_findings))

found_ids = set(re.findall(r"F-\d{3}", findings_text))
extra_in_findings = sorted(found_ids - set(migrated))
t("docs/standard-findings.md 가 언급하는 F-ID 가 인덱스의 '이관' 표준결함과 정확히 일치",
  not extra_in_findings, str(extra_in_findings))

# F-208 — 연결 오류 응답은 다른 RSC-only Response와 달리 9byte 고정부를
# 유지한다. Protocol의 두 설명이 구현과 반대로 회귀하지 않게 직접 읽는다.
_iface = read(ROOT / "project_code" / "contracts" / "siap_iface.py")
t("FrameBuilder 연결 오류 설명이 9byte 고정부 계약과 일치 (F-208)",
  "9byte 고정부(RSC + 자리표시 NODE_PROPERTY, N=0)는 유지" in _iface
  and "RES_SET_CONNECTION은 LAYOUT의 9byte 고정부를 유지" in _iface
  and "rsc != SUCCESS 이면 node·devices 는 생략하고 RSC 만 싣는다" not in _iface)

# F-209 — 미규정 구현 결정은 §3.5와 관련 설계 문서에 남기고, 표준 자체 결함
# 19건 전용 정본으로 이관하지 않는다. 지적된 두 문맥만 좁혀 검사한다.
_frame_contract = read(ROOT / "project_code" / "contracts" / "frame.py")
_frame_spec = read(find("Frame_구조_명세서.md"))
_reply_doc = _frame_contract.partition("def reply_kind")[2].partition("\n    if kind is None:")[0]
_reply_spec = _frame_spec.partition("### 5.2")[2].partition("\n## 6.")[0]
t("위반 Notify 미규정 결정이 §3.5·관련 명세만 참조 (F-209)",
  "CLAUDE.md §3.5" in _reply_doc and "`CLAUDE.md` §3.5" in _reply_spec
  and "docs/standard-findings.md 참조" not in _reply_doc
  and "`docs/standard-findings.md`에 등재" not in _reply_spec)

# ═══════════════════════════════════════════════════════════════
#  4. DDL 객체 수 ↔ 설계 문서 서술
# ═══════════════════════════════════════════════════════════════
sql = read(find("schema.sql"))
n_trg = len(re.findall(r"CREATE TRIGGER", sql))
TABLES = set(re.findall(r"CREATE TABLE (\w+)", sql))
n_tbl = len(re.findall(r"CREATE TABLE", sql))
n_idx = len(re.findall(r"CREATE INDEX", sql))
t("schema.sql 파싱", bool(sql), f"테이블 {n_tbl} · 트리거 {n_trg} · 인덱스 {n_idx}")

DOCS = ["아키텍처_설계서.md", "DB_스키마_설계서.md", "진행보고서.md", "CLAUDE.md"]
LABELS = ((n_trg, "트리거"), (n_tbl, "테이블"), (n_idx, "인덱스"))
bad = []
for name in DOCS:
    p = ROOT / name if (ROOT / name).exists() else find(name)
    if not p:
        continue
    for line in read(p).splitlines():
        # '테이블 6개'(서브타입 테이블 수 등) 같은 국소 서술은 총계가 아니다.
        # 총계로 간주하는 조건: 세 라벨 중 둘 이상이 한 줄에 있거나, 라벨이 '트리거'인 경우.
        many = sum(1 for _, lab in LABELS if lab in line) >= 2
        for want, label in LABELS:
            if not (many or label == "트리거"):
                continue
            for got in re.findall(rf"{label}\s*\*{{0,2}}(\d+)\s*개", line):
                if int(got) != want:
                    bad.append(f"{p.name}: {label} {got} ≠ {want}")
t("설계 문서의 DDL 객체 수 서술이 schema.sql 과 일치", not bad, "; ".join(bad))

# ═══════════════════════════════════════════════════════════════
#  5. 회귀 테스트가 실제로 존재하는가
#     '수정완료' 라고 적어둔 코드버그는 해당 ID 를 검증 코드가 언급해야 한다.
# ═══════════════════════════════════════════════════════════════
# F-063 — 산출물을 쓰는 생성기(spec_verify · golden_layout)는 검증 중에 체크인된
#   파일을 덮어써서는 안 된다. 그러면 변질돼 있었다는 사실이 그 자리에서 사라진다.
# F-101 — spec_verify.py 는 이제 인자 없는 기본값 자체가 대조(비파괴)이고,
#   쓰기는 명시적 --write 로만 한다(`tools/run_all.py` 가 인자 없이 돌리는
#   전체 회귀 경로에서 매번 쓰기 모드로 실행돼 손상을 마스킹했던 결함의 재발
#   방지). golden_layout.py 는 아직 기본이 쓰기 모드라 --check 를 명시해야 한다.
VERIFIER_ARGS: dict[str, list[str]] = {
    "verify.py":        [],
    "test_contract.py": [],
    "spec_verify.py":   [],
    "api_verify.py":    [],
    "golden_layout.py": ["--check"],
    "golden_verify.py": [],
    "firmware_verify.py": [],
    "demo_verify.py": [],
    "services_verify.py": [],
    "web_verify.py": [],
    "dev_verify.py": [],
}
VERIFIERS = list(VERIFIER_ARGS)
# meta_verify.py 자신도 검증 코드다 — 자기 자신의 결함(F-050)에 대한 회귀 가드가
# 여기 들어 있으므로 탐색 대상에 포함한다.
SOURCES = tuple(VERIFIERS) + ("meta_verify.py",)
test_src = "".join(read(p) for p in ROOT.rglob("*.py")
                   if p.name in SOURCES and not _skip(p))

# F-111 · F-112 · F-113 — 위 스캔은 project_docs/**/*_verify.py 명명
# 규칙에 고정돼 있어, project_code/firmware/(C·헤더·Makefile)나 새로
# 생긴 도우미 스크립트(check_wur.py·clean.py) 안의 회귀 근거를 못
# 찾았다. 코드버그 회귀는 언어·파일명 관례를 가리지 않고 project_code/
# · tools/ 어디에나 생길 수 있으므로(F-094 "목록 고정 금지 — 디렉터리
# 전수로 본다" 와 같은 이유), 대상을 이름 목록이 아니라 두 디렉터리
# 전수 + 확장자/파일명 패턴으로 넓힌다.
_CODE_EXTS = {".py", ".c", ".h"}
def _is_makefile(p: Path) -> bool:
    return p.name in ("Makefile", "makefile", "GNUmakefile")
_extra_src = [
    p for base in (ROOT / "project_code", ROOT / "tools")
    for p in base.rglob("*")
    if p.is_file() and not _skip(p) and (p.suffix in _CODE_EXTS or _is_makefile(p))
]
test_src += "".join(read(p) for p in _extra_src)

absent = [fid for fid, r in sorted(rows.items())
          if r["분류"] == "코드버그" and r["상태"] == "수정완료" and fid not in test_src]
t("수정완료 코드버그에 대응 회귀 테스트 존재", not absent, str(absent))

# ═══════════════════════════════════════════════════════════════
#  5-a. F-097 · F-098 · F-102 · F-103 · F-104 회귀 — tools/where.py ·
#     tools/offline_verify.py · tools/run_all.py 는 project_docs/**/*_verify.py
#     명명 규칙 밖이라 위 test_src 스캔과 §6 의 CP949 실행 루프 어느 쪽도
#     다루지 않는다(offline_verify.py 는 오프라인 설치 검사 때문에 완주에
#     70초 이상 걸려 그 무거운 루프에 넣지 않는다). 반례를 직접 재현해
#     여기서만 고정한다 — pytest 파일이 아니라 이 파일 자체가 "코드버그에
#     대응하는 회귀 테스트"다.
# ═══════════════════════════════════════════════════════════════
import ast as _ast

_tools_dir = ROOT / "tools"
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))
try:
    import offline_verify as _ov
    import where as _wh
    import layer_verify as _lv
    import board_verify as _bv

    # F-105 회귀 — 상대 import(level>0)와 정적 문자열 동적 import
    # (importlib.import_module/__import__)가 계층 위반으로 잡히는가. src 를
    # 직접 넘기는 순수 함수라 파일을 실제로 쓸 필요가 없다 — path 는 패키지
    # 위치 계산에만 쓰인다(파일이 실재할 필요 없음).
    _f105_path = _lv.PROJECT_CODE / "backend" / "_synthetic.py"
    _f105_rel = _lv._top_level_modules("from ..siap import codec\n", _f105_path)
    t("F-105 회귀 - 상대 import(from ..siap import x)가 top-level 'siap' 로 해석됨",
      "siap" in _f105_rel, str(sorted(_f105_rel)))
    _f105_dyn = _lv._top_level_modules(
        'import importlib\nimportlib.import_module("siap.codec")\n', _f105_path)
    t("F-105 회귀 - importlib.import_module(\"siap.codec\") 동적 import 가 'siap' 로 잡힘",
      "siap" in _f105_dyn, str(sorted(_f105_dyn)))
    _f105_dunder = _lv._top_level_modules('__import__("siap")\n', _f105_path)
    t("F-105 회귀 - __import__(\"siap\") 동적 import 가 'siap' 로 잡힘",
      "siap" in _f105_dunder, str(sorted(_f105_dunder)))
    _f105_normal = _lv._top_level_modules(
        "from . import repository\nfrom .models import Thing\n", _f105_path)
    t("F-105 회귀 - 같은 패키지 내부 상대 import는 'siap' 오탐이 없음",
      "siap" not in _f105_normal, str(sorted(_f105_normal)))

    # F-109 회귀 — 패키지 접두어(`project_code.siap...`)와 별칭 동적 import
    # (`import_module as load`)까지 같은 최상위 이름으로 정규화되는가.
    # F-105 의 세 반례와는 다른 두(+dunder 변형 1) 표기 방식이다.
    _f109_qual_import = _lv._top_level_modules("import project_code.siap.codec\n", _f105_path)
    t("F-109 회귀 - import project_code.siap.codec 가 'siap' 로 정규화됨",
      "siap" in _f109_qual_import, str(sorted(_f109_qual_import)))
    _f109_qual_from = _lv._top_level_modules("from project_code.siap import codec\n", _f105_path)
    t("F-109 회귀 - from project_code.siap import codec 가 'siap' 로 정규화됨",
      "siap" in _f109_qual_from, str(sorted(_f109_qual_from)))
    _f109_alias = _lv._top_level_modules(
        'from importlib import import_module as load\nload("siap.codec")\n', _f105_path)
    t("F-109 회귀 - import_module 별칭(load) 호출도 'siap' 로 잡힘",
      "siap" in _f109_alias, str(sorted(_f109_alias)))
    _f109_dunder_qual = _lv._top_level_modules('__import__("project_code.siap.codec")\n', _f105_path)
    t("F-109 회귀 - __import__(\"project_code.siap.codec\") 도 'siap' 로 정규화됨",
      "siap" in _f109_dunder_qual, str(sorted(_f109_dunder_qual)))
    _f109_normal = _lv._top_level_modules(
        "import json\nfrom importlib import import_module\nimport_module('json')\n", _f105_path)
    t("F-109 회귀 - 무관한 모듈(json) 별칭 import는 'siap' 오탐이 없음",
      "siap" not in _f109_normal, str(sorted(_f109_normal)))

    # F-097 반례 1 / F-103 반례 1 — requirements.txt 유효 행을 실제로
    # 파싱하고, == 로 정확히 고정됐는지까지 보는가.
    with tempfile.TemporaryDirectory() as _tmp:
        _req = Path(_tmp) / "requirements.txt"
        _req.write_text(
            "# 주석\nfastapi==0.115.6\nuvicorn==0.34.0\npyserial==3.5\nclick==8.4.2\n",
            encoding="utf-8")
        _parsed97 = {_ov._norm_pkg(n) for n, _op, _ver in _ov._parse_requirements(_req)}
        _req.write_text("fastapi>=0.115.6\nuvicorn~=0.34.0\npyserial==3.5\n", encoding="utf-8")
        _loose = [(n, op, v) for n, op, v in _ov._parse_requirements(_req) if op != "==" or not v]
    t("F-097 회귀 - requirements.txt 를 실제로 파싱해 4번째 의존성을 잡음",
      _parsed97 == {"fastapi", "uvicorn", "pyserial", "click"}, str(sorted(_parsed97)))
    t("F-103 회귀 - >=·~= 같은 느슨한 지정자를 == 미고정으로 잡음",
      len(_loose) == 2 and {n for n, *_ in _loose} == {"fastapi", "uvicorn"}, str(_loose))

    # F-097 반례 2 — .gitignore 의 주석 줄은 규칙으로 세지 않는가.
    with tempfile.TemporaryDirectory() as _tmp2:
        _gi = Path(_tmp2) / ".gitignore"
        _gi.write_text("# .omc/ 는 주석에만 있다\n", encoding="utf-8")
        _pat97b = _ov._active_gitignore_patterns(_gi)
    t("F-097 회귀 - .gitignore 주석 줄을 활성 규칙으로 세지 않음",
      _pat97b == [], str(_pat97b))

    # F-097 반례 3 — .git/ 이 zip·실행파일 스캔 제외 목록에 실제로 들어갔는가.
    t("F-097 회귀 - .git/ 이 패키징 제외 스캔에 걸림 (_is_excluded)",
      _ov._is_excluded(ROOT / ".git" / "config"))

    # F-103 반례 2 — 같은 배포명에 서로 다른 버전이 섞인 휠을 잠금 파괴로 잡는가
    # (플랫폼·ABI 가 다른 동일 버전 휠은 허용해야 한다).
    _wv_same = [_ov._wheel_name_version(n) for n in
                ["pydantic_core-2.46.4-cp311-cp311-win_amd64.whl",
                 "pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.whl"]]
    _wv_diff = [_ov._wheel_name_version(n) for n in
                ["click-8.0.0-py3-none-any.whl", "click-9.9.9-py3-none-any.whl"]]
    t("F-103 회귀 - 휠 파일명 파싱이 배포명·버전을 정확히 분리함",
      _wv_same == [("pydantic_core", "2.46.4"), ("pydantic_core", "2.46.4")] and
      _wv_diff == [("click", "8.0.0"), ("click", "9.9.9")],
      f"{_wv_same} / {_wv_diff}")
    with tempfile.TemporaryDirectory() as _tmp3:
        _wdir = Path(_tmp3) / "project_code" / "wheels"
        _wdir.mkdir(parents=True)
        for _n in ("fastapi-0.115.6-py3-none-any.whl", "uvicorn-0.34.0-py3-none-any.whl",
                   "pyserial-3.5-py2.py3-none-any.whl",
                   "click-8.0.0-py3-none-any.whl", "click-9.9.9-py3-none-any.whl"):
            (_wdir / _n).write_bytes(b"")
        (Path(_tmp3) / "project_code" / "requirements.txt").write_text(
            "fastapi==0.115.6\nuvicorn==0.34.0\npyserial==3.5\n", encoding="utf-8")
        _orig_root = _ov.REPO_ROOT
        _ov.REPO_ROOT = Path(_tmp3)
        try:
            _ok103b, _detail103b = _ov.check_wheels_present()
        finally:
            _ov.REPO_ROOT = _orig_root
    t("F-103 회귀 - 배포명당 버전 2개(잠금 파괴)를 check_wheels_present 가 차단",
      _ok103b is False and "click" in _detail103b, _detail103b)

    # F-103 반례 3 — .gitignore 의 순서·'!' 재포함을 실제 git 의미로 판정하는가.
    if shutil.which("git"):
        with tempfile.TemporaryDirectory() as _tmp4:
            _orig_root2 = _ov.REPO_ROOT
            _ov.REPO_ROOT = Path(_tmp4)
            _real_gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
            (Path(_tmp4) / ".gitignore").write_text(
                _real_gi.replace(".omc/\n", ".omc/\n!.omc/\n", 1), encoding="utf-8")
            try:
                _ok103c, _detail103c = _ov.check_gitignore_excludes()
            finally:
                _ov.REPO_ROOT = _orig_root2
        t("F-103 회귀 - .gitignore 의 '!' 재포함(negation)을 실제 git 의미로 잡음",
          _ok103c is False and ".omc" in _detail103c, _detail103c)
    else:
        t("F-103 회귀 - .gitignore 재포함 검사", False, "git 실행 파일 없음 - 검증 불가")

    # F-098 반례 — 단계 2c/7/8 이 예전처럼 항목 1~2개로 쪼그라들지 않았는가.
    _r7 = _wh.check_stage_7()
    t("F-098 회귀 - 단계 7 출구가 렌더 확인 항목을 포함해 3건 이상",
      len(_r7) >= 3, f"{len(_r7)}건: {[d for d, *_ in _r7]}")
    t("F-098 회귀 - 단계 7의 렌더 확인 항목이 MANUAL(None)이지 자동 통과가 아님",
      any(ok is None for _, ok, _ in _r7), "")
    # F-238/F-239 로 단계 8 구조가 바뀌었다 — 죽은 Makefile 빌드(_build_and_size,
    # 40% 지표)를 제거하고 avr-size↔예산 실측은 board_verify.py(55% 정본)에 위임,
    # 물리 3종 빌드는 툴체인 의존이라 MANUAL 로 남겼다. F-098 의 원 취지("board_verify
    # 하나로 쪼그라들지 않는다 — ①빌드·③로그도 있다")는 그대로 유지되는지 본다.
    _r8 = _wh.check_stage_8()
    _r8_labels = [d for d, *_ in _r8]
    t("F-098 회귀 - 단계 8 출구가 board_verify.py 하나가 아니라 빌드(①)·로그(③)도 포함",
      len(_r8) >= 3
      and any("board_verify.py" in d for d in _r8_labels)
      and any("빌드" in d for d in _r8_labels)
      and any(("replay" in d or "logs" in d) for d in _r8_labels),
      f"{len(_r8)}건: {_r8_labels}")
    t("F-098 회귀 - 단계 8의 실측 로그·물리 빌드 항목이 MANUAL(None)이지 자동 통과가 아님",
      sum(1 for _, ok, _ in _r8 if ok is None) >= 2, "")

    # F-104 반례 — avr-size 출력을 실제로 파싱해 SRAM 예산과 비교하는가.
    # (이전에는 avr-size 종료 코드 0만 보고, 999,999,999 byte 도 통과시켰다.)
    # F-238/F-239 이후 이 파싱·예산 비교는 board_verify.py(_parse_sram_used·
    # _check_avr_size, 전체-globals 55%)가 정본으로 소유한다 — where.py 가 아니다.
    _huge = "   text\t   data\t    bss\t    dec\t    hex\tfilename\n" \
            "999999999\t999999999\t999999999\t2999999997\tb2d05dff\tfirmware.elf\n"
    _small = "   text\t   data\t    bss\t    dec\t    hex\tfilename\n" \
             "8900\t20\t300\t9220\t2404\tfirmware.elf\n"
    t("F-104 회귀 - avr-size(berkeley) 파싱이 data+bss 를 뽑음",
      _bv._parse_sram_used(_small) == 320)
    t("F-104 회귀 - Arduino IDE 'Global variables use' 형식도 파싱됨",
      _bv._parse_sram_used("Global variables use 1025 bytes (50%) of dynamic memory") == 1025)
    # board_verify._check_avr_size 는 <board>/size_report.txt 를 읽어 55% 와 대조한다.
    # FW_DIR 를 임시 디렉터리로 갈아끼워 가짜/정상 실측을 실제 판정 경로에 태운다.
    def _budget_verdict(report_text: str):
        with tempfile.TemporaryDirectory() as _tmp5:
            _bdir = Path(_tmp5) / "arduino_sensor_node"
            _bdir.mkdir(parents=True)
            (_bdir / "size_report.txt").write_text(report_text, encoding="utf-8")
            _orig_fw = _bv.FW_DIR
            _bv.FW_DIR = Path(_tmp5)
            try:
                return _bv._check_avr_size()
            finally:
                _bv.FW_DIR = _orig_fw
    _v_bad = _budget_verdict(_huge)
    _v_good = _budget_verdict(_small)
    t("F-104 회귀 - 999,999,999B 짜리 가짜 avr-size 실측을 55% 예산 초과로 차단",
      _v_bad[1] is False, str(_v_bad))
    t("F-104 회귀 - 정상 크기(320B/2048B)는 55% 예산 안으로 통과",
      _v_good[1] is True, str(_v_good))
except Exception as e:
    t("F-097·F-098·F-103·F-104 회귀 테스트 로드 및 실행", False, f"{type(e).__name__}: {e}")

# F-102 반례 1 — offline_verify.py(tools/*_verify.py 명명 규칙에 걸리는 전부)를
# 실제 CP949 기본 콘솔처럼 강제한 뒤 직접 실행한다. run_all.py 처럼 자식에
# PYTHONIOENCODING=utf-8 을 강제하면 이 버그 자체가 가려진다(F-102 현상 그대로) -
# 그래서 여기서는 반대로 cp949 를 강제해 재현 조건을 그대로 지킨다.
#
# F-108 — 검증기마다 실제 최악 실행시간이 다르다. offline_verify.py 는 6개
# Python/플랫폼 조합의 실제 --no-index 설치를 수행해 단독 정상 실행도 약
# 179초다. 전부에 같은 180초 제한을 걸면 여유가 1초도 안 남아 사소한 시스템
# 부하만으로 TimeoutExpired 가 나고, 그게 "CP949 결함"과 같은 FAIL 로 뭉뚱그려
# 보고되어 원인을 구분할 수 없었다. 실측 최악값보다 충분히 큰 개별 제한을 두고,
# 시간 초과는 크래시와 다른 사유로 표시한다.
_CP949_TIMEOUT = {"offline_verify.py": 600}   # 실측 ~179초 + 충분한 여유 (F-108)
_CP949_TIMEOUT_DEFAULT = 180


def _run_cp949(script: Path, timeout: int) -> tuple[str, str]:
    """CP949 콘솔을 강제한 채 스크립트를 직접 실행한다.
    반환: (status, detail). status ∈ {'ok', 'crash', 'timeout', 'error'}.
    F-108 — 시간 초과(설치 지연 등, 정상일 수 있음)와 비정상 종료(진짜 CP949
    결함)를 같은 예외 처리 경로로 묶지 않는다. 원인이 갈려야 재현 없이도
    보고서만 보고 무엇을 고칠지 알 수 있다."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    env["PYTHONIOENCODING"] = "cp949"
    try:
        proc = subprocess.run([sys.executable, "-B", str(script)], cwd=str(script.parent),
                               capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        out = ((e.stdout or b"") + (e.stderr or b"")).decode("utf-8", errors="replace")
        return "timeout", f"{timeout}초 제한 초과. 부분 출력 마지막 200자: {out[-200:]!r}"
    except Exception as e:
        return "error", f"{type(e).__name__}: {e}"
    if proc.returncode != 0:
        return "crash", (proc.stdout + proc.stderr).decode("utf-8", errors="replace")[-300:]
    return "ok", ""


for _tv in sorted((ROOT / "tools").glob("*_verify.py")):
    _tmo = _CP949_TIMEOUT.get(_tv.name, _CP949_TIMEOUT_DEFAULT)
    _status, _detail = _run_cp949(_tv, _tmo)
    if _status == "timeout":
        _detail = f"[시간 초과({_tmo}초 제한) - CP949 크래시와 무관, 실행시간 예산 문제(F-108)] {_detail}"
    t(f"F-102 회귀 - {_tv.name} 가 CP949 기본 콘솔에서 직접 실행돼도 죽지 않음",
      _status == "ok", _detail)

# F-108 정상 대조군 — "시간 제한이 너무 빡빡해서 정상 스크립트가 죽는다"는
# 현상 자체를 재현한다. 179초짜리 진짜 설치를 다시 돌리는 대신, 정상 종료
# 하되 시간이 걸리는 스크립트를 합성해 같은 상황을 빠르게 재연한다.
#   ① 넉넉한 제한(5초) 안에서 2초짜리 정상 스크립트는 'ok' 로 분류되어야 한다.
#   ② 빡빡한 제한(1초)에서는 'timeout' 으로 분류되어야 하고, 이때도 종료
#      코드가 아니라 '시간 초과'라는 사유가 detail 에 남아야 한다 — crash 로
#      오분류되면 F-108 이 다시 재발한 것이다.
with tempfile.TemporaryDirectory() as _tmp6:
    _slow = Path(_tmp6) / "_f108_slow_ok.py"
    _slow.write_text(
        "import time, sys\n"
        "time.sleep(2)\n"
        "print('통과')\n"   # '통과' — CP949 표현 가능 문자만 사용 (F-045 원칙)
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    _status_ok, _detail_ok = _run_cp949(_slow, 5)
    t("F-108 회귀 - 넉넉한 제한이면 느린 정상 스크립트도 'ok' 로 분류",
      _status_ok == "ok", f"status={_status_ok} detail={_detail_ok}")
    _status_to, _detail_to = _run_cp949(_slow, 1)
    t("F-108 회귀 - 빡빡한 제한에서는 'timeout' 으로 분류 (crash 로 오분류하지 않음)",
      _status_to == "timeout", f"status={_status_to} detail={_detail_to}")

# F-102 반례 2 (정적, 빠른 버전) — where.py · run_all.py 는 오프라인 설치를
# 반복 실행해(where.py 는 offline_verify.py 를 통째로 다시 부른다) 위 방식으로
# 매번 돌리기엔 비싸다. 대신 print() 에 직접 들어간 문자열 리터럴만 정적으로
# 걷어 CP949 표현 가능한지 본다 — _safe_print() 로 감싼 동적 문자열은 이미
# 런타임에 안전하게 처리되므로 대상이 아니다.
def _printed_literals(py_path: Path) -> list[str]:
    tree = _ast.parse(py_path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name) and node.func.id == "print":
            for arg in node.args:
                if isinstance(arg, _ast.Constant) and isinstance(arg.value, str):
                    out.append(arg.value)
                elif isinstance(arg, _ast.JoinedStr):
                    out.extend(v.value for v in arg.values
                                if isinstance(v, _ast.Constant) and isinstance(v.value, str))
    return out

for _tp in sorted((ROOT / "tools").glob("*.py")):
    if _tp.name == "__pycache__": continue
    _offenders = [(ch, s[:60]) for s in _printed_literals(_tp) for ch in s if not _cp949_ok(ch)]
    t(f"F-102 회귀 - {_tp.name} 의 print() 리터럴이 전부 CP949 표현 가능",
      not _offenders, str(_offenders[:3]))

# ═══════════════════════════════════════════════════════════════
#  4-a. DB 쓰기 소유권 표가 schema.sql 을 전부 덮는가 (F-057)
#       아키텍처 4.4-a 는 "테이블별 단일 소유자"를 불변식으로 선언한다.
#       표에서 빠진 테이블이 하나라도 있으면 그 불변식은 검증 불가능한 주장이다.
# ═══════════════════════════════════════════════════════════════
arch_path = find("아키텍처_설계서.md")
arch = read(arch_path)
own_sec = arch.partition("### 4.4-a")[2].partition("\n## ")[0]

def tables_in(block: str) -> set[str]:
    """소유권 **배정**만 센다 — 표 행(`|` 로 시작)과 분류 머리글에서만 추린다.
    인용문(`>`)의 해설이나 본문 설명은 배정이 아니다.
    `dsd_*` 같은 접두 표기는 펼치고, 메시지명·컬럼명은 TABLES 에 없어 걸러진다."""
    out: set[str] = set()
    lines = block.splitlines()
    for i, line in enumerate(lines):
        st = line.strip()
        if not (st.startswith("|") or i == 0):        # 표 행 또는 분류 머리글
            continue
        if re.fullmatch(r"\|[\s|:-]+\|", st):          # 구분선
            continue
        for m in re.finditer(r"`([a-z_]+)(\*)?`", st):
            name, star = m.group(1), m.group(2)
            if star:
                out |= {c for c in TABLES if c.startswith(name)}
            elif name in TABLES:
                out.add(name)
    return out

# F-059 — 분류별로 나눠 파싱한다. 전체를 하나의 set 으로 합치면 **중복 배정이
#         set 에서 소멸**해 "정확히 하나"라는 불변식의 절반(중복)을 못 본다.
#         분류 구분자는 원문자 머리표(①②③④)다.
BULLETS = "①②③④⑤⑥⑦⑧⑨"
cuts = [(m.start(), m.group(0)) for m in re.finditer(f"\\*\\*[{BULLETS}]", own_sec)]
groups: list[tuple[str, int, set[str]]] = []      # (머리표, 표기 개수, 테이블 집합)
for i, (pos, mark) in enumerate(cuts):
    block = own_sec[pos: cuts[i+1][0] if i+1 < len(cuts) else len(own_sec)]
    head = block.split("\n", 1)[0]
    dm = re.search(r"(\d+)\s*개", head)
    groups.append((mark[-1], int(dm.group(1)) if dm else -1, tables_in(block)))

t(f"소유권 분류 파싱 ({len(groups)}개 분류)", len(groups) >= 3,
  " · ".join(f"{g}={len(ts)}" for g, _, ts in groups))

# ① 누락 없음
owned = set().union(*(ts for _, _, ts in groups)) if groups else set()
missing_own = sorted(TABLES - owned)
t(f"쓰기 소유권 표가 테이블 {len(TABLES)}개를 전부 덮음 (F-057)",
  not missing_own, str(missing_own))

# ② 중복 배정 없음 — "정확히 하나"의 나머지 절반 (F-059)
seen_in: dict[str, list[str]] = {}
for mark, _, ts in groups:
    for tbl in ts: seen_in.setdefault(tbl, []).append(mark)
dup_own = sorted(f"{tbl}({''.join(ms)})" for tbl, ms in seen_in.items() if len(ms) > 1)
t("한 테이블이 두 분류에 배정되지 않음 (F-059)", not dup_own, str(dup_own))

# ③ 분류별 표기 개수 = 실제 고유 테이블 수 (문서의 숫자를 믿지 않는다)
count_bad = [f"{mark}: 표기={dec} 실제={len(ts)}"
             for mark, dec, ts in groups if dec >= 0 and dec != len(ts)]
t("분류별 표기 개수 = 실제 테이블 수 (F-059)", not count_bad, "; ".join(count_bad))

# ④ 합계 산식도 실제에서 도출한 값과 맞는가
m = re.search(r"(\d+(?:\s*\+\s*\d+)+)\s*=\s*\*\*(\d+)\*\*", own_sec)
if m:
    parts = [int(x) for x in re.findall(r"\d+", m.group(1))]
    real = [len(ts) for _, _, ts in groups]
    t("합계 산식 = 분류별 실제 수 = 테이블 수",
      parts == real and sum(parts) == int(m.group(2)) == len(TABLES),
      f"산식={parts} 실제={real} 표기합={m.group(2)} 테이블={len(TABLES)}")

# F-223 — 표 아래 요약이 표와 반대인 회귀를 막는다. 실제 구현도 같은 API
# 호출 스레드에서 send() 반환값으로 결과를 갱신해야 세 근거가 닫힌다.
_fcs = read(ROOT / "project_code" / "backend" / "services" / "fcs.py")
t("실행 결과 UPDATE 소유자가 표·요약·구현 모두 API 스레드 (F-223)",
  "API 스레드가 INSERT하고 같은 API 요청 안에서" in own_sec
  and "I/O 스레드가 나중에 응답 필드만 UPDATE" not in own_sec
  and "result_rsc=int(resp.rsc)" in _fcs and "responded_at=repository.now_iso()" in _fcs)

# F-224 — F-176/F-182 설명과 repository의 등록 주석은 디바이스 속성을 실제로
# 싣는 두 메시지만 가리켜야 한다. 연결 요청은 LAYOUT (0,0)이므로 대상이 아니다.
_repo = read(ROOT / "project_code" / "backend" / "repository.py")
_f176 = own_sec.partition("> **F-176**")[2].partition("\n>")[0]
_f182 = own_sec.partition("> **F-182**")[2].partition("\n>")[0]
_device_triggers = ("REQ_SET_DEVICE_PROPERTY", "REQ_SET_NODE_DEVICE_PROPERTY_ALL")
t("F-176·F-182 등록 트리거가 실제 디바이스 속성 메시지와 일치 (F-224)",
  all(all(k in block for k in _device_triggers) and "_handle_device_property" in block
      and "_handle_connection" not in block and "`REQ_SET_CONNECTION`" not in block
      for block in (_f176, _f182)))
_stale_repo = (
    "변경 대부분은 런타임에 `REQ_SET_CONNECTION`",
    "— REQ_SET_CONNECTION 결과",
    '"""재연결(REQ_SET_CONNECTION',
    '"첫 REQ_SET_CONNECTION 등록"',
    "장차 api.py",
)
t("repository 등록·소유권 주석에 폐기된 트리거·단계 문구 없음 (F-224)",
  not any(x in _repo for x in _stale_repo),
  str([x for x in _stale_repo if x in _repo]))

# ═══════════════════════════════════════════════════════════════
#  4-b. F-090 — 설계 산출물의 수치가 문서마다 갈리지 않는가
#       "완료" 선언 뒤에도 이전 값이 남으면 구현자가 어느 쪽을 따를지 모른다.
#       openapi.json 을 정본으로 삼아 이를 인용하는 문서를 전수 대조한다.
# ═══════════════════════════════════════════════════════════════
import json as _json
_api_p = find("openapi.json")
if _api_p:
    _api = _json.loads(read(_api_p))
    _np = len(_api["paths"])
    _no = sum(1 for v in _api["paths"].values() for k in v
              if k in ("get", "post", "patch", "put", "delete"))
    _nw = sum(1 for v in _api["paths"].values() for k in v
              if k in ("post", "patch", "put", "delete"))
    t("openapi.json 파싱", True, f"경로 {_np} · 오퍼레이션 {_no} · 쓰기 {_nw}")

    _apidoc = read(find("API_명세서.md"))
    m = re.search(r"엔드포인트 (\d+)종 \(경로 (\d+)\)", _apidoc)
    t("API 명세서의 오퍼레이션·경로 수가 openapi.json 과 일치 (F-090)",
      m is not None and int(m.group(1)) == _no and int(m.group(2)) == _np,
      f"문서 {m.groups() if m else None} 실측 ({_no}, {_np})")
    m = re.search(r"\*\*쓰기는 (\d+)건", _apidoc)
    t("API 명세서의 쓰기 건수가 openapi.json 과 일치 (F-090)",
      m is not None and int(m.group(1)) == _nw, f"문서={m.group(1) if m else None} 실측={_nw}")

    # ── F-095: 문서 두 개만 보던 것을 project_docs 전체로 넓힌다 ──────
    #    F-094 는 0937 대조표에서 나왔다 — 대상 목록에 없어서 47/47 을 유지했다.
    #    "이 문서들만 본다"는 목록은 반드시 새 문서를 놓친다. 전수로 바꾼다.
    #    역사적 전이 수치는 같은 줄에 시점 표시가 있으면 통과시킨다.
    _HIST = ("당시", "이전", "한때", "->", "→", "F-090", "F-094", "차 검증", "라운드")
    #    대상은 '설계 문서'다. 발견 기록(fix_log)·삭제 대기(_to_delete)·스테이징
    #    사본(_stage*)·구현 코드(project_code)는 제외한다 — 그 안에는 과거 수치를
    #    인용한 처리 기록이 있고, 그것은 역사이므로 고쳐서는 안 된다.
    NOT_DESIGN = {"fix_log", "_to_delete", "project_code"}
    def _is_design(q) -> bool:
        return not _skip(q) and not any(
            part in NOT_DESIGN or part.startswith("_stage") for part in q.parts)
    _docs = sorted(q for q in ROOT.rglob("*.md") if _is_design(q))
    _drift = []
    for _p in _docs:
        for _ln in read(_p).splitlines():
            if any(_h in _ln for _h in _HIST): continue
            for _m in re.finditer(r"쓰기\s*\*{0,2}(\d+)\s*건", _ln):
                if int(_m.group(1)) != _nw:
                    _drift.append(f"{_p.name}:{_m.group(1)}")
    t(f"쓰기 건수를 인용한 문서 {len(_docs)}개가 전부 실측과 일치 (F-090 · F-095)",
      not _drift, str(sorted(set(_drift))))

    # 오퍼레이션·경로 수도 같은 방식으로 전수 대조한다
    _drift2 = []
    for _p in _docs:
        for _ln in read(_p).splitlines():
            if any(_h in _ln for _h in _HIST): continue
            for _m in re.finditer(r"(?:오퍼레이션|엔드포인트)\s*\*{0,2}(\d+)\s*(?:종|개|건)", _ln):
                if int(_m.group(1)) != _no: _drift2.append(f"{_p.name}:op={_m.group(1)}")
            for _m in re.finditer(r"경로\s*\*{0,2}(\d+)\s*(?:종|개)", _ln):
                if int(_m.group(1)) != _np: _drift2.append(f"{_p.name}:path={_m.group(1)}")
    t("오퍼레이션·경로 수를 인용한 문서가 전부 실측과 일치 (F-095)",
      not _drift2, str(sorted(set(_drift2))))

    # 제약 개수 주장은 실제 DDL 과 대조한다 (F-091 — 문서가 DDL 보다 강한 보장을 주장했다)
    _sql_p = find("schema.sql")
    if _sql_p:
        import sqlite3 as _sq
        _c = _sq.connect(":memory:"); _c.executescript(read(_sql_p))
        _ntrig = _c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
        _rej_trig = _c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'"
                               " AND tbl_name='control_rule' AND sql LIKE '%reject%'").fetchone()[0]
        _rule_ddl = _c.execute("SELECT sql FROM sqlite_master WHERE name='control_rule'").fetchone()[0]
        # F-184 — 시간 형식(ISO 8601) GLOB 검사를 모든 시간 컬럼에 넓히며
        # `rejected_at`에도 걸었다. 이 줄은 컬럼명에 "reject"가 들어 있어
        # 문자열 매칭에는 걸리지만, "거부 워크플로 자체의 제약"(거부자·
        # 거부시각·거부사유의 존재·일관성·배타 규칙 — 화면 설계서 §의
        # "거부 관련 CHECK"가 가리키는 대상)이 아니라 다른 모든 시간
        # 컬럼과 동일한 형식 검사다. GLOB 패턴은 그 형식 검사의 표식이므로
        # 제외한다 — 안 그러면 시간 형식 검사를 컬럼 하나 늘릴 때마다
        # "거부 제약"이 함께 느는 것처럼 보인다.
        _rej_chk = sum(1 for _l in _rule_ddl.splitlines()
                       if "CHECK" in _l and "GLOB" not in _l
                       and ("reject" in _l.lower() or "approved_at IS NULL OR rejected_at" in _l))
        _c.close()
        # '트리거 N개' 는 총계 주장이다. '트리거 N종' 은 부분집합(승인 봉인 · 실행 등)
        # 을 가리키는 관용 표기라 총계와 비교하면 오탐이 된다 — 아래에서 따로 본다.
        _td = []
        for _p in _docs:
            for _ln in read(_p).splitlines():
                if any(_h in _ln for _h in _HIST): continue
                for _m in re.finditer(r"트리거\s*\*{0,2}(\d+)\s*개", _ln):
                    if int(_m.group(1)) != _ntrig: _td.append(f"{_p.name}:{_m.group(1)}")
        t(f"트리거 총계를 인용한 문서가 DDL 실측({_ntrig}개)과 일치 (F-091 · F-095)",
          not _td, str(sorted(set(_td))))

        # F-091 의 실제 지적: 화면 설계서가 거부 제약을 'CHECK 3종 · 트리거 3종' 이라
        # 적었는데 DDL 은 CHECK 4 · 트리거 1 이었다. 부분집합 주장도 실물과 맞춰야 한다.
        _web = find("화면_설계서.md")
        if _web:
            _wt = read(_web)
            _mc = re.search(r"거부 관련 CHECK\*{0,2}\s*(\d+)\s*종", _wt)
            _mt = re.search(r"\*\*트리거 (\d+)종\*\*\(`trg_rule_reject_immutable`\)", _wt)
            t(f"화면 설계서의 거부 제약 주장이 DDL 과 일치 (CHECK {_rej_chk} · 트리거 {_rej_trig}, F-091)",
              _mc is not None and int(_mc.group(1)) == _rej_chk
              and _mt is not None and int(_mt.group(1)) == _rej_trig,
              f"문서=(CHECK {_mc.group(1) if _mc else None}, 트리거 {_mt.group(1) if _mt else None})")

        # F-202 — 위 검사는 화면_설계서.md(Markdown) 만 본다. `_docs` 전수
        # 순회(§4-b)도 project_docs/**/*.md 만 훑어 openapi.json 은 애초에
        # 대상이 아니다. 그런데 `rejectRule` 오퍼레이션의 `description` 이
        # 같은 "CHECK N종과 트리거 N종" 주장을 JSON 문자열로 독립 서술하고
        # 있어, F-091이 화면 설계서·DDL 은 맞췄어도 이 자리는 옛 수치(CHECK
        # 3·트리거 3)로 그대로 남았다(F-202, 재현: `rg "CHECK 3종과 트리거
        # 3종" project_docs/api/openapi.json`). 여기서 그 문자열 하나를
        # 직접 대조한다 — 대상을 넓히지 않고 이미 아는 취약점(JSON 설명
        # 필드)만 정확히 겨눈다.
        if _api_p:
            _reject_desc = ""
            for _v in _api.get("paths", {}).values():
                _op = _v.get("post", {})
                if _op.get("operationId") == "rejectRule":
                    _reject_desc = _op.get("description", "")
                    break
            _mc2 = re.search(r"CHECK\s*(\d+)\s*종", _reject_desc)
            _mt2 = re.search(r"트리거\s*(\d+)\s*종", _reject_desc)
            t(f"openapi.json rejectRule 설명의 거부 제약 주장이 DDL 과 일치 (CHECK {_rej_chk} · 트리거 {_rej_trig}, F-202)",
              bool(_reject_desc) and _mc2 is not None and int(_mc2.group(1)) == _rej_chk
              and _mt2 is not None and int(_mt2.group(1)) == _rej_trig,
              f"openapi.json=(CHECK {_mc2.group(1) if _mc2 else None}, 트리거 {_mt2.group(1) if _mt2 else None})")
        # 승인 봉인 트리거 — API 명세서가 'DB 트리거 7종' 이라 적는다. 그 7종의
        # 정본은 DB 스키마 설계서 §4 의 봉인 트리거 표다. 세 산출물을 함께 본다:
        #   API 명세서의 숫자  <->  설계서 표의 행 수  <->  DDL 에 실재하는 이름
        _c2 = _sq.connect(":memory:"); _c2.executescript(read(_sql_p))
        _alltrig = {r[0] for r in _c2.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        _c2.close()
        _dbdoc = read(find("DB_스키마_설계서.md"))
        _seal_names = re.findall(r"^\| `(trg_\w+)` \|", 
            _dbdoc.split("**\u2463 승인\u00b7거부 기록은 사후에 봉인된다**")[-1].split("\n\n> ")[0],
            re.M)
        _ghost = [n for n in _seal_names if n not in _alltrig]
        _apidoc2 = read(find("API_명세서.md"))
        _ms = re.findall(r"DB 트리거 (\d+)종", _apidoc2)
        t(f"승인 봉인 트리거 {len(_seal_names)}종이 전부 DDL 에 실재 (F-091)",
          _seal_names and not _ghost, str(_ghost))
        t(f"API 명세서의 봉인 트리거 수가 설계서 표와 일치 ({len(_seal_names)}종, F-091)",
          bool(_ms) and all(int(x) == len(_seal_names) for x in _ms),
          f"API 명세서={_ms} 설계서 표={len(_seal_names)}행")

    # 검증기 실측 통과 수 ↔ 문서 표기
    _pairs = [("api_verify.py", "API_명세서.md", r"api_verify\.py` — \*\*(\d+)/\d+ 통과"),
              ("api_verify.py", "API_명세서.md", r"검증 결과 — (\d+)/\d+ 통과")]
    _vd = []
    for _vf, _doc, _pat in _pairs:
        _vp, _dp = find(_vf), find(_doc)
        if not _vp or not _dp: continue
        _r = subprocess.run([sys.executable, "-B", str(_vp)], capture_output=True,
                            cwd=str(_vp.parent), timeout=120)
        _out = _r.stdout.decode("utf-8", "replace")
        _real = re.search(r"(\d+)/(\d+) 통과", _out)
        for _m in re.finditer(_pat, read(_dp)):
            if _real and _m.group(1) != _real.group(1):
                _vd.append(f"{_doc}: 표기 {_m.group(1)} 실측 {_real.group(1)}")
    t("문서가 인용한 검증 통과 수가 실측과 일치 (F-090)", not _vd, str(_vd))

# ═══════════════════════════════════════════════════════════════
#  5-a. CLAUDE.md 1 금지 사항 — 제출 실격 사유를 기계로 검사한다
#       지금까지 수동 grep 이었다. 제출 당일에 처음 돌리면 늦다.
# ═══════════════════════════════════════════════════════════════
SECRET = re.compile(r"api[_-]?key|password|passwd|secret|@author", re.I)
SYNTH  = re.compile(r"random\.(uniform|randint|random|gauss)|math\.sin|np\.random")
BINARY = ("*.hex", "*.bin", "*.elf", "*.exe", "*.apk")

# 오탐 허용 목록 — 반드시 사유를 적는다
ALLOW = {
    # OpenAPI 3.1 이 헤더 기반 보안 스킴에 요구하는 예약어다. 비밀정보가 아니다.
    ('openapi.json', '"type": "apiKey"'),
    # firmware_verify.py 는 설계서에서 같은 패턴을 찾는 검증기다. 패턴 자체를
    # 소스에 적을 수밖에 없다 — fix_log/ 를 통째로 제외한 것과 같은 이유다.
    ('firmware_verify.py', 'SECRET  = re.compile'),
    ('firmware_verify.py', 'SECRET.search'),
    # 펌웨어 7.4 의 Wi-Fi 자격증명 파일명 규약(.gitignore 대상)을 가리키는
    # 오탐 허용 목록 항목이다. 값이 아니라 "커밋하지 말라"는 규칙이다.
    ('firmware_verify.py', '"secrets.h",'),
    # 단계 8 — 같은 파일명 규약. board_verify.py 의 필수 파일 매니페스트와
    # esp32_node.ino 의 include, secrets.h.example 예시 파일 자신이 이 이름을
    # 문자열로 담는다(값이 아니라 파일명 규약, CLAUDE.md §1-2 / 펌웨어 §7.4).
    ('board_verify.py', 'secrets.h.example'),
    ('esp32_node.ino', 'secrets.h'),
    ('secrets.h.example', 'secrets.h'),
    # demo_verify.py 도 같은 이유다 — 시연 시나리오의 블라인드 점검표에서 같은
    # 패턴을 찾는 검증기이므로 패턴을 소스에 적을 수밖에 없다.
    ('demo_verify.py', 'SECRET  = re.compile'),
    ('demo_verify.py', 'SECRET.search'),
    ('services_verify.py', 'SECRET  = re.compile'),
    ('services_verify.py', 'SECRET.search'),
    ('web_verify.py', 'SECRET  = re.compile'),
    ('web_verify.py', 'SECRET.search'),
    # dev_verify.py 도 같은 이유 — 개발 착수 지시서를 같은 패턴으로 훑는다
    ('dev_verify.py', 'SECRET  = re.compile'),
    ('dev_verify.py', 'SECRET.search'),
    # 단계 6 — 기상청 API 키 부재 시 fixtures 목업 폴백(CLAUDE.md §7). 아래는
    # 전부 "환경변수 이름"만 언급한다 — 실제 키 값을 담은 줄이 아니다(값은
    # os.environ.get() 이 런타임에 읽을 뿐 이 저장소 어디에도 없다).
    # "api[_-]?key" 패턴이 "KMA_API_KEY"·"API_KEY_ENV"(둘 다 환경변수
    # 이름/그 이름을 담은 상수명일 뿐 값이 아니다)에도 그대로 걸려 생기는
    # 오탐이다. 값 자체를 담을 수 있는 매개변수는 `kma_key`로 이름을 바꿔
    # 패턴에 안 걸리게 했다(dms.py) — 이름 자체가 상수·환경변수 이름인
    # 아래 항목만 허용 목록에 남긴다.
    ('api.py', 'dms.API_KEY_ENV'),
    ('kma_forecast_mock.json', 'KMA_API_KEY 환경변수'),
    ('seed.sql', '환경변수 KMA_API_KEY'),
    ('dms.py', 'API_KEY_ENV = "KMA_API_KEY"'),
    ('dms.py', '네트워크 필수 의존 금지") `KMA_API_KEY`가 있을 때만'),
    ('dms.py', 'kma_key = os.environ.get(API_KEY_ENV)'),
    ('test_api.py', 'KMA_API_KEY 미설정'),
}
def allowed(fname: str, line: str) -> bool:
    return any(f == fname and frag in line for f, frag in ALLOW)

hits_secret, hits_synth = [], []
for q in ROOT.rglob("*"):
    if _skip(q) or not q.is_file(): continue
    if q.suffix not in (".py", ".sql", ".json", ".c", ".h", ".ino", ".md"): continue
    if q.parent.name == "fix_log": continue      # 결함 기록은 패턴을 인용한다
    try: text = q.read_text(encoding="utf-8")
    except Exception: continue
    for i, line in enumerate(text.splitlines(), 1):
        if q.suffix != ".md" and SECRET.search(line) and not allowed(q.name, line):
            hits_secret.append(f"{q.name}:{i}")
        if q.suffix in (".py", ".c", ".h", ".ino") and SYNTH.search(line):
            hits_synth.append(f"{q.name}:{i}")
t("금지 - 비밀정보·개인식별 패턴 없음 (CLAUDE.md 1 #2 #4)", not hits_secret, str(hits_secret[:5]))

# ── F-070: 개인 절대 경로 — .md 를 포함해 전수로 본다 ─────────────
#    SECRET 스캔은 .md 를 건너뛰고 fix_log 도 제외한다(패턴 인용 때문). 그런데
#    개인 경로는 정확히 그 두 곳에 남아 있었다. 별도 패턴으로 다시 훑는다.
#    <이름> 같은 자리표시자는 식별정보가 아니므로 실제 사용자명만 잡는다.
PERSONAL = re.compile(
    r"[A-Za-z]:[\\/]Users[\\/](?!<)[A-Za-z0-9._-]+"      # C:\Users\<실명>
    r"|/home/(?!runner\b|user\b)[a-z][a-z0-9._-]*"          # /home/<실명>
    r"|/Users/(?!shared\b)[A-Za-z][A-Za-z0-9._-]*"           # macOS
)
hits_path = []
for q in ROOT.rglob("*"):
    if _skip(q) or not q.is_file(): continue
    if q.suffix not in (".py", ".sql", ".json", ".c", ".h", ".ino", ".md", ".txt"): continue
    # 표준 원문 본체(이미지 폴더·PDF)만 건너뛴다. 같은 폴더의 진행보고서·공고문은 본다.
    if any(part.endswith("_artifacts") for part in q.parts): continue
    try: text = q.read_text(encoding="utf-8")
    except Exception: continue
    for i, line in enumerate(text.splitlines(), 1):
        if q.name == "meta_verify.py" and "PERSONAL" in line: continue   # 이 패턴 자신
        if PERSONAL.search(line): hits_path.append(f"{q.name}:{i}")
t("금지 - 개인 절대 경로 없음 (CLAUDE.md 1 #4, F-070)", not hits_path, str(hits_path[:5]))
t("금지 - 합성 데이터 생성 호출 없음 (CLAUDE.md 1 #1)", not hits_synth, str(hits_synth[:5]))

bins = [q.name for pat in BINARY for q in ROOT.rglob(pat) if not _skip(q)]
t("금지 - 실행파일 없음 (CLAUDE.md 1 #3)", not bins, str(bins[:5]))

# ═══════════════════════════════════════════════════════════════
#  6. 재현성 — 검증기 출력이 CP949 콘솔에서 표현 가능한가 (F-045)
#     심사자 다수가 한국어 Windows 기본 환경이다. 표현 불가 문자 하나면
#     `python verify.py` 가 UnicodeEncodeError 로 중단된다.
# ═══════════════════════════════════════════════════════════════
import subprocess

import os

for name in VERIFIERS:
    p = find(name)
    if not p:
        t(f"{name} 존재", False, "파일 없음"); continue
    # F-050 — text=True/encoding= 로 받으면 안 된다.
    #   Windows 의 subprocess 는 리더 스레드에서 디코딩하는데, 그 스레드가
    #   UnicodeDecodeError 로 죽어도 run() 은 예외 없이 stdout=None, returncode=0 을
    #   돌려준다. 검사하려던 출력이 통째로 사라진 채 PASS 가 찍힌다.
    #   -> bytes 로 받고, 디코딩은 여기서 명시적으로 하며, 실패는 FAIL 이다.
    # 자식의 stdout 인코딩을 UTF-8 로 고정해 바이트열을 플랫폼 무관하게 만든다.
    #   (고정하지 않으면 자식의 F-045 가드가 문자를 '?' 로 바꿔 검사 대상이 사라진다)
    env = os.environ | {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        run = subprocess.run([sys.executable, "-B", str(p), *VERIFIER_ARGS[name]],
                             capture_output=True, cwd=str(p.parent), timeout=120, env=env)
    except Exception as e:
        t(f"{name} CP949 콘솔 출력 가능", False, f"실행 실패: {e}")
        t(f"{name} 종료코드 0", False, "실행 실패"); continue

    raw = (run.stdout or b"") + (run.stderr or b"")
    if run.stdout is None:
        t(f"{name} CP949 콘솔 출력 가능", False, "stdout 을 받지 못했다 (F-050)")
    elif not raw:
        t(f"{name} CP949 콘솔 출력 가능", False, "출력이 비어 있다 - 검사 대상이 없다")
    else:
        try:
            text = raw.decode("utf-8")            # strict
        except UnicodeDecodeError as e:
            t(f"{name} CP949 콘솔 출력 가능", False, f"UTF-8 디코딩 실패: {e}")
        else:
            offenders = sorted({f"U+{ord(ch):04X} {ch!r}"
                                for ch in text if not _cp949_ok(ch)})
            t(f"{name} CP949 콘솔 출력 가능 ({len(text)}자)",
              not offenders, "; ".join(offenders[:5]))
    t(f"{name} 종료코드 0", run.returncode == 0, f"exit={run.returncode}")

# ═══════════════════════════════════════════════════════════════
w = max(len(n) for _, n, _ in R)
print("fix_log 메타 검증  (F-043)\n")
for ok, n, note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
passed = sum(1 for o, *_ in R if o)
print(f"\n  {passed}/{len(R)} 통과")
sys.exit(0 if passed == len(R) else 1)
