"""backend/tests/test_api.py — REST + SSE 표면 (backend/api.py).

`fastapi.testclient.TestClient`가 요구하는 `httpx`는 `wheels/`에 없다 —
`_asgi_client.py`(같은 디렉터리, 의존성 0)로 ASGI 요청을 직접 흘려보낸다.

`SiapLink`·`FrameBuilder`는 실제 프로토콜 계층(`siap/`) 대신
`contracts/fake_link.py`의 대역체를 쓴다 — `backend/`는 애초에 `siap/`를
import하지 않으므로(CLAUDE.md §2.2) 이 테스트도 그 경계를 넘지 않는다.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from _asgi_client import call, call_stream

from backend import db, repository
from backend.api import create_app
from contracts.fake_link import FakeFrameBuilder, FakeSiapLink
from contracts.frame import DeviceMainInfo, DevType, NodeProperty, Status, ValueType


@pytest.fixture()
def conn(tmp_path):
    con = db.init_db(tmp_path / "api.db", seed=True)
    yield con
    con.close()


@pytest.fixture()
def link():
    lk = FakeSiapLink()
    lk.start("simulate")
    return lk


@pytest.fixture()
def builder():
    return FakeFrameBuilder(gcg_id=1)


@pytest.fixture()
def app(tmp_path, conn, link, builder):
    conn.close()   # create_app 은 자체적으로 매 요청마다 새 연결을 연다(db.py 계약)
    return create_app(db_path=tmp_path / "api.db", link=link, builder=builder,
                       run_mode="simulate", proto_mode="strict")


@pytest.fixture()
def greenhouse_id(tmp_path):
    con = db.init_db(tmp_path / "_probe.db", seed=True)
    gid = repository.get_default_greenhouse_id(con)
    con.close()
    return gid


def _register_node(link, node_id=3, gcg_id=1, num_devices=1):
    link._registry[node_id] = NodeProperty(sw_version=1, gcg_id=gcg_id, node_id=node_id,
                                            status=Status.NORMAL, num_devices=num_devices)


def _register_link_device(link, node_id, device_id, dev_type, subtype, value_type=ValueType.UINT, value=0):
    """`link.devices(node_id)` — `ems.set_device_property()`가 대상의 현재
    Value Type 을 확인하는 유일한 출처다(F-137과 같은 원칙: 임의로 대체하지
    않는다). `_register_device_install()`(DB)과는 별개로, 링크(런타임 세션)
    쪽에도 등록해야 한다."""
    existing = link._devices.get(node_id, ())
    dmi = DeviceMainInfo(device_id=device_id, dev_type=dev_type, subtype=subtype,
                          value_type=value_type, value=value)
    link._devices[node_id] = tuple(d for d in existing if d.device_id != device_id) + (dmi,)


def _register_device_install(tmp_path, node_id=3, device_id=1, subtype=0x85, kind="ACTUATOR"):
    con = db.connect(tmp_path / "api.db")
    gh = repository.get_default_greenhouse_id(con)
    info_id = repository.get_or_create_device_info(con, device_kind=kind,
                                                     model_name=f"SIAP-0x{subtype:02X}",
                                                     device_name="IRRIGATION_VALVE")
    install_id = repository.upsert_device_install_info(
        con, device_info_id=info_id, device_name="v1", siap_node_id=node_id,
        siap_device_id=device_id, siap_subtype=subtype,
    )
    repository.link_device_install(con, gh, install_id)
    con.commit()
    con.close()
    return install_id


# ── system ──────────────────────────────────────────────────────────────

def test_health_7_0937_6_3(app):                                    # 아키텍처 §6.3
    r = call(app, "GET", "/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["run_mode"] == "simulate"
    assert body["proto_mode"] == "strict"
    assert body["public_data_fallback"] is True   # KMA_API_KEY 미설정 — 목업 폴백


# ── ems — nodes/devices ────────────────────────────────────────────────

def test_list_nodes_empty(app):
    r = call(app, "GET", "/api/v1/nodes")
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0, "limit": 100, "offset": 0}


def test_get_node_404(app):
    r = call(app, "GET", "/api/v1/nodes/999")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json") or r.json()["status"] == 404


def test_list_nodes_after_register_0943_8_1_1(app, link):
    _register_node(link, node_id=3)
    r = call(app, "GET", "/api/v1/nodes")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["node_id"] == 3
    assert body["items"][0]["status"] == "NORMAL"


def test_node_devices_uses_device_install_info_1369_7_2_2_5(app, link, tmp_path):
    _register_node(link, node_id=3)
    install_id = _register_device_install(tmp_path, node_id=3)
    r = call(app, "GET", "/api/v1/nodes/3/devices")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    dev = body["items"][0]
    assert dev["id"] == install_id
    assert dev["subtype"] == "IRRIGATION_VALVE"   # Subtype 레지스트리 조회 — 하드코딩 아님
    assert dev["device_kind"] == "ACTUATOR"


def test_node_devices_unknown_node_404(app):
    r = call(app, "GET", "/api/v1/nodes/12345/devices")
    assert r.status_code == 404


# ── fms — telemetry/device-states/alerts ───────────────────────────────

def test_list_telemetry_empty(app):
    r = call(app, "GET", "/api/v1/telemetry")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_list_telemetry_after_env_measurement_1369_6_3_3(app, tmp_path, greenhouse_id):
    con = db.connect(tmp_path / "api.db")
    info_id = repository.get_or_create_device_info(con, device_kind="SENSOR",
                                                     model_name="SIAP-0x01", device_name="TEMPERATURE")
    install_id = repository.upsert_device_install_info(
        con, device_info_id=info_id, device_name="t1", siap_node_id=3, siap_device_id=1, siap_subtype=1)
    repository.link_device_install(con, greenhouse_id, install_id)
    repository.record_env_measurement(con, install_id=install_id, greenhouse_id=greenhouse_id,
                                       subtype="TEMPERATURE", value=25.3, unit="C")
    con.commit(); con.close()

    r = call(app, "GET", "/api/v1/telemetry", query="subtype=TEMPERATURE")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["value"] == 25.3
    assert body["items"][0]["install_id"] == install_id


def test_list_alerts_0937_6_4_3(app, tmp_path):
    con = db.connect(tmp_path / "api.db")
    repository.record_alert(con, kind="NODE_ERROR", severity="CRITICAL", message="NEC=0x07")
    con.commit(); con.close()
    r = call(app, "GET", "/api/v1/alerts")
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_list_alerts_triggers_stale_device_check_f191(app, monkeypatch):
    """F-191 — `GET /api/v1/alerts`가 `fms.check_stale_devices()`를 실제로
    호출하는가(check-on-read). 이전에는 이 함수가 정의만 되고 어디서도
    불리지 않아 0937 6.4-3 미수집 알림이 영구히 생기지 않았다."""
    from backend.services import fms as fms_module
    calls: list[tuple] = []
    monkeypatch.setattr(fms_module, "check_stale_devices",
                         lambda conn, now: calls.append((conn, now)) or [])
    r = call(app, "GET", "/api/v1/alerts")
    assert r.status_code == 200
    assert len(calls) == 1


# ── conformance — frames ────────────────────────────────────────────────

def test_list_frames_and_get_frame_0943_7_3(app, tmp_path):
    con = db.connect(tmp_path / "api.db")
    frame_id = repository.insert_frame_log(
        con, t=1000.0, direction="rx", raw_hex="AABBCC", version=0x12, msg_type=0,
        trans_type=0, msg_id=1, payload_len=0, gcg_id=1, node_id=3, is_valid=True)
    con.commit(); con.close()

    r = call(app, "GET", "/api/v1/frames")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r2 = call(app, "GET", f"/api/v1/frames/{frame_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["header"]["node_id"] == 3
    assert body["judgement"] == "normal"
    assert len(body["fields"]) == 7   # 헤더 7필드뿐(그림 7-1) — 이 프레임엔 가변 요소가 없다


def test_frame_fields_includes_payload_element_decomposition_f187(app, tmp_path):
    """F-187 — elements_json 이 있는 프레임은 헤더 7필드 뒤에 가변 요소
    (DEVICE_MAIN_INFO) 필드도 이어붙어야 한다."""
    import json
    con = db.connect(tmp_path / "api.db")
    elements = [{"kind": "DMI", "device_id": 1, "dev_type": 0, "subtype": 1,
                 "value_type": 2, "value": 25.5}]
    frame_id = repository.insert_frame_log(
        con, t=1002.0, direction="rx", raw_hex="AABBCC", version=0x12, msg_type=0x0800,
        trans_type=0, msg_id=1, payload_len=7, gcg_id=1, node_id=3, is_valid=True,
        elements_json=json.dumps(elements))
    con.commit(); con.close()

    r = call(app, "GET", f"/api/v1/frames/{frame_id}")
    assert r.status_code == 200
    fields = r.json()["fields"]
    assert len(fields) == 7 + 6   # 헤더 7 + DEVICE_MAIN_INFO 6필드(표 7-14)

    payload_fields = fields[7:]
    assert [f["name"] for f in payload_fields] == \
        ["Device ID", "Type", "Subtype", "Value Type", "Reserved", "Value"]
    assert [f["bit_width"] for f in payload_fields] == [8, 1, 8, 2, 5, 32]
    # 헤더가 96bit(그림 7-1) 뒤에서 이어붙는다
    assert payload_fields[0]["bit_offset"] == 96
    assert payload_fields[-1]["bit_offset"] == 96 + 8 + 1 + 8 + 2 + 5
    assert all(f["element"] == 0 for f in payload_fields)
    assert all(f["clause"] == "표 7-14" for f in payload_fields)
    # Value(FLOAT) 의 raw 는 IEEE-754 big-endian 비트 패턴이어야 한다(부호 없는 정수)
    value_field = payload_fields[-1]
    import struct
    assert value_field["raw"] == struct.unpack(">I", struct.pack(">f", 25.5))[0]


def test_frame_violation_judgement_f060(app, tmp_path):
    con = db.connect(tmp_path / "api.db")
    frame_id = repository.insert_frame_log(
        con, t=1001.0, direction="rx", raw_hex="DEAD", version=None, msg_type=None,
        trans_type=None, msg_id=None, payload_len=None, gcg_id=None, node_id=None, is_valid=False)
    repository.insert_frame_violation(con, frame_id=frame_id, code=9, code_name="INVALID_FORMAT",
                                       clause="7.3.1", detail="test")
    con.commit(); con.close()

    r = call(app, "GET", "/api/v1/frames/violations", query="clause=7.3.1")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["judgement"] == "violation"
    assert body["items"][0]["violations"][0]["code_name"] == "INVALID_FORMAT"


def test_frame_not_found(app):
    r = call(app, "GET", "/api/v1/frames/does-not-exist")
    assert r.status_code == 404


def test_stream_endpoint_responds(app):
    status, chunks = call_stream(app, "/api/v1/stream", timeout=1.0, max_chunks=999)
    assert status == 200


# ── dms — publicdata ────────────────────────────────────────────────────

def test_publicdata_sources_seeded_0937_6_2_2(app):
    r = call(app, "GET", "/api/v1/publicdata/sources")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["provider"] == "기상청"


def test_publicdata_records_empty(app):
    r = call(app, "GET", "/api/v1/publicdata/records")
    assert r.status_code == 200
    assert r.json()["items"] == []


# ── mms — rule draft/approve/reject ─────────────────────────────────────

def test_create_wizard_rule_and_get_0937_6_3(app):
    r = call(app, "POST", "/api/v1/rules",
             json={"origin": "WIZARD", "draft_text": "고온이면 관수", "condition_expr": "forecast.tmax > 33"})
    assert r.status_code == 201
    rule = r.json()
    assert rule["origin"] == "WIZARD"
    assert rule["approved"] is False
    assert rule["action"] is None

    r2 = call(app, "GET", f"/api/v1/rules/{rule['id']}")
    assert r2.status_code == 200
    assert r2.json()["draft_text"] == "고온이면 관수"


def test_create_rule_rejects_extra_fields_f051(app):
    r = call(app, "POST", "/api/v1/rules",
             json={"origin": "WIZARD", "draft_text": "x", "action": {"value": 1, "value_type": "UINT"}})
    assert r.status_code == 400


def test_create_ai_draft_falls_back_to_threshold_f083(app):
    r = call(app, "POST", "/api/v1/rules",
             json={"origin": "AI_DRAFT", "model_id": "demo-model-threshold-tmax",
                   "inputs": {"crop_tmax_c": 33}})
    assert r.status_code == 201
    rule = r.json()
    assert rule["origin"] == "AI_DRAFT"
    assert rule["generation"] == "THRESHOLD_FALLBACK"
    assert "33" in rule["draft_text"] or "예보" in rule["draft_text"]


def test_create_ai_draft_without_crop_threshold_says_so_f190(app):
    """F-190 — 임계값은 서버 상수가 아니라 inputs.crop_tmax_c 로 온다.
    생략하면 추측하지 않고 그렇게 말한다."""
    r = call(app, "POST", "/api/v1/rules",
             json={"origin": "AI_DRAFT", "model_id": "demo-model-threshold-tmax"})
    assert r.status_code == 201
    assert "crop_tmax_c" in r.json()["draft_text"]


def test_approve_requires_all_three_fields(app):
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    r2 = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "a"}, headers={"X-User-Id": "demo-user-1"})
    assert r2.status_code == 400


def test_approve_rejects_unknown_target_400(app):
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    r2 = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "a", "action": {"value": 1, "value_type": "UINT"},
                    "target_install_id": "no-such-install"},
              headers={"X-User-Id": "demo-user-1"})
    assert r2.status_code in (400, 404, 409)   # FK 위반 — Problem 으로 옮겨진다


def test_approve_unknown_user_400(app, tmp_path):
    install_id = _register_device_install(tmp_path)
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    r2 = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "a", "action": {"value": 1, "value_type": "UINT"},
                    "target_install_id": install_id},
              headers={"X-User-Id": "ghost-user"})
    assert r2.status_code == 400


def test_control_action_extra_field_rejected_f051(app, tmp_path):
    install_id = _register_device_install(tmp_path)
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    r2 = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "a",
                    "action": {"value": 1, "value_type": "UINT", "install_id": "sneaky"},
                    "target_install_id": install_id},
              headers={"X-User-Id": "demo-user-1"})
    assert r2.status_code == 400


@pytest.mark.parametrize("value,value_type", [
    (-1, "UINT"), (2**32, "UINT"), (2**31, "INT"), (-2**31 - 1, "INT"), (1e39, "FLOAT"),
])
def test_control_action_range_rejected_f054_f055(app, tmp_path, value, value_type):
    install_id = _register_device_install(tmp_path)
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    r2 = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "a", "action": {"value": value, "value_type": value_type},
                    "target_install_id": install_id},
              headers={"X-User-Id": "demo-user-1"})
    assert r2.status_code == 400


def test_reject_then_approve_blocked_409(app):
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    rr = call(app, "POST", f"/api/v1/rules/{rule_id}/reject", json={"reason": "부적절"},
              headers={"X-User-Id": "demo-user-1"})
    assert rr.status_code == 200
    assert rr.json()["rejected_by"] == "demo-user-1"

    ra = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "a", "action": {"value": 1, "value_type": "UINT"},
                    "target_install_id": "x"}, headers={"X-User-Id": "demo-user-1"})
    assert ra.status_code == 409


def test_reject_empty_reason_400(app):
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    rr = call(app, "POST", f"/api/v1/rules/{rule_id}/reject", json={"reason": "  "},
              headers={"X-User-Id": "demo-user-1"})
    assert rr.status_code == 400


# ── fcs — execute/control/executions (승인 게이트 e2e) ──────────────────

def _approved_rule(app, link, builder, tmp_path, node_id=3, device_id=1, subtype=0x85):
    install_id = _register_device_install(tmp_path, node_id=node_id, device_id=device_id, subtype=subtype)
    builder.device_kinds[(node_id, device_id)] = (DevType.ACTUATOR, subtype)
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "고온 관수",
                                                  "condition_expr": "forecast.tmax > 33"})
    rule_id = r.json()["id"]
    ra = call(app, "POST", f"/api/v1/rules/{rule_id}/approve",
              json={"condition_expr": "forecast.tmax > 33",
                    "action": {"value": 1, "value_type": "UINT", "duration_sec": 1200},
                    "target_install_id": install_id},
              headers={"X-User-Id": "demo-user-1"})
    assert ra.status_code == 200
    return rule_id, install_id


def test_execute_unapproved_rule_409_0937_A_3_2(app):
    r = call(app, "POST", "/api/v1/rules", json={"origin": "WIZARD", "draft_text": "x"})
    rule_id = r.json()["id"]
    re_ = call(app, "POST", f"/api/v1/rules/{rule_id}/execute")
    assert re_.status_code == 409
    assert re_.json()["constraint"] == "trg_exec_requires_approval"


def test_execute_approved_rule_succeeds(app, link, builder, tmp_path):
    rule_id, install_id = _approved_rule(app, link, builder, tmp_path)
    re_ = call(app, "POST", f"/api/v1/rules/{rule_id}/execute")
    assert re_.status_code == 202
    body = re_.json()
    assert body["origin"] == "RULE"
    assert body["install_id"] == install_id
    assert body["result_rsc"] == 0   # RSC.SUCCESS
    assert body["result_rsc_name"] == "SUCCESS"


def test_execute_unknown_rule_404(app):
    r = call(app, "POST", "/api/v1/rules/does-not-exist/execute")
    assert r.status_code == 404


def test_manual_control_202(app, link, builder, tmp_path):
    install_id = _register_device_install(tmp_path, node_id=5, device_id=2, subtype=0x83)
    builder.device_kinds[(5, 2)] = (DevType.ACTUATOR, 0x83)
    r = call(app, "POST", "/api/v1/control",
             json={"install_id": install_id, "action": {"value": 0, "value_type": "UINT"}},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 202
    assert r.json()["origin"] == "MANUAL"
    assert r.json()["issued_by"] == "demo-user-1"


def test_manual_control_requires_known_user_400(app, tmp_path):
    install_id = _register_device_install(tmp_path)
    r = call(app, "POST", "/api/v1/control",
             json={"install_id": install_id, "action": {"value": 0, "value_type": "UINT"}},
             headers={"X-User-Id": "ghost"})
    assert r.status_code == 400


def test_executions_list_after_execute(app, link, builder, tmp_path):
    rule_id, install_id = _approved_rule(app, link, builder, tmp_path)
    call(app, "POST", f"/api/v1/rules/{rule_id}/execute")
    r = call(app, "GET", "/api/v1/executions", query="origin=RULE")
    assert r.status_code == 200
    assert r.json()["total"] == 1


# ── ems — device-property ───────────────────────────────────────────────

def test_device_property_patch_success(app, link, builder, tmp_path):
    install_id = _register_device_install(tmp_path, node_id=3, device_id=1, subtype=0x01)
    builder.device_kinds[(3, 1)] = (DevType.SENSOR, 0x01)
    _register_link_device(link, 3, 1, DevType.SENSOR, 0x01)
    r = call(app, "PATCH", "/api/v1/device-property",
             json={"selector": {"install_id": install_id}, "property": {"period_sec": 60}},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 200
    assert r.json()["items"][0]["id"] == install_id


def test_device_property_partial_patch_preserves_thresholds_f220(app, link, builder, tmp_path):
    install_id = _register_device_install(tmp_path, node_id=3, device_id=1, subtype=0x01)
    builder.device_kinds[(3, 1)] = (DevType.SENSOR, 0x01)
    _register_link_device(link, 3, 1, DevType.SENSOR, 0x01)
    con = db.connect(tmp_path / "api.db")
    con.execute(
        "UPDATE device_install_info SET transfer_mode='BOTH',period_sec=30,"
        "lower_limit=2.0,upper_limit=8.0 WHERE id=?", (install_id,),
    )
    con.commit(); con.close()

    r = call(app, "PATCH", "/api/v1/device-property",
             json={"selector": {"install_id": install_id}, "property": {"period_sec": 60}},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 200
    con = db.connect(tmp_path / "api.db")
    row = con.execute(
        "SELECT transfer_mode,period_sec,lower_limit,upper_limit "
        "FROM device_install_info WHERE id=?", (install_id,),
    ).fetchone()
    con.close()
    assert tuple(row) == ("BOTH", 60, 2.0, 8.0)


def test_device_property_success_records_user_history_f221(app, link, builder, tmp_path):
    import json
    install_id = _register_device_install(tmp_path, node_id=3, device_id=1, subtype=0x01)
    builder.device_kinds[(3, 1)] = (DevType.SENSOR, 0x01)
    _register_link_device(link, 3, 1, DevType.SENSOR, 0x01)
    con = db.connect(tmp_path / "api.db")
    before = con.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    con.close()

    r = call(app, "PATCH", "/api/v1/device-property",
             json={"selector": {"install_id": install_id},
                   "property": {"transfer_mode": "PERIODIC", "period_sec": 60}},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 200
    con = db.connect(tmp_path / "api.db")
    after = con.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    history = con.execute(
        "SELECT table_name,row_id,operation,changes,user_id FROM config_change_log "
        "ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    con.close()
    assert after - before == 1
    assert (history["table_name"], history["row_id"], history["operation"], history["user_id"]) == \
        ("device_install_info", install_id, "UPDATE", "demo-user-1")
    assert json.loads(history["changes"]) == {
        "transfer_mode": {"from": None, "to": "PERIODIC"},
        "period_sec": {"from": None, "to": 60},
    }


def test_device_property_timeout_records_neither_setting_nor_history_f221(
        app, link, builder, tmp_path, monkeypatch):
    install_id = _register_device_install(tmp_path, node_id=3, device_id=1, subtype=0x01)
    builder.device_kinds[(3, 1)] = (DevType.SENSOR, 0x01)
    _register_link_device(link, 3, 1, DevType.SENSOR, 0x01)
    con = db.connect(tmp_path / "api.db")
    before = con.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    con.close()
    monkeypatch.setattr(link, "send", lambda frame, timeout=None: None)

    r = call(app, "PATCH", "/api/v1/device-property",
             json={"selector": {"install_id": install_id}, "property": {"period_sec": 60}},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 504
    con = db.connect(tmp_path / "api.db")
    row = con.execute("SELECT period_sec FROM device_install_info WHERE id=?", (install_id,)).fetchone()
    after = con.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    con.close()
    assert row["period_sec"] is None
    assert after == before


@pytest.mark.parametrize("prop", [
    {"value": 1},
    {"period_sec": 16384},
    {"period_sec": True},
    {"transfer_mode": None},
    {"lower_value": None},
])
def test_device_property_openapi_negative_vectors_rejected_by_http_f228(
        app, link, builder, tmp_path, prop):
    install_id = _register_device_install(tmp_path, node_id=3, device_id=1, subtype=0x01)
    builder.device_kinds[(3, 1)] = (DevType.SENSOR, 0x01)
    _register_link_device(link, 3, 1, DevType.SENSOR, 0x01)
    tx_before = link.stats()["tx"]
    r = call(app, "PATCH", "/api/v1/device-property",
             json={"selector": {"install_id": install_id}, "property": prop},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 400
    assert link.stats()["tx"] == tx_before


def test_device_property_selector_exclusive_400(app):
    r = call(app, "PATCH", "/api/v1/device-property",
             json={"selector": {"install_id": "a", "greenhouse_id": "b"}, "property": {"period_sec": 1}},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 400


# ── conformance — sim/inject ─────────────────────────────────────────────

def test_inject_without_inject_fn_409(app):
    r = call(app, "POST", "/api/v1/sim/inject", json={"vector_id": "X01"},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 409


def test_inject_hardware_mode_409(tmp_path, conn, link, builder):
    conn.close()
    app_hw = create_app(db_path=tmp_path / "api.db", link=link, builder=builder,
                         run_mode="hardware", proto_mode="strict")
    r = call(app_hw, "POST", "/api/v1/sim/inject", json={"vector_id": "X01"},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 409


def test_inject_invalid_vector_400(app):
    r = call(app, "POST", "/api/v1/sim/inject", json={"vector_id": "NOPE"},
             headers={"X-User-Id": "demo-user-1"})
    assert r.status_code == 400
