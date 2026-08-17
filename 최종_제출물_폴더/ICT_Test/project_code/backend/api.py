"""
backend/api.py — REST + SSE 표면. 스키마 정본은 `project_docs/api/openapi.json`.

`create_app()`이 유일한 조립 지점이다 — `run.py`(구성 루트)가 `SiapLink`·
`FrameBuilder` 구현체(`siap.link.SiapNodeLink`·`siap.build.FrameBuilderImpl`)를
주입한다. 이 파일은 `siap/` 내부 심볼을 import하지 않고 —
`contracts/`(Frame·SiapLink·FrameBuilder Protocol)와 `backend/services/*`만
참조한다.

원칙 4가지(openapi.json info.description과 동일) — ①응답 필드명은
1369-Part1 논리 모델 속성명 그대로 ②노드/디바이스 종류를 경로·스키마에
하드코딩하지 않는다 ③표준 위반 판정은 `siap/codec.py`가 이미 끝냈다, 이
API는 렌더링만 한다 ④제어 실행 경로에서 클라이언트는 명령·대상을 지정할
수 없다 — 승인된 스냅샷에서 서버가 도출한다.
"""
from __future__ import annotations

import json
import os
import sqlite3
import struct
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from fastapi import Body, FastAPI, Header, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

try:                    # 패키지로 import될 때
    from backend import repository
    from backend import db as backend_db
    from backend.services import dms, ems, fcs, fms, mms
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from backend import repository
    from backend import db as backend_db
    from backend.services import dms, ems, fcs, fms, mms

try:
    from contracts.frame import (
        RSC, Subtype, ValueType, DevType, TransType, TransferMode, Status,
        element_count as frame_element_count, resolve_kind,
    )
    from contracts.siap_iface import FrameBuilder, Mode, SiapLink
except ImportError:
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from contracts.frame import (
        RSC, Subtype, ValueType, DevType, TransType, TransferMode, Status,
        element_count as frame_element_count, resolve_kind,
    )
    from contracts.siap_iface import FrameBuilder, Mode, SiapLink


# ═══════════════════════════════════════════════════════════════
#  RFC 9457 오류 응답
# ═══════════════════════════════════════════════════════════════

class ApiProblem(Exception):
    """`application/problem+json` 오류. `clause`·`constraint`·`siap_rsc`는
    표준에서 유래한 거부일 때만 채운다 — 화면이 조항 번호를 그대로 표시한다."""

    def __init__(self, status: int, title: str, *, detail: str | None = None,
                 clause: str | None = None, constraint: str | None = None,
                 siap_rsc: str | None = None) -> None:
        super().__init__(title)
        self.status = status
        self.title = title
        self.detail = detail
        self.clause = clause
        self.constraint = constraint
        self.siap_rsc = siap_rsc

    def body(self) -> dict:
        d: dict[str, Any] = {"type": "about:blank", "title": self.title, "status": self.status}
        if self.detail is not None:
            d["detail"] = self.detail
        if self.clause is not None:
            d["clause"] = self.clause
        if self.constraint is not None:
            d["constraint"] = self.constraint
        if self.siap_rsc is not None:
            d["siap_rsc"] = self.siap_rsc
        return d


def _not_found(what: str) -> ApiProblem:
    return ApiProblem(404, "대상 없음", detail=what)


# ═══════════════════════════════════════════════════════════════
#  시각 변환 — frame_log.t 만 epoch, 나머지는 ISO 8601
# ═══════════════════════════════════════════════════════════════

def _iso_to_epoch(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


# ═══════════════════════════════════════════════════════════════
#  ControlAction 검증 (openapi.json 의 allOf 를 그대로 옮김)
# ═══════════════════════════════════════════════════════════════

_INT_MIN, _INT_MAX = -2_147_483_648, 2_147_483_647
_UINT_MIN, _UINT_MAX = 0, 4_294_967_295
_FLOAT_MAX = 3.4028234663852886e38


def _validate_device_property_request(body: Any) -> tuple[dict, dict]:
    """`DevicePropertyRequest`·`DevicePropertySelector`·`DevicePropertyPatch`의
    닫힌 OpenAPI 입력 계약을 런타임에도 적용한다.
    FastAPI의 타입 없는 ``dict``는 JSON Schema를 자동 적용하지 않으므로
    허용 키·필수 키·타입·범위를 명시적으로 같은 값으로 검사한다."""
    if not isinstance(body, dict):
        raise ApiProblem(400, "잘못된 요청 형식", detail="요청 본문은 객체여야 한다")
    extra_body = set(body) - {"selector", "property"}
    if extra_body or set(body) != {"selector", "property"}:
        raise ApiProblem(400, "잘못된 요청 형식",
                          detail=f"본문은 selector·property만 가져야 한다: extra={sorted(extra_body)}")

    selector, prop = body["selector"], body["property"]
    if not isinstance(selector, dict) or not isinstance(prop, dict) or not prop:
        raise ApiProblem(400, "잘못된 요청 형식",
                          detail="selector·property는 객체이며 property는 최소 1개 필드가 있어야 한다")

    selector_keys = {"install_id", "greenhouse_id", "install_location", "subtype"}
    extra_selector = set(selector) - selector_keys
    if extra_selector:
        raise ApiProblem(400, "잘못된 요청 형식",
                          detail=f"selector에 허용되지 않는 필드가 있다: {sorted(extra_selector)}")
    has_install = "install_id" in selector
    has_greenhouse = "greenhouse_id" in selector
    if has_install == has_greenhouse:
        raise ApiProblem(400, "잘못된 요청 형식",
                          detail="selector는 install_id 또는 greenhouse_id 중 정확히 하나여야 한다")
    if has_install and set(selector) != {"install_id"}:
        raise ApiProblem(400, "잘못된 요청 형식",
                          detail="install_id 개별 선택에는 구역 필터를 함께 쓸 수 없다")
    for key in ("install_id", "greenhouse_id", "install_location"):
        if key in selector and (not isinstance(selector[key], str) or not selector[key]):
            raise ApiProblem(400, "잘못된 요청 형식", detail=f"selector.{key}는 빈 문자열이 아닌 문자열이어야 한다")
    if "subtype" in selector:
        subtype = selector["subtype"]
        if isinstance(subtype, bool) or not isinstance(subtype, int) or not (0 <= subtype <= 255):
            raise ApiProblem(400, "잘못된 요청 형식", detail="selector.subtype은 0~255 정수여야 한다")

    property_keys = {"transfer_mode", "period_sec", "lower_value", "upper_value"}
    extra_property = set(prop) - property_keys
    if extra_property:
        raise ApiProblem(400, "잘못된 요청 형식",
                          detail=f"property에 허용되지 않는 필드가 있다: {sorted(extra_property)}")
    if "transfer_mode" in prop and prop["transfer_mode"] not in {"PERIODIC", "EVENT", "BOTH"}:
        raise ApiProblem(400, "잘못된 요청 형식", detail="property.transfer_mode이 허용 열거값이 아니다")
    if "period_sec" in prop:
        period = prop["period_sec"]
        if isinstance(period, bool) or not isinstance(period, int) or not (0 <= period <= 16383):
            raise ApiProblem(400, "잘못된 요청 형식", detail="property.period_sec은 0~16383 정수여야 한다")
    for key in ("lower_value", "upper_value"):
        if key not in prop:
            continue
        value = prop[key]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not (-_FLOAT_MAX <= float(value) <= _FLOAT_MAX)):
            raise ApiProblem(400, "잘못된 요청 형식",
                              detail=f"property.{key}는 float32 범위의 숫자여야 한다")
    return selector, prop


def _validate_control_action(action: Any) -> dict:
    if not isinstance(action, dict):
        raise ApiProblem(400, "잘못된 요청 형식", detail="action 은 객체여야 한다")
    extra = set(action) - {"value", "value_type", "duration_sec"}
    if extra:
        raise ApiProblem(400, "잘못된 요청 형식",
                          detail=f"action 에 허용되지 않는 필드가 있다: {sorted(extra)} ")
    if "value" not in action or "value_type" not in action:
        raise ApiProblem(400, "잘못된 요청 형식", detail="action.value, action.value_type 는 필수다")
    vt = action["value_type"]
    if vt not in ("INT", "UINT", "FLOAT"):
        raise ApiProblem(400, "잘못된 요청 형식",
                          detail=f"value_type={vt!r} 는 INT/UINT/FLOAT 중 하나여야 한다(0x03 Reserved)")
    v = action["value"]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ApiProblem(400, "잘못된 요청 형식", detail=f"value={v!r} 는 숫자가 아니다")
    if vt in ("INT", "UINT"):
        if not float(v).is_integer():
            raise ApiProblem(400, "잘못된 요청 형식", detail=f"value_type={vt} 인데 value={v} 는 정수가 아니다")
        v = int(v)
        lo, hi = (_INT_MIN, _INT_MAX) if vt == "INT" else (_UINT_MIN, _UINT_MAX)
        if not (lo <= v <= hi):
            raise ApiProblem(400, "잘못된 요청 형식",
                              detail=f"value={v} 가 {vt} 32bit 범위를 벗어난다")
    else:
        if not (-_FLOAT_MAX <= float(v) <= _FLOAT_MAX):
            raise ApiProblem(400, "잘못된 요청 형식",
                              detail=f"value={v} 가 FLOAT 표현 가능 범위를 벗어난다")
    duration = action.get("duration_sec")
    if duration is not None:
        if isinstance(duration, bool) or not isinstance(duration, int) or duration < 0:
            raise ApiProblem(400, "잘못된 요청 형식", detail=f"duration_sec={duration!r} 는 0 이상 정수여야 한다")
    return {"value": v, "value_type": vt, **({"duration_sec": duration} if duration is not None else {})}


# ═══════════════════════════════════════════════════════════════
#  응답 변환 — DB row/dataclass → openapi.json 스키마 dict
# ═══════════════════════════════════════════════════════════════

#: 0943 그림 7-1 헤더 7필드의 비트 폭. `contracts/frame.py::Header`의 필드
#: 선언 순서·주석(version:8, msg_type:14, trans_type:2, msg_id:16,
#: payload_len:16, gcg_id:20, node_id:20)과 동일 — 새로 해석하지 않고
#: 그대로 옮긴 것이다. 가변 요소(DEVICE_MAIN_INFO 등) 필드 분해는
#: `_payload_field_slices()`가 이어받는다(아래).
_HEADER_FIELD_LAYOUT: tuple[tuple[str, int], ...] = (
    ("Version", 8), ("Message Type", 14), ("Transmission Type", 2),
    ("Message Identifier", 16), ("Payload Length", 16), ("GCG ID", 20), ("Node ID", 20),
)


def _header_field_slices(f: repository.models.FrameLog) -> list[dict]:
    values = (f.version, f.msg_type, f.trans_type, f.msg_id, f.payload_len, f.gcg_id, f.node_id)
    out, offset = [], 0
    for (name, width), value in zip(_HEADER_FIELD_LAYOUT, values):
        # Transmission Type(표 7-6)만 코드→이름 디코딩. 나머지 헤더는 수치.
        disp = _enum_name(TransType, value) if name == "Transmission Type" and value is not None else None
        out.append({"name": name, "bit_offset": offset, "bit_width": width,
                     "raw": value if value is not None else 0, "display": disp,
                     "element": None, "clause": "그림 7-1"})
        offset += width
    return out


#: 표 7-14 DEVICE_MAIN_INFO(56bit). `siap/codec.py::encode_dmi()`의 `w.write(...)`
#: 호출 순서·폭을 그대로 옮긴 것이다(새로 해석하지 않는다) — 값 자체는 `ingest.py`가
#: 이미 디코딩해 `frame_log.elements_json`에 저장해 둔 것을 읽을 뿐이다.
_DMI_FIELD_LAYOUT: tuple[tuple[str, int, str], ...] = (
    ("Device ID", 8, "device_id"), ("Type", 1, "dev_type"), ("Subtype", 8, "subtype"),
    ("Value Type", 2, "value_type"), ("Reserved", 5, None), ("Value", 32, "value"),
)
#: 표 7-15 DEVICE_PROPERTY(240bit) = DEVICE_MAIN_INFO(56bit) + 아래 8필드.
#: `siap/codec.py::encode_dp()`의 `w.write(...)` 순서·폭 그대로.
_DP_EXTRA_FIELD_LAYOUT: tuple[tuple[str, int, str], ...] = (
    ("Transfer Mode", 2, "transfer_mode"), ("Period", 14, "period"),
    ("Lower Value", 32, "lower_value"), ("Upper Value", 32, "upper_value"),
    ("Lower Limit", 32, "lower_limit"), ("Upper Limit", 32, "upper_limit"),
    ("Precision", 32, "precision"), ("Status", 8, "status"),
)
DMI_BIT_WIDTH = sum(w for _, w, _ in _DMI_FIELD_LAYOUT)                  # 56
DP_BIT_WIDTH = DMI_BIT_WIDTH + sum(w for _, w, _ in _DP_EXTRA_FIELD_LAYOUT)  # 240

#: FieldSlice.raw 계약은 "원시 비트열을 부호 없는 정수로"다. `elements_json`
#: 에는 이미 해석된 값(음수 INT·FLOAT 포함)이 들어 있어 이 필드들만 역산이
#: 필요하다 — 나머지(device_id·subtype 등)는 원래도 부호 없는 정수다.
_VALUE_LIKE_KEYS = {"value", "lower_value", "upper_value", "lower_limit", "upper_limit", "precision"}


def _value_to_raw_bits(value, value_type: int) -> int:
    """이미 해석된 값에서 32bit 부호 없는 원시 비트열을 역산한다. IEEE-754·
    2의 보수 변환은 고정된 산술 규칙이지 표준을 다시 해석하는 게 아니다 —
    엔디안·FLOAT 표현 결정(big-endian, IEEE-754 single)을 그대로 따른다."""
    if value_type == int(ValueType.FLOAT):
        return struct.unpack(">I", struct.pack(">f", float(value)))[0]
    return int(value) & 0xFFFFFFFF


def _enum_name(enum_cls, raw: int) -> str | None:
    """코드값 → 표준 enum 이름(정본). 미정의 코드면 None(화면은 raw 로 대체)."""
    try:
        return enum_cls(raw).name
    except ValueError:
        return None


def _fmt_num(v) -> str | None:
    if v is None or isinstance(v, bool):
        return None
    return f"{v:g}" if isinstance(v, float) else str(v)


def _dmi_field_display(key: str | None, raw: int, item: dict) -> str | None:
    """표 7-14/7-15 코드 필드엔 표준 enum 이름을, 값 계열엔 디코딩된 실제
    값을 단다(화면은 이 문자열을 그대로 보여줄 뿐 다시 해석하지 않는다,
    §3.4 — 정본 enum(contracts/frame.py)을 재사용한다)."""
    if key == "dev_type":
        return _enum_name(DevType, raw)
    if key == "value_type":
        return _enum_name(ValueType, raw)
    if key == "subtype":
        return _enum_name(Subtype, raw)
    if key == "transfer_mode":
        return _enum_name(TransferMode, raw)
    if key == "status":
        return _enum_name(Status, raw)
    if key in _VALUE_LIKE_KEYS:
        return _fmt_num(item.get(key))
    return None


def _payload_field_slices(f: repository.models.FrameLog) -> list[dict]:
    """`frame_log.elements_json`(ingest.py가 저장한, 이미 디코딩된 가변 요소)을
    `_header_field_slices()`와 이어지는 `FieldSlice` 목록으로
    편다. 비트 재파싱을 하지 않는다 — 값은 전부 저장된 JSON에서 그대로
    읽는다. `elements_json`이 없으면(고정부만 있는 메시지·위반 프레임 등)
    빈 목록."""
    if not f.elements_json:
        return []
    items = json.loads(f.elements_json)
    out: list[dict] = []
    offset = sum(w for _, w in _HEADER_FIELD_LAYOUT)
    for idx, item in enumerate(items):
        layout = _DMI_FIELD_LAYOUT if item["kind"] == "DMI" else _DMI_FIELD_LAYOUT + _DP_EXTRA_FIELD_LAYOUT
        for name, width, key in layout:
            if key is None:
                raw = 0
            elif key in _VALUE_LIKE_KEYS:
                raw = _value_to_raw_bits(item.get(key, 0), item["value_type"])
            else:
                raw = int(item.get(key, 0))
            out.append({"name": name, "bit_offset": offset, "bit_width": width,
                         "raw": raw, "display": _dmi_field_display(key, raw, item),
                         "element": idx, "clause": "표 7-14" if item["kind"] == "DMI" else "표 7-15"})
            offset += width
    return out


def _node_dict(conn: sqlite3.Connection, node_id: int, prop) -> dict:
    return {
        "node_id": node_id, "gcg_id": prop.gcg_id, "sw_version": prop.sw_version,
        "status": prop.status.name, "device_count": prop.num_devices,
        "connected_at": repository.node_connected_at(conn, node_id),
        "last_seen_at": repository.node_last_seen_at(conn, node_id),
    }


def _device_dict(conn: sqlite3.Connection, install) -> dict:
    info = repository.get_by_id(conn, "device_info", install.device_info_id)
    device_kind = info.device_kind if info is not None and info.device_kind in ("SENSOR", "ACTUATOR") else None
    subtype_name = None
    if install.siap_subtype is not None:
        try:
            subtype_name = Subtype(install.siap_subtype).name
        except ValueError:
            subtype_name = None
    return {
        "id": install.id, "created_at": install.created_at, "updated_at": install.updated_at,
        "device_name": install.device_name, "installed_at": install.installed_at,
        "install_location": install.install_location, "install_loc_unit": install.install_loc_unit,
        "device_info_id": install.device_info_id, "device_kind": device_kind,
        "siap_node_id": install.siap_node_id, "siap_device_id": install.siap_device_id,
        "siap_subtype": install.siap_subtype, "subtype": subtype_name,
        "transfer_mode": install.transfer_mode, "period_sec": install.period_sec,
        "unit": install.unit, "lower_limit": install.lower_limit, "upper_limit": install.upper_limit,
        "precision_val": install.precision_val,
    }


def _telemetry_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "measured_at": row["measured_at"], "location": row["location"],
        "location_unit": row["location_unit"], "install_id": row["install_id"],
        "subtype": row["subtype"], "value": row["value"], "unit": row["unit"],
        "error_range": row["error_range"], "lower_limit": row["lower_limit"],
        "upper_limit": row["upper_limit"],
    }


def _device_state_dict(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    return {
        "id": row["id"], "reported_at": row["reported_at"], "install_id": row["install_id"],
        "subtype": row["subtype"],
        "attributes": repository.device_state_attributes(conn, row["id"], row["subtype"]),
    }


def _alert_dict(a) -> dict:
    return {
        "id": a.id, "raised_at": a.raised_at, "kind": a.kind, "severity": a.severity,
        "install_id": a.install_id, "siap_nec": a.siap_nec, "message": a.message,
        "ack_at": a.ack_at, "frame_id": a.frame_id,
    }


def _source_dict(s) -> dict:
    return {"id": s.id, "name": s.name, "provider": s.provider, "registered_at": s.registered_at,
            "updated_at": s.updated_at, "source_url": s.source_url, "license": s.license,
            "scope": s.scope}


def _record_dict(r) -> dict:
    return {"id": r.id, "source_id": r.source_id, "fetched_at": r.fetched_at,
            "period_from": r.period_from, "period_to": r.period_to, "region": r.region,
            "item": r.item, "payload": json.loads(r.payload) if r.payload else None}


def _rule_dict(r) -> dict:
    return {
        "id": r.id, "model_id": r.model_id, "created_at": r.created_at, "origin": r.origin,
        "draft_text": r.draft_text, "condition_expr": r.condition_expr,
        "action": json.loads(r.action_json) if r.action_json else None,
        "target_install_id": r.target_install_id, "approved": r.is_approved,
        "approved_at": r.approved_at, "approved_by": r.approved_by, "generation": r.generation,
        "rejected_at": r.rejected_at, "rejected_by": r.rejected_by, "reject_reason": r.reject_reason,
    }


def _execution_dict(e) -> dict:
    rsc_name = None
    if e.result_rsc is not None:
        try:
            rsc_name = RSC(e.result_rsc).name
        except ValueError:
            rsc_name = None
    return {
        "id": e.id, "origin": e.origin, "rule_id": e.rule_id, "issued_by": e.issued_by,
        "install_id": e.install_id, "issued_at": e.issued_at,
        "command": json.loads(e.command_json), "siap_msg_id": e.siap_msg_id,
        "result_rsc": e.result_rsc, "result_rsc_name": rsc_name, "responded_at": e.responded_at,
    }


def _frame_dict(conn: sqlite3.Connection, f, proto_mode: Mode) -> dict:
    header = {"version": f.version, "msg_type": f.msg_type, "trans_type": f.trans_type,
              "msg_id": f.msg_id, "payload_len": f.payload_len, "gcg_id": f.gcg_id,
              "node_id": f.node_id}
    kind_name, elem = None, None
    if f.is_valid and f.msg_type is not None and f.payload_len is not None:
        # `resolve_kind`/`element_count`는 contracts/frame.py의 순수 함수다 —
        # siap/codec.py 를 다시 구현하지 않는다. 위반 프레임은 kind 를 재판정하지
        # 않고, is_valid 인 프레임만 표시용으로 푼다.
        kind = resolve_kind(f.msg_type, f.payload_len, proto_mode)
        if kind is not None:
            kind_name = kind.name
            elem = frame_element_count(kind, f.payload_len)
    violations = [{"code": v.code, "code_name": v.code_name, "clause": v.clause,
                   "detail": v.detail or ""} for v in repository.list_frame_violations(conn, f.id)]
    return {
        "id": f.id, "t": f.t, "direction": f.direction, "raw_hex": f.raw_hex,
        "header": header, "kind": kind_name, "element_count": elem, "is_valid": f.is_valid,
        "violations": violations,
        "fields": _header_field_slices(f) + _payload_field_slices(f),
        "judgement": repository.frame_judgement(conn, f),
    }


def _page(items: list, total: int, limit: int, offset: int) -> dict:
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ═══════════════════════════════════════════════════════════════
#  create_app — 유일한 조립 지점
# ═══════════════════════════════════════════════════════════════

def create_app(*, db_path: str | Path, link: SiapLink, builder: FrameBuilder,
               run_mode: str = "replay", proto_mode: Mode = "strict",
               default_timeout: float | None = None,
               inject_fn: Callable[[str], bytes] | None = None) -> FastAPI:
    """`run.py`(구성 루트)가 부른다. `link`·`builder`는 `contracts/siap_iface.py`
    Protocol만 만족하면 된다 — 테스트는 `contracts/fake_link.py`의
    `FakeSiapLink`·`FakeFrameBuilder`를 넘긴다.

    `inject_fn` — `POST /sim/inject`가 골든 벡터 원본 바이트를 실제
    전송 계층에 흘려보낼 때 쓰는 훅. simulate 모드에서는 `run.py`가
    `sim/inject.py`를 감싼 콜백을 넘긴다(`sim/`도 계약 경계 반대편이라
    이 파일이 직접 import하지 않는다). 없으면
    (`None`) 항상 409로 거부한다."""
    app = FastAPI(
        title="표준 프로토콜 기반 개방형 스마트온실 노드 - REST API",
        version="1.0.0",
    )
    app.state.db_path = Path(db_path)
    app.state.link = link
    app.state.builder = builder
    app.state.run_mode = run_mode
    app.state.proto_mode = proto_mode
    app.state.default_timeout = default_timeout
    app.state.inject_fn = inject_fn
    app.state.start_time = time.monotonic()

    def get_conn() -> sqlite3.Connection:
        """호출마다 새 연결을 연다(`backend/db.py` 계약 그대로) — API
        스레드가 자신만의 연결로 쓰기까지 끝낸다."""
        return backend_db.connect(app.state.db_path)

    @app.exception_handler(ApiProblem)
    def _problem_handler(request: Request, exc: ApiProblem):      # noqa: ARG001
        return JSONResponse(status_code=exc.status, content=exc.body(),
                             media_type="application/problem+json")

    def _require_user(x_user_id: str, conn: sqlite3.Connection) -> str:
        if not repository.user_exists(conn, x_user_id):
            raise ApiProblem(400, "잘못된 요청 형식",
                              detail=f"X-User-Id={x_user_id!r} 가 사용자정보에 실재하지 않는다(1369-P1 7.2.2.6)")
        return x_user_id

    # ── system ──────────────────────────────────────────────────
    @app.get("/api/v1/health")
    def get_health():
        stats = link.stats()
        alive = stats.get("uptime", 0) > 0
        return {
            "status": "ok" if alive else "degraded",
            "run_mode": run_mode,
            "proto_mode": proto_mode,
            "io_thread_alive": alive,
            "public_data_fallback": os.environ.get(dms.API_KEY_ENV) is None,
            "link": stats,
        }

    # ── ems ─────────────────────────────────────────────────────
    @app.get("/api/v1/nodes")
    def list_nodes(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            nodes = ems.list_nodes(conn, link)
        finally:
            conn.close()
        return _page(nodes[offset:offset + limit], len(nodes), limit, offset)

    @app.get("/api/v1/nodes/{nodeId}")
    def get_node(nodeId: int):
        conn = get_conn()
        try:
            node = ems.get_node(conn, link, nodeId)
        finally:
            conn.close()
        if node is None:
            raise _not_found(f"node_id={nodeId}")
        return node

    @app.get("/api/v1/nodes/{nodeId}/devices")
    def list_node_devices(nodeId: int):
        if nodeId not in link.registry():
            raise _not_found(f"node_id={nodeId}")
        conn = get_conn()
        try:
            installs = ems.list_node_devices(conn, nodeId)
            devices = [_device_dict(conn, i) for i in installs]
        finally:
            conn.close()
        return _page(devices, len(devices), len(devices), 0)

    @app.patch("/api/v1/device-property")
    def set_device_property(body: dict = Body(...), x_user_id: str = Header(..., alias="X-User-Id")):
        selector, prop = _validate_device_property_request(body)
        conn = get_conn()
        try:
            _require_user(x_user_id, conn)
            try:
                installs = ems.set_device_property(conn, link, builder, selector=selector,
                                                     property_patch=prop, user_id=x_user_id,
                                                     timeout=default_timeout)
            except ems.DevicePropertyError as e:
                raise ApiProblem(e.status, "디바이스 속성 설정 실패", detail=str(e), siap_rsc=e.siap_rsc) from e
            devices = [_device_dict(conn, i) for i in installs]
        finally:
            conn.close()
        return _page(devices, len(devices), len(devices) or 1, 0)

    # ── fms ─────────────────────────────────────────────────────
    @app.get("/api/v1/telemetry")
    def list_telemetry(install_id: str | None = None, subtype: str | None = None,
                        since: str | None = None, until: str | None = None,
                        limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            rows, total = fms.query_env(conn, install_id=install_id, subtype=subtype,
                                         since=since, until=until, limit=limit, offset=offset)
            items = [_telemetry_dict(r) for r in rows]
        finally:
            conn.close()
        return _page(items, total, limit, offset)

    @app.get("/api/v1/device-states")
    def list_device_states(install_id: str | None = None, subtype: str | None = None,
                            since: str | None = None, until: str | None = None,
                            limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            rows, total = fms.query_device_states(conn, install_id=install_id, subtype=subtype,
                                                    since=since, until=until, limit=limit, offset=offset)
            items = [_device_state_dict(conn, r) for r in rows]
        finally:
            conn.close()
        return _page(items, total, limit, offset)

    @app.get("/api/v1/alerts")
    def list_alerts(since: str | None = None, until: str | None = None,
                     unacked: bool | None = None, limit: int = Query(100, ge=1, le=500),
                     offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            # 0937 6.4-3 "미수집 알림"이 실제로 생성되는 유일한 진입점. 전용
            # 스케줄러 스레드를 새로 두지 않고 조회 시점에 판정한다(check-on-read) —
            # 이 목록을 읽는 사람이 그 시점 기준 최신 판정을 보장받는다. `/stream`
            # (SSE)도 매 틱 같은 함수를 불러 대시보드가 실시간에 가깝게 갱신된다.
            fms.check_stale_devices(conn, repository.now_iso())
            rows, total = fms.list_alerts(conn, since=since, until=until, unacked=unacked,
                                           limit=limit, offset=offset)
            items = [_alert_dict(a) for a in rows]
        finally:
            conn.close()
        return _page(items, total, limit, offset)

    # ── conformance ─────────────────────────────────────────────
    @app.get("/api/v1/frames")
    def list_frames(direction: str | None = None, valid: bool | None = None,
                     node_id: int | None = None, since: str | None = None, until: str | None = None,
                     limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            rows, total = repository.list_frames(
                conn, direction=direction, valid=valid, node_id=node_id,
                since=_iso_to_epoch(since) if since else None,
                until=_iso_to_epoch(until) if until else None, limit=limit, offset=offset,
            )
            items = [_frame_dict(conn, f, proto_mode) for f in rows]
        finally:
            conn.close()
        return _page(items, total, limit, offset)

    @app.get("/api/v1/frames/violations")
    def list_frame_violations_ep(code: int | None = None, clause: str | None = None,
                                  since: str | None = None, until: str | None = None,
                                  limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            rows, total = repository.list_violation_frames(
                conn, code=code, clause=clause,
                since=_iso_to_epoch(since) if since else None,
                until=_iso_to_epoch(until) if until else None, limit=limit, offset=offset,
            )
            items = [_frame_dict(conn, f, proto_mode) for f in rows]
        finally:
            conn.close()
        return _page(items, total, limit, offset)

    @app.get("/api/v1/frames/{frameId}")
    def get_frame(frameId: str):
        conn = get_conn()
        try:
            f = repository.get_frame(conn, frameId)
            if f is None:
                raise _not_found(f"frame_id={frameId}")
            return _frame_dict(conn, f, proto_mode)
        finally:
            conn.close()

    @app.get("/api/v1/stream")
    async def stream_events(events: str | None = None, request: Request = None):
        """SSE — node_up/node_down/frame/violation/alert/execution. 폴백은
        1초 폴링 — 이 엔드포인트 자체는 0.5초 간격으로
        DB·`link.registry()`를 다시 읽어 새 행만 내보낸다."""
        wanted = set(events.split(",")) if events else None

        async def gen() -> Iterator[bytes]:
            import asyncio
            conn = get_conn()
            try:
                known_nodes = set(link.registry().keys())
                last_frame_t = 0.0
                last_alert_seen: set[str] = set()
                last_exec_seen: set[str] = set()
                while True:
                    if request is not None and await request.is_disconnected():
                        return
                    now_nodes = set(link.registry().keys())
                    for nid in now_nodes - known_nodes:
                        if wanted is None or "node_up" in wanted:
                            node = ems.get_node(conn, link, nid)
                            yield f"event: node_up\ndata: {json.dumps(node, ensure_ascii=False)}\n\n".encode("utf-8")
                    for nid in known_nodes - now_nodes:
                        if wanted is None or "node_down" in wanted:
                            yield f"event: node_down\ndata: {json.dumps({'node_id': nid}, ensure_ascii=False)}\n\n".encode("utf-8")
                    known_nodes = now_nodes

                    frames, _ = repository.list_frames(conn, since=last_frame_t, limit=50, offset=0)
                    for f in reversed(frames):
                        if f.t <= last_frame_t:
                            continue
                        last_frame_t = max(last_frame_t, f.t)
                        d = _frame_dict(conn, f, proto_mode)
                        ev = "violation" if not f.is_valid else "frame"
                        if wanted is None or ev in wanted:
                            yield f"event: {ev}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n".encode("utf-8")

                    fms.check_stale_devices(conn, repository.now_iso())
                    alerts, _ = repository.list_alerts_page(conn, limit=20, offset=0)
                    for a in alerts:
                        if a.id in last_alert_seen:
                            continue
                        last_alert_seen.add(a.id)
                        if wanted is None or "alert" in wanted:
                            yield f"event: alert\ndata: {json.dumps(_alert_dict(a), ensure_ascii=False)}\n\n".encode("utf-8")

                    execs, _ = repository.list_control_executions(conn, limit=20, offset=0)
                    for e in execs:
                        if e.id in last_exec_seen:
                            continue
                        last_exec_seen.add(e.id)
                        if wanted is None or "execution" in wanted:
                            yield f"event: execution\ndata: {json.dumps(_execution_dict(e), ensure_ascii=False)}\n\n".encode("utf-8")

                    await asyncio.sleep(0.5)
            finally:
                conn.close()

        return StreamingResponse(gen(), media_type="text/event-stream")

    # ── dms ─────────────────────────────────────────────────────
    @app.get("/api/v1/publicdata/sources")
    def list_publicdata_sources():
        conn = get_conn()
        try:
            sources = repository.list_public_data_sources(conn)
        finally:
            conn.close()
        items = [_source_dict(s) for s in sources]
        return _page(items, len(items), len(items), 0)

    @app.get("/api/v1/publicdata/records")
    def list_publicdata_records(source_id: str | None = None, since: str | None = None,
                                 until: str | None = None,
                                 limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            recs, total = dms.list_records(conn, source_id=source_id, since=since, until=until,
                                            limit=limit, offset=offset)
            items = [_record_dict(r) for r in recs]
        finally:
            conn.close()
        return _page(items, total, limit, offset)

    # ── mms ─────────────────────────────────────────────────────
    @app.get("/api/v1/rules")
    def list_rules(approved: bool | None = None, limit: int = Query(100, ge=1, le=500),
                    offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            rules, total = repository.list_control_rules(conn, approved=approved, limit=limit, offset=offset)
            items = [_rule_dict(r) for r in rules]
        finally:
            conn.close()
        return _page(items, total, limit, offset)

    @app.post("/api/v1/rules", status_code=201)
    def create_rule_draft(body: dict = Body(...)):
        origin = body.get("origin")
        if origin not in ("AI_DRAFT", "WIZARD", "SCRIPT"):
            raise ApiProblem(400, "잘못된 요청 형식", detail="origin 은 AI_DRAFT/WIZARD/SCRIPT 중 하나여야 한다")
        extra = set(body) - {"origin", "model_id", "inputs", "draft_text", "condition_expr"}
        if extra:
            raise ApiProblem(400, "잘못된 요청 형식", detail=f"허용되지 않는 필드: {sorted(extra)}")
        conn = get_conn()
        try:
            if origin == "AI_DRAFT":
                model_id = body.get("model_id")
                if not model_id:
                    raise ApiProblem(400, "잘못된 요청 형식", detail="origin=AI_DRAFT 는 model_id 가 필수다")
                inputs = dict(body.get("inputs") or {})
                # 0937 6.3-3/6.3-4 — DMS 가 사전 획득한 공공데이터를 입력으로 쓴다.
                record_id = inputs.get("public_data_record_id")
                if record_id:
                    rec = repository.get_by_id(conn, "public_data_record", record_id)
                else:
                    rec, fallback = dms.fetch_public_data(conn)
                if rec is not None:
                    inputs["forecast_payload"] = json.loads(rec.payload)
                try:
                    rule = mms.draft_rule(conn, origin=origin, model_id=model_id, inputs=inputs,
                                           condition_expr=body.get("condition_expr"))
                except mms.RuleNotFound as e:
                    raise _not_found(str(e)) from e
            else:
                draft_text = body.get("draft_text")
                if not draft_text:
                    raise ApiProblem(400, "잘못된 요청 형식", detail=f"origin={origin} 는 draft_text 가 필수다")
                rule = mms.draft_rule(conn, origin=origin, draft_text=draft_text,
                                       condition_expr=body.get("condition_expr"))
            return JSONResponse(status_code=201, content=_rule_dict(rule))
        finally:
            conn.close()

    @app.get("/api/v1/rules/{ruleId}")
    def get_rule(ruleId: str):
        conn = get_conn()
        try:
            rule = repository.get_control_rule(conn, ruleId)
        finally:
            conn.close()
        if rule is None:
            raise _not_found(f"rule_id={ruleId}")
        return _rule_dict(rule)

    @app.post("/api/v1/rules/{ruleId}/approve")
    def approve_rule(ruleId: str, body: dict = Body(...), x_user_id: str = Header(..., alias="X-User-Id")):
        required = {"condition_expr", "action", "target_install_id"}
        if set(body) != required:
            raise ApiProblem(400, "잘못된 요청 형식",
                              detail=f"condition_expr·action·target_install_id 셋 모두 필수다(부분 승인 없음). 받은 필드: {sorted(body)}")
        action = _validate_control_action(body["action"])
        conn = get_conn()
        try:
            _require_user(x_user_id, conn)
            try:
                rule = mms.approve_rule(conn, ruleId, user_id=x_user_id,
                                         condition_expr=body["condition_expr"], action=action,
                                         target_install_id=body["target_install_id"])
            except mms.RuleNotFound as e:
                raise _not_found(str(e)) from e
            except mms.RuleGateError as e:
                raise ApiProblem(409, "이미 승인된 규칙", detail=str(e), clause="0937 A.3.2",
                                  constraint=e.constraint) from e
            return _rule_dict(rule)
        finally:
            conn.close()

    @app.post("/api/v1/rules/{ruleId}/reject")
    def reject_rule(ruleId: str, body: dict = Body(...), x_user_id: str = Header(..., alias="X-User-Id")):
        reason = body.get("reason")
        if not isinstance(reason, str) or not reason.strip() or set(body) != {"reason"}:
            raise ApiProblem(400, "잘못된 요청 형식", detail="reason(빈 문자열 아님) 만 받는다")
        conn = get_conn()
        try:
            _require_user(x_user_id, conn)
            try:
                rule = mms.reject_rule(conn, ruleId, user_id=x_user_id, reason=reason)
            except mms.RuleNotFound as e:
                raise _not_found(str(e)) from e
            except mms.RuleGateError as e:
                raise ApiProblem(409, "이미 승인되었거나 거부된 규칙", detail=str(e), clause="0937 A.3.2",
                                  constraint=e.constraint) from e
            return _rule_dict(rule)
        finally:
            conn.close()

    # ── fcs ─────────────────────────────────────────────────────
    @app.post("/api/v1/rules/{ruleId}/execute", status_code=202)
    def execute_rule(ruleId: str):
        conn = get_conn()
        try:
            try:
                execution = fcs.execute(conn, link, builder, ruleId, timeout=default_timeout)
            except LookupError as e:
                raise _not_found(str(e)) from e
            except fcs.ExecutionGateError as e:
                raise ApiProblem(409, "미승인 규칙으로는 제어를 실행할 수 없다", detail=str(e),
                                  clause="0937 A.3.2", constraint=e.constraint) from e
            except fcs.ExecutionTimeoutError as e:
                raise ApiProblem(504, "노드 응답 시간 초과", detail=str(e)) from e
            return JSONResponse(status_code=202, content=_execution_dict(execution))
        finally:
            conn.close()

    @app.post("/api/v1/control", status_code=202)
    def manual_control(body: dict = Body(...), x_user_id: str = Header(..., alias="X-User-Id")):
        if set(body) != {"install_id", "action"}:
            raise ApiProblem(400, "잘못된 요청 형식", detail="install_id·action 만 받는다")
        action = _validate_control_action(body["action"])
        conn = get_conn()
        try:
            _require_user(x_user_id, conn)
            try:
                execution = fcs.manual_control(conn, link, builder, install_id=body["install_id"],
                                                action=action, user_id=x_user_id, timeout=default_timeout)
            except LookupError as e:
                raise _not_found(str(e)) from e
            except fcs.ExecutionTimeoutError as e:
                raise ApiProblem(504, "노드 응답 시간 초과", detail=str(e)) from e
            return JSONResponse(status_code=202, content=_execution_dict(execution))
        finally:
            conn.close()

    @app.get("/api/v1/executions")
    def list_executions(origin: str | None = None, install_id: str | None = None,
                         since: str | None = None, until: str | None = None,
                         limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
        conn = get_conn()
        try:
            execs, total = fcs.query_history(conn, origin=origin, install_id=install_id,
                                              since=since, until=until, limit=limit, offset=offset)
            items = [_execution_dict(e) for e in execs]
        finally:
            conn.close()
        return _page(items, total, limit, offset)

    # ── conformance: 위반 주입 ──────────────────────────────────
    @app.post("/api/v1/sim/inject", status_code=202)
    def inject_vector(body: dict = Body(...), x_user_id: str = Header(..., alias="X-User-Id")):
        vector_id = body.get("vector_id")
        if vector_id not in {f"X0{i}" for i in range(1, 9)} or set(body) != {"vector_id"}:
            raise ApiProblem(400, "잘못된 요청 형식", detail="vector_id 는 X01~X08 중 하나만 받는다")
        if run_mode == "hardware":
            raise ApiProblem(409, "hardware 모드에서는 주입할 수 없다",
                              detail="실물 링크에 조작된 프레임을 흘리면 실측 로그의 신뢰성이 깨진다")
        conn = get_conn()
        try:
            _require_user(x_user_id, conn)
            if app.state.inject_fn is None:
                raise ApiProblem(409, "이 실행 모드에서는 주입을 지원하지 않는다",
                                  detail=f"run_mode={run_mode}")
            raw = app.state.inject_fn(vector_id)
            raw_hex = raw.hex().upper()
            deadline = time.monotonic() + 1.0
            frame_row = None
            while time.monotonic() < deadline:
                frames, _ = repository.list_frames(conn, direction="rx", limit=20, offset=0)
                for f in frames:
                    if f.raw_hex.upper() == raw_hex:
                        frame_row = f
                        break
                if frame_row is not None:
                    break
                time.sleep(0.05)
                conn.close()
                conn = get_conn()
            if frame_row is None:
                return JSONResponse(status_code=202, content={
                    "id": "", "t": time.time(), "direction": "rx", "raw_hex": raw_hex,
                    "header": None, "kind": None, "element_count": None, "is_valid": False,
                    "violations": [], "fields": [], "judgement": "violation",
                })
            return JSONResponse(status_code=202, content=_frame_dict(conn, frame_row, proto_mode))
        finally:
            conn.close()

    # ── web/ 정적 서빙 ────────────────────────────────────────────
    # web/ 은 빌드 없는 순수 바닐라라 파일을 그대로 서빙하면 된다. 같은
    # 오리진(http://127.0.0.1:8000)에서 API 와 화면을 함께 띄워
    # CORS 를 아예 필요 없게 만드는 쪽을 골랐다 — 새 의존성도, 새 오리진
    # 헤더 관리도 늘리지 않는다. `/api/v1/*` 라우트가 먼저 등록돼 있으므로
    # 이 마운트는 그 외 경로("/", "/verify.html" 등)만 받는다. `html=True`
    # 로 확장자 없는 "/" 요청에 index.html 을 돌려준다.
    web_dir = Path(__file__).resolve().parent.parent / "web"
    if web_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app
