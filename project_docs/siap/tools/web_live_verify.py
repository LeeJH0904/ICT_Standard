#!/usr/bin/env python3
"""tools/web_live_verify.py — web/ 실물이 openapi.json·화면_설계서 §10 을
실제로 지키는가 (단계 7, 개발_착수_지시서 §3.9 신설).

project_docs/web/web_verify.py 는 web/*.html 이 생기면 자동으로 lang·
landmark·skip-link 같은 정적 마크업 8항목을 검사한다(§8.3). 이 검증기는
그 바깥의 세 가지를 본다 — 전부 web/ 실물 텍스트를 직접 파싱한다(실 서버
기동도 headless 브라우저도 필요 없다):

  1. static/api.js 의 오퍼레이션별 fetch 경로가 openapi.json 의 실제 경로와
     맞는가, 각 화면(html)이 부르는 api.<name>() 이 api.js 에 실재하는가·
     api.js 가 만든 오퍼레이션이 최소 하나의 화면에서 쓰이는가(양방향)
  2. 화면_설계서.md §10 금지 6종 — 외부 CDN·번들러·localStorage 는 web_verify.py
     와 같은 패턴으로 다시 확인하고, "위반 코드→한국어 매핑"·"Subtype→종류명
     매핑"·"비트 언팩"·"미승인 규칙의 실행 경로"는 이 스크립트가 추가로 본다
  3. static/app.css 의 CONTRAST-PAIRS 선언을 읽어 상대 휘도비를 실제로
     계산한다(§8.3 8번 — "실제로 계산한다") — 4.5 미만이면 FAIL

명시적 한계: 2번의 "비트 언팩 없음"은 `<<`·`>>`(시프트) 존재 여부만 본다.
`&`(AND) 단독 문자는 URL 쿼리 문자열("a=1&b=2")·문자열 리터럴과 구별할
정적 분석기가 없어 검사하지 않는다 — 오탐이 실질 오류보다 흔해 대신
services_verify.py(F-195)처럼 한계를 그대로 적는다.

실행: python tools/web_live_verify.py   (저장소 루트에서)
종료 코드: 통과 0 / 실패 1
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

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
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "project_code" / "web"
STATIC_DIR = WEB_DIR / "static"
API_JSON = REPO_ROOT / "project_docs" / "api" / "openapi.json"

R: list[tuple[bool, str, str]] = []


def t(name: str, ok: bool, note: str = "") -> None:
    R.append((bool(ok), name, note))


def _report_and_exit() -> int:
    w = max((len(n) for _, n, _ in R), default=0)
    print("web/ 실물 검증 - fetch-라우트 대조 · 금지 6종 · 명도대비 (단계 7)\n")
    for ok, n, note in R:
        print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
    p = sum(1 for o, *_ in R if o)
    print(f"\n  {p}/{len(R)} 통과")
    return 0 if p == len(R) else 1


if not WEB_DIR.is_dir() or not list(WEB_DIR.glob("*.html")):
    t("web/ 실물 없음 - 단계 7 구현 전이므로 건너뛴다", True, "구현 후 자동 활성")
    sys.exit(_report_and_exit())

HTML_FILES = sorted(WEB_DIR.glob("*.html"))
JS_FILES = sorted(STATIC_DIR.glob("*.js")) if STATIC_DIR.is_dir() else []
CSS_FILES = sorted(STATIC_DIR.glob("*.css")) if STATIC_DIR.is_dir() else []
HTML_TXT = {p.name: p.read_text(encoding="utf-8") for p in HTML_FILES}
JS_TXT = {p.name: p.read_text(encoding="utf-8") for p in JS_FILES}
CSS_TXT = {p.name: p.read_text(encoding="utf-8") for p in CSS_FILES}
INLINE_JS_TXT = extract_inline_scripts(HTML_TXT)
SCRIPT_TXT = {**JS_TXT, **INLINE_JS_TXT}
ALL_TXT = {**HTML_TXT, **JS_TXT}

# ═══════════════════════════════════════════════════════════════
#  1. fetch 경로 ↔ 실행 라우트(openapi.json)
# ═══════════════════════════════════════════════════════════════
API = json.loads(API_JSON.read_text(encoding="utf-8")) if API_JSON.exists() else {"paths": {}}
OPS: dict[str, tuple[str, str]] = {}
for p, methods in API.get("paths", {}).items():
    for m, op in methods.items():
        if m in ("get", "post", "put", "patch", "delete"):
            OPS[op["operationId"]] = (m.upper(), p)
t(f"openapi.json 오퍼레이션 {len(OPS)}종 적재", bool(OPS))

api_js = JS_TXT.get("api.js", "")
# api.js 안의 `request("METHOD", "/path", ...)` 호출을 오퍼레이션 이름과 짝짓는다
# — 파일 구조상 각 오퍼레이션은 `opName: (...) => request("M", "/path"...)` 한 줄이다.
DEF_RE = re.compile(r"(\w+):\s*\([^)]*\)\s*=>\s*request\(\s*\"(\w+)\"\s*,\s*[`\"]([^`\"]+)[`\"]")
api_js_defs: dict[str, tuple[str, str]] = {}
for name, method, path in DEF_RE.findall(api_js):
    # 템플릿 리터럴의 `${x}` 를 openapi 의 `{x}` 표기로 정규화한다
    norm = re.sub(r"\$\{(\w+)\}", r"{\1}", path)
    api_js_defs[name] = (method, norm)
t(f"api.js 오퍼레이션 정의 {len(api_js_defs)}종 파싱", bool(api_js_defs), str(sorted(api_js_defs)))

mismatched = []
for name, (method, path) in api_js_defs.items():
    want = OPS.get(name)
    if want is None:
        mismatched.append(f"{name}: openapi 에 없음")
        continue
    want_method, want_path = want
    want_suffix = want_path.removeprefix("/api/v1")
    if method != want_method or path != want_suffix:
        mismatched.append(f"{name}: api.js=({method},{path}) openapi=({want_method},{want_suffix})")
t("api.js 의 모든 오퍼레이션이 openapi.json 라우트와 일치", not mismatched, "; ".join(mismatched[:5]))

# ── 각 화면이 부르는 api.<name>() 이 api.js 에 실재하는가 ──────────
CALL_RE = re.compile(r"\bapi\.(\w+)\s*\(")
used_by_screen: dict[str, set[str]] = {}
for fname, txt in HTML_TXT.items():
    used_by_screen[fname] = set(CALL_RE.findall(txt))

ghost_calls = []
for fname, names in used_by_screen.items():
    for n in names:
        if n not in api_js_defs:
            ghost_calls.append(f"{fname}:{n}")
t("화면이 부르는 api.*() 이 전부 api.js 에 실재", not ghost_calls, str(ghost_calls))

all_used = {n for names in used_by_screen.values() for n in names}
unused_defs = sorted(set(api_js_defs) - all_used)
t("api.js 의 오퍼레이션이 전부 최소 한 화면에서 쓰인다", not unused_defs, str(unused_defs))

# ── F-201 — 위 두 검사(115~121행)는 "화면이 부르는 것이 api.js 에 있는가"
#    "api.js 오퍼레이션이 어딘가에서는 쓰이는가"만 본다. 어느 쪽도 화면_
#    설계서.md §2.1 "화면 ↔ API 대응표"와 대조하지 않는다 — 그래서 그
#    표가 실제 호출 4종(verify.html 의 listAlerts, rules.html 의
#    listPublicDataSources·listNodes·listNodeDevices)을 누락한 채로도
#    이 파일과 project_docs/web/web_verify.py 양쪽 다 통과했다(전자는
#    표를 openapi.json 하고만, 후자는 구현 호출을 api.js 하고만 대조해
#    각각 62/62·16/16 이었다 — 재현: `rg -n
#    "api\\.(listAlerts|listPublicDataSources|listNodes|listNodeDevices)"
#    web/verify.html web/rules.html` 은 4건을 찾지만 표에는 없었다). 여기서
#    §2.1 표를 직접 파싱해 화면별 읽기 칸을 실제 GET 호출 집합과 **양방향**
#    대조한다 — `streamEvents` 는 api.js 오퍼레이션이 아니라 stream.js 의
#    `connectStream()` 을 가리키는 표기라 비교에서 제외한다.
SCREEN_DOC = REPO_ROOT / "project_docs" / "web" / "화면_설계서.md"
screen_doc_txt = SCREEN_DOC.read_text(encoding="utf-8") if SCREEN_DOC.exists() else ""
MAP_ROW_RE = re.compile(r"^\|\s*`?(\w+\.html)`?\s*\|(.+?)\|(.+?)\|\s*$", re.M)
doc_read_by_screen: dict[str, set[str]] = {
    fname: set(re.findall(r"`(\w+)`", read_col)) - {"streamEvents"}
    for fname, read_col, _write_col in MAP_ROW_RE.findall(screen_doc_txt)
}
t(f"화면_설계서.md §2.1 대응표 {len(doc_read_by_screen)}행 파싱",
  len(doc_read_by_screen) == 4, str(sorted(doc_read_by_screen)))

actual_read_by_screen: dict[str, set[str]] = {
    fname: {n for n in names if api_js_defs.get(n, ("", ""))[0] == "GET"}
    for fname, names in used_by_screen.items()
}

mapping_drift = []
for fname in sorted(set(doc_read_by_screen) | set(actual_read_by_screen)):
    missing_in_doc = actual_read_by_screen.get(fname, set()) - doc_read_by_screen.get(fname, set())
    missing_in_impl = doc_read_by_screen.get(fname, set()) - actual_read_by_screen.get(fname, set())
    if missing_in_doc:
        mapping_drift.append(f"{fname}: 문서 누락 {sorted(missing_in_doc)}")
    if missing_in_impl:
        mapping_drift.append(f"{fname}: 구현 누락 {sorted(missing_in_impl)}")
t("화면_설계서.md §2.1 읽기 칸이 실제 GET 호출과 화면별로 정확히 일치 (F-201)",
  not mapping_drift, "; ".join(mapping_drift))

# ── F-200 — 화면_설계서.md §3.2 "누락 보정": 폴백 중 놓친 프레임은 재연결
#    직후 listFrames?since= 로 채운다. `connectStream()`이 재연결을 아는
#    유일한 지점(stream.js)이고, "무엇을 since= 로 조회할지"는 verify.html
#    만 안다 — 두 파일이 실제로 결선돼 있는지 텍스트로 확인한다(헤드리스
#    브라우저로 단절·재연결을 실제로 재현하는 것은 이 환경 밖이다, 원 신고
#    F-200 재현 기록과 같은 한계).
stream_js = JS_TXT.get("stream.js", "")
verify_html = HTML_TXT.get("verify.html", "")
missing_recovery = []
if "onReconnect" not in stream_js:
    missing_recovery.append("stream.js: onReconnect 훅 없음")
if not re.search(r"\bonReconnect\s*:", verify_html):
    missing_recovery.append("verify.html: connectStream({onReconnect:...}) 결선 없음")
if not re.search(r"\bsince\s*[:,]", verify_html):
    missing_recovery.append("verify.html: since= 조회가 없음")
t("재연결 시 listFrames?since= 로 누락 프레임을 복구하는 결선이 있다 (F-200)",
  not missing_recovery, str(missing_recovery))

recovery_issues = recovery_pagination_issues(api_js, verify_html)
t("재연결 누락 복구가 until 스냅샷의 total까지 모든 offset 페이지를 소비한다 (F-205)",
  not recovery_issues, str(recovery_issues))
cursor_issues = recovery_cursor_issues(stream_js, verify_html)
t("폴링 중에도 최초 SSE 단절의 연속 커서를 복구 성공까지 보존한다 (F-233)",
  not cursor_issues, str(cursor_issues))

# ── F-197 — 위 두 검사는 api.js 의 request() 래퍼 정의만 본다. 화면이나
#    다른 정적 모듈이 그 래퍼를 거치지 않고 직접 fetch() 를 부르면(존재하지
#    않는 라우트든 외부 URL 이든) 위 "일치" 판정 자체가 그 호출을 아예 보지
#    못해 조용히 통과했다 — 재현: a11y.js 끝에
#    `fetch("https://example.invalid/unlisted", {method:"POST"})` 를 추가해도
#    62/62·16/16 이 그대로 통과함을 확인(GPT 재현, 임시 사본에서 검증 후 삭제).
#    api.js 밖의 모든 fetch() 호출을 무조건 위반으로 잡는다 — api.js 자신도
#    request() 안 1곳 외에는 fetch() 를 부르지 않는지 함께 확인한다.
FETCH_RE = re.compile(r"\bfetch\s*\(")
direct_fetch = [f"{f}({len(FETCH_RE.findall(txt))}건)" for f, txt in ALL_TXT.items()
                if f != "api.js" and FETCH_RE.search(txt)]
t("api.js 밖에서 직접 fetch() 를 호출하지 않는다 (F-197)", not direct_fetch, str(direct_fetch))

api_js_fetch_count = len(FETCH_RE.findall(api_js))
t("api.js 자신도 request() 안 1곳에서만 fetch() 를 부른다 (F-197)",
  api_js_fetch_count == 1, f"{api_js_fetch_count}건")

# 문자열 리터럴로 외부 절대 URL 을 fetch() 에 직접 넘기는 경우 — 위 두 검사를
# 우회해 api.js 내부에 추가되더라도 잡는다(변수 경유 호출은 정적 분석 한계 밖).
EXTERNAL_FETCH_RE = re.compile(r'fetch\s*\(\s*[`"\']https?://')
external_fetch = [f for f, txt in ALL_TXT.items() if EXTERNAL_FETCH_RE.search(txt)]
t("fetch() 에 외부 절대 URL 리터럴을 직접 넘기지 않는다 (F-197)", not external_fetch, str(external_fetch))

# ═══════════════════════════════════════════════════════════════
#  2. 화면_설계서.md §10 금지 6종
# ═══════════════════════════════════════════════════════════════
ext_ref = [f for f, txt in ALL_TXT.items()
           if re.search(r'(src|href)\s*=\s*["\']https?://', txt)]
ext_ref.extend(external_css_references(CSS_TXT))
t("외부 스크립트·폰트·CDN 참조 0건", not ext_ref, str(ext_ref))

bundler = [f for f, txt in ALL_TXT.items() if re.search(r"node_modules|webpack|vite|rollup|package\.json", txt)]
t("번들러·node_modules 흔적 0건 (빌드 없음)", not bundler, str(bundler))

storage_use = [f for f, txt in ALL_TXT.items() if re.search(r"\blocalStorage\b|\bsessionStorage\b", txt)]
t("localStorage·sessionStorage 사용 0건 (재현성)", not storage_use, str(storage_use))

# RSC/NEC 코드 → 한국어 문구 매핑, Subtype 코드 → 종류명 매핑이 없는가.
# web_verify.py 의 자동 검사(JS 한정)와 같은 패턴을 HTML 인라인 스크립트까지 넓혀 다시 본다.
CODE_MAP_PATTERN = re.compile(r"INVALID_(VERSION|FORMAT|NODE_ID|GCG_ID|DEVICE_ID|DATA_TYPE|DATA_SUBTYPE|TRANSMISSION_TYPE)"
                               r"|ERROR_BATTERY|ERROR_PWR|0x8[0-9A-F]\b")
code_hits = [f for f, txt in SCRIPT_TXT.items() if CODE_MAP_PATTERN.search(txt)]
t("RSC·NEC 코드 상수가 화면 코드에 없다 (CLAUDE.md 3.4)", not code_hits, str(code_hits))

# Subtype 코드값(siap_subtype 같은 필드 접근이 아니라, 리터럴 0x.. 스위치)이 없는가.
# 필드 접근(dev.siap_subtype)은 허용 — 화면이 스스로 코드를 만들지 않으면 된다.
SWITCH_SUBTYPE = re.compile(r"switch\s*\([^)]*subtype[^)]*\)", re.I)
subtype_switch = [f for f, txt in SCRIPT_TXT.items() if SWITCH_SUBTYPE.search(txt)]
t("Subtype 코드를 분기(switch)로 재해석하지 않는다 (§1-6)", not subtype_switch, str(subtype_switch))

# F-231 — 정적 모듈뿐 아니라 실제 HTML 인라인 모듈도 같은 코드 입력이다.
# 시프트와 숫자 마스크, 숫자 키 기반 한국어 코드 매핑을 함께 금지한다.
bit_hits = bit_unpack_sources(SCRIPT_TXT)
t("화면 스크립트 전체에 시프트·숫자 마스크 언팩이 없다 (코덱은 siap/ 하나, §10)",
  not bit_hits, str(bit_hits))
numeric_map_hits = numeric_korean_map_sources(SCRIPT_TXT)
t("화면 스크립트에 숫자 코드→한국어 매핑 객체가 없다 (CLAUDE.md 3.4)",
  not numeric_map_hits, str(numeric_map_hits))

# F-199 — rule.draft_text·condition_expr·reject_reason 을 escapeHtml() 없이
# 템플릿 리터럴에 그대로 보간하면 innerHTML 렌더 시 저장형 DOM 주입이
# 가능하다(재현: draft_text 에 `<img src=x onerror=...>` 저장 후 rules.html
# 렌더에서 실행됨, GPT 재현). "실제로 이스케이프됐다"는 실행 없이 판정할
# 수 없으므로, 대신 위험한 자유 텍스트 필드가 escapeHtml(...) 로 감싸이지
# 않은 채 원문 그대로 보간되는 패턴이 없는지를 본다 — 누군가 나중에
# `${rule.draft_text}` 를 되돌리면(회귀) 이 검사가 먼저 잡는다.
UNSAFE_INTERP_RE = re.compile(r"\$\{\s*(rule\.draft_text|rule\.condition_expr|rule\.reject_reason)\s*(?:\?\?[^}]*)?\}")
unsafe_interp = {f: UNSAFE_INTERP_RE.findall(txt) for f, txt in HTML_TXT.items()}
unsafe_interp = {f: v for f, v in unsafe_interp.items() if v}
t("rule.draft_text·condition_expr·reject_reason 이 escapeHtml() 없이 보간되지 않는다 (F-199)",
  not unsafe_interp, str(unsafe_interp))

# F-204 — pendingCardHtml 한 함수만 자르지 않고 호출 가능한 로컬 헬퍼를
# 끝까지 따라간다. 실행 버튼, 실행 form action, /execute 경로가 하나라도
# 도달 가능하면 미승인 카드의 실행 경로 부재 계약을 위반한다.
rules_txt = HTML_TXT.get("rules.html", "")
pending_exec = pending_execute_paths(rules_txt)
t("미승인 규칙 카드에 실행 버튼 마크업이 없다 (disabled 아니라 부재, §6.2)",
  not pending_exec, str(pending_exec))
t("승인된 규칙 카드에만 실행 버튼이 있다",
  approved_has_execute_path(rules_txt))

status_issues = status_cue_issues(verify_html)
t("프레임 정상·위반·알림 상태가 색 외 아이콘과 문자로 함께 표시된다 (F-232)",
  not status_issues, str(status_issues))

# ═══════════════════════════════════════════════════════════════
#  3. 명도대비 — app.css 의 CONTRAST-PAIRS 를 실제로 계산한다 (§8.3 8번)
# ═══════════════════════════════════════════════════════════════
def _srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex6: str) -> float:
    r, g, b = int(hex6[0:2], 16), int(hex6[2:4], 16), int(hex6[4:6], 16)
    return 0.2126 * _srgb_to_linear(r) + 0.7152 * _srgb_to_linear(g) + 0.0722 * _srgb_to_linear(b)


def _contrast(hex_a: str, hex_b: str) -> float:
    la, lb = _luminance(hex_a), _luminance(hex_b)
    l1, l2 = max(la, lb), min(la, lb)
    return (l1 + 0.05) / (l2 + 0.05)


css_txt = (STATIC_DIR / "app.css").read_text(encoding="utf-8") if (STATIC_DIR / "app.css").exists() else ""
pairs_line = re.search(r"CONTRAST-PAIRS:\s*(.+)", css_txt)
t("app.css 에 CONTRAST-PAIRS 선언이 있다 (§8.3 8번)", pairs_line is not None)

if pairs_line:
    # 같은 주석 블록(다음 "*/" 전까지)만 본다 — 임의 글자 수 창은 블록 밖의
    # 산문("tools/web_live_verify.py 가 …")까지 끌어들여 가짜 쌍을 만든다.
    end = css_txt.find("*/", pairs_line.start())
    block = css_txt[pairs_line.start():end if end != -1 else pairs_line.end()]
    pair_names = re.findall(r"(fg-[\w-]+)/(bg-[\w-]+)", block)
    var_hex = dict(re.findall(r"(--[\w-]+):\s*#([0-9a-fA-F]{6})", css_txt))
    low = []
    missing = []
    for fg, bg in pair_names:
        fg_v, bg_v = var_hex.get(f"--{fg}"), var_hex.get(f"--{bg}")
        if fg_v is None or bg_v is None:
            missing.append(f"{fg}/{bg}")
            continue
        ratio = _contrast(fg_v, bg_v)
        if ratio < 4.5:
            low.append(f"{fg}/{bg}={ratio:.2f}")
    t(f"CSS 변수 선언이 실재 ({len(pair_names)}쌍)", not missing, str(missing))
    t("모든 명도대비 쌍이 4.5:1 이상 (WCAG 1.4.3)", not low, str(low))

sys.exit(_report_and_exit())
