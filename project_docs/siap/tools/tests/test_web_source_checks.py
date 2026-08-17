import re
from pathlib import Path

from tools.web_source_checks import (
    approved_has_execute_path,
    bit_unpack_sources,
    external_css_references,
    extract_inline_scripts,
    function_bodies,
    numeric_korean_map_sources,
    pending_execute_paths,
    recovery_cursor_issues,
    recovery_pagination_issues,
    status_cue_issues,
)


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "project_code" / "web"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_f204_pending_helper_execute_path_is_detected():
    source = _read(WEB / "rules.html")
    helper = (
        'function hiddenPendingExecuteForm(id) { '
        'return `<form action="/api/v1/rules/${id}/execute">'
        '<button>실행</button></form>`; }\n'
    )
    mutated = source.replace(
        "function pendingCardHtml(rule) {",
        helper + "function pendingCardHtml(rule) {",
        1,
    ).replace("${genNote}", "${genNote}${hiddenPendingExecuteForm(id)}", 1)
    assert pending_execute_paths(source) == []
    assert pending_execute_paths(mutated) == ["hiddenPendingExecuteForm"]
    assert approved_has_execute_path(source)


def test_f234_pending_arrow_helper_execute_path_is_detected():
    # F-234: 지역 화살표 함수도 pendingCardHtml 호출 그래프의 일부다.
    source = _read(WEB / "rules.html")
    helper = (
        "const hiddenPendingExecuteForm = (id) => "
        "'<form action=\"/api/v1/rules/execute\"><button>실행</button></form>';\n"
    )
    mutated = source.replace(
        "function pendingCardHtml(rule) {",
        helper + "function pendingCardHtml(rule) {",
        1,
    ).replace("${genNote}", "${genNote}${hiddenPendingExecuteForm(id)}", 1)
    assert pending_execute_paths(mutated) == ["hiddenPendingExecuteForm"]


def test_f230_external_css_import_and_url_are_detected():
    css = _read(WEB / "static" / "app.css")
    assert external_css_references({"app.css": css}) == []
    assert external_css_references(
        {"app.css": "@import url(https://cdn.example.invalid/theme.css);\n" + css}
    ) == ["app.css"]
    assert external_css_references(
        {"app.css": ".x{background:url('http://cdn.example.invalid/a.png')}"}
    ) == ["app.css"]


def test_f235_protocol_relative_css_is_detected():
    # F-235: // URL은 현재 페이지의 프로토콜을 쓰는 외부 네트워크 참조다.
    assert external_css_references(
        {"app.css": "@import url(//cdn.example.invalid/theme.css);"}
    ) == ["app.css"]
    assert external_css_references(
        {"app.css": ".x{background:url('//cdn.example.invalid/a.png')}"}
    ) == ["app.css"]


def test_f231_inline_bit_unpack_and_numeric_mapping_are_detected():
    html = _read(WEB / "verify.html")
    scripts = extract_inline_scripts({"verify.html": html})
    assert bit_unpack_sources(scripts) == []
    assert numeric_korean_map_sources(scripts) == []
    mutated = html.replace(
        "</body>",
        '<script>const v=(0x1200 >> 8) & 0xff; const names={0x80:"오류"};</script></body>',
        1,
    )
    mutated_scripts = extract_inline_scripts({"verify.html": mutated})
    assert "verify.html:inline-2" in bit_unpack_sources(mutated_scripts)
    assert "verify.html:inline-2" in numeric_korean_map_sources(mutated_scripts)


def test_f232_color_only_frame_status_is_detected():
    html = _read(WEB / "verify.html")
    assert status_cue_issues(html) == []
    mutated = html.replace("${m.icon} ${f.id} — ${m.text}", "${f.id}")
    assert status_cue_issues(mutated) == [
        "frameListItemHtml:m.icon",
        "frameListItemHtml:m.text",
    ]


def test_f205_recovery_consumes_all_pages():
    api_js = _read(WEB / "static" / "api.js")
    verify_html = _read(WEB / "verify.html")
    assert recovery_pagination_issues(api_js, verify_html) == []
    assert recovery_pagination_issues(
        api_js.replace("while (offset < total)", "if (offset < total)", 1),
        verify_html,
    ) == ["페이지 반복"]


def test_f233_recovery_uses_disconnect_cursor_not_polled_list():
    stream_js = _read(WEB / "static" / "stream.js")
    verify_html = _read(WEB / "verify.html")
    assert recovery_cursor_issues(stream_js, verify_html) == []
    overwritten = verify_html.replace(
        "const since = state.recoverySince;",
        "const since = epochToIso(state.frames.length ? state.frames[0].t : null);",
        1,
    )
    assert recovery_cursor_issues(stream_js, overwritten) == ["고정 커서 사용"]


def test_verify_injection_controls_stay_above_scrollable_frame_list():
    html = _read(WEB / "verify.html")
    css = _read(WEB / "static" / "app.css")
    assert html.index('id="inject-buttons"') < html.index('id="frame-list"')
    frame_list_rule = re.search(r"#frame-list\s*\{([^}]*)\}", css, re.S)
    assert frame_list_rule is not None
    declarations = frame_list_rule.group(1)
    assert re.search(r"\bheight\s*:", declarations)
    assert re.search(r"\boverflow-y\s*:\s*auto\b", declarations)


def test_verify_violation_filter_applies_to_load_and_live_upsert():
    html = _read(WEB / "verify.html")
    bodies = function_bodies(html)
    assert 'frame.judgement === "violation"' in bodies["frameMatchesCurrentFilter"]
    assert ".filter(frameMatchesCurrentFilter)" in bodies["loadFrames"]
    assert "loadRevision !== state.loadRevision" in bodies["loadFrames"]
    assert "if (!frameMatchesCurrentFilter(frame))" in bodies["upsertFrame"]
