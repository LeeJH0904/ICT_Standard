"""openapi.json 검증 — 표준·스키마·계약과의 대조

이 스크립트는 openapi.json 을 **독립된 출처와 대조**한다.
  - project_docs/db/schema.sql      : 응답 필드가 실재하는 컬럼인가, enum 이 CHECK 와 같은가
  - project_docs/contracts/frame.py : RSC·ValueType·Status·비트 폭이 계약과 같은가
자기 자신에서 생성한 값을 정답으로 삼지 않는다(CLAUDE.md 10 '자기 검증 순환').

실행:  python project_docs/api/api_verify.py
종료코드: 0 = 전부 일치, 1 = 불일치 있음
"""
from __future__ import annotations
import json, re, sqlite3, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent              # project_docs/api/
DOCS = HERE.parent                                  # project_docs/

# F-045 — 한국어 Windows 기본 콘솔은 CP949 다. 표현 불가 문자로 검증이 중단되면
#         재현성이 깨진다. 출력 문자는 CP949 안에서 고른다(meta_verify.py 가 강제).
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

def find(name: str) -> Path | None:
    for base in (DOCS, DOCS.parent):
        hits = [q for q in base.rglob(name) if not _skip(q)]
        if hits: return hits[0]
    return None

SPEC = json.loads((HERE / "openapi.json").read_text(encoding="utf-8"))
SCHEMAS = SPEC["components"]["schemas"]
PATHS = SPEC["paths"]
METHODS = ("get", "post", "put", "patch", "delete")

def ops():
    for path, item in PATHS.items():
        for m, op in item.items():
            if m in METHODS:
                yield path, m, op

def walk(node):
    """스키마 트리의 모든 dict 노드를 순회한다."""
    if isinstance(node, dict):
        yield node
        for v in node.values(): yield from walk(v)
    elif isinstance(node, list):
        for v in node: yield from walk(v)

def props_of(name: str) -> dict:
    """allOf 병합을 포함해 스키마의 properties 를 모은다."""
    s = SCHEMAS[name]
    out = dict(s.get("properties", {}))
    for part in s.get("allOf", []):
        if "$ref" in part:
            out |= props_of(part["$ref"].rsplit("/", 1)[-1])
        else:
            out |= part.get("properties", {})
    return out


# ═══════════════════════════════════════════════════════════════
#  0-a. 최소 JSON Schema 평가기 (표준 라이브러리만)
#       F-051 · F-054 — "스키마에 필드가 없다"만 보면 부족하다. 반례를 실제로
#       넣어보고 거부되는지 확인해야 계약이 성립한다. jsonschema 패키지를 쓰면
#       직접 의존성이 늘어 wheels/ 에 실리므로(CLAUDE.md 4.3) 필요한 키워드만 구현한다.
#       지원: type · enum · const · minimum · maximum · minLength · maxLength
#             required · properties · additionalProperties · minProperties
#             allOf · anyOf · oneOf · not · if/then/else · $ref
#             format (date-time 만, F-166)
#
#       F-166 — "필드가 있다"(F-158)·"required 다"(F-162)를 넘어 "값이 실제로
#       그 형식이다"도 다르다. `format: date-time` 을 스키마에 적어도 이
#       평가기가 `format` 자체를 몰라 'not-a-date' 가 그대로 통과했다.
#       JSON Schema 표준 자체도 `format` 을 기본으로는 주석(annotation)
#       으로만 다루고 검증하지 않는다(F-166 재현의 "FormatChecker 를 지정했을
#       때만 거부된다"가 바로 이 사양이다) — 아래 §7 교차검증에서도 `jsonschema`
#       호출부에 `FormatChecker` 를 명시로 붙여야 표준 구현조차 이 반례를
#       잡는다.
#
#       F-095 — 이 구현 자체가 검증 대상이다. 직접 만든 검증기로 자기 스키마를
#       검사하면 "구현하지 않은 키워드"가 조용히 통과로 바뀐다(F-093 의 minLength
#       미지원이 정확히 그것이었다). 그래서 §7.1 의 반례 매트릭스는 jsonschema 가
#       설치돼 있으면 **같은 매트릭스를 표준 구현으로 한 번 더 돌려 판정이 일치하는지**
#       대조한다. 없으면 그 사실을 출력에 남긴다 — 조용히 건너뛰지 않는다.
# ═══════════════════════════════════════════════════════════════
# F-166 — RFC 3339 date-time. jsonschema 기본 FormatChecker 가 받아들이는
# 폭(초 소수점 자릿수 자유, 대소문자 무관 T/Z, ±HH:MM 오프셋)에 맞춘다.
# 이 코드베이스가 실제로 쓰는 두 표기(...Z / ...+09:00, NOW 상수들)를 전제로
# 손으로 작성했다 — jsonschema 구현을 들여다보고 베낀 것이 아니라 표준
# 형식(RFC 3339 §5.6)을 직접 옮긴 것이므로 §7 교차검증이 여전히 유의미하다.
_DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$"
)


def js_valid(schema: dict, inst) -> bool:
    if schema is True: return True
    if schema is False: return False

    if "$ref" in schema:
        kind, name = schema["$ref"].rsplit("/", 2)[-2:]
        return js_valid(SPEC["components"][kind][name], inst)

    ty = schema.get("type")
    if ty is not None:
        tys = ty if isinstance(ty, list) else [ty]
        def is_t(name: str) -> bool:
            if name == "null":    return inst is None
            if name == "boolean": return isinstance(inst, bool)
            if name == "integer": return isinstance(inst, int) and not isinstance(inst, bool)
            if name == "number":  return isinstance(inst, (int, float)) and not isinstance(inst, bool)
            if name == "string":  return isinstance(inst, str)
            if name == "array":   return isinstance(inst, list)
            if name == "object":  return isinstance(inst, dict)
            return True
        if not any(is_t(n) for n in tys): return False

    if "const" in schema and inst != schema["const"]: return False
    if "enum" in schema and inst not in schema["enum"]: return False

    if isinstance(inst, (int, float)) and not isinstance(inst, bool):
        if "minimum" in schema and inst < schema["minimum"]: return False
        if "maximum" in schema and inst > schema["maximum"]: return False

    if isinstance(inst, str):
        if "minLength" in schema and len(inst) < schema["minLength"]: return False
        if "maxLength" in schema and len(inst) > schema["maxLength"]: return False
        if schema.get("format") == "date-time" and not _DATE_TIME_RE.match(inst):
            return False

    if isinstance(inst, dict):
        for r in schema.get("required", []):
            if r not in inst: return False
        if "minProperties" in schema and len(inst) < schema["minProperties"]: return False
        if "maxProperties" in schema and len(inst) > schema["maxProperties"]: return False
        props = schema.get("properties", {})
        for k, v in inst.items():
            if k in props:
                if not js_valid(props[k], v): return False
            elif schema.get("additionalProperties") is False:
                return False

    for sub in schema.get("allOf", []):
        if not js_valid(sub, inst): return False
    if "anyOf" in schema and not any(js_valid(sub, inst) for sub in schema["anyOf"]):
        return False
    if "oneOf" in schema and sum(1 for sub in schema["oneOf"] if js_valid(sub, inst)) != 1:
        return False
    if "not" in schema and js_valid(schema["not"], inst):
        return False

    if "if" in schema:
        if js_valid(schema["if"], inst):
            if "then" in schema and not js_valid(schema["then"], inst): return False
        elif "else" in schema and not js_valid(schema["else"], inst):
            return False
    return True

# ═══════════════════════════════════════════════════════════════
#  1. 문서 구조
# ═══════════════════════════════════════════════════════════════
t("OpenAPI 3.1", SPEC.get("openapi", "").startswith("3.1"), SPEC.get("openapi", ""))

ids = [op["operationId"] for _, _, op in ops()]
t(f"operationId 존재·고유 ({len(ids)}건)", len(ids) == len(set(ids)) and all(ids),
  str([i for i in set(ids) if ids.count(i) > 1]))

# 모든 $ref 가 실재하는가
refs = {n["$ref"] for n in walk(SPEC) if "$ref" in n and isinstance(n["$ref"], str)}
dangling = []
for r in refs:
    kind, name = r.rsplit("/", 2)[-2:]
    if name not in SPEC["components"].get(kind, {}):
        dangling.append(r)
t(f"$ref {len(refs)}건 전부 해소", not dangling, str(dangling))

# 정의해두고 아무도 안 쓰는 스키마 (오탈자 탐지)
used = {r.rsplit("/", 1)[-1] for r in refs}
orphan = [k for k in SCHEMAS if k not in used]
t("고아 스키마 없음", not orphan, str(orphan))

# 경로 파라미터가 선언되어 있는가
missing_param = []
for path, m, op in ops():
    declared = {p.get("name") or
                SPEC["components"]["parameters"][p["$ref"].rsplit("/", 1)[-1]]["name"]
                for p in op.get("parameters", [])}
    for want in re.findall(r"\{(\w+)\}", path):
        if want not in declared: missing_param.append(f"{m.upper()} {path} -> {want}")
t("경로 파라미터 전부 선언", not missing_param, str(missing_param))

# ═══════════════════════════════════════════════════════════════
#  2. schema.sql 과의 대조 — 응답 필드가 실재하는 컬럼인가
# ═══════════════════════════════════════════════════════════════
sql_path = find("schema.sql")
con = sqlite3.connect(":memory:")
con.executescript(sql_path.read_text(encoding="utf-8"))
COLS = {tbl: {r[1] for r in con.execute(f"PRAGMA table_info({tbl})")}
        for (tbl,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
t("schema.sql 로드", bool(COLS), f"테이블 {len(COLS)}개")

# (스키마명, 대응 테이블, 표준·유도 필드로 인정할 예외)
BINDING = {
    "Device":           ("device_install_info", {"device_kind", "subtype"}),
    "TelemetryPoint":   ("env_state_data|env_measurement", {"install_id"}),
    "DeviceState":      ("device_state_data", {"install_id", "attributes"}),
    "Alert":            ("alert", set()),
    "PublicDataSource": ("public_data_source", set()),
    "PublicDataRecord": ("public_data_record", set()),
    # fields · judgement 는 codec 이 만드는 유도 필드다 (F-085). 저장하지 않는다 -
    # 같은 바이트에서 언제든 다시 만들 수 있고, 저장하면 코덱과 DB 가 갈릴 수 있다.
    "Frame":            ("frame_log", {"header", "kind", "element_count", "violations",
                                       "fields", "judgement"}),
    "FrameHeader":      ("frame_log", set()),
    "Violation":        ("frame_violation", set()),
    "Execution":        ("control_execution", {"command", "result_rsc_name"}),
    "Rule":             ("control_rule", {"action", "approved"}),
}
stray = []
for sname, (tables, allowed) in BINDING.items():
    cols = set().union(*(COLS[t_] for t_ in tables.split("|")))
    for pname in props_of(sname):
        if pname not in cols and pname not in allowed:
            stray.append(f"{sname}.{pname}")
t("응답 필드가 전부 실재 컬럼 (또는 명시된 유도 필드)", not stray, str(stray))

# 반대 방향 — 컬럼이 있는데 노출도 안 하고 사유도 없는 것은 누락 후보다.
# 컬럼명과 다른 이름으로 노출한 것 (JSON 문자열 -> 파싱된 객체)
RENAMED = {
    "control_execution": {"command_json": "command"},
    "control_rule":      {"action_json": "action"},
}
# 내부 전용으로 의도해 노출하지 않는 컬럼 (사유를 여기 적는다)
INTERNAL = {
    # frame_violation 은 Frame 안에 중첩되므로 조인 키가 응답에 필요 없다
    "frame_violation": {"id", "frame_id"},
    # F-187 — elements_json 은 이미 디코딩된 가변 요소의 내부 캐시다.
    # Frame.fields[]로 펼쳐지지만 1:1 개명이 아니라 다대일 변환(요소 하나가
    # 여러 FieldSlice 로 쪼개진다)이라 RENAMED 로 표현할 수 없다 — fields
    # 자체는 F-085 원칙대로 저장하지 않고 매 요청마다 다시 만든다(코덱↔DB
    # 드리프트 회피, 위 BINDING 주석과 같은 이유).
    "frame_log": {"elements_json"},
}
exposed_by_table: dict[str, set[str]] = {}
for sname, (tables, _) in BINDING.items():
    for tbl in tables.split("|"):
        exposed_by_table.setdefault(tbl, set()).update(props_of(sname))
unexposed = []
for tbl, exposed in exposed_by_table.items():
    exposed = exposed | set(RENAMED.get(tbl, {}).values())
    for c in COLS[tbl] - INTERNAL.get(tbl, set()):
        if c in exposed: continue
        if RENAMED.get(tbl, {}).get(c) in exposed: continue
        unexposed.append(f"{tbl}.{c}")
t("테이블 컬럼 미노출 없음 (개명·내부 전용 제외)", not unexposed, str(sorted(set(unexposed))))

# ═══════════════════════════════════════════════════════════════
#  3. enum 이 DB CHECK 와 같은가
# ═══════════════════════════════════════════════════════════════
ddl = sql_path.read_text(encoding="utf-8")
TABLE_DDL = {m.group(1): m.group(2) for m in
             re.finditer(r"CREATE TABLE (\w+) \((.*?)\n\);", ddl, re.S)}

def check_enum(table: str, col: str) -> set[str]:
    """해당 **테이블의** CHECK (col IN (...)) 만 본다.
    origin 처럼 같은 이름의 컬럼이 여러 테이블에 있으므로 범위를 좁혀야 한다."""
    body = TABLE_DDL.get(table, "")
    m = re.search(rf"CHECK \({col} IN \(([^)]*)\)\)", body, re.S)
    return set(re.findall(r"'([^']+)'", m.group(1))) if m else set()

def spec_enum(schema: str, prop: str) -> set[str]:
    e = props_of(schema)[prop].get("enum", [])
    return {v for v in e if v is not None}

for label, (schema, prop, table, col) in {
    "알림 kind":      ("Alert", "kind", "alert", "kind"),
    "알림 severity":  ("Alert", "severity", "alert", "severity"),
    "실행 origin":    ("Execution", "origin", "control_execution", "origin"),
    "규칙 origin":    ("Rule", "origin", "control_rule", "origin"),
    "프레임 방향":     ("Frame", "direction", "frame_log", "direction"),
}.items():
    a, b = spec_enum(schema, prop), check_enum(table, col)
    t(f"enum 일치 - {label}", a == b and bool(a), f"spec={sorted(a)} ddl={sorted(b)}")

# subtype 은 열거하지 않는 것이 요건이다 (CLAUDE.md 1 - 노드 종류 하드코딩 금지)
sub_enums = [f"{s}.{p}" for s in SCHEMAS for p, v in props_of(s).items()
             if p in ("subtype", "device_kind") and p == "subtype" and "enum" in v]
t("subtype 을 API 스키마에 열거하지 않음", not sub_enums, str(sub_enums))

param_enums = [k for k, v in SPEC["components"]["parameters"].items()
               if "enum" in v.get("schema", {}) and k in ("subtype",)]
t("subtype 질의 파라미터도 열거하지 않음", not param_enums, str(param_enums))

# ═══════════════════════════════════════════════════════════════
#  4. contracts/frame.py 와의 대조 — 표준 상수·비트 폭
# ═══════════════════════════════════════════════════════════════
frame_py = find("frame.py")
ns: dict = {}
exec(compile(frame_py.read_text(encoding="utf-8"), str(frame_py), "exec"), ns)
missing = [k for k in ("RSC", "ValueType", "Status", "MsgKind") if k not in ns]
if missing:
    print(f"  FAIL  계약 파일을 잘못 찾았다: {frame_py} (없는 심볼 {missing})")
    sys.exit(1)                       # 조용히 통과시키지 않는다
RSC, ValueType, Status = ns["RSC"], ns["ValueType"], ns["Status"]

t("Node.status enum = 계약 Status",
  spec_enum("Node", "status") == {s.name for s in Status},
  f"spec={sorted(spec_enum('Node','status'))}")

t("ControlAction.value_type = 계약 ValueType (Reserved 제외)",
  spec_enum("ControlAction", "value_type") == {v.name for v in ValueType},
  f"spec={sorted(spec_enum('ControlAction','value_type'))} contract={sorted(v.name for v in ValueType)}")

# 비트 폭: 20bit / 16bit / 14bit / 8bit 필드의 maximum 이 맞는가
WIDTH = {
    ("Node", "node_id"): 20, ("Node", "gcg_id"): 20, ("Node", "sw_version"): 8,
    ("FrameHeader", "version"): 8, ("FrameHeader", "msg_type"): 14,
    ("FrameHeader", "trans_type"): 2, ("FrameHeader", "msg_id"): 16,
    ("FrameHeader", "payload_len"): 16, ("FrameHeader", "gcg_id"): 20,
    ("FrameHeader", "node_id"): 20,
    ("Device", "siap_device_id"): 8, ("Device", "siap_subtype"): 8,
    ("Alert", "siap_nec"): 8,
    ("Execution", "siap_msg_id"): 16, ("Execution", "result_rsc"): 8,
}
badw = []
for (sname, pname), bits in WIDTH.items():
    got = props_of(sname)[pname].get("maximum")
    if got != (1 << bits) - 1: badw.append(f"{sname}.{pname}: {got} != {(1<<bits)-1} ({bits}bit)")
t(f"비트 폭 {len(WIDTH)}필드가 0943 명시값과 일치", not badw, "; ".join(badw))

# ═══════════════════════════════════════════════════════════════
#  5. 안전 요건 — 승인 게이트가 API 표면에서 성립하는가
#     "AI 출력이 직접 구동기를 제어하지 않는다"를 스키마로 검사한다.
# ═══════════════════════════════════════════════════════════════
draft = SCHEMAS["RuleDraftRequest"]
t("초안 생성 요청이 실행 가능한 필드를 받지 않음",
  draft.get("additionalProperties") is False
  and not ({"action", "target_install_id", "approved_at", "approved_by"} & set(draft["properties"])),
  str(sorted(draft["properties"])))

appr = SCHEMAS["ApproveRequest"]
t("승인 요청이 스냅샷 3요소를 모두 필수로 요구",
  set(appr["required"]) == {"condition_expr", "action", "target_install_id"},
  str(sorted(appr["required"])))
t("승인 요청에 승인자·승인시각을 실을 수 없음 (헤더·서버 시각이 출처)",
  appr.get("additionalProperties") is False
  and not ({"approved_by", "approved_at"} & set(appr["properties"])))

t("제어 명령 본문에 대상 장치가 없음 (F-049 - 대상은 컬럼이 정본)",
  "install_id" not in SCHEMAS["ControlAction"].get("properties", {}))

exec_op = PATHS["/api/v1/rules/{ruleId}/execute"]["post"]
t("규칙 실행에 요청 본문이 없음 (클라이언트가 명령·대상을 지정할 수 없다)",
  "requestBody" not in exec_op)

# 승인·수동제어는 사용자 식별이 필수다
def has_user_header(op) -> bool:
    for p in op.get("parameters", []):
        ref = p.get("$ref", "")
        if ref.endswith("/userId"): return True
        if p.get("name") == "X-User-Id" and p.get("required"): return True
    return False
t("승인과 수동제어에 사용자 식별 헤더 필수",
  has_user_header(PATHS["/api/v1/rules/{ruleId}/approve"]["post"])
  and has_user_header(PATHS["/api/v1/control"]["post"]))

# 5-a. F-051 · F-054 — ControlAction 이 반례를 실제로 거부하는가
CA = SCHEMAS["ControlAction"]
t("ControlAction 이 닫힌 객체 (F-051)", CA.get("additionalProperties") is False)
t("ControlAction 에 value_type 별 범위 분기 존재 (F-054 · F-055)",
  len(CA.get("allOf", [])) == 3 and all("if" in b and "then" in b for b in CA["allOf"]))

# 반례 - 전부 거부되어야 한다. 경계값은 통과해야 한다.
REJECT = [
    ("대상 장치 밀반입",   {"value": 1, "value_type": "UINT", "install_id": "B"}),
    ("미선언 필드",        {"value": 1, "value_type": "UINT", "note": "x"}),
    ("UINT 음수",          {"value": -1, "value_type": "UINT"}),
    ("UINT 2^32",          {"value": 1 << 32, "value_type": "UINT"}),
    ("UINT 에 소수",       {"value": 1.5, "value_type": "UINT"}),
    ("INT 2^31",           {"value": 1 << 31, "value_type": "INT"}),
    ("INT -2^31-1",        {"value": -(1 << 31) - 1, "value_type": "INT"}),
    ("INT 에 소수",        {"value": 1.5, "value_type": "INT"}),
    ("Reserved 타입",      {"value": 0, "value_type": "RESERVED"}),
    ("value_type 누락",    {"value": 0}),
    ("FLOAT 1e39",         {"value": 1e39, "value_type": "FLOAT"}),      # F-055
    ("FLOAT -1e39",        {"value": -1e39, "value_type": "FLOAT"}),     # F-055
    ("FLOAT 1e308",        {"value": 1e308, "value_type": "FLOAT"}),     # F-055
    ("FLOAT 10**400",      {"value": 10 ** 400, "value_type": "FLOAT"}),  # F-058
    ("INT   10**400",      {"value": 10 ** 400, "value_type": "INT"}),    # F-058
    ("value 가 문자열",    {"value": "1", "value_type": "UINT"}),         # F-058
    ("value 가 null",     {"value": None, "value_type": "UINT"}),        # F-058
]
ACCEPT = [
    ("INT 최솟값",   {"value": -(1 << 31), "value_type": "INT"}),
    ("INT 최댓값",   {"value": (1 << 31) - 1, "value_type": "INT"}),
    ("UINT 최솟값",  {"value": 0, "value_type": "UINT"}),
    ("UINT 최댓값",  {"value": (1 << 32) - 1, "value_type": "UINT"}),
    ("FLOAT 25.3",   {"value": 25.3, "value_type": "FLOAT"}),
    ("FLOAT 최댓값", {"value": 3.4028234663852886e38, "value_type": "FLOAT"}),
    ("FLOAT 최솟값", {"value": -3.4028234663852886e38, "value_type": "FLOAT"}),
    ("구동시간 포함", {"value": 1, "value_type": "UINT", "duration_sec": 1200}),
]
leaked = [n for n, o in REJECT if js_valid(CA, o)]
t(f"ControlAction 반례 {len(REJECT)}종 전부 거부", not leaked, str(leaked))
blocked = [n for n, o in ACCEPT if not js_valid(CA, o)]
t(f"ControlAction 정상값 {len(ACCEPT)}종 전부 허용", not blocked, str(blocked))

# 요청 본문 스키마가 전부 닫혀 있는가 (중첩 포함)
open_bodies = [n for n in ("RuleDraftRequest", "ApproveRequest", "ManualControlRequest", "ControlAction")
               if SCHEMAS[n].get("additionalProperties") is not False]
t("제어·승인 요청 스키마 4종이 전부 닫힘", not open_bodies, str(open_bodies))

# 5-b. F-052 — 인증이 아님을 문서가 명시하는가
sec = SPEC["components"].get("securitySchemes", {}).get("UserIdHeader", {})
t("사용자 식별 헤더가 securityScheme 으로 선언됨", sec.get("name") == "X-User-Id")
t("인증이 아님을 설명에 명시 (F-052)",
  "인증이 아니다" in sec.get("description", "") and "신원 보장이 아니다" in sec.get("description", ""))
t("승인·수동제어에 security 요구가 걸려 있음",
  all("security" in PATHS[p]["post"]
      for p in ("/api/v1/rules/{ruleId}/approve", "/api/v1/control")))

# F-056 — 개수만 세면 경로가 통째로 바뀌어도 통과한다.
#         POST /rules 를 지우고 POST /health 를 만들어도 4건이라 PASS 였다.
#         허용된 (메서드, 경로) 의 **정확한 집합**을 대조한다.
WRITE_ALLOWED = {
    ("POST", "/api/v1/rules"),                      # 0937 6.3 MMS - 초안 생성
    ("POST", "/api/v1/rules/{ruleId}/approve"),     # 0937 부속서 A 3.2 - 승인 게이트
    ("POST", "/api/v1/rules/{ruleId}/execute"),     # 0937 6.5 FCS - 승인 규칙 실행
    ("POST", "/api/v1/control"),                    # 0937 부속서 A 1·2 - 수동 제어
    ("PATCH", "/api/v1/device-property"),           # 0937 6.4-2 · A.1-3 · A.1-5 - 수집 설정
    ("POST", "/api/v1/rules/{ruleId}/reject"),      # 0937 부속서 A 3.2 - 거부 (F-083)
    ("POST", "/api/v1/sim/inject"),                 # 0943 7.3.1 - 위반 주입 (F-084)
}
writes = {(m.upper(), p) for p, m, _ in ops() if m != "get"}
extra   = sorted(f"{m} {p}" for m, p in writes - WRITE_ALLOWED)
missing = sorted(f"{m} {p}" for m, p in WRITE_ALLOWED - writes)
t("쓰기 경로가 허용 집합과 정확히 일치 (아키텍처 4.4-a 사람 유발 쓰기)",
  not extra and not missing,
  (f"허용 밖 {extra}" if extra else "") + (f" 누락 {missing}" if missing else ""))
def _tags(method: str, path: str) -> set:
    """없는 경로에 대해 예외를 던지지 않는다 - 누락은 위 검사가 이미 FAIL 로 잡았고,
    검증기가 역추적으로 죽으면 나머지 결과가 통째로 사라진다."""
    return set(PATHS.get(path, {}).get(method.lower(), {}).get("tags", []))
bad_tag = [f"{m} {p}" for m, p in sorted(WRITE_ALLOWED)
           if not _tags(m, p) & {"mms", "fcs", "ems", "conformance"}]
t("허용된 쓰기 경로가 전부 mutation 태그 (mms/fcs/ems/conformance)", not bad_tag, str(bad_tag))

# ── 설정 경로가 제어값을 쓰지 못하게 막는다 (CLAUDE.md 1-7) ─────
#    표 7-15 DEVICE_PROPERTY 8개 필드 중 Value 계열이 들어오면 승인 게이트를
#    우회하는 구동 경로가 생긴다. 스키마에서 원천 차단하고 여기서 확인한다.
_dpp = SCHEMAS.get("DevicePropertyPatch", {})
_props = set(_dpp.get("properties", {}))
t("설정 경로 스키마가 표 7-15 의 사용자 지정 4필드만 받는다",
  _props == {"transfer_mode", "period_sec", "lower_value", "upper_value"}, str(sorted(_props)))
t("설정 경로에 제어값(value) 필드가 없다 (승인 게이트 우회 차단, CLAUDE.md 1-7)",
  not any(k == "value" or k.endswith("_value") and k not in ("lower_value", "upper_value")
          for k in _props),
  str(sorted(_props)))
t("설정 경로 스키마가 닫혀 있다 (additionalProperties false)",
  _dpp.get("additionalProperties") is False
  and SCHEMAS.get("DevicePropertyRequest", {}).get("additionalProperties") is False
  and SCHEMAS.get("DevicePropertySelector", {}).get("additionalProperties") is False)

# 표 7-15 비트 폭이 스키마 범위와 맞는가
_p = _dpp.get("properties", {})
# ── F-088: 설정 요청 계약의 구멍 ──────────────────────────────
_sel = SCHEMAS.get("DevicePropertySelector", {})
t("선택자가 개별·구역 배타를 oneOf 로 강제 (F-088)",
  isinstance(_sel.get("oneOf"), list) and len(_sel["oneOf"]) == 2
  and _sel.get("minProperties") == 1,
  f"oneOf={len(_sel.get('oneOf', []))} minProperties={_sel.get('minProperties')}")
t("변경 필드가 최소 1개 필요 (빈 패치 거부, F-088)",
  _dpp.get("minProperties") == 1, str(_dpp.get("minProperties")))
_lv = _dpp.get("properties", {}).get("lower_value", {})
_uv = _dpp.get("properties", {}).get("upper_value", {})
FMAX = 3.4028234663852886e38
t("임계값이 IEEE-754 single 범위로 제한 (표 7-15 32bit, F-088)",
  _lv.get("maximum") == FMAX and _lv.get("minimum") == -FMAX
  and _uv.get("maximum") == FMAX and _uv.get("minimum") == -FMAX,
  f"lower={_lv.get('minimum')}~{_lv.get('maximum')}")
t("Value Type 별 정합은 서버가 검사한다고 명시 (F-088 · F-093)",
  "Value Type" in _dpp.get("description", "") and "422" in _dpp.get("description", ""))
# ── F-093: 선택자 필드에서 null 을 제거했는가 ─────────────────
#    required 는 '키가 있는가'만 본다. nullable 이면 {"install_id": null} 이
#    required 와 minProperties 를 모두 통과해 대상 없는 요청이 내려간다.
_selp = _sel.get("properties", {})
_nullable = [k for k, v in _selp.items()
             if "null" in (v.get("type") if isinstance(v.get("type"), list) else [v.get("type")])]
t("선택자 필드에 null 타입이 없다 (F-093)", not _nullable, str(_nullable))
t("설정 경로에 422(대상 타입 불일치·전량 거부) 응답이 있다 (F-093)",
  "422" in PATHS.get("/api/v1/device-property", {}).get("patch", {}).get("responses", {}))
t("Problem 이 0943 표 7-10 RSC 를 실어 보낼 수 있다 (F-093)",
  "INVALID_DATA_TYPE" in (SCHEMAS.get("Problem", {}).get("properties", {})
                          .get("siap_rsc", {}).get("enum") or []))
t("구역 일괄 실패 시 전량 거부를 계약에 명시 (F-093)",
  "전량 거부" in PATHS["/api/v1/device-property"]["patch"].get("description", ""))

t("period_sec 범위가 표 7-15 Period 14bit 와 일치 (0~16383)",
  _p.get("period_sec", {}).get("minimum") == 0 and _p.get("period_sec", {}).get("maximum") == 16383,
  str(_p.get("period_sec")))
t("transfer_mode 열거가 표 7-15 3종 (Periodic/Event/Both)",
  _p.get("transfer_mode", {}).get("enum") == ["PERIODIC", "EVENT", "BOTH"],
  str(_p.get("transfer_mode", {}).get("enum")))

# ═══════════════════════════════════════════════════════════════
#  5-a. 기능 3 워크플로가 HTTP 계약으로 닫히는가 (F-083)
# ═══════════════════════════════════════════════════════════════
_rdr = SCHEMAS.get("RuleDraftRequest", {})
_rp = set(_rdr.get("properties", {}))
t("초안 요청이 model_id·inputs 를 받는다 (서버가 모델을 돌린다, F-083)",
  {"model_id", "inputs"} <= _rp, str(sorted(_rp)))
t("AI_DRAFT 는 draft_text 를 받지 않는다 (클라이언트 문장 위장 차단, F-083)",
  any(b.get("if", {}).get("properties", {}).get("origin", {}).get("const") == "AI_DRAFT"
      and b.get("then", {}).get("properties", {}).get("draft_text", {}).get("type") == "null"
      and "model_id" in b.get("then", {}).get("required", [])
      for b in _rdr.get("allOf", [])))
t("초안 요청이 action·target 을 받지 않는다 (0937 A.3.2)",
  not ({"action", "target_install_id"} & _rp) and _rdr.get("additionalProperties") is False)
_rule = SCHEMAS.get("Rule", {}).get("properties", {})
t("Rule 이 생성 경로를 노출한다 (AI / THRESHOLD_FALLBACK, F-083)",
  "generation" in _rule and "THRESHOLD_FALLBACK" in (_rule["generation"].get("enum") or []))
t("Rule 이 거부 상태 3필드를 노출한다 (F-083)",
  {"rejected_at", "rejected_by", "reject_reason"} <= set(_rule))
t("거부 오퍼레이션이 존재하고 사유를 요구한다 (F-083)",
  "/api/v1/rules/{ruleId}/reject" in PATHS
  and SCHEMAS.get("RejectRequest", {}).get("required") == ["reason"])

# ═══════════════════════════════════════════════════════════════
#  5-b. 위반 주입 경로 (F-084)
# ═══════════════════════════════════════════════════════════════
_inj = PATHS.get("/api/v1/sim/inject", {}).get("post", {})
t("주입 오퍼레이션이 존재한다 (기능 2 의 브라우저 실행 경로, F-084)",
  _inj.get("operationId") == "injectVector")
_ireq = SCHEMAS.get("InjectRequest", {})
_enum = _ireq.get("properties", {}).get("vector_id", {}).get("enum") or []
t("주입이 골든 벡터 ID 열거만 받는다 (임의 hex 불가, F-084)",
  _enum == [f"X0{i}" for i in range(1, 9)] and _ireq.get("additionalProperties") is False,
  str(_enum))
t("hardware 모드에서 409 로 거부한다고 계약에 있다 (F-084)",
  "409" in _inj.get("responses", {}) and "hardware" in _inj.get("description", ""))
t("주입이 운영 데이터를 바꾸지 않음을 명시 (F-084)",
  "운영 데이터를 바꾸지 않는다" in _inj.get("description", ""))

# ═══════════════════════════════════════════════════════════════
#  5-c. 검증 뷰 응답 계약 (F-085)
# ═══════════════════════════════════════════════════════════════
_fr = SCHEMAS.get("Frame", {}).get("properties", {})
t("Frame 이 필드 분해를 제공한다 (화면이 비트를 자르지 않는다, F-085)",
  "fields" in _fr and _fr["fields"].get("items", {}).get("$ref", "").endswith("FieldSlice"))
_fs = SCHEMAS.get("FieldSlice", {})
t("FieldSlice 가 이름·비트오프셋·폭·값을 갖는다 (F-085)",
  set(_fs.get("required", [])) == {"name", "bit_offset", "bit_width", "raw"},
  str(_fs.get("required")))
t("FieldSlice 가 조항·요소 인덱스를 갖는다 (표 7-14 등 표시용)",
  {"clause", "element", "display"} <= set(_fs.get("properties", {})))
t("Frame 이 judgement 3종을 제공한다 (F-060 · F-085)",
  _fr.get("judgement", {}).get("enum") == ["normal", "violation", "alert"])
t("Frame.required 에 fields·judgement 가 있다",
  {"fields", "judgement"} <= set(SCHEMAS.get("Frame", {}).get("required", [])))
t("Alert 이 원인 프레임을 가리킨다 (F-085)",
  "frame_id" in SCHEMAS.get("Alert", {}).get("properties", {}))
# ── F-092: 속성이 있는 것과 값이 반드시 오는 것은 다르다 ───────
_al = SCHEMAS.get("Alert", {})
t("Alert.required 에 frame_id·siap_nec 가 있다 (nullable 필수, F-092)",
  {"frame_id", "siap_nec"} <= set(_al.get("required", [])), str(_al.get("required")))
t("NEC 알림이면 frame_id 가 non-null 이도록 조건부 강제 (F-092)",
  any(br.get("if", {}).get("properties", {}).get("siap_nec", {}).get("type") == "integer"
      and br.get("then", {}).get("properties", {}).get("frame_id", {}).get("type") == "string"
      for br in _al.get("allOf", [])))
# ── F-091: 생성 경로·거부 증거가 응답 계약에서 생략될 수 없는가 ─
_rule = SCHEMAS.get("Rule", {})
t("Rule.required 에 생성경로·승인·거부 증거가 있다 (F-091)",
  {"generation", "approved_at", "approved_by",
   "rejected_at", "rejected_by", "reject_reason"} <= set(_rule.get("required", [])),
  str(sorted(set(_rule.get("required", [])))))
t("AI 초안이면 generation 이 AI/폴백으로 좁혀진다 (F-091)",
  any(br.get("if", {}).get("properties", {}).get("origin", {}).get("const") == "AI_DRAFT"
      and br.get("then", {}).get("properties", {}).get("generation", {}).get("enum")
          == ["AI", "THRESHOLD_FALLBACK"]
      for br in _rule.get("allOf", [])))
t("거부에는 사유·거부자가 non-null 로 따라온다 (F-091)",
  any("rejected_at" in br.get("if", {}).get("required", [])
      and br.get("then", {}).get("properties", {}).get("reject_reason", {}).get("minLength") == 1
      for br in _rule.get("allOf", [])))

# ═══════════════════════════════════════════════════════════════
#  6. 표준 조항 근거가 문서에 남아 있는가 (CLAUDE.md 3.1)
# ═══════════════════════════════════════════════════════════════
CLAUSE = re.compile(r"(0937|0943|1369-P1|1369-Part1)")
# 아키텍처 설계서가 근거인 것(health)과, 목록 오퍼레이션과 같은 자원을 다루는
# 단건 조회는 제외한다. 그 외에는 표준 조항이 서술에 남아야 한다(CLAUDE.md 3.1).
EXEMPT = {"getHealth", "getNode", "getRule", "getFrame"}
noclause = [op["operationId"] for _, _, op in ops()
            if op["operationId"] not in EXEMPT
            and not CLAUSE.search(op.get("summary", "") + op.get("description", ""))]
t("모든 표준 유래 오퍼레이션에 조항 근거 서술", not noclause, str(noclause))

# ═══════════════════════════════════════════════════════════════
#  7. 반례 매트릭스 — 스키마에 실제로 넣어보고 판정한다 (F-095)
#     "필드가 있다 / 키워드가 있다"는 구조 검사만으로는 F-091·F-092·F-093 이
#     전부 통과했다. required 는 키의 존재만 보고 null 을 막지 않으며,
#     minProperties 는 nullable 필드 하나로 충족된다. 그래서 정상/반례를
#     쌍으로 넣어보고 기대 판정과 맞는지 본다.
# ═══════════════════════════════════════════════════════════════
NOW = "2026-08-07T00:00:00Z"
_RULE_OK = {"id": "r", "created_at": NOW, "origin": "WIZARD", "draft_text": "x",
            "approved": False, "generation": "WIZARD",
            "approved_at": None, "approved_by": None,
            "rejected_at": None, "rejected_by": None, "reject_reason": None}
_ALERT_OK = {"id": "a", "raised_at": NOW, "kind": "NODE_ERROR", "severity": "WARN",
             "message": "m", "install_id": None, "siap_nec": None,
             "frame_id": None, "ack_at": None}
def _minus(d, k): return {a: b for a, b in d.items() if a != k}

# (스키마명, 인스턴스, 유효해야 하는가, 라벨)
MATRIX = [
  # ── F-083 · F-091 초안 요청 ────────────────────────────────
  ("RuleDraftRequest", {"origin": "AI_DRAFT", "model_id": "m1", "inputs": {"pd": 1}}, True,  "AI 초안 정상"),
  ("RuleDraftRequest", {"origin": "AI_DRAFT", "model_id": None},                      False, "AI 초안 + model_id null"),
  ("RuleDraftRequest", {"origin": "AI_DRAFT", "model_id": ""},                        False, "AI 초안 + model_id 빈문자"),
  ("RuleDraftRequest", {"origin": "AI_DRAFT"},                                        False, "AI 초안 + model_id 생략"),
  ("RuleDraftRequest", {"origin": "AI_DRAFT", "model_id": "m1", "draft_text": "손문장"}, False, "AI 초안에 문장 주입"),
  ("RuleDraftRequest", {"origin": "WIZARD", "draft_text": "온도 33 이상 환기"},        True,  "위자드 정상"),
  ("RuleDraftRequest", {"origin": "WIZARD", "draft_text": None},                      False, "위자드 + 문장 null"),
  ("RuleDraftRequest", {"origin": "WIZARD", "draft_text": ""},                        False, "위자드 + 문장 빈값"),
  ("RuleDraftRequest", {"origin": "SCRIPT", "draft_text": None},                      False, "스크립트 + 문장 null"),
  ("RuleDraftRequest", {"origin": "AI_DRAFT", "model_id": "m1", "action": {}},        False, "실행 필드 주입"),
  # ── F-091 규칙 응답 ────────────────────────────────────────
  ("Rule", _RULE_OK,                                                        True,  "규칙 응답 정상"),
  ("Rule", _minus(_RULE_OK, "generation"),                                  False, "생성 경로 생략"),
  ("Rule", _minus(_RULE_OK, "reject_reason"),                               False, "거부 사유 필드 생략"),
  ("Rule", {**_RULE_OK, "origin": "AI_DRAFT", "generation": None},          False, "AI 초안인데 경로 null"),
  ("Rule", {**_RULE_OK, "origin": "AI_DRAFT", "generation": "WIZARD"},      False, "AI 초안인데 경로 위자드"),
  ("Rule", {**_RULE_OK, "origin": "AI_DRAFT", "generation": "THRESHOLD_FALLBACK"}, True, "AI 초안 + 폴백"),
  ("Rule", {**_RULE_OK, "rejected_at": NOW, "rejected_by": "u", "reject_reason": None}, False, "거부인데 사유 null"),
  ("Rule", {**_RULE_OK, "rejected_at": NOW, "rejected_by": "u", "reject_reason": ""},   False, "거부인데 사유 빈값"),
  ("Rule", {**_RULE_OK, "rejected_at": NOW, "rejected_by": "u", "reject_reason": "대상 상이"}, True, "거부 정상"),
  ("RejectRequest", {"reason": "대상 장치가 다름"}, True,  "거부 요청 정상"),
  ("RejectRequest", {"reason": ""},                False, "거부 요청 + 빈 사유"),
  # ── F-092 알림 ────────────────────────────────────────────
  ("Alert", _ALERT_OK,                                          True,  "알림 정상 (프레임 무관)"),
  ("Alert", _minus(_ALERT_OK, "frame_id"),                      False, "frame_id 필드 생략"),
  ("Alert", {**_ALERT_OK, "siap_nec": 7},                       False, "NEC 있는데 프레임 null"),
  ("Alert", {**_ALERT_OK, "siap_nec": 7, "frame_id": "f1"},     True,  "NEC + 프레임 결속"),
  ("Alert", {**_ALERT_OK, "kind": "THRESHOLD"},                 True,  "임계 알림은 프레임 없이"),
  # ── F-088 · F-093 설정 요청 ────────────────────────────────
  ("DevicePropertySelector", {"install_id": "i1"},                              True,  "선택자 개별"),
  ("DevicePropertySelector", {"greenhouse_id": "g1"},                           True,  "선택자 온실 전체"),
  ("DevicePropertySelector", {"greenhouse_id": "g1", "install_location": "중앙"}, True, "선택자 구역 좁힘"),
  ("DevicePropertySelector", {},                                                False, "선택자 빈 객체"),
  ("DevicePropertySelector", {"install_id": None},                              False, "선택자 install_id null"),
  ("DevicePropertySelector", {"greenhouse_id": None},                           False, "선택자 greenhouse_id null"),
  ("DevicePropertySelector", {"install_id": "i1", "greenhouse_id": "g1"},       False, "개별+구역 동시"),
  ("DevicePropertySelector", {"install_location": "중앙"},                       False, "위치만 (대상 불명)"),
  ("DevicePropertyPatch", {"period_sec": 60},          True,  "패치 정상"),
  ("DevicePropertyPatch", {},                          False, "패치 빈 객체"),
  ("DevicePropertyPatch", {"lower_value": 1e39},       False, "패치 float32 초과"),
  ("DevicePropertyPatch", {"period_sec": 16384},       False, "패치 Period 14bit 초과"),
  ("DevicePropertyPatch", {"value": 1},                False, "패치에 제어값 주입"),
  # ── F-084 주입 요청 ────────────────────────────────────────
  ("InjectRequest", {"vector_id": "X03"}, True,  "주입 정상"),
  ("InjectRequest", {"vector_id": "X99"}, False, "주입 미등록 벡터"),
  ("InjectRequest", {"vector": "X03"},    False, "주입 필드명 오기"),
  ("InjectRequest", {},                   False, "주입 벡터 생략"),
  # ── F-158·F-162 장치설치 설치일자 — "컬럼이 있다"와 "값이 온다"는 다르다 ──
  ("Device", {"id": "d1", "device_name": "온도센서", "siap_device_id": 1,
              "installed_at": NOW},                                       True,  "장치설치 정상"),
  ("Device", {"id": "d1", "device_name": "온도센서", "siap_device_id": 1},  False, "설치일자 생략"),
  ("Device", {"id": "d1", "device_name": "온도센서", "siap_device_id": 1,
              "installed_at": ""},                                        False, "설치일자 빈 문자열"),
  ("Device", {"id": "d1", "device_name": "온도센서", "siap_device_id": 1,
              "installed_at": None},                                      False, "설치일자 null"),
  ("Device", {"id": "d1", "device_name": "온도센서", "siap_device_id": 1,
              "installed_at": "not-a-date"},                              False, "설치일자 형식 위반 (F-166)"),
  ("Device", {"id": "d1", "device_name": "온도센서", "siap_device_id": 1,
              "installed_at": "2026-08-01T09:00:00+09:00"},               True,  "설치일자 오프셋 표기 (F-166)"),
]
_mis = [lab for name, inst, want, lab in MATRIX if js_valid(SCHEMAS[name], inst) != want]
t(f"요청·응답 반례 매트릭스 {len(MATRIX)}종 (F-095)", not _mis, str(_mis))

# ── 매트릭스를 표준 구현으로 교차 검증한다 ─────────────────────
#    직접 만든 js_valid 로만 돌리면 '구현하지 않은 키워드'가 통과로 바뀐다.
#    jsonschema 는 개발 편의 도구이며 런타임 의존성이 아니다(CLAUDE.md 4.3).
#    설치 버전은 환경마다 다르다(심사자 PC 는 3.x 일 수 있다). 있는 것 중
#    가장 새 드래프트를 고른다 — 쓰는 키워드는 전부 Draft 7 에 있다.
_xcheck, _why = None, ""
try:
    import warnings as _w; _w.filterwarnings("ignore")
    import jsonschema as _js
    _V = next((getattr(_js, n) for n in
               ("Draft202012Validator", "Draft201909Validator", "Draft7Validator")
               if hasattr(_js, n)), None)
    if _V is None:
        _why = "jsonschema 에 Draft7 이상 검증기 없음"
    else:
        _res = _js.RefResolver.from_schema(SPEC, store={"": SPEC})
        # F-166 — `format` 은 JSON Schema 표준상 기본으로는 주석일 뿐 검증되지
        # 않는다. `FormatChecker` 를 명시로 붙여야 표준 구현도 date-time 형식을
        # 실제로 본다 — 그래야 이 교차검증이 우리 js_valid() 의 format 판정과
        # 의미 있게 비교된다(안 붙이면 양쪽 다 'not-a-date' 를 통과시켜
        # "일치"만 확인하고 버그는 숨는다).
        _fmt = _js.FormatChecker()
        _dis = []
        for name, inst, want, lab in MATRIX:
            std = not list(_V(SCHEMAS[name], resolver=_res, format_checker=_fmt).iter_errors(inst))
            if std != js_valid(SCHEMAS[name], inst): _dis.append(lab)
        _xcheck, _why = not _dis, f"{_V.__name__} / 불일치 {_dis}"
except ImportError:
    _why = "jsonschema 미설치 - pip install jsonschema 로 활성화"
except Exception as _e:                      # 라이브러리 버전 차이는 실패가 아니라 미실행이다
    _why = f"교차 검증 미실행: {type(_e).__name__}"
t(f"자체 검증기 판정이 표준 구현과 일치 ({len(MATRIX)}종, F-095)",
  True if _xcheck is None else _xcheck,
  _why if _xcheck is not False else f"불일치! {_why}")

# ═══════════════════════════════════════════════════════════════
w = max(len(n) for _, n, _ in R)
print("openapi.json 검증  (schema.sql / frame.py 대조)\n")
for ok, n, note in R:
    print(f"  {'PASS' if ok else 'FAIL'}  {n:<{w}}  {note}")
p = sum(1 for o, *_ in R if o)
print(f"\n  {p}/{len(R)} 통과")
sys.exit(0 if p == len(R) else 1)
