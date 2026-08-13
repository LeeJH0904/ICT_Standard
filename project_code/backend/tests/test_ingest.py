"""backend/tests/test_ingest.py — Frame 소비 지점 (backend/ingest.py).

`contracts/frame.py`의 `Frame`을 직접 만들어 `handle()`에 넣는다 — `siap/`를
전혀 거치지 않는다(backend가 `siap/` 내부 심볼을 import하지 않는다는
CLAUDE.md §2.2 계약을 테스트 구성 자체로도 지킨다).

F-198 — 이 파일이 손으로 만드는 "연결" 프레임은 `kind=REQ_SET_NODE_DEVICE_
PROPERTY_ALL`이다(예전에는 `REQ_SET_CONNECTION`이었는데, 그 메시지는
`contracts/frame.py::LAYOUT`상 페이로드가 없어 실제 디코더는 절대
`device_properties`를 채운 `REQ_SET_CONNECTION` 프레임을 만들 수 없다 —
이 파일이 그런 "불가능한 프레임"으로 회귀를 가려 왔다는 것 자체가 F-198의
일부였다). `siap/tests/test_wire_to_ingest_f198.py`가 손으로 만든 Frame이
아니라 실제 wire bytes → `siap/codec.py` 디코드 → `ingest.handle()` 전체
경로로 같은 사실을 다시 검증한다 — 이 파일은 여전히 backend 계층 단독
테스트(빠른 표본 스윕)로 남긴다."""
from __future__ import annotations

import sqlite3

import pytest

from backend import db, ingest, repository
from contracts.frame import (
    DeviceMainInfo, DeviceProperty, DevType, Frame, Header, MsgKind, NEC,
    NodeProperty, Status, Subtype, TransferMode, ValueType, Violation,
)

NODE_ID = 3


def _header(msg_type=0, trans_type=0, msg_id=1, payload_len=0, node_id=NODE_ID) -> Header:
    return Header(version=0x12, msg_type=msg_type, trans_type=trans_type, msg_id=msg_id,
                  payload_len=payload_len, gcg_id=1, node_id=node_id)


@pytest.fixture()
def conn(tmp_path):
    con = db.init_db(tmp_path / "ingest.db", seed=True)
    yield con
    con.close()


def _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE):
    dmi = DeviceMainInfo(device_id=device_id, dev_type=DevType.SENSOR, subtype=int(subtype),
                          value_type=ValueType.FLOAT, value=0.0)
    dp = DeviceProperty(main=dmi, transfer_mode=TransferMode.PERIODIC, period=60,
                         lower_value=-10.0, upper_value=50.0, lower_limit=-40.0, upper_limit=80.0,
                         precision=0.1, status=Status.NORMAL)
    frame = Frame(header=_header(), kind=MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL, device_properties=(dp,), t=1.0)
    ingest.handle(frame, conn)


def _connect_actuator(conn, device_id=2, subtype=Subtype.IRRIGATION_VALVE):
    dmi = DeviceMainInfo(device_id=device_id, dev_type=DevType.ACTUATOR, subtype=int(subtype),
                          value_type=ValueType.UINT, value=0)
    dp = DeviceProperty(main=dmi, transfer_mode=TransferMode.EVENT, period=0,
                         lower_value=0, upper_value=100, lower_limit=0, upper_limit=100,
                         precision=1, status=Status.NORMAL)
    frame = Frame(header=_header(), kind=MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL, device_properties=(dp,), t=1.0)
    ingest.handle(frame, conn)


# ── frame_log — 모든 프레임 ───────────────────────────────────

def test_handle_logs_every_frame(conn):
    frame = Frame(header=_header(msg_type=0x0C00), kind=MsgKind.ACK, t=5.0)
    ingest.handle(frame, conn)
    logs = repository.list_frame_log(conn)
    assert len(logs) == 1
    assert logs[0].direction == "rx"
    assert logs[0].is_valid is True
    assert logs[0].node_id == NODE_ID


def test_handle_violation_frame_isolates_and_logs_violation(conn):
    """위반 프레임은 frame_log+frame_violation만 남기고 비즈니스 테이블은
    건드리지 않는다 — codec.py가 위반 시 kind=None·구조 필드 전부 비움을
    보장하므로 반영할 데이터 자체가 없다."""
    frame = Frame(
        header=_header(msg_type=0xFFFF), kind=None, t=6.0,
        violations=(Violation(code=1, code_name="INVALID_VERSION", clause="7.3.1", detail="x"),),
    )
    ingest.handle(frame, conn)
    logs = repository.list_frame_log(conn)
    assert len(logs) == 1
    assert logs[0].is_valid is False
    violations = repository.list_frame_violations(conn, logs[0].id)
    assert len(violations) == 1
    assert violations[0].code_name == "INVALID_VERSION"
    assert conn.execute("SELECT COUNT(*) FROM device_install_info").fetchone()[0] == 0


# ── REQ_SET_NODE_DEVICE_PROPERTY_ALL → device_install_info + device_install (F-198) ────

def test_handle_connection_creates_install_and_links_greenhouse(conn):
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    install = repository.find_device_install_by_siap(conn, NODE_ID, 1)
    assert install is not None
    assert install["siap_subtype"] == int(Subtype.TEMPERATURE)
    greenhouse_id = repository.get_default_greenhouse_id(conn)
    linked = conn.execute(
        "SELECT 1 FROM device_install WHERE greenhouse_id=? AND install_id=?",
        (greenhouse_id, install["id"]),
    ).fetchone()
    assert linked is not None


def test_handle_connection_links_device_manage_to_greenhouse_manager(conn):
    """F-176 재현 — 디바이스 속성 선언(F-198) 처리 뒤 device_manage 가 그 온실의
    관리자로 채워져야 한다(1369-P1 §7.1(7)). 이전에는 이 관계가 런타임
    경로에서 항상 0행이었다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    install = repository.find_device_install_by_siap(conn, NODE_ID, 1)
    greenhouse_id = repository.get_default_greenhouse_id(conn)
    manager_id = repository.get_greenhouse_manager_user_id(conn, greenhouse_id)
    row = conn.execute(
        "SELECT user_id FROM device_manage WHERE install_id=?", (install["id"],)
    ).fetchone()
    assert row is not None, "F-176 재발: 정상 디바이스 속성 선언 뒤에도 device_manage 가 비어 있다"
    assert row["user_id"] == manager_id


def test_handle_connection_stores_device_property_elements_json_f187(conn):
    """F-187 — 가변 요소(DEVICE_PROPERTY)가 이미 디코딩된 채로
    frame_log.elements_json 에 그대로 저장돼야 한다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    logs = repository.list_frame_log(conn)
    assert len(logs) == 1
    assert logs[0].elements_json is not None
    import json
    items = json.loads(logs[0].elements_json)
    assert len(items) == 1
    assert items[0]["kind"] == "DP"
    assert items[0]["device_id"] == 1
    assert items[0]["subtype"] == int(Subtype.TEMPERATURE)
    assert items[0]["period"] == 60


def test_handle_reconnection_does_not_duplicate_device_manage(conn):
    """F-176 — 재연결로 device_manage 가 중복 삽입되지 않는다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    install = repository.find_device_install_by_siap(conn, NODE_ID, 1)
    n = conn.execute(
        "SELECT COUNT(*) FROM device_manage WHERE install_id=?", (install["id"],)
    ).fetchone()[0]
    assert n == 1


def test_handle_connection_records_config_change_log(conn):
    """F-182 재현 — 디바이스 속성 선언(F-198)은 device_info(CREATE)와
    device_install_info(CREATE)를 만드는데, 이전에는 어느 쪽도
    config_change_log 에 남기지 않아 1369-P1 6.2.1 "변경 이력이 관리되어야
    한다"가 정상 Plug & Play 경로에서 성립하지 않았다."""
    before = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    after = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    assert after - before == 2, "F-182 재발: device_info·device_install_info CREATE 이력이 남지 않았다"
    rows = conn.execute(
        "SELECT table_name, operation FROM config_change_log ORDER BY rowid DESC LIMIT 2"
    ).fetchall()
    seen = {(r["table_name"], r["operation"]) for r in rows}
    assert ("device_info", "CREATE") in seen
    assert ("device_install_info", "CREATE") in seen


def test_handle_reconnection_records_update_not_another_create(conn):
    """F-182 — 재연결(기존 install 행 UPDATE)은 device_install_info 에
    UPDATE 1건만 남긴다. device_info 는 model_name 이 같으면 재사용되므로
    (get_or_create_device_info) 새 CREATE 가 생기지 않는다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    before = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    after = conn.execute("SELECT COUNT(*) FROM config_change_log").fetchone()[0]
    assert after - before == 1, "F-182 재발: 재연결 UPDATE 이력이 남지 않았다"
    # F-184: changed_at 은 초 단위라 같은 초 안의 여러 INSERT 는 값이 같을 수
    # 있다 — 삽입 순서를 보려면 (숨은) rowid 로 정렬해야 한다.
    row = conn.execute(
        "SELECT table_name, operation FROM config_change_log ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    assert (row["table_name"], row["operation"]) == ("device_install_info", "UPDATE")


def test_handle_connection_defaults_install_location_to_greenhouse_location(conn):
    """F-183 재현 — 정상 디바이스 속성 선언(F-198) 뒤에도 install_location/
    install_loc_unit 이 항상 NULL 이었다(1369-P1 6.2.5 "설치위치 등이
    포함되어야 한다" 위반). 장치별 세부 위치를 넣을 수단이 없으므로, 그
    장치가 설치된 온실 자신의 위치를 기본값으로 쓴다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    install = repository.find_device_install_by_siap(conn, NODE_ID, 1)
    greenhouse_id = repository.get_default_greenhouse_id(conn)
    gh_location, gh_loc_unit = repository.get_greenhouse_location(conn, greenhouse_id)
    assert gh_location is not None, "시드 온실에 location 이 없다 — 이 테스트의 전제가 깨졌다"
    assert install["install_location"] == gh_location, "F-183 재발: install_location 이 채워지지 않았다"
    assert install["install_loc_unit"] == gh_loc_unit


def test_handle_reconnection_does_not_reapply_default_location_over_manual_value(conn):
    """F-183 — 재연결은 온실 기본값을 다시 덮어쓰지 않는다(F-170 보존
    의미론과 충돌하면 안 된다). 다른 경로로 더 구체적인 위치가 이미
    설정돼 있다고 가정하고, 재연결이 그것을 온실 기본값으로 되돌리지
    않는지 확인한다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    install = repository.find_device_install_by_siap(conn, NODE_ID, 1)
    conn.execute(
        "UPDATE device_install_info SET install_location=?, install_loc_unit=? WHERE id=?",
        ("중앙 상단", "m", install["id"]),
    )
    conn.commit()
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)   # 재연결
    install2 = repository.find_device_install_by_siap(conn, NODE_ID, 1)
    assert install2["install_location"] == "중앙 상단", (
        "F-183 재발: 재연결이 더 구체적인 위치를 온실 기본값으로 되돌렸다"
    )
    assert install2["install_loc_unit"] == "m"


def test_handle_connection_dev_type_inconsistent_with_subtype_is_skipped(conn):
    """F-180 재현 — 디바이스 속성 선언(F-198)에도 F-175 와 같은 Type/Subtype
    일관성 검사가 있어야 한다. HUMIDITY subtype 에 ACTUATOR Type 을 실은
    등록은 device_info/device_install_info 어느 것도 만들면 안 된다."""
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.ACTUATOR, subtype=int(Subtype.HUMIDITY),
                          value_type=ValueType.FLOAT, value=0.0)
    dp = DeviceProperty(main=dmi, transfer_mode=TransferMode.PERIODIC, period=60,
                         lower_value=-10.0, upper_value=50.0, lower_limit=-40.0, upper_limit=80.0,
                         precision=0.1, status=Status.NORMAL)
    frame = Frame(header=_header(), kind=MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL, device_properties=(dp,), t=1.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM device_install_info").fetchone()[0] == 0, (
        "F-180 재발: Type/Subtype 이 어긋난 연결 등록이 그대로 저장됐다"
    )
    assert conn.execute("SELECT COUNT(*) FROM device_info").fetchone()[0] == 0


def test_handle_connection_does_not_hardcode_node_kind(conn):
    """CLAUDE.md §1-6 — device_info.model_name 은 오직 Subtype 코드에서
    유도된다. 서로 다른 Node ID 라도 같은 subtype 이면 같은 device_info 를
    공유한다(노드 종류별 분기가 없다는 증거)."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    frame2 = Frame(
        header=_header(node_id=102), kind=MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL,
        device_properties=(DeviceProperty(
            main=DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                                 value_type=ValueType.FLOAT, value=0.0),
            transfer_mode=TransferMode.PERIODIC, period=60, lower_value=-10.0, upper_value=50.0,
            lower_limit=-40.0, upper_limit=80.0, precision=0.1, status=Status.NORMAL),),
        t=1.0,
    )
    ingest.handle(frame2, conn)
    assert conn.execute("SELECT COUNT(*) FROM device_info").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM device_install_info").fetchone()[0] == 2


def test_handle_reconnection_updates_not_duplicates(conn):
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    assert conn.execute("SELECT COUNT(*) FROM device_install_info").fetchone()[0] == 1


def test_handle_reconnection_with_new_subtype_stores_value_under_new_kind(conn):
    """F-169 재현 — 같은 (node,device) 주소가 TEMPERATURE 로 연결됐다가
    HUMIDITY 로 재연결되면, 이후 값 알림은 HUMIDITY 로 정확히 저장돼야
    한다(예전 device_info.device_kind 와 섞이지 않는다)."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    _connect_sensor(conn, device_id=1, subtype=Subtype.HUMIDITY)
    install = repository.find_device_install_by_siap(conn, NODE_ID, 1)
    assert install["siap_subtype"] == int(Subtype.HUMIDITY)

    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.HUMIDITY),
                          value_type=ValueType.FLOAT, value=55.0)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=2.0)
    ingest.handle(frame, conn)
    row = conn.execute("SELECT subtype, value FROM env_measurement").fetchone()
    assert row["subtype"] == "HUMIDITY", "F-169 재발: 재연결 후 값이 예전 subtype 정체성으로 저장됐다"
    assert row["value"] == pytest.approx(55.0)


# ── NOTI_DEVICE_VALUE → env_* (센서) / device_state_* (액추에이터) ──

def test_handle_device_value_sensor_records_env_measurement(conn):
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                          value_type=ValueType.FLOAT, value=25.3)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=2.0)
    ingest.handle(frame, conn)
    row = conn.execute(
        "SELECT subtype, value, unit, lower_limit, upper_limit FROM env_measurement"
    ).fetchone()
    assert row["subtype"] == "TEMPERATURE"
    assert row["value"] == pytest.approx(25.3)
    assert row["lower_limit"] == -40.0
    assert row["upper_limit"] == 80.0


def test_handle_device_value_stores_dmi_elements_json_f187(conn):
    """F-187 — DEVICE_MAIN_INFO 요소도 elements_json 에 그대로 저장돼야
    한다(디바이스 속성 선언의 DEVICE_PROPERTY 와 별개 경로, F-198)."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                          value_type=ValueType.FLOAT, value=25.3)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=2.0)
    ingest.handle(frame, conn)
    logs = repository.list_frame_log(conn)
    value_frame_log = next(f for f in logs if f.t == 2.0)
    assert value_frame_log.elements_json is not None
    import json
    items = json.loads(value_frame_log.elements_json)
    assert items == [{"kind": "DMI", "device_id": 1, "dev_type": int(DevType.SENSOR),
                       "subtype": int(Subtype.TEMPERATURE), "value_type": int(ValueType.FLOAT),
                       "value": pytest.approx(25.3)}]


def test_handle_device_value_actuator_records_device_state(conn):
    _connect_actuator(conn, device_id=2, subtype=Subtype.IRRIGATION_VALVE)
    dmi = DeviceMainInfo(device_id=2, dev_type=DevType.ACTUATOR, subtype=int(Subtype.IRRIGATION_VALVE),
                          value_type=ValueType.UINT, value=100)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=3.0)
    ingest.handle(frame, conn)
    row = conn.execute(
        "SELECT ds.subtype, v.open_level FROM device_state_data ds "
        "JOIN dsd_irrigation_valve v ON v.id = ds.id"
    ).fetchone()
    assert row["subtype"] == "IRRIGATION_VALVE"
    assert row["open_level"] == 100


def test_handle_device_value_env_measurement_carries_install_location(conn):
    """F-170 — 환경 측정 위치는 설치 행의 install_location/install_loc_unit
    을 참조한다(1369-P1 §7.2.3.3). 이전에는 이 두 값을
    record_env_measurement() 호출에 아예 넘기지 않아 항상 NULL 이었다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    # 위치는 지금 디바이스 속성 선언 경로로는 들어오지 않는다 — 이미 관리 중인
    # 값이 있다고 가정하고 직접 채운다(장차 API 쓰기 경로가 채울 값과 동일 컬럼).
    conn.execute(
        "UPDATE device_install_info SET install_location=?, install_loc_unit=? "
        "WHERE siap_node_id=? AND siap_device_id=?",
        ("GH-A-1", "m", NODE_ID, 1),
    )
    conn.commit()
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                          value_type=ValueType.FLOAT, value=25.3)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=2.0)
    ingest.handle(frame, conn)
    row = conn.execute("SELECT location, location_unit FROM env_state_data").fetchone()
    assert row["location"] == "GH-A-1", "F-170 재발: 환경 측정에 설치 위치가 실리지 않았다"
    assert row["location_unit"] == "m"


def test_handle_device_value_sensor_out_of_range_is_discarded(conn):
    """F-171 — 1369-P1 §6.3.2 "센서 유효범위를 벗어난 값은 측정 오류로 보고
    무시해야 하며". _connect_sensor 는 lower_limit=-40 / upper_limit=80 로
    등록한다 — 그 범위를 크게 벗어난 값은 정상 환경 데이터로 저장되면 안 된다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                          value_type=ValueType.FLOAT, value=999.0)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=2.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 0, (
        "F-171 재발: 유효범위 밖 값이 정상 측정으로 저장됐다"
    )
    # 프로토콜 위반이 아니므로 frame_log 는 정상 유효 프레임으로 남는다.
    assert repository.list_frame_log(conn)[0].is_valid is True


def test_handle_device_value_one_sided_lower_limit_rejects_below(conn):
    """F-177 재현 — 하한만 등록된 센서(상한 없음)도 하한 밖 값을 걸러야
    한다. F-171 최초 구현은 두 경계가 모두 있을 때만 검사해 편측 유효범위를
    우회시켰다."""
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                          value_type=ValueType.FLOAT, value=0.0)
    dp = DeviceProperty(main=dmi, transfer_mode=TransferMode.PERIODIC, period=60,
                         lower_value=-10.0, upper_value=50.0, lower_limit=0.0, upper_limit=None,
                         precision=0.1, status=Status.NORMAL)
    connect_frame = Frame(header=_header(), kind=MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL, device_properties=(dp,), t=1.0)
    ingest.handle(connect_frame, conn)

    dmi_value = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                                value_type=ValueType.FLOAT, value=-10.0)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi_value,), t=2.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 0, (
        "F-177 재발: 하한만 등록된 센서에서 하한 밖 값이 저장됐다"
    )


def test_handle_device_value_one_sided_upper_limit_rejects_above(conn):
    """F-177 변형 — 상한만 등록된 센서."""
    dmi = DeviceMainInfo(device_id=2, dev_type=DevType.SENSOR, subtype=int(Subtype.HUMIDITY),
                          value_type=ValueType.FLOAT, value=0.0)
    dp = DeviceProperty(main=dmi, transfer_mode=TransferMode.PERIODIC, period=60,
                         lower_value=0.0, upper_value=100.0, lower_limit=None, upper_limit=100.0,
                         precision=0.1, status=Status.NORMAL)
    connect_frame = Frame(header=_header(), kind=MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL, device_properties=(dp,), t=1.0)
    ingest.handle(connect_frame, conn)

    dmi_value = DeviceMainInfo(device_id=2, dev_type=DevType.SENSOR, subtype=int(Subtype.HUMIDITY),
                                value_type=ValueType.FLOAT, value=101.0)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi_value,), t=2.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 0, (
        "F-177 재발: 상한만 등록된 센서에서 상한 밖 값이 저장됐다"
    )


def test_handle_device_value_sensor_within_range_boundary_is_kept(conn):
    """경계값(하한·상한 자체)은 유효범위 "안"이다 — 배타적으로 거르지 않는다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)  # -40..80
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                          value_type=ValueType.FLOAT, value=80.0)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=2.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 1


def test_handle_device_value_subtype_mismatch_with_registration_is_skipped(conn):
    """F-173 재현 — node/device 번호가 등록돼 있어도, 알림의 subtype이
    등록된 siap_subtype과 다르면(예: SENSOR로 등록됐는데 ACTUATOR 값이 옴)
    그 알림이 주장하는 종류로 저장하면 안 된다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.HUMIDITY)
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.ACTUATOR, subtype=int(Subtype.IRRIGATION_VALVE),
                          value_type=ValueType.UINT, value=100)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=2.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM device_state_data").fetchone()[0] == 0, (
        "F-173 재발: 등록된 정체성과 다른 subtype의 값이 그대로 저장됐다"
    )


def test_handle_device_value_dev_type_inconsistent_with_subtype_is_skipped(conn):
    """F-175 재현 — Type(표 7-14)은 Subtype과 별개인 독립 1bit 필드라 코덱은
    이 조합을 정상 디코드한다(RSC.INVALID_DEVICE_TYPE 미사용, 프로토콜
    계층 밖의 문제). 등록은 HUMIDITY/SENSOR인데 알림이 같은 subtype에
    ACTUATOR Type을 실으면(subtype만 보는 F-173 가드는 통과) 저장 분기가
    엉뚱한 서브타입 집합을 골라 ValueError로 죽으면 안 된다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.HUMIDITY)
    dmi = DeviceMainInfo(device_id=1, dev_type=DevType.ACTUATOR, subtype=int(Subtype.HUMIDITY),
                          value_type=ValueType.FLOAT, value=55.0)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=2.0)
    ingest.handle(frame, conn)  # 예외 없이 끝나야 한다 (이전에는 ValueError)
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM device_state_data").fetchone()[0] == 0, (
        "F-175 재발: subtype 일치만 보고 Type 불일치 알림을 저장하려다 죽거나 잘못 저장했다"
    )


def test_handle_device_value_without_prior_connection_is_skipped(conn):
    """방어적 경로 — 등록되지 않은 (node_id, device_id) 의 값은 조용히
    건너뛴다. frame_log는 그래도 남는다(모든 프레임 → frame_log)."""
    dmi = DeviceMainInfo(device_id=99, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                          value_type=ValueType.FLOAT, value=1.0)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=4.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 0
    assert len(repository.list_frame_log(conn)) == 1


# ── 프레임 단위 원자성 (F-178) ────────────────────────────────

def test_handle_frame_processing_failure_rolls_back_partial_writes(conn):
    """F-178 재현 — 프레임 처리 중 예외가 나면 같은 프레임에서 이미 실행된
    INSERT도 rollback돼야 한다(아키텍처 §4.4 "프레임 1건 = 트랜잭션 1건",
    이유: "부분 반영 방지"). SQLite의 `RAISE(ABORT,...)`는 현재 문장만
    되돌리고 트랜잭션은 열어 둔 채 남기므로, `handle()` 자신이 예외 시
    전체를 rollback해야 앞선 요소(TEMPERATURE)의 INSERT가 남지 않는다.
    두 번째 요소(HUMIDITY, 유효범위 안의 값 50)에서만 실패하는 임시
    트리거로 재현한다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    _connect_sensor(conn, device_id=2, subtype=Subtype.HUMIDITY)
    conn.execute(
        "CREATE TEMP TRIGGER f178_abort_humidity BEFORE INSERT ON env_measurement "
        "WHEN NEW.subtype = 'HUMIDITY' AND NEW.value = 50.0 "
        "BEGIN SELECT RAISE(ABORT, 'F-178 injected failure'); END"
    )
    dmi_temp = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                               value_type=ValueType.FLOAT, value=25.3)
    dmi_hum = DeviceMainInfo(device_id=2, dev_type=DevType.SENSOR, subtype=int(Subtype.HUMIDITY),
                              value_type=ValueType.FLOAT, value=50.0)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE,
                  device_main_infos=(dmi_temp, dmi_hum), t=2.0)
    with pytest.raises(sqlite3.Error):
        ingest.handle(frame, conn)
    conn.execute("DROP TRIGGER f178_abort_humidity")
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 0, (
        "F-178 재발: 실패한 프레임의 첫 요소(TEMPERATURE)가 rollback 되지 않고 남았다"
    )
    assert conn.execute("SELECT COUNT(*) FROM frame_log WHERE t=2.0").fetchone()[0] == 0, (
        "F-178 재발: 실패한 프레임 자신의 frame_log 도 rollback 되지 않고 남았다"
    )
    # 이후 무관한 정상 프레임을 처리·commit해도 실패 프레임의 흔적이 살아나지 않는다.
    frame_ok = Frame(header=_header(msg_type=0x0C00), kind=MsgKind.ACK, t=3.0)
    ingest.handle(frame_ok, conn)
    assert conn.execute("SELECT COUNT(*) FROM env_measurement").fetchone()[0] == 0


# ── NOTI_ERROR → alert ───────────────────────────────────────

def test_handle_noti_error_records_alert_bound_to_frame(conn):
    frame = Frame(header=_header(), kind=MsgKind.NOTI_ERROR, nec=NEC.ERROR_BATTERY_LOW, t=7.0)
    ingest.handle(frame, conn)
    alerts = repository.list_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0].kind == "NODE_ERROR"
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].siap_nec == int(NEC.ERROR_BATTERY_LOW)
    assert alerts[0].install_id is None
    assert alerts[0].frame_id is not None
    logged = repository.list_frame_log(conn)
    assert logged[0].id == alerts[0].frame_id


def test_handle_noti_error_non_battery_is_warn(conn):
    frame = Frame(header=_header(), kind=MsgKind.NOTI_ERROR, nec=NEC.ERROR_RECEIVE, t=8.0)
    ingest.handle(frame, conn)
    assert repository.list_alerts(conn)[0].severity == "WARN"


# ── NOTI_DISCONNECT → alert (F-191) ────────────────────────────

def test_handle_noti_disconnect_records_alert_bound_to_frame(conn):
    """F-191 — 0937 6.5-2 "네트워크 단절" 알림. NEC 와 마찬가지로 노드
    단위(install_id=None)이고 프레임에서 유래한다(frame_id 필수)."""
    frame = Frame(header=_header(node_id=9), kind=MsgKind.NOTI_DISCONNECT, t=9.0)
    ingest.handle(frame, conn)
    alerts = repository.list_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0].kind == "DISCONNECT"
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].install_id is None
    assert alerts[0].siap_nec is None
    assert alerts[0].frame_id is not None
    assert "9" in alerts[0].message


# ── bind() — on_frame 어댑터 (F-154) ──────────────────────────

def test_bind_produces_single_arg_callable_that_persists(conn):
    """F-154 — `bind(conn)`이 만든 콜백은 `Callable[[Frame], None]`이고,
    `handle(frame, conn)`과 같은 DB 반영을 한다."""
    on_frame = ingest.bind(conn)
    frame = Frame(header=_header(msg_type=0x0C00), kind=MsgKind.ACK, t=1.0)
    result = on_frame(frame)
    assert result is None
    assert len(repository.list_frame_log(conn)) == 1


# ── operating_env — 작동 환경 (F-156) ─────────────────────────

def test_handle_device_value_links_operating_env_when_unambiguous(conn):
    """1369-P1 7.2.3.4 — 같은 프레임에 센서 값과 액추에이터 상태가 함께
    오면(장치상태 정확히 1건) operating_env 로 묶인다."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    _connect_actuator(conn, device_id=2, subtype=Subtype.IRRIGATION_VALVE)
    dmi_sensor = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                                 value_type=ValueType.FLOAT, value=25.3)
    dmi_actuator = DeviceMainInfo(device_id=2, dev_type=DevType.ACTUATOR, subtype=int(Subtype.IRRIGATION_VALVE),
                                   value_type=ValueType.UINT, value=100)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE,
                  device_main_infos=(dmi_sensor, dmi_actuator), t=9.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM env_state_data").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM device_state_data").fetchone()[0] == 1
    row = conn.execute(
        "SELECT oe.device_state_id, oe.env_state_id FROM operating_env oe"
    ).fetchone()
    assert row is not None
    dsd_id = conn.execute("SELECT id FROM device_state_data").fetchone()[0]
    esd_id = conn.execute("SELECT id FROM env_state_data").fetchone()[0]
    assert (row["device_state_id"], row["env_state_id"]) == (dsd_id, esd_id)


def test_handle_device_value_skips_operating_env_when_ambiguous(conn):
    """장치상태가 2건 이상이면(어느 것과 짝지어야 할지 프레임만으로 정할 수
    없다) operating_env 를 만들지 않는다(§3.5 결정)."""
    _connect_sensor(conn, device_id=1, subtype=Subtype.TEMPERATURE)
    _connect_actuator(conn, device_id=2, subtype=Subtype.IRRIGATION_VALVE)
    dmi_sensor = DeviceMainInfo(device_id=1, dev_type=DevType.SENSOR, subtype=int(Subtype.TEMPERATURE),
                                 value_type=ValueType.FLOAT, value=25.3)
    dmi_actuator1 = DeviceMainInfo(device_id=2, dev_type=DevType.ACTUATOR, subtype=int(Subtype.IRRIGATION_VALVE),
                                    value_type=ValueType.UINT, value=100)
    dmi_actuator2 = DeviceMainInfo(device_id=2, dev_type=DevType.ACTUATOR, subtype=int(Subtype.IRRIGATION_VALVE),
                                    value_type=ValueType.UINT, value=50)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE,
                  device_main_infos=(dmi_sensor, dmi_actuator1, dmi_actuator2), t=10.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM device_state_data").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM operating_env").fetchone()[0] == 0


def test_handle_device_value_no_operating_env_without_env_state(conn):
    """장치상태만 있고 환경상태가 없으면 묶을 대상이 없다."""
    _connect_actuator(conn, device_id=2, subtype=Subtype.IRRIGATION_VALVE)
    dmi = DeviceMainInfo(device_id=2, dev_type=DevType.ACTUATOR, subtype=int(Subtype.IRRIGATION_VALVE),
                          value_type=ValueType.UINT, value=100)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=11.0)
    ingest.handle(frame, conn)
    assert conn.execute("SELECT COUNT(*) FROM operating_env").fetchone()[0] == 0


# ── 냉난방기 — power 만 채운다 (F-157) ──────────────────────────

def test_handle_device_value_cooling_heater_does_not_duplicate_value(conn):
    """F-157 — 냉난방기는 value 를 power 에만 반영하고 temperature 는
    NULL로 둔다(FAN 과 같은 패턴). 이전에는 같은 값을 두 필드에 중복 기입해
    관측 근거가 하나인데 두 물리량을 관측한 것처럼 보였다."""
    _connect_actuator(conn, device_id=3, subtype=Subtype.COOLING_HEATER)
    dmi = DeviceMainInfo(device_id=3, dev_type=DevType.ACTUATOR, subtype=int(Subtype.COOLING_HEATER),
                          value_type=ValueType.FLOAT, value=18.5)
    frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE, device_main_infos=(dmi,), t=12.0)
    ingest.handle(frame, conn)
    row = conn.execute("SELECT power, temperature, wind_level FROM dsd_cooling_heater").fetchone()
    assert tuple(row) == (1, None, None)
