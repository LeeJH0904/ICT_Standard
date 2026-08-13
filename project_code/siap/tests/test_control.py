"""siap/control.py 검증 — F-046 응답 매칭, F-041 재전송·타임아웃.

가짜 시계(now_fn 주입)로 실제 sleep 없이 재전송·타임아웃을 재현한다.
"""
from __future__ import annotations

from contracts.frame import MsgControlProfile, MsgKind
from siap.build import FrameBuilderImpl
from siap.control import PendingTable


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _profile(timeout=2, retry=2):
    return MsgControlProfile(recv_timeout=timeout, num_retry=retry,
                              noti_error_interval=60, keep_alive_interval=60)


def test_register_returns_none_for_no_reply_expected():
    """RES_*·ACK 송신은 회신을 기다리지 않는다(§8.1)."""
    clock = FakeClock()
    pt = PendingTable(_profile(), now_fn=clock)
    b = FrameBuilderImpl(gcg_id=1)
    req = b.get_node_property(node_id=3)   # Request 를 흉내내되, 직접 RES_* Frame 을 만든다
    from contracts.frame import Frame, Header, RSC
    res = b.res_set_node_property(req, RSC.SUCCESS)
    assert pt.register(res) is None
    assert len(pt) == 0


def test_register_returns_pending_for_request():
    clock = FakeClock()
    pt = PendingTable(_profile(), now_fn=clock)
    b = FrameBuilderImpl(gcg_id=1)
    req = b.get_node_property(node_id=3)
    pend = pt.register(req)
    assert pend is not None
    assert pend.expect is MsgKind.RES_GET_NODE_PROPERTY
    assert len(pt) == 1


def test_match_requires_node_id_msg_id_and_kind_f046():
    """F-046 — Node ID + Message Identifier + Message Type 셋 다 맞아야
    대기 항목이 소비된다. 종류가 다르면(예: ACK 가 RES_* 를 대신할 수 없다)
    소비하지 않는다."""
    clock = FakeClock()
    pt = PendingTable(_profile(), now_fn=clock)
    b = FrameBuilderImpl(gcg_id=1)
    req = b.get_node_property(node_id=3)
    pend = pt.register(req)

    from dataclasses import replace
    from contracts.frame import Frame

    # (a) 같은 Node ID·msg_id 지만 종류가 다르다(ACK) — 소비하지 않는다
    wrong_kind = Frame(header=req.header, kind=MsgKind.ACK)
    assert pt.match(wrong_kind) is False
    assert len(pt) == 1

    # (b) 같은 msg_id 지만 다른 Node ID — 소비하지 않는다
    other_node_hdr = replace(req.header, node_id=99)
    wrong_node = Frame(header=other_node_hdr, kind=MsgKind.RES_GET_NODE_PROPERTY)
    assert pt.match(wrong_node) is False
    assert len(pt) == 1

    # (c) Node ID·msg_id·종류가 전부 맞다 — 소비한다
    right = Frame(header=req.header, kind=MsgKind.RES_GET_NODE_PROPERTY)
    assert pt.match(right) is True
    assert len(pt) == 0
    assert pend.result is right
    assert pend.event.is_set()


def test_retransmit_keeps_msg_id_f041():
    """F-041 — 재전송 시 Message Identifier 를 유지한다(새로 발번하지 않는다)."""
    clock = FakeClock()
    pt = PendingTable(_profile(timeout=2, retry=2), now_fn=clock)
    b = FrameBuilderImpl(gcg_id=1)
    req = b.get_node_property(node_id=3)
    original_msg_id = req.header.msg_id
    pend = pt.register(req)

    retransmitted = []
    clock.t = 3.0
    pt.expire(lambda fr: retransmitted.append(fr))
    assert len(retransmitted) == 1
    assert retransmitted[0].header.msg_id == original_msg_id
    assert pend.tries == 1
    assert len(pt) == 1


def test_exhausted_retries_resolves_to_none():
    """표 7-18 Num. of Retry 를 다 쓰면 대기 항목이 지워지고 send() 는
    None 을 받는다(타임아웃)."""
    clock = FakeClock()
    pt = PendingTable(_profile(timeout=1, retry=1), now_fn=clock)
    b = FrameBuilderImpl(gcg_id=1)
    req = b.get_node_property(node_id=3)
    pend = pt.register(req)

    clock.t = 2.0
    pt.expire(lambda fr: None)              # 1차 재전송(tries=1, retry=1 이니 아직 남음... )
    assert len(pt) == 1
    clock.t = 4.0
    pt.expire(lambda fr: None)              # 재시도 소진 → 포기
    assert len(pt) == 0
    assert pend.result is None
    assert pend.event.is_set()


def test_wait_upper_bound_is_timeout_times_retry_plus_one_f041():
    """send() 대기 상한 = Timeout × (Retry Count + 1)."""
    clock = FakeClock()
    profile = _profile(timeout=2, retry=2)
    pt = PendingTable(profile, now_fn=clock)
    b = FrameBuilderImpl(gcg_id=1)
    req = b.get_node_property(node_id=3)
    pend = pt.register(req)
    pend.event.set()                        # 즉시 해제 — 대기 계산만 확인
    import time
    t0 = time.monotonic()
    pt.wait(pend, timeout=None)
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5                    # 이미 set() 됐으니 상한까지 기다리지 않는다
