"""
sim/virtual_node.py — `simulate` 모드 가상 노드 서버 (아키텍처 설계서 §5.5).

`socket://127.0.0.1:5556` 로 게이트웨이(`SiapNodeLink`)가 클라이언트로
접속한다(§5.2). 접속 후 노드 3종(Uno·Pro Mini·ESP32 흉내)이 한 연결
위에서 각자의 `Node ID`로 프레임을 주고받는다 — 실물은 노드마다 물리
링크가 분리되지만, `simulate` 모드는 그 다중 링크를 하나의 TCP 연결 위
프레임 다중화로 흉내낸다(§5.1 표: `simulate` 포트는 하나뿐이다).

이 서버가 만드는 모든 바이트는 `sim/_wire.py`(독립 인코더)를 거친다 —
`siap/codec.py`를 재사용하지 않는다(§5.5, 인코더 버그 상쇄 방지).

센서값 출처 — **골든 벡터 DMI 값 재사용** (2026-08-09 사용자 확인).
아키텍처 설계서 §5.5는 "센서값은 실측 로그의 값 분포를 재사용한다"고
규정하지만, 실측 로그(`project_code/logs/*.jsonl`)는 단계 8(보드 3종
실물 통합)에서만 채워진다 — 이 단계에는 존재하지 않는 산출물을 전제로
한 순환 의존이다. 실측 데이터가 준비되기 전까지는 `contracts/vectors/
golden.jsonl`의 `judgement=normal` DEVICE_MAIN_INFO.Value 값(사람이
손으로 만들고 코드로 검증한, 이미 감사된 프로젝트 산출물)을 재사용한다
— 무작위 함수나 사인파 생성으로 만든 값이 아니므로 CLAUDE.md §1-1
(합성 데이터 금지) 위반이 아니다. 단계 8에서 실측 캡처가 준비되면
`_load_value_pool()`을 실측 로그 기반으로 교체한다(§5.5 결정 표 참조).

디바이스 구성 선언 — **F-198.** `REQ_SET_CONNECTION`(8.1.1)은 페이로드가
없어(`contracts/frame.py::LAYOUT (0,0)`) 디바이스 구성을 실을 수 없다.
이 서버는 `RES_SET_CONNECTION`(RSC=SUCCESS) 수신 직후 `REQ_SET_NODE_
DEVICE_PROPERTY_ALL`(8.1.3.3, 노드→GCG) 1회로 자신의 전체 디바이스
구성을 게이트웨이에 선언한다(CLAUDE.md §3.5 결정). 회신(`RES_SET_NODE_
DEVICE_PROPERTY_ALL`)을 받을 때까지 유한 횟수 재전송한다 — fire-and-
forget으로 두면 그 프레임 하나가 유실됐을 때 "장치 0개"로 조용히
되돌아간다(F-198 GPT 검증 지적). `DEVICE_PROPERTY`의 USER DEPENDENT
5필드(하한·상한값/한계·정밀도)에 쓰는 물리적 범위 상수(`_PROPERTY_RANGES`)
는 손으로 고른 설정값이지 "측정값"이 아니다 — CLAUDE.md §1-1이 금지하는
무작위·주기함수 생성 대상이 아니다.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    from sim import _wire as wire
except ImportError:                      # 스크립트로 직접 실행될 때
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from sim import _wire as wire

log = logging.getLogger("sim.virtual_node")

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = REPO_ROOT / "contracts" / "vectors" / "golden.jsonl"

# 이 파일 전용 Subtype 상수(1369-P1 6.3.3/6.3.4) — contracts/frame.py 를
# import 하지 않는다(§5.5 독립성 원칙, sim/_wire.py 와 같은 이유).
SUBTYPE_TEMPERATURE = 0x01        # 6.3.3.2
SUBTYPE_HUMIDITY = 0x02           # 6.3.3.3
SUBTYPE_IRRIGATION_VALVE = 0x85   # 6.3.4.6

# DEVICE_PROPERTY(표 7-15) USER DEPENDENT 5필드 중 하한·상한(Lower/Upper
# Limit·Value 는 같은 범위를 재사용한다, 근거는 아래 함수 참고) — 손으로
# 고른 물리적으로 합당한 설정 상수다. §1-1이 금지하는 것은 무작위·주기
# 함수로 만든 "측정값"이지, 이런 설정용 상수가 아니다(F-198).
# {subtype: (lower_limit, upper_limit, precision)}
_PROPERTY_RANGES: dict[int, tuple[float, float, float]] = {
    SUBTYPE_TEMPERATURE: (-10.0, 60.0, 0.1),
    SUBTYPE_HUMIDITY: (0.0, 100.0, 1.0),
    SUBTYPE_IRRIGATION_VALVE: (0.0, 100.0, 1.0),
}

# F-198 — 노드가 자신의 디바이스 구성을 선언하는 REQ_SET_NODE_DEVICE_
# PROPERTY_ALL 은 fire-and-forget이 아니다(응답을 기다리고 유한 재전송한다).
# siap/link.py::DEFAULT_PROFILE(recv_timeout=2, num_retry=2)과 같은 이유로
# 고른 값이지만 이 파일은 siap/를 import하지 않으므로(§5.5 독립성 원칙)
# 독립적으로 같은 상수를 다시 적는다.
PROPERTY_DECLARE_RETRY_SEC = 2.0
PROPERTY_DECLARE_MAX_ATTEMPTS = 3


def _pack_by_type(value: float, value_type: int) -> int:
    """DEVICE_PROPERTY 의 USER DEPENDENT 필드를 main.value_type 규칙대로
    32bit raw 로 packing한다(F-022, WireDMI.value 와 같은 관례)."""
    if value_type == wire.VT_FLOAT:
        return wire.float_to_raw(float(value))
    return int(value) & 0xFFFFFFFF   # VT_UINT · VT_INT(2의 보수) 공통


def _load_value_pool() -> dict[int, tuple[int, int]]:
    """골든 벡터에서 `{subtype: (value_type, raw_value)}` 풀을 만든다.
    같은 subtype 에 category="정상"과 "경계값" 예시가 둘 다 있으면
    "정상"을 우선한다(경계값은 2^31 같은 극단치라 데모 화면에 그대로
    보이면 실제 물리량처럼 오인될 수 있다)."""
    by_subtype_normal: dict[int, tuple[int, int]] = {}
    by_subtype_any: dict[int, tuple[int, int]] = {}
    if not GOLDEN_PATH.exists():
        return {}
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            v = json.loads(line)
            if v.get("judgement") != "normal":
                continue
            cur: dict | None = None
            for fd in v.get("fields", []):
                name = fd["name"]
                if name == "Subtype":
                    cur = {"subtype": fd["value"]}
                elif name == "Value Type" and cur is not None:
                    cur["value_type"] = fd["value"]
                elif name == "Value" and cur is not None and "subtype" in cur and "value_type" in cur:
                    st = cur["subtype"]
                    pair = (cur["value_type"], fd["value"])
                    by_subtype_any.setdefault(st, pair)
                    if v.get("category") == "정상":
                        by_subtype_normal.setdefault(st, pair)
                    cur = None
    merged = dict(by_subtype_any)
    merged.update(by_subtype_normal)
    return merged


@dataclass
class SimDevice:
    device_id: int
    dev_type: int          # wire.DEV_SENSOR / wire.DEV_ACTUATOR
    subtype: int
    value_type: int
    value: int              # 32bit raw (INT 2의 보수/UINT/FLOAT 비트패턴)


@dataclass
class SimNode:
    node_id: int
    label: str
    devices: list[SimDevice]
    msg_id: int = 0
    connected: bool = False
    # F-198 — 디바이스 구성 선언(REQ_SET_NODE_DEVICE_PROPERTY_ALL) 상태.
    # property_declared 는 게이트웨이가 RSC=SUCCESS 로 확인해 줬을 때만 True —
    # 그전까지는 재전송 대상이다. next_declare_at 은 None 이면 "아직 보낼
    # 때가 아니다"(RES_SET_CONNECTION 성공을 기다리는 중), 값이 있으면
    # 그 monotonic 시각에 (재)전송한다.
    property_declared: bool = False
    next_declare_at: float | None = None
    declare_attempts: int = 0

    def next_msg_id(self) -> int:
        """7.2.2 — 0부터 시작, 0xFFFF 다음은 0으로 순환(F-135 와 같은 원칙을
        이 파일에서 독립적으로 다시 구현)."""
        v = self.msg_id
        self.msg_id = (v + 1) & 0xFFFF
        return v


def _dmi(pool: dict[int, tuple[int, int]], device_id: int, dev_type: int, subtype: int,
         fallback: tuple[int, int]) -> SimDevice:
    vt, val = pool.get(subtype, fallback)
    return SimDevice(device_id, dev_type, subtype, vt, val)


def _device_property(d: SimDevice, period_sec: int) -> "wire.WireDP":
    """SimDevice 1개를 DEVICE_PROPERTY(표 7-15)로 편다(F-198). `Period` 는
    실제 NOTI_DEVICE_VALUE 송신 주기와 같은 값을 그대로 쓴다(아키텍처
    설계서 §5.5 결정 표) — 선언한 주기와 실제 전송 주기가 어긋나지 않는다.
    Lower/Upper Value 는 이 데모에 별도의 "목표 운용 범위" 개념이 없으므로
    Lower/Upper Limit(유효범위)과 같은 값을 재사용한다."""
    lo, hi, prec = _PROPERTY_RANGES.get(d.subtype, (0.0, 0.0, 0.0))
    lo_raw, hi_raw, prec_raw = (_pack_by_type(lo, d.value_type),
                                _pack_by_type(hi, d.value_type),
                                _pack_by_type(prec, d.value_type))
    dmi = wire.WireDMI(d.device_id, d.dev_type, d.subtype, d.value_type, d.value)
    return wire.WireDP(
        main=dmi, transfer_mode=wire.TM_PERIODIC, period=period_sec,
        lower_value=lo_raw, upper_value=hi_raw,
        lower_limit=lo_raw, upper_limit=hi_raw,
        precision=prec_raw, status=wire.STATUS_NORMAL,
    )


def _default_nodes(pool: dict[int, tuple[int, int]]) -> list[SimNode]:
    """3종 혼용 데모 — Uno/Pro Mini/ESP32 를 흉내내는 노드 3대.

    Uno 흉내 노드의 ID 는 101이 아니라 **3**이다(F-145). `contracts/vectors/
    golden.jsonl` 의 정상 34종·위반 8종(X01~X08) 은 B06(최대값 경계)·X02
    (미등록 Node ID 를 의도적으로 만드는 반례) 를 뺀 전부가 `Node ID=3` 을
    쓴다 — 골든벡터 명세서가 손으로 고른 "표준 테스트 노드" 관례다.
    `sim/inject.py` 가 이 golden hex 를 바이트 그대로 링크에 흘려보내므로
    (시연 시나리오 §3.1 "주입은 실제 바이트를 바꾼다"), 그 프레임들이
    가리키는 Node ID 도 그대로 3 이다. 이 서버가 3을 등록하지 않으면
    `decode_frame()` 은 Value Type·Subtype·NEC 를 보기도 전에
    `INVALID_NODE_ID` 로 판정해 X06·X07·X08 세 종의 목표 판정
    (INVALID_DATA_TYPE·INVALID_DATA_SUBTYPE·ERROR_BATTERY_LOW) 이 전부
    가려진다."""
    return [
        SimNode(3, "arduino_sensor_node(Uno) 흉내", [
            _dmi(pool, 1, wire.DEV_SENSOR, SUBTYPE_TEMPERATURE, (wire.VT_FLOAT, 0)),
        ]),
        SimNode(102, "arduino_actuator_node(Pro Mini) 흉내", [
            _dmi(pool, 1, wire.DEV_SENSOR, SUBTYPE_HUMIDITY, (wire.VT_FLOAT, 0)),
            _dmi(pool, 2, wire.DEV_ACTUATOR, SUBTYPE_IRRIGATION_VALVE, (wire.VT_UINT, 0)),
        ]),
        SimNode(103, "esp32_node 흉내", [
            _dmi(pool, 1, wire.DEV_SENSOR, SUBTYPE_TEMPERATURE, (wire.VT_FLOAT, 0)),
        ]),
    ]


def _late_node(pool: dict[int, tuple[int, int]]) -> SimNode:
    """§5.5 "실행 중 노드 1개 추가 접속" — 기능 1 Plug & Play 시연용."""
    return SimNode(104, "실행 중 추가 접속 노드", [
        _dmi(pool, 1, wire.DEV_SENSOR, SUBTYPE_TEMPERATURE, (wire.VT_FLOAT, 0)),
    ])


class VirtualNodeServer:
    """`simulate` 모드 TCP 서버. 게이트웨이가 클라이언트로 접속한다
    (아키텍처 설계서 §5.2 "replay/simulate 서버는 같은 프로세스의
    스레드로 기동. 별도 실행 불필요")."""

    def __init__(self, host: str = "127.0.0.1", port: int = 5556, *,
                 control_port: int | None = 5557,
                 device_value_period: float = 2.0,
                 keep_alive_period: float = 6.0,
                 late_node_delay: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._control_port = control_port
        self._device_value_period = device_value_period
        self._keep_alive_period = keep_alive_period
        self._late_node_delay = late_node_delay

        pool = _load_value_pool()
        self._nodes: list[SimNode] = _default_nodes(pool)
        self._late_node = _late_node(pool)

        self._srv: socket.socket | None = None
        self._ctrl_srv: socket.socket | None = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._conn: socket.socket | None = None
        self._conn_lock = threading.Lock()
        self.stats = {"tx": 0, "rx": 0}

    # ── 수명주기 ────────────────────────────────────────────
    def start(self) -> None:
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self._host, self._port))
        self._srv.listen(1)
        self._srv.settimeout(0.2)
        t = threading.Thread(target=self._accept_loop, name="sim-vnode-accept", daemon=True)
        t.start()
        self._threads.append(t)

        if self._control_port is not None:
            self._ctrl_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._ctrl_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._ctrl_srv.bind((self._host, self._control_port))
            self._ctrl_srv.listen(1)
            self._ctrl_srv.settimeout(0.2)
            tc = threading.Thread(target=self._control_loop, name="sim-vnode-ctrl", daemon=True)
            tc.start()
            self._threads.append(tc)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2.0)
        with self._conn_lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except OSError:
                    pass
                self._conn = None
        if self._srv is not None:
            self._srv.close()
            self._srv = None
        if self._ctrl_srv is not None:
            self._ctrl_srv.close()
            self._ctrl_srv = None

    # ── 게이트웨이 접속 처리 ───────────────────────────────
    def _accept_loop(self) -> None:
        assert self._srv is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            conn.settimeout(0.1)
            with self._conn_lock:
                self._conn = conn
            log.info("게이트웨이 접속 수락")
            try:
                self._serve_connection(conn)
            finally:
                with self._conn_lock:
                    if self._conn is conn:
                        self._conn = None

    def _serve_connection(self, conn: socket.socket) -> None:
        start = time.monotonic()
        next_dv = {n.node_id: start for n in self._nodes}
        next_ka = {n.node_id: start for n in self._nodes}
        late_fired = False
        buf = bytearray()

        for i, n in enumerate(self._nodes):
            time.sleep(0.05 * i)
            self._send(conn, wire.build_req_set_connection(n.next_msg_id(), 1, n.node_id))

        while not self._stop.is_set():
            now = time.monotonic()

            for n in self._nodes:
                # F-198 — 디바이스 구성 선언. RES_SET_CONNECTION 성공 뒤에만
                # next_declare_at 이 채워진다(_handle() 에서) — 등록 전에
                # 보내면 게이트웨이가 INVALID_NODE_ID 로 거부한다(경합 방지).
                # 재전송은 유한하다(PROPERTY_DECLARE_MAX_ATTEMPTS) — 그
                # 이상은 포기하고 로그만 남긴다(가상 노드는 표준 준수
                # 검증기가 아니다, _drain() 독스트링과 같은 원칙).
                if (not n.property_declared and n.next_declare_at is not None
                        and now >= n.next_declare_at):
                    if n.declare_attempts >= PROPERTY_DECLARE_MAX_ATTEMPTS:
                        n.next_declare_at = None
                        log.warning("노드 %s 디바이스 구성 선언 %d회 시도 후 포기",
                                    n.node_id, n.declare_attempts)
                    else:
                        np = wire.WireNP(sw_version=1, gcg_id=1, node_id=n.node_id,
                                          status=wire.STATUS_NORMAL, num_devices=len(n.devices))
                        dps = [_device_property(d, int(self._device_value_period)) for d in n.devices]
                        self._send(conn, wire.build_req_set_node_device_property_all(
                            n.next_msg_id(), 1, n.node_id, np, dps))
                        n.declare_attempts += 1
                        n.next_declare_at = now + PROPERTY_DECLARE_RETRY_SEC
                if now >= next_dv[n.node_id]:
                    dmis = [wire.WireDMI(d.device_id, d.dev_type, d.subtype, d.value_type, d.value)
                            for d in n.devices]
                    self._send(conn, wire.build_noti_device_value(n.next_msg_id(), 1, n.node_id, dmis))
                    next_dv[n.node_id] = now + self._device_value_period
                if now >= next_ka[n.node_id]:
                    self._send(conn, wire.build_noti_keep_alive(n.next_msg_id(), 1, n.node_id))
                    next_ka[n.node_id] = now + self._keep_alive_period

            if not late_fired and (now - start) >= self._late_node_delay:
                late_fired = True
                self._nodes.append(self._late_node)
                next_dv[self._late_node.node_id] = now
                next_ka[self._late_node.node_id] = now
                self._send(conn, wire.build_req_set_connection(
                    self._late_node.next_msg_id(), 1, self._late_node.node_id))
                log.info("노드 %s 실행 중 추가 접속 (기능 1 Plug & Play 시연)", self._late_node.node_id)

            try:
                chunk = conn.recv(4096)
            except socket.timeout:
                chunk = None
            except OSError:
                break
            if chunk == b"":
                log.info("게이트웨이 연결 종료")
                break
            if chunk:
                buf += chunk
                self._drain(conn, buf)

    def _drain(self, conn: socket.socket, buf: bytearray) -> None:
        """가상 노드는 표준 준수 검증기가 아니다 — 헤더가 깨졌거나 길이가
        터무니없으면 그냥 버퍼를 비우고 다음 바이트부터 다시 헤더 후보로
        본다. 진짜 §5.7 재동기 알고리즘은 `siap/codec.py`·`firmware/`의
        몫이다(F-140·F-141)."""
        while len(buf) >= wire.HEADER_BYTES:
            try:
                h = wire.decode_header(bytes(buf[:wire.HEADER_BYTES]))
            except ValueError:
                buf.clear()
                return
            if h.payload_len > 2048:
                buf.clear()
                return
            total = wire.HEADER_BYTES + h.payload_len
            if len(buf) < total:
                return
            payload = bytes(buf[wire.HEADER_BYTES:total])
            del buf[:total]
            self.stats["rx"] += 1
            self._handle(conn, h, payload)

    def _handle(self, conn: socket.socket, h: "wire.WireHeader", payload: bytes) -> None:
        node = next((n for n in self._nodes if n.node_id == h.node_id), None)
        if h.msg_type == wire.MT_RES_SET_CONNECTION:
            try:
                rsc = wire.decode_res_set_connection(payload)
            except ValueError:
                return
            if node is not None:
                node.connected = (rsc == wire.RSC_SUCCESS)
                if rsc == wire.RSC_SUCCESS and not node.property_declared:
                    # F-198 — 연결 성공 직후에만 디바이스 구성 선언을 시작한다
                    # (등록 전에 보내면 INVALID_NODE_ID 로 거부되는 경합을 피한다).
                    node.next_declare_at = time.monotonic()
            log.info("노드 %s 연결 응답 RSC=0x%02X", h.node_id, rsc)
        elif h.msg_type == wire.MT_RES_SET_NODE_DEVICE_PROPERTY_ALL:
            try:
                rsc = wire.decode_res_set_node_device_property_all(payload)
            except ValueError:
                return
            if node is not None and rsc == wire.RSC_SUCCESS:
                node.property_declared = True
                node.next_declare_at = None
            log.info("노드 %s 디바이스 구성 선언 응답 RSC=0x%02X", h.node_id, rsc)
        elif h.msg_type == wire.MT_ACK:
            log.debug("노드 %s ACK msg_id=%s", h.node_id, h.msg_id)
        elif h.msg_type == wire.MT_REQ_SET_DEVICE_CONTROL:
            try:
                dmis = wire.decode_req_set_device_control(payload)
            except ValueError:
                return
            if node is not None:
                for cmd in dmis:
                    for dev in node.devices:
                        if dev.device_id == cmd.device_id:
                            dev.value = cmd.value
                            log.info("노드 %s 디바이스 %s 제어값 갱신: 0x%08X",
                                      h.node_id, dev.device_id, dev.value)
            self._send(conn, wire.build_res_set_device_control(h.msg_id, h.gcg_id, h.node_id))
        elif h.msg_type == wire.MT_RES_SET_DEVICE_CONTROL:
            log.debug("노드 %s 제어 응답 msg_id=%s", h.node_id, h.msg_id)
        else:
            log.debug("노드 %s 미처리 메시지 msg_type=0x%04X", h.node_id, h.msg_type)

    def _send(self, conn: socket.socket, data: bytes) -> None:
        try:
            conn.sendall(data)
            self.stats["tx"] += 1
        except OSError:
            pass

    # ── 로컬 주입 제어 채널 — `sim/inject.py` 가 여기에 접속한다 ──
    # (시연 시나리오 §3.1 S4-b "주입 버튼 클릭"이 실행할 대상. 단계 6 의
    # `POST /api/v1/sim/inject`(F-084) 는 이 서버 인스턴스를 직접 참조해
    # 이 로컬 소켓 왕복 없이 호출할 수도 있다 — 어느 쪽이든 최종적으로
    # `sim.inject.inject()` 하나로 수렴한다.)
    def _control_loop(self) -> None:
        assert self._ctrl_srv is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._ctrl_srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                self._serve_control(conn)
            finally:
                conn.close()

    def _serve_control(self, ctrl_conn: socket.socket) -> None:
        ctrl_conn.settimeout(2.0)
        buf = b""
        try:
            while not self._stop.is_set():
                chunk = ctrl_conn.recv(256)
                if not chunk:
                    return
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self._handle_control_line(ctrl_conn, line.decode("ascii", "replace").strip())
        except socket.timeout:
            return

    def _handle_control_line(self, ctrl_conn: socket.socket, line: str) -> None:
        parts = line.split()
        if len(parts) == 2 and parts[0] == "INJECT":
            vector_id = parts[1]
            with self._conn_lock:
                conn = self._conn
            if conn is None:
                ctrl_conn.sendall(b"ERR no-gateway-connected\n")
                return
            try:
                from sim import inject
                data = inject.inject(vector_id, conn)
            except Exception as e:                       # noqa: BLE001 — 제어 채널은 원인을 그대로 회신한다
                ctrl_conn.sendall(f"ERR {e}\n".encode("ascii", "replace"))
                return
            ctrl_conn.sendall(f"OK {len(data)}\n".encode("ascii"))
        else:
            ctrl_conn.sendall(b"ERR unknown-command\n")


def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="[virtual_node] %(message)s")
    p = argparse.ArgumentParser(prog="sim/virtual_node.py")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5556)
    p.add_argument("--control-port", type=int, default=5557)
    p.add_argument("--duration", type=float, default=0.0, help="0이면 Ctrl+C 까지 계속 실행")
    args = p.parse_args(argv)

    srv = VirtualNodeServer(args.host, args.port, control_port=args.control_port)
    srv.start()
    log.info("가상 노드 서버 시작 host=%s port=%s (제어 포트 %s)", args.host, args.port, args.control_port)
    try:
        if args.duration > 0:
            time.sleep(args.duration)
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        srv.stop()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
