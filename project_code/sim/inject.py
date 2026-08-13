"""
sim/inject.py — 위반 프레임 주입 (시연 시나리오 §3.1 S4-b, 개발 착수 지시서 §3.6).

"주입은 실제 바이트를 바꾼다. 화면에 결과만 찍는 것이 아니라 `sim/inject.py`가
골든 벡터의 hex를 그대로 링크에 흘려보낸다. 영상 속 hex와 제출 `golden.jsonl`의
hex가 같아야 한다." — 시연 시나리오 §3.1.

허용 대상은 CLAUDE.md §6.3 위반 케이스 8종(`X01`~`X08`)뿐이다 — 자유
바이트열을 받으면 "주입 결과가 골든 벡터와 같다"는 기능 2의 판정 근거가
사라진다(F-084 처리 기록과 동일한 이유로 이 파일도 골든 ID로만 입력을
제한한다).

두 가지 쓰임:
  1. 라이브러리 — `inject(vector_id, sock)` 을 직접 호출한다. 이미 열린
     소켓(게이트웨이와 연결된 소켓)에 골든 벡터의 원본 바이트를 그대로
     쓴다. `sim/virtual_node.py`의 로컬 제어 채널과 단계 6의
     `POST /api/v1/sim/inject`(F-084) 가 둘 다 이 함수로 수렴한다.
  2. CLI — `python -m sim.inject --vector X03` 은 `virtual_node.py`의
     제어 채널(기본 포트 5557)에 접속해 `INJECT X03`을 보낸다. 터미널에서
     또는 시연 리허설에서 웹 버튼 없이 주입을 재현할 때 쓴다.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = REPO_ROOT / "contracts" / "vectors" / "golden.jsonl"

#: CLAUDE.md §6.3 — 기능 2가 판정하는 위반 케이스 8종. 이 집합 밖의 ID는
#: 거부한다(F-084 근거와 동일 — 임의 바이트열 주입 경로를 만들지 않는다).
ALLOWED_VECTORS = frozenset(f"X0{i}" for i in range(1, 9))


def _load_golden() -> dict[str, dict]:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return {v["id"]: v for v in (json.loads(line) for line in f if line.strip())}


def load_vector(vector_id: str) -> dict:
    """골든 벡터 레코드를 그대로 돌려준다. `X01`~`X08` 이외는 거부한다."""
    if vector_id not in ALLOWED_VECTORS:
        raise ValueError(f"허용되지 않은 벡터 ID: {vector_id!r} (X01~X08 만 허용)")
    vectors = _load_golden()
    if vector_id not in vectors:
        raise ValueError(f"golden.jsonl 에 {vector_id!r} 가 없음")
    return vectors[vector_id]


def vector_bytes(vector_id: str) -> bytes:
    """골든 벡터의 원본 hex 를 바이트로. 이 값이 곧 "영상 속 hex == 제출
    golden.jsonl 의 hex"라는 진위 대조의 근거다 — 여기서 한 바이트도
    가공하지 않는다."""
    v = load_vector(vector_id)
    return bytes.fromhex(v["hex"])


def inject(vector_id: str, sock: socket.socket) -> bytes:
    """골든 벡터의 원본 바이트를 이미 연결된 소켓에 그대로 쓴다.
    반환값은 실제로 보낸 바이트(로깅·검증용)."""
    data = vector_bytes(vector_id)
    sock.sendall(data)
    return data


def _cli_inject(vector_id: str, host: str, control_port: int, timeout: float = 3.0) -> str:
    """`virtual_node.py`의 로컬 제어 채널에 `INJECT <id>`를 보내고 회신
    한 줄을 돌려준다."""
    with socket.create_connection((host, control_port), timeout=timeout) as s:
        s.sendall(f"INJECT {vector_id}\n".encode("ascii"))
        s.settimeout(timeout)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(256)
            if not chunk:
                break
            buf += chunk
        return buf.decode("ascii", "replace").strip()


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="sim/inject.py",
                                 description="골든 벡터 위반 8종을 실행 중인 virtual_node.py 에 주입한다")
    p.add_argument("--vector", required=True, choices=sorted(ALLOWED_VECTORS),
                    help="주입할 골든 벡터 ID (X01~X08)")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--control-port", type=int, default=5557,
                    help="virtual_node.py 의 로컬 제어 채널 포트")
    args = p.parse_args(argv)

    try:
        reply = _cli_inject(args.vector, args.host, args.control_port)
    except OSError as e:
        print(f"[inject] 제어 채널 접속 실패: {e} "
              f"(virtual_node.py 가 --control-port {args.control_port} 로 실행 중인지 확인)")
        return 1
    print(f"[inject] {args.vector} -> {reply}")
    return 0 if reply.startswith("OK") else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
