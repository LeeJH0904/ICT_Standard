"""
sim/replayer.py — `replay` 모드 TCP 서버.

`socket://127.0.0.1:5555`로 게이트웨이가 클라이언트로 접속하면, 로그
파일의 `dir=="rx"` 레코드는 원래 간격을 정규화해 그대로 흘려보내고,
`dir=="tx"` 레코드는 같은 시점의 게이트웨이 실제 송신과 바이트 대조한다.

`dir=="tx"` 레코드는 주입하지 않는다. 그 레코드는 "그 세션에서
게이트웨이가 실제로 보냈던 바이트"이지 재생 입력이 아니다. 무시하면 과거의 `RES_SET_CONNECTION`이 현재 세션의
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
                 speed: float = 1.0, tx_timeout: float = 2.0) -> None:
        self._log_path = Path(log_path)
        self._host = host
        self._port = port
        self._speed = speed if speed > 0 else 1.0
        self._tx_timeout = tx_timeout

        self._srv: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.done = threading.Event()      # 재생이 끝나면 set 된다(run.py 가 이걸로 종료 시점을 안다)
        self.error: Exception | None = None
        self.stats = {
            "sent": 0, "skipped_tx": 0, "skipped_other": 0,
            "expected_tx": 0, "matched_tx": 0, "mismatched_tx": 0,
        }

    def _load_records(self) -> list[dict]:
        records: list[dict] = []
        with open(self._log_path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if not isinstance(rec, dict):
                        raise ValueError("JSON object가 아님")
                    if not isinstance(rec.get("t"), (int, float)):
                        raise ValueError("t가 숫자가 아님")
                    if not isinstance(rec.get("hex"), str):
                        raise ValueError("hex가 문자열이 아님")
                    rec = dict(rec)
                    rec["_bytes"] = bytes.fromhex(rec["hex"])
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"{self._log_path.name}:{lineno}: {exc}") from exc
                d = rec.get("dir")
                if d == "rx":                        # tx는 주입하지 않는다
                    records.append(rec)
                elif d == "tx":
                    records.append(rec)
                    self.stats["skipped_tx"] += 1
                    self.stats["expected_tx"] += 1
                else:
                    self.stats["skipped_other"] += 1
        return records

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
            try:
                self._play(conn)
            except Exception as exc:
                # daemon 작업 스레드의 traceback은 호출자에게 전달되지
                # 않는다. 오류를 명시적으로 보관하고 done과 함께 공개한다.
                self.error = exc
            # 마지막 프레임을 보낸 직후 바로 close() 하면(그 다음 줄), 상대
            # 쪽 recv() 가 아직 커널 버퍼의 마지막 바이트를 읽지 않은
            # 상태에서 연결 종료 이벤트가 먼저 보일 수 있다(TIME_WAIT 이전
            # 구간의 경합 — 실측에서 마지막 레코드가 간헐적으로 유실됐다).
            # 소켓이 전달을 마칠 시간을 짧게 준다.
            if self.error is None:
                time.sleep(0.2)
        finally:
            conn.close()
            self.done.set()

    def _play(self, conn: socket.socket) -> None:
        """`t`는 epoch 시각이다. 첫 레코드를 빼서 정규화하고
        `time.monotonic()`과 비교한다(`time.time()`을 쓰면 시스템 시계
        조정에 재생이 튄다)."""
        records = self._load_records()
        if not records:
            return
        first_t = records[0]["t"]
        start = time.monotonic()
        for rec in records:
            if self._stop.is_set():
                return
            target = (rec["t"] - first_t) / self._speed
            wait = target - (time.monotonic() - start)
            if wait > 0:
                time.sleep(wait)
            if rec["dir"] == "rx":
                try:
                    conn.sendall(rec["_bytes"])
                except OSError as exc:
                    raise RuntimeError(f"rx 송신 실패: {exc}") from exc
                self.stats["sent"] += 1
            else:
                actual = self._recv_exact(conn, len(rec["_bytes"]))
                if actual != rec["_bytes"]:
                    self.stats["mismatched_tx"] += 1
                    raise ValueError(
                        f"tx 기대 출력 불일치: 기대={rec['_bytes'].hex().upper()} "
                        f"실제={actual.hex().upper()}"
                    )
                self.stats["matched_tx"] += 1
        self._reject_unexpected_tx(conn)

    def _recv_exact(self, conn: socket.socket, size: int) -> bytes:
        """게이트웨이 송신 스트림에서 기대 레코드 한 건의 길이만큼 읽는다."""
        data = bytearray()
        deadline = time.monotonic() + self._tx_timeout
        conn.settimeout(min(0.2, self._tx_timeout))
        while len(data) < size and not self._stop.is_set():
            if time.monotonic() >= deadline:
                break
            try:
                chunk = conn.recv(size - len(data))
            except socket.timeout:
                continue
            except OSError as exc:
                raise RuntimeError(f"tx 수신 실패: {exc}") from exc
            if not chunk:
                break
            data += chunk
        if len(data) != size:
            self.stats["mismatched_tx"] += 1
            raise ValueError(
                f"tx 기대 출력 길이 미달: 기대={size}byte 실제={len(data)}byte "
                f"({bytes(data).hex().upper()})"
            )
        return bytes(data)

    def _reject_unexpected_tx(self, conn: socket.socket) -> None:
        """로그에 대응 레코드가 없는 추가 게이트웨이 송신도 재현 실패다."""
        conn.settimeout(0.2)
        try:
            extra = conn.recv(1)
        except socket.timeout:
            return
        except OSError as exc:
            raise RuntimeError(f"추가 tx 확인 실패: {exc}") from exc
        if extra:
            self.stats["mismatched_tx"] += 1
            raise ValueError(f"로그에 없는 추가 tx 출력: {extra.hex().upper()}...")


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
    if r.error is not None:
        print(f"[replayer] 재생 실패: {r.error}")
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
