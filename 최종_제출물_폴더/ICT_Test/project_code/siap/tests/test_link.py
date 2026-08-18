"""siap/link.py 통합 검증 — simulate 모드 소켓 왕복.

실제 sim/virtual_node.py와 독립적으로, 여기서는 노드 역할을 하는
얇은 TCP 서버를 테스트 안에서 직접 띄운다. 검증 대상은 link.py 의 배선
(SIAP I/O 스레드가 REQ_SET_CONNECTION 을 자동 등록하고, send() 가 큐잉·매칭·
타임아웃을 스레드 경계 너머로 올바르게 전달하는가)이다.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

from contracts.frame import (
    Frame, Header, MsgControlProfile, MsgKind, NodeProperty, RSC, Status, Violation,
)
from siap import codec
from siap.link import SiapNodeLink


class _FlakyTransport:
    """ 재현용 — write() 가 지정된 청크 크기만큼만 쓰고, 목록이
    바닥나면 항상 0을 돌려준다(Transport.write 의 부분 쓰기 계약)."""

    def __init__(self, chunk_sizes):
        self.chunk_sizes = list(chunk_sizes)
        self.written = bytearray()

    def open(self) -> None: ...
    def close(self) -> None: ...

    def write(self, data: bytes) -> int:
        if not self.chunk_sizes:
            return 0
        n = min(self.chunk_sizes.pop(0), len(data))
        self.written += data[:n]
        return n

    def read(self, max_bytes: int, timeout: float) -> bytes:
        return b""


class _AlwaysErrorReadTransport:
    """ 재현용 — read() 가 항상 OSError, write() 는 정상 성공한다
    (송신 자체는 되지만 아무도 응답하지 않는 링크)."""

    def open(self) -> None: ...
    def close(self) -> None: ...

    def read(self, max_bytes: int, timeout: float) -> bytes:
        raise OSError("simulated link failure")

    def write(self, data: bytes) -> int:
        return len(data)


def test_reverse_settings_update_runtime_state_f213():
    link = SiapNodeLink(gcg_id=1)
    old = NodeProperty(1, 1, 3, Status.NORMAL, 0)
    link._registry.register(old, ())

    def apply(req: Frame) -> None:
        reply = link._default_reply(req)
        assert reply is not None and reply.rsc == RSC.SUCCESS
        link._apply_registry_effects(req, reply)

    header = Header(0x12, 0, 0, 7, 0, 1, 3)
    node_only = NodeProperty(9, 1, 3, Status.ABNORMAL, 0)
    apply(Frame(header, MsgKind.REQ_SET_NODE_PROPERTY, node_property=node_only))
    assert link.registry()[3] == node_only

    all_node = NodeProperty(10, 1, 3, Status.NORMAL, 0)
    apply(Frame(header, MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL,
                node_property=all_node))
    assert link.registry()[3] == all_node

    changed = MsgControlProfile(9, 4, 30, 45)
    apply(Frame(header, MsgKind.REQ_SET_MSG_FLOW_CONTROL_PROFILE, profile=changed))
    assert link._profile == changed
    assert link._pending.profile() == changed


def test_headerless_violation_gets_no_reply_or_registry_effect_f215():
    link = SiapNodeLink(gcg_id=1)
    frame = Frame(header=None, raw=b"\x12", violations=(
        Violation(9, "INVALID_FORMAT", "7.3.1", "header incomplete"),
    ))
    assert link._default_reply(frame) is None
    link._apply_registry_effects(frame, None)
    assert link.registry() == {}


def test_write_retries_partial_writes_and_reports_truth_f139():
    link = SiapNodeLink(gcg_id=1)
    link._transport = _FlakyTransport([4, 0, 0, 6])
    ok = link._write(b"0123456789")
    assert ok is True
    assert bytes(link._transport.written) == b"0123456789"
    assert link.stats()["tx"] == 1


def test_write_gives_up_after_bounded_stalls_and_does_not_report_success_f139():
    link = SiapNodeLink(gcg_id=1)
    link._transport = _FlakyTransport([4])         # 4byte 만 쓰고 그 뒤로는 계속 0
    ok = link._write(b"0123456789")
    assert ok is False
    assert bytes(link._transport.written) == b"0123"    # 잔여는 버려지지만 성공으로 집계되지 않는다
    assert link.stats()["tx"] == 0


def test_send_bounded_even_when_read_always_errors_f138():
    """read() 가 지속적으로 OSError 를 던져도 send() 는 표 7-18
    상한 안에 돌아온다. 예전에는 `_io_loop()` 가 그 회차의 큐 처리·pending
    만료를 통째로 건너뛰어, pending 등록 자체가 무한정 미뤄졌다."""
    from contracts.frame import MsgControlProfile

    fast_profile = MsgControlProfile(recv_timeout=1, num_retry=1,
                                      noti_error_interval=60, keep_alive_interval=60)
    link = SiapNodeLink(gcg_id=1, profile=fast_profile)
    link._transport = _AlwaysErrorReadTransport()
    link._decoder = codec.Decoder("strict", node_known=link._registry.is_known)
    link._stop.clear()
    link._thread = threading.Thread(target=link._io_loop, name="siap-io-test", daemon=True)
    link._thread.start()
    try:
        frame = link._build.get_node_property(node_id=3)
        t0 = time.monotonic()
        result = link.send(frame)                   # 상한 = 1 × (1+1) = 2초
        elapsed = time.monotonic() - t0
        assert result is None
        # 옛 4.0초 여유는 계약 상한(2초)의 두 배라 상한을 거의
        # 통째로 위반하는 구현도 통과시켰다(실측: send() 반환을 1초 지연시켜
        # 3.032초로 만들어도 PASS). 계약값에서 직접 유도한 상한 + 스케줄링
        # 여유(0.5초)로 좁힌다 — 이 여유보다 큰 지연은 반드시 실패해야 한다.
        upper = fast_profile.recv_timeout * (fast_profile.num_retry + 1)
        assert elapsed < upper + 0.5, (
            f"링크가 죽어 있어도 상한({upper}s) 근처에서 돌아와야 한다 (실제 {elapsed:.2f}s)")
    finally:
        link._stop.set()
        link._thread.join(timeout=2.0)


@pytest.fixture()
def node_socket_pair():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    yield srv, port
    srv.close()


def test_req_set_connection_auto_registers(node_socket_pair):
    srv, port = node_socket_pair
    accepted: list = []

    def node_server():
        conn, _ = srv.accept()
        accepted.append(conn)
        req_hdr = Header(version=0x12, msg_type=0x0000, trans_type=0, msg_id=1,
                          payload_len=0, gcg_id=1, node_id=3)
        conn.sendall(codec.encode_header(req_hdr))
        buf = b""
        while len(buf) < 21:                       # RES_SET_CONNECTION(N=0) = 21byte
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        node_server.result = codec.decode_frame(buf, node_known=lambda n: True)

    t = threading.Thread(target=node_server, daemon=True)
    t.start()

    link = SiapNodeLink(gcg_id=1)
    link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port)
    try:
        t.join(timeout=3.0)
        assert getattr(node_server, "result", None) is not None
        res = node_server.result
        assert not res.violations
        assert res.kind is MsgKind.RES_SET_CONNECTION
        assert res.rsc == RSC.SUCCESS

        assert 3 in link.registry()
        assert link.stats()["rx"] == 0 or link.stats()["rx"] >= 0   # 스모크: 예외 없이 조회된다
    finally:
        link.stop()


def test_recv_stamps_real_wall_clock_time_f203(node_socket_pair):
    """`decode_frame()` 은 `Frame.t` 를 채우지 않는다(순수 함수, 골든
    벡터 재생·단독 코덱 테스트의 결정론을 지키기 위해 의도적이다). 실제
    수신 시각은 I/O 스레드가 디코더에서 완결된 프레임을
    받는 "지금"만 안다 — `_io_loop()` 이 `dataclasses.replace(frame, t=...)`
    로 그 시각을 채워야 한다. 이전에는 이 자리가 없어 `Frame.t` 기본값 0.0
    이 그대로 `frame_log.t`에 저장돼 모든 프레임·노드 시각이 1970년으로
    보였다(실측: simulate 모드 1,409 프레임 전부 t=0.0)."""
    srv, port = node_socket_pair

    def node_server():
        conn, _ = srv.accept()
        req_hdr = Header(version=0x12, msg_type=0x0000, trans_type=0, msg_id=1,
                          payload_len=0, gcg_id=1, node_id=3)
        conn.sendall(codec.encode_header(req_hdr))
        time.sleep(0.3)
        conn.close()

    t = threading.Thread(target=node_server, daemon=True)
    t.start()

    link = SiapNodeLink(gcg_id=1)
    seen: list[Frame] = []
    before = time.time()

    link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port,
               on_frame=lambda frame: seen.append(frame))
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not seen:
            time.sleep(0.05)
        after = time.time()
        assert seen, "on_frame 이 프레임을 받지 못했다"
        assert seen[0].t != 0.0, "Frame.t 가 기본값(0.0) 그대로다 — 재발"
        assert before - 1.0 <= seen[0].t <= after + 1.0, \
            f"Frame.t={seen[0].t} 가 실측 수신 구간[{before}, {after}] 밖이다"
    finally:
        link.stop()
        t.join(timeout=1.0)


def test_on_frame_success_still_registers_f137(node_socket_pair):
    """`on_frame` 이 주입돼도 `link.registry()` 는 연결을 반영해야
    한다. 이전에는 `_default_reply()` 경로만 registry 를 갱신해, on_frame 이
    주입되는 순간(backend 를 실제로 연결하는 순간) 등록이 유실됐다.

    갱신 — `on_frame` 은 이제 회신을 대신 만들지 않으므로(부수효과
    전용, `_default_reply()` 가 항상 회신을 만든다) 아래 `fake_backend_handle`
    이 스스로 RES_SET_CONNECTION 을 반환하는 것은 더 이상 registry 갱신의
    전제가 아니다 — 무엇을 반환하든 `_default_reply()` 가 등록을 보장한다.
    이 테스트는 그 상태에서도 여전히 통과함을 보여 회귀가 없음을 확인한다
    (반환값에 무관한 새 보장은 `test_on_frame_is_side_effect_only_f154` 가
    직접 검증한다)."""
    srv, port = node_socket_pair

    def node_server():
        conn, _ = srv.accept()
        req_hdr = Header(version=0x12, msg_type=0x0000, trans_type=0, msg_id=1,
                          payload_len=0, gcg_id=1, node_id=3)
        conn.sendall(codec.encode_header(req_hdr))
        time.sleep(0.3)
        conn.close()

    t = threading.Thread(target=node_server, daemon=True)
    t.start()

    link = SiapNodeLink(gcg_id=1)

    def fake_backend_handle(frame: Frame) -> Frame | None:
        """backend.ingest.handle() 을 흉내낸다 — registry.py 를 전혀 모른 채
        RES_SET_CONNECTION 을 스스로 구성해 회신한다( 시나리오)."""
        if frame.kind is MsgKind.REQ_SET_CONNECTION:
            node = NodeProperty(sw_version=1, gcg_id=1, node_id=frame.header.node_id,
                                 status=Status.NORMAL, num_devices=0)
            return link._build.res_set_connection(frame, RSC.SUCCESS, node=node, devices=())
        return None

    link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port,
               on_frame=fake_backend_handle)
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and 3 not in link.registry():
            time.sleep(0.05)
        assert 3 in link.registry(), "on_frame 경로로 성공한 연결이 registry 에 반영되지 않았다"
    finally:
        link.stop()
        t.join(timeout=1.0)


def test_on_frame_is_side_effect_only_f154(node_socket_pair):
    """`on_frame`은 회신을 대신 만들지 않는다. 반환값과 무관하게
    (여기서는 항상 None을 돌려주는, `backend.ingest.handle`을 흉내낸 콜백)
    노드가 실제로 받는 바이트는 여전히 `_default_reply()`가 만든 정상
    RES_SET_CONNECTION이어야 한다 — 이전에는 `on_frame`이 설정되면
    `_default_reply()`를 완전히 대신해, 이런 콜백을 꽂는 순간 노드가 아무
    회신도 받지 못했다(0943 6.2.2 위반)."""
    srv, port = node_socket_pair
    received: list[bytes] = []

    def node_server():
        conn, _ = srv.accept()
        req_hdr = Header(version=0x12, msg_type=0x0000, trans_type=0, msg_id=1,
                          payload_len=0, gcg_id=1, node_id=3)
        conn.sendall(codec.encode_header(req_hdr))
        buf = b""
        while len(buf) < 21:                       # RES_SET_CONNECTION(N=0) = 21byte
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        received.append(buf)
        conn.close()

    t = threading.Thread(target=node_server, daemon=True)
    t.start()

    calls: list[Frame] = []

    def side_effect_only_handler(frame: Frame) -> None:
        """DB 반영만 하고 아무것도 반환하지 않는 backend.ingest.handle 흉내."""
        calls.append(frame)
        return None

    link = SiapNodeLink(gcg_id=1)
    link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port,
               on_frame=side_effect_only_handler)
    try:
        t.join(timeout=3.0)
        assert len(received) == 1 and received[0], "on_frame이 None만 돌려줘도 노드는 회신을 받아야 한다"
        res = codec.decode_frame(received[0], node_known=lambda n: True)
        assert not res.violations
        assert res.kind is MsgKind.RES_SET_CONNECTION
        assert res.rsc == RSC.SUCCESS

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and 3 not in link.registry():
            time.sleep(0.05)
        assert 3 in link.registry(), "_default_reply() 가 항상 registry 를 갱신해야 한다"

        assert len(calls) == 1 and calls[0].kind is MsgKind.REQ_SET_CONNECTION, (
            "on_frame 은 여전히 매 프레임마다 부수효과로 호출돼야 한다")
    finally:
        link.stop()


def test_send_matches_response_across_thread_boundary(node_socket_pair):
    srv, port = node_socket_pair

    def node_server():
        conn, _ = srv.accept()
        buf = b""
        while len(buf) < 12:
            buf += conn.recv(4096)
        req = codec.decode_frame(buf, node_known=lambda n: True)
        assert req.kind is MsgKind.REQ_GET_NODE_PROPERTY
        resp_hdr = Header(version=0x12, msg_type=0x0407, trans_type=0,
                           msg_id=req.header.msg_id, payload_len=9,
                           gcg_id=req.header.gcg_id, node_id=req.header.node_id)
        resp = Frame(header=resp_hdr, kind=MsgKind.RES_GET_NODE_PROPERTY, rsc=RSC.SUCCESS,
                     node_property=NodeProperty(sw_version=1, gcg_id=1, node_id=3,
                                                 status=Status.NORMAL, num_devices=0))
        conn.sendall(codec.encode_frame(resp))
        time.sleep(0.3)
        conn.close()

    t = threading.Thread(target=node_server, daemon=True)
    t.start()

    link = SiapNodeLink(gcg_id=1)
    link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port)
    try:
        # 실사용에서는 REQ_SET_CONNECTION 핸드셰이크를 먼저 거쳐야 노드가
        # 등록된다 — 등록 전 Node ID 로 온 응답은 decode_frame() 이 위반
        # 2(INVALID_NODE_ID)로 판정한다(의도된 동작). 이 테스트는 send()/매칭
        # 자체가 관심사이므로 등록을 직접 주입한다.
        link._registry.register(
            NodeProperty(sw_version=1, gcg_id=1, node_id=3, status=Status.NORMAL, num_devices=0))
        frame = link._build.get_node_property(node_id=3)
        result = link.send(frame, timeout=3.0)
        assert result is not None
        assert result.kind is MsgKind.RES_GET_NODE_PROPERTY
        assert result.rsc == RSC.SUCCESS
    finally:
        link.stop()
        t.join(timeout=1.0)


def test_send_times_out_when_no_response(node_socket_pair):
    """상대가 응답하지 않으면 표 7-18 상한(Timeout×(Retry+1)) 이후 None."""
    srv, port = node_socket_pair
    accepted = threading.Event()

    def node_server():
        conn, _ = srv.accept()
        accepted.set()
        time.sleep(5.0)                             # 응답하지 않는다
        conn.close()

    t = threading.Thread(target=node_server, daemon=True)
    t.start()

    from contracts.frame import MsgControlProfile
    fast_profile = MsgControlProfile(recv_timeout=1, num_retry=1,
                                      noti_error_interval=60, keep_alive_interval=60)
    link = SiapNodeLink(gcg_id=1, profile=fast_profile)
    link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port)
    try:
        assert accepted.wait(timeout=2.0)
        frame = link._build.get_node_property(node_id=3)
        t0 = time.monotonic()
        result = link.send(frame)                   # 상한 = 1 × (1+1) = 2초
        elapsed = time.monotonic() - t0
        assert result is None
        # 이 5.0초도 위와 같은 결함이다: 노드의 5초 sleep 을
        # "기다리지 않았다"만 확인하려던 여유가 계약 상한(2초)을 2.5배
        # 초과하는 구현까지 통과시킨다. 계약값 + 스케줄링 여유(0.5초)로 좁힌다.
        upper = fast_profile.recv_timeout * (fast_profile.num_retry + 1)
        assert elapsed < upper + 0.5, (
            f"노드의 5초 sleep 을 기다리면 안 된다 — 상한({upper}s) 근처에서 돌아와야 한다 "
            f"(실제 {elapsed:.2f}s)")
    finally:
        link.stop()


def test_req_set_node_device_property_all_registers_devices_f198(node_socket_pair):
    """전체 경로 회귀: wire bytes(`sim/_wire.py`, 실제 프로덕션
    인코더) → `siap/codec.py` 디코드 → `siap/link.py` 디스패치 →
    `siap/registry.py` 갱신. 손으로 만든 Frame이 아니라 실제 바이트로
    검증한다(GPT 지적 — 기존 backend 단독 테스트는 코덱이 만들 수 없는
    `Frame(kind=REQ_SET_CONNECTION, device_properties=(...))`으로 회귀를
    가렸다). `REQ_SET_CONNECTION`은 페이로드가 없으므로 이 시나리오에서
    등록 뒤에도 `link.devices()`가 계속 비어 있다가, `REQ_SET_NODE_
    DEVICE_PROPERTY_ALL`을 보낸 뒤에야 채워져야 한다."""
    from sim import _wire as wire

    srv, port = node_socket_pair
    phase1_done = threading.Event()   # ① 완료 — 메인 스레드가 registry 를 확인할 때까지 대기
    phase2_go = threading.Event()     # 메인 스레드가 확인을 마쳤으니 ②를 진행해도 된다

    def node_server():
        conn, _ = srv.accept()

        # ① REQ_SET_CONNECTION — 페이로드 없음. 응답만 확인하고 넘어간다.
        conn.sendall(wire.build_req_set_connection(1, 1, 3))
        buf = b""
        while len(buf) < 21:                        # RES_SET_CONNECTION(N=0) = 21byte
            chunk = conn.recv(4096)
            if not chunk:
                phase1_done.set()
                return
            buf += chunk
        res1 = codec.decode_frame(buf, node_known=lambda n: True)
        node_server.res1 = res1
        phase1_done.set()
        if res1.violations or res1.rsc != RSC.SUCCESS:
            return
        if not phase2_go.wait(timeout=3.0):
            return

        # ② REQ_SET_NODE_DEVICE_PROPERTY_ALL — 실제 프로덕션 인코더로 만든
        # NODE_PROPERTY + DEVICE_PROPERTY×1.
        np = wire.WireNP(sw_version=1, gcg_id=1, node_id=3, status=wire.STATUS_NORMAL, num_devices=1)
        dmi = wire.WireDMI(device_id=1, dev_type=wire.DEV_SENSOR, subtype=1,
                            value_type=wire.VT_FLOAT, value=wire.float_to_raw(25.3))
        dp = wire.WireDP(main=dmi, transfer_mode=wire.TM_PERIODIC, period=2,
                          lower_value=wire.float_to_raw(-10.0), upper_value=wire.float_to_raw(60.0),
                          lower_limit=wire.float_to_raw(-10.0), upper_limit=wire.float_to_raw(60.0),
                          precision=wire.float_to_raw(0.1), status=wire.STATUS_NORMAL)
        conn.sendall(wire.build_req_set_node_device_property_all(2, 1, 3, np, [dp]))
        buf2 = b""
        while len(buf2) < 13:                       # RES_SET_NODE_DEVICE_PROPERTY_ALL(RSC만) = 13byte
            chunk = conn.recv(4096)
            if not chunk:
                return
            buf2 += chunk
        node_server.res2 = codec.decode_frame(buf2, node_known=lambda n: True)
        conn.close()

    t = threading.Thread(target=node_server, daemon=True)
    t.start()

    link = SiapNodeLink(gcg_id=1)
    link.start("simulate", proto_mode="strict", host="127.0.0.1", socket_port=port)
    try:
        assert phase1_done.wait(timeout=3.0)
        res1 = getattr(node_server, "res1", None)
        assert res1 is not None and not res1.violations and res1.rsc == RSC.SUCCESS

        # 게이트웨이가 회신을 실제로 처리(_apply_registry_effects)할 시간을
        # 준다 — node_server 의 recv() 완료와 link 쪽 registry 갱신은 각자
        # 다른 스레드에서 비동기로 일어난다.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and 3 not in link.registry():
            time.sleep(0.02)

        # REQ_SET_CONNECTION 만으로는(구조적으로 페이로드가 없으므로) 아직
        # 디바이스가 하나도 등록되지 않아야 한다 —이 고친 바로 그 지점.
        assert 3 in link.registry()
        assert link.devices(3) == (), (
            "REQ_SET_CONNECTION 만으로 디바이스가 등록됐다 — 그 메시지는 페이로드가 없다")

        phase2_go.set()   # ②를 진행해도 좋다는 신호

        res2 = None
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            res2 = getattr(node_server, "res2", None)
            if res2 is not None:
                break
            time.sleep(0.05)
        assert res2 is not None and not res2.violations
        assert res2.kind is MsgKind.RES_SET_NODE_DEVICE_PROPERTY_ALL
        assert res2.rsc == RSC.SUCCESS

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and not link.devices(3):
            time.sleep(0.05)
        devices = link.devices(3)
        assert len(devices) == 1, " 재발: REQ_SET_NODE_DEVICE_PROPERTY_ALL 뒤에도 registry 가 비어 있다"
        assert devices[0].device_id == 1
        assert devices[0].subtype == 1
        assert devices[0].value == pytest.approx(25.3, abs=1e-4)

        dps = link._registry.device_properties(3)
        assert len(dps) == 1
        assert dps[0].period == 2
        assert dps[0].lower_limit == pytest.approx(-10.0)
        assert dps[0].upper_limit == pytest.approx(60.0)
        t.join(timeout=2.0)
    finally:
        link.stop()
