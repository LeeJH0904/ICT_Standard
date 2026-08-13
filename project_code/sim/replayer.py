"""
sim/replayer.py — `replay` 모드 TCP 서버 (아키텍처 설계서 §5.3~§5.4).

`socket://127.0.0.1:5555`로 게이트웨이가 클라이언트로 접속하면, 로그
파일의 `dir=="rx"` 레코드만 원래 간격을 정규화해 그대로 흘려보낸다.

F-042 — `dir=="tx"` 레코드는 주입하지 않는다. 그 레코드는 "그 세션에서
게이트웨이가 실제로 보냈던 바이트"이지 재생 입력이 아니다(아키텍처
설계서 §5.4-a). 무시하면 과거의 `RES_SET_CONNECTION`이 현재 세션의
수신으로 들어와 `INVALID_NODE_ID` 같은 조작 없는 위반이 발생한다.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path


class Replayer:
    """단일 접속을 받아 로그 하나를 재생하고 끝나면 연결을 닫는다.
    `speed`>1 이면 그만큼 빨리 재생한다(`run.py --speed`)."""

    def __init__(self, log_path: str | Path, host: str = "127.0.0.1", port: int = 5555,
                 speed: float = 1.0) -> None:
        self._log_path = Path(log_path)
        self._host = host
        self._port = port
        self._speed = speed if speed > 0 else 1.0

        self._srv: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.done = threading.Event()      # 재생이 끝나면 set 된다(run.py 가 이걸로 종료 시점을 안다)
        self.stats = {"sent": 0, "skipped_tx": 0, "skipped_other": 0}

    def _load_rx(self) -> list[dict]:
        rx: list[dict] = []
        with open(self._log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                d = rec.get("dir")
                if d == "rx":                        # F-042 — 방향 필터가 먼저다
                    rx.append(rec)
                elif d == "tx":
                    self.stats["skipped_tx"] += 1
                else:
                    self.stats["skipped_other"] += 1
        return rx

    def start(self) -> None:
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self._host, self._port))
        self._srv.listen(1)
        self._srv.settimeout(0.5)
        self._thread = threading.Thread(target=self._accept_and_play, name="sim-replayer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._srv is not None:
            self._srv.close()
            self._srv = None

    def _accept_and_play(self) -> None:
        assert self._srv is not None
        conn = None
        while not self._stop.is_set() and conn is None:
            try:
                conn, _addr = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                return
        if conn is None:
            return
        try:
            self._play(conn)
            # 마지막 프레임을 보낸 직후 바로 close() 하면(그 다음 줄), 상대
            # 쪽 recv() 가 아직 커널 버퍼의 마지막 바이트를 읽지 않은
            # 상태에서 연결 종료 이벤트가 먼저 보일 수 있다(TIME_WAIT 이전
            # 구간의 경합 — 실측에서 마지막 레코드가 간헐적으로 유실됐다).
            # 소켓이 전달을 마칠 시간을 짧게 준다.
            time.sleep(0.2)
        finally:
            conn.close()
            self.done.set()

    def _play(self, conn: socket.socket) -> None:
        """§5.4 — `t`는 epoch 시각이다. 첫 레코드를 빼서 정규화하고
        `time.monotonic()`과 비교한다(`time.time()`을 쓰면 시스템 시계
        조정에 재생이 튄다)."""
        rx = self._load_rx()
        if not rx:
            return
        first_t = rx[0]["t"]
        start = time.monotonic()
        for rec in rx:
            if self._stop.is_set():
                return
            target = (rec["t"] - first_t) / self._speed
            wait = target - (time.monotonic() - start)
            if wait > 0:
                time.sleep(wait)
            try:
                conn.sendall(bytes.fromhex(rec["hex"]))
            except OSError:
                return
            self.stats["sent"] += 1


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="sim/replayer.py")
    p.add_argument("--log", required=True)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=5555)
    p.add_argument("--speed", type=float, default=1.0)
    args = p.parse_args(argv)

    r = Replayer(args.log, args.host, args.port, args.speed)
    r.start()
    print(f"[replayer] {args.log} 재생 대기 중 host={args.host} port={args.port} speed={args.speed}")
    try:
        r.done.wait()
        print(f"[replayer] 재생 완료: {r.stats}")
    except KeyboardInterrupt:
        pass
    finally:
        r.stop()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
