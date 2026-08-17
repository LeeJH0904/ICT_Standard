"""웹 소스 출구 검증에서 공통으로 쓰는 경량 정적 검사.

브라우저 실행을 대체하려는 파서가 아니라, 이미 신고된 우회 패턴을 두 웹
출구가 같은 입력 범위와 규칙으로 판정하게 하는 작은 보조 모듈이다.
"""
from __future__ import annotations

import re
from collections.abc import Mapping


_FUNCTION_HEAD = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{")
_ARROW_FUNCTION = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?"
    r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*(.*?)"
    r"(?:;\s*(?=\r?\n|$)|$)",
    re.S,
)
_CALL = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")


def function_bodies(source: str) -> dict[str, str]:
    """일반 함수 선언과 지역 화살표 함수 바인딩의 본문을 잘라낸다."""
    bodies: dict[str, str] = {}
    for match in _FUNCTION_HEAD.finditer(source):
        name = match.group(1)
        start = match.end()
        depth = 1
        i = start
        quote: str | None = None
        escaped = False
        line_comment = False
        block_comment = False
        while i < len(source):
            ch = source[i]
            nxt = source[i + 1] if i + 1 < len(source) else ""
            if line_comment:
                if ch in "\r\n":
                    line_comment = False
                i += 1
                continue
            if block_comment:
                if ch == "*" and nxt == "/":
                    block_comment = False
                    i += 2
                else:
                    i += 1
                continue
            if quote:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                i += 1
                continue
            if ch == "/" and nxt == "/":
                line_comment = True
                i += 2
                continue
            if ch == "/" and nxt == "*":
                block_comment = True
                i += 2
                continue
            if ch in ("'", '"', "`"):
                quote = ch
                i += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    bodies[name] = source[start:i]
                    break
            i += 1
    for match in _ARROW_FUNCTION.finditer(source):
        bodies[match.group(1)] = match.group(2)
    return bodies


def _reachable_functions(source: str, root: str) -> dict[str, str]:
    bodies = function_bodies(source)
    reachable: dict[str, str] = {}
    pending = [root]
    while pending:
        name = pending.pop()
        if name in reachable or name not in bodies:
            continue
        body = bodies[name]
        reachable[name] = body
        pending.extend(c for c in _CALL.findall(body) if c in bodies)
    return reachable


_EXECUTE_MARKER = re.compile(
    r"\brun-rule\b|/execute\b|<form\b[^>]*\baction\s*=|"
    r"<button\b[^>]*>[^<]*실행",
    re.I | re.S,
)


def pending_execute_paths(rules_html: str) -> list[str]:
    """미승인 카드가 직접 또는 헬퍼를 거쳐 실행 마크업을 만들면 함수명을 돌려준다."""
    reachable = _reachable_functions(rules_html, "pendingCardHtml")
    if "pendingCardHtml" not in reachable:
        return ["pendingCardHtml:missing"]
    return sorted(name for name, body in reachable.items() if _EXECUTE_MARKER.search(body))


def approved_has_execute_path(rules_html: str) -> bool:
    reachable = _reachable_functions(rules_html, "approvedCardHtml")
    return any(_EXECUTE_MARKER.search(body) for body in reachable.values())


def extract_inline_scripts(html_text: Mapping[str, str]) -> dict[str, str]:
    scripts: dict[str, str] = {}
    tag = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
    for filename, text in html_text.items():
        for index, (attrs, body) in enumerate(tag.findall(text), 1):
            if re.search(r"\bsrc\s*=", attrs, re.I):
                continue
            scripts[f"{filename}:inline-{index}"] = body
    return scripts


def external_css_references(css_text: Mapping[str, str]) -> list[str]:
    pattern = re.compile(
        r"@import\s+(?:url\(\s*)?[\"']?\s*(?:https?:)?//|"
        r"url\(\s*[\"']?\s*(?:https?:)?//",
        re.I,
    )
    hits = []
    for filename, text in css_text.items():
        no_comments = re.sub(r"/[*].*?[*]/", "", text, flags=re.S)
        if pattern.search(no_comments):
            hits.append(filename)
    return sorted(hits)


_BIT_UNPACK = re.compile(r"<<|>>>?|(?<!&)&(?!&)\s*(?:0x[0-9a-f]+|\d+)", re.I)
_NUMERIC_KO_MAP = re.compile(
    r"(?:^|[,{])\s*(?:0x[0-9a-f]+|\d+)\s*:\s*[\"'][^\"'\r\n]*[가-힣]",
    re.I | re.M,
)


def bit_unpack_sources(script_text: Mapping[str, str]) -> list[str]:
    return sorted(name for name, text in script_text.items() if _BIT_UNPACK.search(text))


def numeric_korean_map_sources(script_text: Mapping[str, str]) -> list[str]:
    return sorted(name for name, text in script_text.items() if _NUMERIC_KO_MAP.search(text))


def status_cue_issues(verify_html: str) -> list[str]:
    bodies = function_bodies(verify_html)
    meta = bodies.get("judgementMeta", "")
    item = bodies.get("frameListItemHtml", "")
    issues: list[str] = []
    returns = re.findall(
        r"return\s*\{\s*cls:\s*[\"']([^\"']+)[\"']\s*,"
        r"\s*icon:\s*[\"']([^\"']+)[\"']\s*,"
        r"\s*text:\s*[\"']([^\"']+)[\"']\s*\}",
        meta,
    )
    by_class = {cls: (icon.strip(), text.strip()) for cls, icon, text in returns}
    for state in ("normal", "violation", "alert"):
        icon, text = by_class.get(state, ("", ""))
        if not icon or not text:
            issues.append(f"{state}:icon/text")
    if "${m.icon}" not in item:
        issues.append("frameListItemHtml:m.icon")
    if "${m.text}" not in item:
        issues.append("frameListItemHtml:m.text")
    return issues


def recovery_pagination_issues(api_js: str, verify_html: str) -> list[str]:
    api_bodies = function_bodies(api_js)
    collect = api_bodies.get("collectAllPages", "")
    recover = function_bodies(verify_html).get("recoverMissedFrames", "")
    issues: list[str] = []
    required_collect = {
        "collectAllPages 함수": bool(collect),
        "페이지 반복": bool(re.search(r"\bwhile\s*\(\s*offset\s*<\s*total\s*\)", collect)),
        "total 소비": ".total" in collect,
        "offset 전달": "offset" in collect,
        "응답 길이만큼 전진": bool(re.search(r"\b(?:batch|items)\.length\b", collect)),
    }
    issues.extend(name for name, ok in required_collect.items() if not ok)
    if not re.search(r"\bcollectAllPages\s*\(", recover):
        issues.append("recoverMissedFrames 결선")
    if not re.search(r"\bsince\b", recover):
        issues.append("since 고정")
    if not re.search(r"\buntil\b", recover):
        issues.append("until 스냅샷")
    return issues


def recovery_cursor_issues(stream_js: str, verify_html: str) -> list[str]:
    """최초 SSE 단절 커서가 폴링 목록과 분리되어 성공 시까지 유지되는지 본다."""
    stream = function_bodies(stream_js).get("connectStream", "")
    verify_bodies = function_bodies(verify_html)
    pin = verify_bodies.get("pinRecoveryCursor", "")
    recover = verify_bodies.get("recoverMissedFrames", "")
    issues: list[str] = []
    if (
        "const firstFailure = !recovering" not in stream
        or not re.search(r"if\s*\(\s*firstFailure\s*&&\s*onDisconnect\s*\)", stream)
    ):
        issues.append("최초 단절 훅")
    if (
        "state.recoverySince !== undefined" not in pin
        or "state.recoverySince = epochToIso" not in pin
    ):
        issues.append("단절 커서 고정")
    if not re.search(r"\bonDisconnect\s*:\s*pinRecoveryCursor\b", verify_html):
        issues.append("단절 훅 결선")
    if "const since = state.recoverySince" not in recover:
        issues.append("고정 커서 사용")
    collect_at = recover.find("collectAllPages")
    clear_at = recover.rfind("state.recoverySince = undefined")
    if collect_at < 0 or clear_at < collect_at:
        issues.append("성공 후 커서 해제")
    return issues
