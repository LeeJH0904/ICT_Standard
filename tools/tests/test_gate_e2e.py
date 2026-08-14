"""F-225 회귀 — 승인 거부 전에 발생한 실제 링크 TX를 출구가 검출한다."""
from tools import gate_e2e
from backend import repository
from backend.services import fcs
from contracts.frame import DevType, ValueType


def test_f225_rejected_execute_tx_side_effect_fails_gate(monkeypatch):
    original = fcs.execute
    sent = 0

    def mutant(conn, link, builder, rule_id, *, timeout=None):
        nonlocal sent
        rule = repository.get_control_rule(conn, rule_id)
        if rule is not None and not rule.is_approved:
            builder.device_kinds[(0, 0)] = (DevType.ACTUATOR, 0x81)
            link.send(builder.device_control(0, [(0, 1, ValueType.UINT)]), timeout=timeout)
            sent += 1
        return original(conn, link, builder, rule_id, timeout=timeout)

    monkeypatch.setattr(fcs, "execute", mutant)
    gate_e2e.RESULTS.clear()
    assert gate_e2e.main() == 1
    assert sent == 3
    assert any("F-225" in name and not ok for name, ok, _ in gate_e2e.RESULTS)
    gate_e2e.RESULTS.clear()
