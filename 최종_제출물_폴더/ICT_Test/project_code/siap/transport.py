"""
siap/transport.py — 전송 계층 3모드.

심사자에게는 라즈베리파이도 MCU 도 없다 — 교체 대상은 전송 계층 한 곳뿐이다.

  hardware : 실제 시리얼 포트 (pyserial)
  replay   : TCP 소켓 클라이언트 — 실측 로그 재생 서버(`sim/replayer.py`)에 접속
  simulate : TCP 소켓 클라이언트 — 가상 노드 서버(`sim/virtual_node.py`)에 접속

replay·simulate 모두 TCP 소켓만 쓴다 — `socat` 등 외부 도구 의존을 피해
심사자 OS에 무관하게 동작하게 한다. 이 파일은 **클라이언트 쪽
배관만** 담당한다 — 반대편(로그 재생 서버·가상 노드 서버)은 `sim/`의
몫이며, 그 서버가 없어도 `SocketTransport` 자체는 임의의
TCP 서버(테스트 더블 포함)에 접속해 동작한다.
"""
from __future__ import annotations

import socket
from typing import Protocol

#: URLS 표 그대로. hardware 는 장치 경로, replay/simulate 는 (host, port).
DEFAULT_URLS: dict[str, object] = {
    "hardware": "/dev/ttyUSB0",
    "replay": ("127.0.0.1", 5555),      # 실측 로그 재생
    "simulate": ("127.0.0.1", 5556),    # 가상 노드 (양방향)
}


class Transport(Protocol):
    """link.py 의 SIAP I/O 스레드가 아는 유일한 인터페이스. `siap_io_t`
    (firmware/core/siap_types.h) 의 Python 대응 — `read_byte`/`write`/`millis`
    를 `read`/`write` 로 묶었다(Python 은 블로킹 I/O 도 timeout 인자로
    논블로킹처럼 쓸 수 있어 바이트 단위 콜백이 필요 없다)."""

    def open(self) -> None: ...

    def close(self) -> None: ...

    def read(self, max_bytes: int, timeout: float) -> bytes:
        """`timeout` 초 안에 1byte도 못 읽으면 `b""`를 돌려준다 —
        무수신에도 I/O 루프가 돈다)."""
        ...

    def write(self, data: bytes) -> int:
        """실제로 쓴 바이트 수. 부분 쓰기를 허용한다(`siap_io_write_fn` 과
        동일 계약) — 호출자가 남은 바이트를 재시도한다."""
        ...


class SerialTransport:
    """hardware 모드. `pyserial` 은 프로젝트 원칙이 허용한 의존성 3종 중
    하나다. import 는 지연시킨다 — replay/simulate 만 쓰는 심사 환경에서
    `pyserial` 이 없어도 이 파일 자체(및 이 클래스 정의)는 로드돼야 한다."""

    def __init__(self, port: str, baudrate: int = 9600) -> None:
        self._port_name = port
        self._baudrate = baudrate
        self._ser = None

    def open(self) -> None:
        import serial   # pyserial — 지연 import (실제 하드웨어 접속 시점에만 필요)
        self._ser = serial.Serial(self._port_name, self._baudrate, timeout=0)

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def read(self, max_bytes: int, timeout: float) -> bytes:
        if self._ser is None:
            raise RuntimeError("open() 을 먼저 불러야 한다")
        self._ser.timeout = timeout
        data = self._ser.read(max_bytes)
        return data or b""

    def write(self, data: bytes) -> int:
        if self._ser is None:
            raise RuntimeError("open() 을 먼저 불러야 한다")
        n = self._ser.write(data)
        return n if n is not None else 0


class SocketTransport:
    """replay·simulate 공통 — TCP 소켓 클라이언트 하나로 양쪽을 구현한다
    (URLS 표: 둘 다 `socket://` 이고 포트만 다르다).

    알려진 단순화 — `recv()` 가 돌려주는 `b""` 는 "타임아웃(아직 안 왔다)"과
    "상대가 연결을 정상 종료했다(FIN)"를 구분하지 않는다. link.py 의 폴링
    루프는 어느 쪽이든 다음 회차에 다시 시도하므로
    (골든 벡터 재생·pytest)에는 영향이 없지만, 재접속 로직이 필요해지면
    실제 연결 끊김 처리가 필요해지면 여기서 `recv()==b""`를 소켓 상태 조회와
    함께 판정하도록 넓혀야 한다."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._sock: socket.socket | None = None

    def open(self) -> None:
        self._sock = socket.create_connection((self._host, self._port), timeout=5.0)
        self._sock.settimeout(0)   # 이후는 read()/write() 가 매번 timeout 을 지정한다

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def read(self, max_bytes: int, timeout: float) -> bytes:
        if self._sock is None:
            raise RuntimeError("open() 을 먼저 불러야 한다")
        self._sock.settimeout(timeout)
        try:
            return self._sock.recv(max_bytes)
        except (socket.timeout, BlockingIOError):
            return b""

    def write(self, data: bytes) -> int:
        if self._sock is None:
            raise RuntimeError("open() 을 먼저 불러야 한다")
        self._sock.settimeout(None)   # 쓰기는 짧다 — 전량 전송으로 단순화한다
        self._sock.sendall(data)
        return len(data)


def open_transport(run_mode: str, **opts) -> Transport:
    """`SiapLink.start(run_mode, **opts)` 에서 호출한다.

    opts:
      hardware — `port`(시리얼 장치 경로, 기본 `/dev/ttyUSB0`) · `baudrate`(기본 9600)
      replay/simulate — `host`(기본 127.0.0.1) · `socket_port`(기본은 표.
        `port` 를 쓰지 않는 이유는 hardware 의 `port`(장치 경로, str)와 이름이
        겹치면 `run.py --port` 인자가 두 의미로 오버로드되기 때문이다)."""
    if run_mode == "hardware":
        port = opts.get("port") or DEFAULT_URLS["hardware"]
        return SerialTransport(str(port), opts.get("baudrate", 9600))
    if run_mode in ("replay", "simulate"):
        default_host, default_port = DEFAULT_URLS[run_mode]
        host = opts.get("host", default_host)
        port = opts.get("socket_port", default_port)
        return SocketTransport(host, int(port))
    raise ValueError(f"알 수 없는 run_mode: {run_mode!r}")
