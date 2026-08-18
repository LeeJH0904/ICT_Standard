"""backend/tests/test_services_fms.py — backend/services/fms.py 단위 테스트.

 회귀 테스트 전용 — `check_stale_devices()`가 실제로 `alert(kind=
'NO_DATA')`를 만드는지, 그리고 중복 생성을 막는지 확인한다(0937 6.4-3).
`env_state_data.measured_at`은 트리거로 불변이라(1369-P1 7.2.3.3) 과거로
되돌릴 수 없다 — 대신 "관측은 방금, 판정 시각(`now`)만 미래로" 방향으로
만든다. `check_stale_devices(conn, now)`가 `now`를 인자로 받도록 설계돼
있는 이유가 이 테스트 가능성이다."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend import db, ingest, repository
from backend.services import fms
from contracts.frame import (
    DeviceMainInfo, DeviceProperty, DevType, Frame, Header, MsgKind, Status,
    Subtype, TransferMode, ValueType,
)

NODE_ID = 3


def _header(msg_type=0, trans_type=0, msg_id=1, payload_len=0, node_id=NODE_ID) -> Header:
    return Header(version=0x12, msg_type=msg_type, trans_type=trans_type, msg_id=msg_id,
                  payload_len=payload_len, gcg_id=1, node_id=node_id)


@pytest.fixture()
def conn(tmp_path):
    con = db.init_db(tmp_path / "fms.db", seed=True)
    yield con
    con.close()


def _connect_and_report_temperature(conn, device_id=1, value=20.0) -> str:
    """센서 1개를 등록하고 값을 1건 보고한다. 반환: install_id."""
    dmi_conn = DeviceMainInfo(device_id=device_id, dev_type=DevType.SENSOR,
                               subtype=int(Subtype.TEMPERATURE), value_type=ValueType.FLOAT, value=0.0)
    dp = DeviceProperty(main=dmi_conn, transfer_mode=TransferMode.PERIODIC, period=60,
                         lower_value=-10.0, upper_value=50.0, lower_limit=-40.0, upper_limit=80.0,
                         precision=0.1, status=Status.NORMAL)
    # 디바이스 속성 선언은 REQ_SET_NODE_DEVICE_PROPERTY_ALL(노드→GCG)로
    # 온다. REQ_SET_CONNECTION(8.1.1)은 페이로드가 없어(LAYOUT (0,0)) 이
    # device_properties 를 실을 수 없다.
    connect_frame = Frame(header=_header(), kind=MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL,
                           device_properties=(dp,), t=1.0)
    ingest.handle(connect_frame, conn)
    install = repository.find_device_install_by_siap(conn, NODE_ID, device_id)
    install_id = install["id"]

    dmi = DeviceMainInfo(device_id=device_id, dev_type=DevType.SENSOR,
                          subtype=int(Subtype.TEMPERATURE), value_type=ValueType.FLOAT, value=value)
    value_frame = Frame(header=_header(), kind=MsgKind.NOTI_DEVICE_VALUE,
                         device_main_infos=(dmi,), t=2.0)
    ingest.handle(value_frame, conn)
    return install_id


def _future_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc).astimezone() + timedelta(seconds=seconds)).isoformat(timespec="seconds")


def test_check_stale_devices_creates_no_data_alert_f191(conn):
    install_id = _connect_and_report_temperature(conn)
    judged_at = _future_iso(181)   # Period 60 × 3 = 180, 독립 기대값

    created = fms.check_stale_devices(conn, judged_at)
    assert len(created) == 1

    alerts = repository.list_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0].kind == "NO_DATA"
    assert alerts[0].severity == "WARN"
    assert alerts[0].install_id == install_id


def test_check_stale_devices_does_not_duplicate_unacked_alert(conn):
    _connect_and_report_temperature(conn)
    judged_at = _future_iso(181)   # Period 60 × 3 = 180

    first = fms.check_stale_devices(conn, judged_at)
    second = fms.check_stale_devices(conn, judged_at)
    assert len(first) == 1
    assert second == []
    assert len(repository.list_alerts(conn)) == 1


def test_check_stale_devices_fresh_data_creates_no_alert(conn):
    _connect_and_report_temperature(conn)   # 방금 관측 — 임계값을 넘지 않는다
    created = fms.check_stale_devices(conn, repository.now_iso())
    assert created == []
    assert repository.list_alerts(conn) == []


def test_check_stale_devices_uses_each_device_period_f227(conn):
    fast_id = _connect_and_report_temperature(conn, device_id=1)
    slow_id = _connect_and_report_temperature(conn, device_id=2)
    conn.execute("UPDATE device_install_info SET period_sec=300 WHERE id=?", (slow_id,))
    conn.commit()

    created = fms.check_stale_devices(conn, _future_iso(181))
    assert len(created) == 1
    alerts = repository.list_alerts(conn)
    assert [alert.install_id for alert in alerts] == [fast_id]
