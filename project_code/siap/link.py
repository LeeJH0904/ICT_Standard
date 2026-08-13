"""
siap/link.py — `SiapLink` 구현 (contracts/siap_iface.py Protocol).

아키텍처 설계서 §3.1-b/§4.1/§4.2 — SIAP I/O 스레드가 시리얼/소켓의 유일한
소유자다. 수신·송신·재전송을 같은 루프에서 매 회 처리한다(무한 블로킹 금지 —
그래야 무수신 중에도 API 의 송신 요청이 나간다).

`on_frame` 콜백으로 부수효과(`backend.ingest`)를 주입받는다 — `siap/`
은 `backend/` 를 import 하지 않는다(CLAUDE.md §2.2)는 계층 규칙을 지키면서도,
아키텍처 설계서 §3.1-b 의사코드가 그리는 "I/O 스레드가 `ingest.handle()` 을
직접 부른다" 동작을 실현하는 유일한 방법이 의존성 주입이다 — `run.py`(단계 5,
F-160)가 `link.start(..., on_frame=_make_on_frame(db_path))` 로 연결한다.

F-167 — 여기 꽂는 콜백은 `backend.ingest.bind(conn)` 을 **그대로** 쓰지
않는다. `on_frame` 은 이 파일의 SIAP I/O 스레드 안에서 호출되는데,
`bind(conn)` 은 호출자가 미리 연 연결을 클로저에 가둘 뿐이라 그 연결을
다른 스레드(보통 `run.py` 의 메인 스레드)에서 열면 `sqlite3.
ProgrammingError` 로 죽는다(아키텍처 설계서 §4.1 "스레드별 연결",
`check_same_thread=False` 금지 — F-160 재현 실측). `run.py::_make_on_frame()`
은 DB 파일 **경로**만 받아 이 스레드 안에서 첫 호출 시점에 지연 연결한다.
`bind(conn)` 은 스레드 경계가 이미 보장된 호출자(테스트 등)를 위해
`backend/ingest.py`에 남아 있다.

F-154 — **`on_frame` 은 회신을 대신 만들지 않는다.** 회신 구성("REQ_SET_
CONNECTION 에 어떤 NODE_PROPERTY 로 응답할까" 같은 판정)은 표준 해석이고,
표준 해석은 프로토콜 계층에만 있다(CLAUDE.md §3.4) — `backend/` 가 그 판정을
다시 하면 두 곳에서 서로 다르게 해석될 위험이 생긴다. 그래서 회신은 **항상**
`_default_reply()` 가 만들고, `on_frame` 은 매 프레임마다 **부수효과 전용**
으로 추가 호출될 뿐이다(반환값은 무시된다) — `backend.ingest.handle(frame,
conn)` 처럼 DB 반영만 하는 함수를 그대로 꽂을 수 있다. (이전 버전은 `on_frame`
이 설정되면 `_default_reply()` 를 완전히 대신했다 — `backend/` 가 `siap/
build.py` 없이도 완결된 RES_SET_CONNECTION 을 만들어야 했던 지점이라
CLAUDE.md §3.4 를 어겼다.)

`on_frame` 이 없어도 내장 기본 처리기(`_default_reply`)가 항상 동작한다 —
`REQ_SET_CONNECTION` 자동 등록 + SUCCESS 회신, 그 외 노드발 Request 는
SUCCESS 회신, Notify 는 ACK. `python run.py --mode simulate`(단계 4 출구)가
`backend/` 없이도 프레임을 주고받는 이유다.

**`on_frame` 은 절대 `link.send()` 를 불러선 안 된다** — `send()` 는 이 파일의
I/O 스레드가 처리하는 큐에 넣고 기다리는데, 그 큐를 비우는 것이 지금 `on_frame`
을 호출하며 블로킹된 바로 그 스레드다(자기대기 교착, 아키텍처 설계서 §3.1-a).
"""
from __future__ import annotations

import dataclasses
import queue
import threading
import time
from typing import Callable, Iterator

try:                    # F-025 — 패키지로 import될 때
    from contracts.frame import (
        DeviceMainInfo, Frame, Mode, MsgControlProfile, MsgKind, NodeProperty,
        NODE_ORIGINATED_NOTIFIES, NODE_ORIGINATED_REQUESTS, RSC, Status,
    )
    from siap import codec, transport
    from siap.build import FrameBuilderImpl
    from siap.control import PendingTable
    from siap.registry import NodeRegistry
except ImportError:     # 스크립트로 직접 실행되거나 project_code 가 sys.path 밖일 때
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    from contracts.frame import (
        DeviceMainInfo, Frame, Mode, MsgControlProfile, MsgKind, NodeProperty,
        NODE_ORIGINATED_NOTIFIES, NODE_ORIGINATED_REQUESTS, RSC, Status,
    )
    from siap import codec, transport
    from siap.build import FrameBuilderImpl
    from siap.control import PendingTable
    from siap.registry import NodeRegistry


#: 아키텍처 §6.2-a — Timeout ≥ 2×wire_time, 기본 2초(N=16 501byte, 9600baud
#: 522ms 의 2배). Retry·Interval 은 표 7-18 이 값 자체를 규정하지 않아 이
#: 프로젝트의 기본값으로 둔다 — 실제 노드별 프로파일은 RES_SET_CONNECTION
#: 협상 결과로 갱신될 여지를 남긴다(이번 단계는 단일 전역 프로파일로 시작).
DEFAULT_PROFILE = MsgControlProfile(recv_timeout=2, num_retry=2,
                                     noti_error_interval=60, keep_alive_interval=60)


class SiapNodeLink:
    """`SiapLink` Protocol 구현. 시리얼/소켓은 이 클래스의 I/O 스레드만 연다."""

    def __init__(self, gcg_id: int = 1, profile: MsgControlProfile = DEFAULT_PROFILE) -> None:
        self._gcg_id = gcg_id
        self._profile = profile
        self._registry = NodeRegistry()
        self._pending = PendingTable(self._profile)
        self._proto_mode: Mode = "strict"
        self._build = FrameBuilderImpl(gcg_id, mode=self._proto_mode, registry=self._registry)
        self._decoder: codec.Decoder | None = None
        self._transport: transport.Transport | None = None
        self._txq: "queue.Queue" = queue.Queue()
        self._recvq: "queue.Queue" = queue.Queue()
        self._on_frame: Callable[[Frame], Frame | None] | None = None   # F-154: 부수효과 전용, 반환값 무시
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._stats = {"rx": 0, "tx": 0, "violations": 0, "retries": 0, "uptime": 0.0}
        self._start_time = 0.0

    # ── SiapLink ────────────────────────────────────────────────
    def start(self, run_mode: str, *, proto_mode: Mode = "strict", **opts) -> None:
        self._proto_mode = proto_mode
        self._build = FrameBuilderImpl(self._gcg_id, mode=proto_mode, registry=self._registry)
        self._on_frame = opts.pop("on_frame", None)
        self._decoder = codec.Decoder(proto_mode, node_known=self._registry.is_known)
        self._transport = transport.open_transport(run_mode, **opts)
        self._transport.open()
        self._start_time = time.monotonic()
        self._stop.clear()
        self._thread = threading.Thread(target=self._io_loop, name="siap-io", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._transport is not None:
            self._transport.close()
            self._transport = None

    def recv(self) -> Iterator[Frame]:
        """위반 프레임도 그대로 흘려보낸다(계약, contracts/siap_iface.py).
        `stop()` 이후에는 큐에 남은 것만 마저 내보내고 끝난다."""
        while True:
            try:
                yield self._recvq.get(timeout=0.1)
            except queue.Empty:
                if self._stop.is_set():
                    return

    def send(self, frame: Frame, timeout: float | None = None) -> Frame | None:
        """Request → Response Frame 반환 / Notify → None. 큐에 넣고 기다릴
        뿐이다 — 호출자는 I/O 스레드를 의식하지 않는다(계약).

        F-138 — 대기 상한(`Timeout × (Retry Count + 1)`)은 pending 등록 *이후*
        뿐 아니라 큐잉부터 회신까지 **호출 전체**에 걸린다. I/O 스레드가
        전송 계층 오류로 계속 막혀 있으면(과거에는 `_io_loop()` 가 그 회차의
        큐 처리·만료 검사를 통째로 건너뛰어 pending 등록 자체가 무한정
        미뤄졌다) 이 마감시각이 없으면 `out.get()` 이 영원히 블로킹한다."""
        upper = timeout if timeout is not None else self._profile.recv_timeout * (self._profile.num_retry + 1)
        deadline = time.monotonic() + upper
        out: "queue.Queue" = queue.Queue(maxsize=1)
        self._txq.put((frame, out))
        try:
            req = out.get(timeout=max(deadline - time.monotonic(), 0.0))
        except queue.Empty:
            return None                       # I/O 스레드가 상한 안에 등록조차 못 했다(링크 다운)
        if req is None:
            return None                       # 회신을 기다리지 않는 송신(RES_*·ACK, F-046)
        return self._pending.wait(req, timeout=max(deadline - time.monotonic(), 0.0))

    def registry(self) -> dict[int, NodeProperty]:
        return self._registry.registry()

    def devices(self, node_id: int) -> tuple[DeviceMainInfo, ...]:
        return self._registry.devices(node_id)

    def stats(self) -> dict:
        s = dict(self._stats)
        s["uptime"] = (time.monotonic() - self._start_time) if self._start_time else 0.0
        return s

    # ── I/O 스레드 (아키텍처 설계서 §3.1-b) ─────────────────────
    def _write(self, data: bytes) -> bool:
        """부분 쓰기를 재시도해 전량 내보낸다(펌웨어 설계서 §5.8 의 논블로킹
        부분 쓰기 계약을 host 쪽에서 흡수).

        F-139 — `write()` 가 0을 돌려주는 것은 "지금은 못 썼다"는 뜻이지
        "더 쓸 수 없다"는 뜻이 아니다(Transport.write 계약). 예전에는 그
        자리에서 `break` 해 잔여 바이트를 조용히 버리면서도 `stats['tx']`
        는 성공으로 셌다 — 프레임이 절단된 채로 "정상 송신"처럼 보였다.
        유한 횟수(최대 50회, 회당 10ms)로 재시도하고, 그래도 다 못 보내면
        `tx` 를 올리지 않고 False 를 돌려준다 — 실패를 조용히 성공으로
        보고하지 않는다."""
        assert self._transport is not None
        sent = 0
        stalls = 0
        while sent < len(data) and stalls < 50:
            n = self._transport.write(data[sent:])
            if n <= 0:
                stalls += 1
                time.sleep(0.01)
                continue
            sent += n
            stalls = 0
        if sent < len(data):
            return False
        self._stats["tx"] += 1
        return True

    def _io_loop(self) -> None:
        assert self._transport is not None and self._decoder is not None
        while not self._stop.is_set():
            # ① 수신 — timeout 이 지나면 b"" 를 돌려주고 넘어간다.
            # 전송 계층 예외(상대가 연결을 끊는 등)도 이 회차의 ②·③ 은
            # 반드시 계속 돈다(F-138) — 예전에는 여기서 continue 해 read
            # 오류가 계속되는 동안 송신 큐 처리·pending 만료가 통째로
            # 멈췄다. 그러면 `send()` 가 등록조차 못 해 표 7-18 상한
            # 계산 자체에 도달하지 못하고 무한 대기했다.
            try:
                chunk = self._transport.read(4096, 0.05)
            except OSError:
                chunk = b""
            if chunk:
                for frame in self._decoder.feed(chunk):
                    # F-203 — decode_frame() 은 바이트를 해석할 뿐 수신 시각을
                    # 모른다(자기 완결적 순수 함수, 골든 벡터 재생·단독 코덱
                    # 테스트에서 결정론이 깨지면 안 되므로 일부러 그렇다).
                    # 실제 수신 시각(Frame 구조 명세서 §3)은 이 스레드가
                    # 전송 계층에서 바이트를 받아 디코더가 완결된 프레임을
                    # 내보낸 "지금"만이 안다 — 여기서 한 번만 채운다. Frame
                    # 은 frozen dataclass 라 replace() 로 새 값을 만든다.
                    frame = dataclasses.replace(frame, t=time.time())
                    self._stats["rx"] += 1
                    if frame.violations:
                        self._stats["violations"] += 1
                    self._recvq.put(frame)                    # frame_log 대응 — RES_*/ACK 도 남긴다
                    if not self._pending.match(frame):
                        reply = self._dispatch(frame)
                        self._apply_registry_effects(frame, reply)     # F-137
                        if reply is not None:
                            self._write(codec.encode_frame(reply, self._proto_mode))
            # ② API 가 넣어둔 송신 요청 — 수신 여부와 무관하게 매 회 처리한다
            self._drain_txq()
            # ③ 응답이 오지 않은 요청의 재전송·타임아웃 (표 7-18)
            self._pending.expire(self._retransmit)

    def _retransmit(self, frame: Frame) -> None:
        self._write(codec.encode_frame(frame, self._proto_mode))
        self._stats["retries"] += 1

    def _drain_txq(self) -> None:
        while True:
            try:
                frame, out = self._txq.get_nowait()
            except queue.Empty:
                return
            self._write(codec.encode_frame(frame, self._proto_mode))
            out.put(self._pending.register(frame))

    def _dispatch(self, frame: Frame) -> Frame | None:
        """F-154 — 회신은 항상 `_default_reply()` 가 만든다(표준 해석은
        프로토콜 계층에만, CLAUDE.md §3.4). `on_frame` 은 설정돼 있으면
        부수효과(예: `backend.ingest.handle` 의 DB 반영)로 추가 호출될
        뿐이고, 반환값은 쓰지 않는다 — 이전에는 `on_frame` 이 설정되면
        `_default_reply()` 자체를 건너뛰어, `backend/` 가 `siap/build.py`
        없이도 완결된 프로토콜 회신을 스스로 만들어야 했다."""
        reply = self._default_reply(frame)
        if self._on_frame is not None:
            self._on_frame(frame)
        return reply

    def _apply_registry_effects(self, frame: Frame, reply: Frame | None) -> None:
        """레지스트리 갱신은 회신 경로(내장 기본 처리기 / 주입된 `on_frame`)와
        무관하게 이 한 곳에서만 일어난다(F-137) — `on_frame` 이
        `backend.ingest.handle` 로 교체돼도 `registry()`/`devices()` 가
        실제 연결 상태를 반영하도록 보장한다. `_default_reply()` 는 더 이상
        직접 `register()`/`unregister()` 를 부르지 않는다 — 중복 갱신을
        피하고, 갱신 지점을 하나로 좁힌다.

        회신 Frame 자체에서 등록 내용을 읽는다 — `build.res_set_connection()`
        은 항상 유효한 `node_property` 를 채우므로(§ build.py), 어느 경로가
        회신을 만들었든 이 판정은 동일하게 성립한다."""
        if (frame.kind is MsgKind.REQ_SET_CONNECTION and reply is not None
                and reply.kind is MsgKind.RES_SET_CONNECTION and reply.rsc == RSC.SUCCESS
                and reply.node_property is not None):
            self._registry.register(reply.node_property, reply.device_properties)
        elif frame.kind is MsgKind.NOTI_DISCONNECT:
            self._registry.unregister(frame.header.node_id)
        elif (frame.kind is MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL and reply is not None
                and reply.rsc == RSC.SUCCESS):
            # F-198 — REQ_SET_CONNECTION 은 페이로드가 없어(LAYOUT (0,0)) 디바이스
            # 구성을 실을 수 없다. 노드가 연결 성공 뒤 이 메시지로 전체 구성을
            # 선언하면 그때 registry 를 갱신한다("ALL"이므로 전체 교체).
            self._registry.merge_device_properties(
                frame.header.node_id, frame.device_properties, replace=True)
        elif (frame.kind is MsgKind.REQ_SET_DEVICE_PROPERTY and reply is not None
                and reply.rsc == RSC.SUCCESS):
            # 부분 갱신 — device_id 기준 병합(표에 없는 기존 디바이스는 유지).
            self._registry.merge_device_properties(
                frame.header.node_id, frame.device_properties, replace=False)

    def _default_reply(self, frame: Frame) -> Frame | None:
        """`backend/` 가 아직 없을 때(이 단계) 쓰는 최소 기본 처리기 —
        `REQ_SET_CONNECTION` 은 SUCCESS 회신(등록은 `_apply_registry_effects()`
        가 한다), 그 외 노드발 Request 는 SUCCESS 회신, Notify 는 ACK."""
        if frame.violations:
            return self._build.error_response(frame, RSC(frame.violations[0].code))

        if frame.kind is MsgKind.REQ_SET_CONNECTION:
            node = NodeProperty(sw_version=1, gcg_id=self._gcg_id,
                                 node_id=frame.header.node_id, status=Status.NORMAL,
                                 num_devices=0)
            return self._build.res_set_connection(frame, RSC.SUCCESS, node=node, devices=())

        if frame.kind in NODE_ORIGINATED_REQUESTS:
            if frame.kind is MsgKind.REQ_SET_NODE_PROPERTY:
                return self._build.res_set_node_property(frame, RSC.SUCCESS)
            if frame.kind is MsgKind.REQ_SET_DEVICE_PROPERTY:
                return self._build.res_set_device_property(frame, RSC.SUCCESS)
            if frame.kind is MsgKind.REQ_SET_NODE_DEVICE_PROPERTY_ALL:
                return self._build.res_set_node_device_property_all(frame, RSC.SUCCESS)
            if frame.kind is MsgKind.REQ_SET_MSG_FLOW_CONTROL_PROFILE:
                return self._build.res_set_msg_flow_control_profile(frame, RSC.SUCCESS)

        if frame.kind in NODE_ORIGINATED_NOTIFIES:
            return self._build.ack(frame)       # NOTI_DISCONNECT 등록 해제는 _apply_registry_effects() 가 한다

        return None                            # RES_*/ACK — 이미 위에서 match() 시도했다
