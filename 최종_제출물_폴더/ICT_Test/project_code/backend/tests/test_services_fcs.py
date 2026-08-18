"""backend/tests/test_services_fcs.py — backend/services/fcs.py 단위 테스트.

 회귀 테스트 전용 — `link.send()`가 재전송을 모두 소진해 `None`을
반환할 때(0943 표 7-18 `Timeout × (Retry Count + 1)`), 0937 6.5-2 "긴급
상황시 사용자 알림"이 요구하는 `alert(kind='CONTROL_TIMEOUT')`이 실제로
생기는지를 HTTP 계층 없이 직접 확인한다.
"""
from __future__ import annotations

import pytest

from backend import db, repository
from backend.services import fcs
from contracts.fake_link import FakeFrameBuilder, FakeSiapLink
from contracts.frame import DevType


@pytest.fixture()
def conn(tmp_path):
    con = db.init_db(tmp_path / "fcs.db", seed=True)
    yield con
    con.close()


@pytest.fixture()
def builder():
    return FakeFrameBuilder(gcg_id=1)


def _register_install(conn, builder, *, node_id=3, device_id=1, subtype=0x85) -> str:
    gh = repository.get_default_greenhouse_id(conn)
    info_id = repository.get_or_create_device_info(
        conn, device_kind="ACTUATOR", model_name=f"SIAP-0x{subtype:02X}", device_name="dev")
    install_id = repository.upsert_device_install_info(
        conn, device_info_id=info_id, device_name="v", siap_node_id=node_id,
        siap_device_id=device_id, siap_subtype=subtype)
    repository.link_device_install(conn, gh, install_id)
    conn.commit()
    builder.device_kinds[(node_id, device_id)] = (DevType.ACTUATOR, subtype)
    return install_id


class _TimeoutLink(FakeSiapLink):
    """재전송이 전부 실패해 응답 없이 소진됐다는 것을 흉내낸다 — `send()`가
    항상 `None`을 돌려준다(실제 `siap/control.py::_expire_pending`이
    `SiapLink.send()`의 반환값 자리에서 이렇게 만든다)."""

    def send(self, frame, timeout=None):
        self._stats["tx"] += 1
        return None


def test_manual_control_timeout_records_control_timeout_alert_f191(conn, builder):
    install_id = _register_install(conn, builder)
    link = _TimeoutLink()
    link.start("simulate")

    with pytest.raises(fcs.ExecutionTimeoutError) as exc:
        fcs.manual_control(conn, link, builder, install_id=install_id,
                            action={"value": 1, "value_type": "UINT"}, user_id="demo-user-1")
    exec_id = exc.value.exec_id

    alerts = repository.list_alerts(conn)
    assert len(alerts) == 1
    assert alerts[0].kind == "CONTROL_TIMEOUT"
    assert alerts[0].severity == "CRITICAL"
    assert alerts[0].install_id == install_id
    assert exec_id in alerts[0].message

    execution = repository.get_control_execution(conn, exec_id)
    assert execution.result_rsc is None
    assert execution.responded_at is None


def test_manual_control_success_records_no_alert(conn, builder):
    """정상 응답이면 CONTROL_TIMEOUT 알림이 생기지 않는다(음성 대조)."""
    install_id = _register_install(conn, builder)
    link = FakeSiapLink()
    link.start("simulate")

    fcs.manual_control(conn, link, builder, install_id=install_id,
                        action={"value": 1, "value_type": "UINT"}, user_id="demo-user-1")
    assert repository.list_alerts(conn) == []
