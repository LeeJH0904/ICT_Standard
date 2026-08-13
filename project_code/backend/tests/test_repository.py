"""backend/tests/test_repository.py — SQL 계층 (backend/repository.py)."""
from __future__ import annotations

import pytest

from backend import db, repository


@pytest.fixture()
def conn(tmp_path):
    con = db.init_db(tmp_path / "repo.db", seed=True)
    yield con
    con.close()


@pytest.fixture()
def greenhouse_id(conn):
    return repository.get_default_greenhouse_id(conn)


# ── device_info / device_install_info / device_install ──────────────

def test_get_or_create_device_info_reuses_by_model_name(conn):
    """model_name 은 7.2.2.4 상 불변·전역 식별 — 같은 model_name 재요청은
    같은 id 를 돌려준다(새 행을 만들지 않는다)."""
    id1 = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    id2 = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    assert id1 == id2
    assert conn.execute("SELECT COUNT(*) FROM device_info").fetchone()[0] == 1


def test_get_or_create_device_info_stores_device_characteristics(conn):
    """F-185 재현 — 1369-P1 6.2.4 "장치정보에는... 장치특성 등이 포함되어야
    한다"인데 저장할 컬럼 자체가 없었다. manufacturer 와 같은 자격의
    nullable 컬럼으로 열어 둔다."""
    id_ = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE",
        device_characteristics="IP65 방수, 측정범위 -40~80도")
    row = conn.execute(
        "SELECT device_characteristics FROM device_info WHERE id=?", (id_,)
    ).fetchone()
    assert row["device_characteristics"] == "IP65 방수, 측정범위 -40~80도"

    info = repository.get_by_id(conn, "device_info", id_)
    assert info.device_characteristics == "IP65 방수, 측정범위 -40~80도"


def test_get_or_create_device_info_device_characteristics_defaults_none(conn):
    """0943 DEVICE_PROPERTY(표 7-15, F-198)는 장치특성을 나르지 않는다 —
    동적 등록 경로(ingest.py)가 이 인자를 넘기지 않으면 manufacturer 와
    같이 None."""
    id_ = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x02", device_name="HUMIDITY")
    row = conn.execute(
        "SELECT device_characteristics FROM device_info WHERE id=?", (id_,)
    ).fetchone()
    assert row["device_characteristics"] is None


def test_upsert_device_install_info_inserts_then_updates(conn):
    dev_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    id1 = repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="node3-temp-1",
        siap_node_id=3, siap_device_id=1, siap_subtype=1)
    id2 = repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="node3-temp-1-renamed",
        siap_node_id=3, siap_device_id=1, siap_subtype=1, unit="C")
    assert id1 == id2
    assert conn.execute("SELECT COUNT(*) FROM device_install_info").fetchone()[0] == 1
    row = repository.find_device_install_by_siap(conn, 3, 1)
    assert row["device_name"] == "node3-temp-1-renamed"
    assert row["unit"] == "C"


def test_upsert_device_install_info_reconnect_moves_device_info_id(conn):
    """F-169 재현 — 재연결로 장치 종류(subtype)가 바뀌면 device_info_id 도
    새 device_info 를 가리켜야 한다. 이전에는 UPDATE 절에서 이 컬럼이
    빠져 예전 모델(TEMPERATURE)을 계속 참조했다."""
    temp_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    humid_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x02", device_name="HUMIDITY")
    assert temp_id != humid_id

    install_id_1 = repository.upsert_device_install_info(
        conn, device_info_id=temp_id, device_name="node3-1",
        siap_node_id=3, siap_device_id=1, siap_subtype=1)
    install_id_2 = repository.upsert_device_install_info(
        conn, device_info_id=humid_id, device_name="node3-1",
        siap_node_id=3, siap_device_id=1, siap_subtype=2)

    assert install_id_1 == install_id_2, "같은 (node,device) 주소는 같은 설치 행이어야 한다"
    row = repository.find_device_install_by_siap(conn, 3, 1)
    assert row["device_info_id"] == humid_id, (
        "F-169 재발: 재연결 후에도 device_info_id 가 예전 모델을 계속 참조한다"
    )
    assert row["siap_subtype"] == 2


def test_upsert_device_install_info_reconnect_preserves_unset_location_and_unit(conn):
    """F-170 재현 — 재연결 호출자가 설치 위치·단위를 넘기지 않으면(None)
    기존에 관리되던 값을 지우지 않고 보존해야 한다."""
    dev_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="node3-1",
        siap_node_id=3, siap_device_id=1, siap_subtype=1,
        install_location="GH-A-1", install_loc_unit="m", unit="C")
    # 재연결 — 위치·단위 정보를 모르는 호출(ingest._handle_device_property 의 실제 패턴)
    repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="node3-1-renamed",
        siap_node_id=3, siap_device_id=1, siap_subtype=1)
    row = repository.find_device_install_by_siap(conn, 3, 1)
    assert row["device_name"] == "node3-1-renamed"
    assert row["install_location"] == "GH-A-1", "F-170 재발: 재연결이 설치 위치를 지웠다"
    assert row["install_loc_unit"] == "m", "F-170 재발: 재연결이 위치 단위를 지웠다"
    assert row["unit"] == "C", "F-170 재발: 재연결이 측정 단위를 지웠다"


def test_get_or_create_device_info_records_config_change_only_on_create(conn):
    """F-182 재현 — 새 device_info 를 만들 때만 config_change_log 에 CREATE
    가 남는다. model_name 재사용(재요청)은 아무것도 바뀌지 않으므로 이력이
    아니다."""
    before = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    id1 = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    after_create = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    assert after_create - before == 1, "F-182 재발: device_info CREATE 이력이 남지 않았다"
    # F-184: changed_at 은 초 단위라 같은 초 안의 여러 INSERT 는 값이 같을 수
    # 있다 — 삽입 순서를 보려면 (숨은) rowid 로 정렬해야 한다.
    row = conn.execute(
        "SELECT table_name, row_id, operation FROM config_change_log ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert (row["table_name"], row["row_id"], row["operation"]) == ("device_info", id1, "CREATE")

    repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    after_reuse = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    assert after_reuse == after_create, "재사용은 변경이 아니므로 이력이 늘면 안 된다"


def test_upsert_device_install_info_records_config_change_create_and_update(conn):
    """F-182 — 최초 등록은 CREATE, 재연결(UPDATE 경로)은 UPDATE 로 남는다."""
    before = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    dev_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    install_id = repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="node3-1",
        siap_node_id=3, siap_device_id=1, siap_subtype=1)
    after_create = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    # F-184: changed_at 은 초 단위라 같은 초 안의 여러 INSERT 는 값이 같을 수
    # 있다 — 삽입 순서를 보려면 (숨은) rowid 로 정렬해야 한다.
    row = conn.execute(
        "SELECT table_name, row_id, operation FROM config_change_log ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert (row["table_name"], row["row_id"], row["operation"]) == ("device_install_info", install_id, "CREATE")

    repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="node3-1-renamed",
        siap_node_id=3, siap_device_id=1, siap_subtype=1)
    after_update = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    assert after_update - after_create == 1, "F-182 재발: 재연결 UPDATE 이력이 남지 않았다"
    row2 = conn.execute(
        "SELECT table_name, row_id, operation FROM config_change_log ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert (row2["table_name"], row2["row_id"], row2["operation"]) == ("device_install_info", install_id, "UPDATE")
    assert after_create - before == 2, "device_info CREATE + device_install_info CREATE = 2건이어야 한다"


def test_record_config_change_stores_json_changes_and_defaults_version_1(conn):
    log_id = repository.record_config_change(
        conn, table_name="device_info", row_id="x1", operation="CREATE",
        changes={"model_name": "SIAP-0x01"})
    row = conn.execute(
        "SELECT table_name, row_id, operation, changes, user_id, version FROM config_change_log WHERE id=?",
        (log_id,),
    ).fetchone()
    assert row["table_name"] == "device_info"
    assert row["operation"] == "CREATE"
    assert '"model_name"' in row["changes"]
    assert row["user_id"] is None
    assert row["version"] == 1


def test_get_greenhouse_location_returns_seeded_location(conn, greenhouse_id):
    """F-183 — 시드 온실(`fixtures/seed.sql`)의 위치를 그대로 돌려준다."""
    location, unit = repository.get_greenhouse_location(conn, greenhouse_id)
    row = conn.execute(
        "SELECT location, location_unit FROM greenhouse_info WHERE id=?", (greenhouse_id,)
    ).fetchone()
    assert (location, unit) == (row["location"], row["location_unit"])
    assert location is not None


def test_get_greenhouse_location_none_when_missing(tmp_path):
    con = db.init_db(tmp_path / "no-gh.db", seed=False)
    try:
        assert repository.get_greenhouse_location(con, "no-such-gh") == (None, None)
    finally:
        con.close()


def test_get_greenhouse_manager_user_id_returns_seeded_manager(conn, greenhouse_id):
    """F-176 — `greenhouse_manage`(1369-P1 §7.1(3))는 시드로 이미 채워져
    있다. 그 관리자를 그대로 조회할 수 있어야 한다."""
    user_id = repository.get_greenhouse_manager_user_id(conn, greenhouse_id)
    assert user_id is not None
    row = conn.execute(
        "SELECT user_id FROM greenhouse_manage WHERE greenhouse_id=?", (greenhouse_id,)
    ).fetchone()
    assert user_id == row["user_id"]


def test_get_greenhouse_manager_user_id_none_when_unmanaged(tmp_path):
    con = db.init_db(tmp_path / "unmanaged.db", seed=False)
    try:
        assert repository.get_greenhouse_manager_user_id(con, "no-such-gh") is None
    finally:
        con.close()


def test_link_device_manage_is_idempotent(conn, greenhouse_id):
    """F-176 — 재연결로 다시 불려도 `device_manage`는 1행만 유지한다
    (`UNIQUE(install_id)`, `link_device_install()`과 같은 멱등 패턴)."""
    dev_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    install_id = repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="x", siap_node_id=3, siap_device_id=1, siap_subtype=1)
    user_id = repository.get_greenhouse_manager_user_id(conn, greenhouse_id)
    repository.link_device_manage(conn, user_id, install_id)
    repository.link_device_manage(conn, user_id, install_id)
    n = conn.execute("SELECT COUNT(*) FROM device_manage WHERE install_id=?", (install_id,)).fetchone()[0]
    assert n == 1
    row = conn.execute("SELECT user_id FROM device_manage WHERE install_id=?", (install_id,)).fetchone()
    assert row["user_id"] == user_id


def test_link_device_install_is_idempotent(conn, greenhouse_id):
    dev_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    install_id = repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="x", siap_node_id=3, siap_device_id=1, siap_subtype=1)
    repository.link_device_install(conn, greenhouse_id, install_id)
    repository.link_device_install(conn, greenhouse_id, install_id)
    n = conn.execute("SELECT COUNT(*) FROM device_install WHERE install_id=?", (install_id,)).fetchone()[0]
    assert n == 1


def test_get_default_greenhouse_id_returns_seeded_one(conn, greenhouse_id):
    assert greenhouse_id is not None
    row = conn.execute("SELECT id FROM greenhouse_info").fetchone()
    assert greenhouse_id == row["id"]


def test_get_default_greenhouse_id_none_when_empty(tmp_path):
    con = db.init_db(tmp_path / "noseed.db", seed=False)
    try:
        assert repository.get_default_greenhouse_id(con) is None
    finally:
        con.close()


# ── env_measurement (FMS 센서) ───────────────────────────────────────

def test_record_env_measurement_links_install_and_greenhouse(conn, greenhouse_id):
    dev_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x01", device_name="TEMPERATURE")
    install_id = repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="x", siap_node_id=3, siap_device_id=1, siap_subtype=1)
    esd_id = repository.record_env_measurement(
        conn, install_id=install_id, greenhouse_id=greenhouse_id,
        subtype="TEMPERATURE", value=25.3, unit="C", error_range=0.1, lower_limit=-40, upper_limit=80)
    assert conn.execute("SELECT value FROM env_measurement WHERE id=?", (esd_id,)).fetchone()[0] == 25.3
    assert conn.execute("SELECT 1 FROM env_measure WHERE env_state_id=?", (esd_id,)).fetchone() is not None
    assert conn.execute("SELECT 1 FROM greenhouse_env WHERE env_state_id=?", (esd_id,)).fetchone() is not None


def test_record_env_measurement_rain_detection_strips_error_and_limits(conn, greenhouse_id):
    """그림 7-3 CHECK — RAIN_DETECTION 은 오차범위·유효범위를 가질 수 없다.
    호출자가 넘겨도 repository 가 스키마의 이 결정을 존중해 비운다."""
    dev_id = repository.get_or_create_device_info(
        conn, device_kind="SENSOR", model_name="SIAP-0x07", device_name="RAIN_DETECTION")
    install_id = repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="x", siap_node_id=3, siap_device_id=2, siap_subtype=7)
    esd_id = repository.record_env_measurement(
        conn, install_id=install_id, greenhouse_id=greenhouse_id,
        subtype="RAIN_DETECTION", value=1, unit="ON/OFF", error_range=0.1, lower_limit=0, upper_limit=1)
    row = conn.execute("SELECT error_range,lower_limit,upper_limit FROM env_measurement WHERE id=?", (esd_id,)).fetchone()
    assert tuple(row) == (None, None, None)


def test_record_env_measurement_rejects_unknown_subtype(conn, greenhouse_id):
    with pytest.raises(ValueError):
        repository.record_env_measurement(
            conn, install_id="x", greenhouse_id=greenhouse_id, subtype="LUX", value=1)


# ── device_state (FMS 액추에이터) ────────────────────────────────────

@pytest.fixture()
def actuator_install_id(conn):
    dev_id = repository.get_or_create_device_info(
        conn, device_kind="ACTUATOR", model_name="SIAP-0x85", device_name="IRRIGATION_VALVE")
    return repository.upsert_device_install_info(
        conn, device_info_id=dev_id, device_name="x", siap_node_id=3, siap_device_id=2, siap_subtype=0x85)


def test_record_device_state_irrigation_valve(conn, actuator_install_id):
    dsd_id = repository.record_device_state(
        conn, install_id=actuator_install_id, subtype="IRRIGATION_VALVE", value=100, valid_range="0-100")
    row = conn.execute("SELECT open_level,valid_range FROM dsd_irrigation_valve WHERE id=?", (dsd_id,)).fetchone()
    assert tuple(row) == (100, "0-100")


def test_record_device_state_fan_power_derived_from_nonzero_value(conn, actuator_install_id):
    dsd_id = repository.record_device_state(conn, install_id=actuator_install_id, subtype="FAN", value=1)
    assert conn.execute("SELECT power FROM dsd_fan WHERE id=?", (dsd_id,)).fetchone()[0] == 1
    dsd_id2 = repository.record_device_state(conn, install_id=actuator_install_id, subtype="FAN", value=0)
    assert conn.execute("SELECT power FROM dsd_fan WHERE id=?", (dsd_id2,)).fetchone()[0] == 0


def test_record_device_state_rejects_unknown_subtype(conn, actuator_install_id):
    with pytest.raises(ValueError):
        repository.record_device_state(conn, install_id=actuator_install_id, subtype="SHADING_SCREEN", value=1)


def test_record_device_state_cooling_heater_only_fills_power(conn, actuator_install_id):
    """F-157 — 냉난방기는 power 만 채우고 temperature·wind_level 은 NULL로
    둔다(FAN 과 같은 패턴). 이전에는 value 가 power 와 temperature 양쪽에
    중복 기입됐다."""
    dsd_id = repository.record_device_state(
        conn, install_id=actuator_install_id, subtype="COOLING_HEATER", value=18.5)
    row = conn.execute(
        "SELECT power, temperature, wind_level FROM dsd_cooling_heater WHERE id=?", (dsd_id,)).fetchone()
    assert tuple(row) == (1, None, None)
    dsd_id2 = repository.record_device_state(
        conn, install_id=actuator_install_id, subtype="COOLING_HEATER", value=0)
    assert conn.execute(
        "SELECT power FROM dsd_cooling_heater WHERE id=?", (dsd_id2,)).fetchone()[0] == 0


# ── operating_env — 작동 환경 (F-156) ─────────────────────────────

def test_record_operating_env_links_device_state_and_env_state(conn, greenhouse_id, actuator_install_id):
    dsd_id = repository.record_device_state(
        conn, install_id=actuator_install_id, subtype="IRRIGATION_VALVE", value=50)
    esd_id = repository.record_env_measurement(
        conn, install_id=actuator_install_id, greenhouse_id=greenhouse_id,
        subtype="TEMPERATURE", value=25.3)
    repository.record_operating_env(conn, device_state_id=dsd_id, env_state_id=esd_id)
    row = conn.execute(
        "SELECT device_state_id, env_state_id FROM operating_env WHERE env_state_id=?", (esd_id,)).fetchone()
    assert tuple(row) == (dsd_id, esd_id)


def test_record_operating_env_env_state_id_unique(conn, greenhouse_id, actuator_install_id):
    """7.1(10) — 환경상태 1건은 정확히 하나의 장치상태에만 귀속된다."""
    dsd_id1 = repository.record_device_state(
        conn, install_id=actuator_install_id, subtype="IRRIGATION_VALVE", value=50)
    dsd_id2 = repository.record_device_state(
        conn, install_id=actuator_install_id, subtype="IRRIGATION_VALVE", value=60)
    esd_id = repository.record_env_measurement(
        conn, install_id=actuator_install_id, greenhouse_id=greenhouse_id,
        subtype="TEMPERATURE", value=25.3)
    repository.record_operating_env(conn, device_state_id=dsd_id1, env_state_id=esd_id)
    with pytest.raises(Exception):
        repository.record_operating_env(conn, device_state_id=dsd_id2, env_state_id=esd_id)


# ── alert (FCS) ───────────────────────────────────────────────────

def test_record_alert_requires_frame_id_when_nec_present(conn):
    """F-092 — siap_nec 가 있으면 frame_id 가 필수. repository 가 SQL을 치기
    전에 막아 IntegrityError 대신 명확한 ValueError 를 낸다."""
    with pytest.raises(ValueError):
        repository.record_alert(conn, kind="NODE_ERROR", severity="WARN", message="x", siap_nec=7)


def test_record_alert_with_frame_id_succeeds(conn):
    frame_id = repository.insert_frame_log(
        conn, t=1.0, direction="rx", raw_hex="00", version=0x12, msg_type=0x0800,
        trans_type=0, msg_id=1, payload_len=1, gcg_id=1, node_id=3, is_valid=True)
    alert_id = repository.record_alert(
        conn, kind="NODE_ERROR", severity="CRITICAL", message="NEC=0x07", siap_nec=7, frame_id=frame_id)
    alerts = repository.list_alerts(conn)
    assert alerts[0].id == alert_id
    assert alerts[0].frame_id == frame_id


# ── frame_log / frame_violation ──────────────────────────────────

def test_insert_frame_log_and_violation_roundtrip(conn):
    frame_id = repository.insert_frame_log(
        conn, t=2.0, direction="rx", raw_hex="deadbeef", version=0x99, msg_type=0,
        trans_type=0, msg_id=0, payload_len=0, gcg_id=1, node_id=3, is_valid=False)
    repository.insert_frame_violation(
        conn, frame_id=frame_id, code=1, code_name="INVALID_VERSION", clause="7.3.1", detail="x")
    violations = repository.list_frame_violations(conn, frame_id)
    assert len(violations) == 1
    assert violations[0].code_name == "INVALID_VERSION"
    logs = repository.list_frame_log(conn)
    assert logs[0].id == frame_id
    assert logs[0].is_valid is False


def test_get_by_id_generic_lookup(conn, greenhouse_id):
    gh = repository.get_by_id(conn, "greenhouse_info", greenhouse_id)
    assert gh is not None
    assert gh.id == greenhouse_id
    assert repository.get_by_id(conn, "greenhouse_info", "no-such-id") is None
