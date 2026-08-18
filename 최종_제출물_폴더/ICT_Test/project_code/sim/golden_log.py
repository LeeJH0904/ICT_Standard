"""
sim/golden_log.py — 실측 로그가 없는 단계에서 `replay` 모드가 재생할
골든 벡터 기반 세션 로그를 만든다.

개발 착수 지시서 §3.6 "하지 않을 것": "`logs/`는 단계 8의 실측 캡처로
채운다. 그전까지는 **골든 벡터만 재생**한다." — 이 스크립트가 그 문장을
실제 파일로 만든다. 아키텍처 설계서 §5.3의 포맷(`{"t","dir","hex"}`)을
그대로 따른다.

합성 금지(CLAUDE.md §1-1)는 **페이로드 바이트**(센서값 등)에 적용된다.
이 로그의 수신 payload는 전부 `golden.jsonl` 원본 그대로다. 기대 응답은
골든 응답 payload를 쓰되 Message Identifier·GCG ID·Node ID를 바로 앞 RX와
결속한다(7.2.2). 서로 무관한 골든 Request/Response의 헤더를 그대로 나열하면
세션으로서는 성립하지 않기 때문이다. 새로 만드는 값은 재생 간격(`t`, 균일
카운터)뿐이다 — 실측 로그가 없어 원본 타이밍 정보 자체가 없으므로 균일
간격으로 대체했다는 점을 여기 명시한다. `dir`이
"양방향"(REQ_SET_NODE_PROPERTY 류, 표준상 방향이 고정되지 않은 8종)인
벡터는 rx/tx 어느 쪽으로 단정할 근거가 없어 기본 로그에서 제외한다.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = REPO_ROOT / "contracts" / "vectors" / "golden.jsonl"
DEFAULT_OUT = REPO_ROOT / "logs" / "session_00_golden.jsonl"

#: 골든 벡터 dir("N->G"/"G->N") -> 세션 로그 dir("rx"/"tx"). 아키텍처
#: 설계서 §5.3 — 게이트웨이 관점: 노드가 보낸 것(N->G)이 게이트웨이의
#: 수신(rx), 게이트웨이가 보낸 것(G->N)이 게이트웨이의 송신(tx).
#: "양방향"은 매핑하지 않는다(의도적 — 위 모듈 docstring 참조).
_DIR_MAP = {"N->G": "rx", "G->N": "tx"}

#: 기본 로그에 담을 골든 벡터 — 연결·주기 데이터·keep-alive·alert·해제까지
#: 기능 1(Plug & Play)과 기능 2(정상 판정) 경로를 골고루 보여주는 curated
#: 부분집합이다. 44건(judgement=normal/alert) 전부를 쓰면 기본 --speed
#: 1.0 에서 재생이 지나치게 길어진다 — 필요하면 `build(vector_ids=None)`
#: 으로 전량을 생성할 수 있다.
DEFAULT_VECTOR_IDS = [
    "N01",  # REQ_SET_CONNECTION — 노드 연결 요청
    "N34",  # NOTI_DEVICE_VALUE — 센서값 통지 (DEVICE_MAIN_INFO x2)
    "N09",  # NOTI_KEEP_ALIVE
    "N33",  # NOTI_ERROR — 정상 오류 알림(위반 아님)
    "X08",  # NOTI_ERROR — NEC=ERROR_BATTERY_LOW, judgement=alert(위반 아님, F-060)
    "N17",  # RES_SET_DEVICE_CONTROL — 제어 응답
    "N07",  # NOTI_DISCONNECT — 정상 연결 해제
]


def _default_session(by_id: dict[str, dict], interval: float) -> list[dict]:
    """기본 벡터를 실제 양방향 세션으로 결속한다(F-218).

    연결 응답의 본문은 런타임 기본 계약(Software Version=1, GCG/Node ID는
    요청값, NORMAL, N=0)으로 독립 구성하고 헤더는 N01과 상관관계를 맞춘다.
    이는 센서 합성값이 아니라 게이트웨이 회신의 고정 메타데이터다.
    Notify의 기대 출력은 같은 헤더 식별자를 가진 ACK다."""
    from sim import _wire as wire

    records: list[dict] = []
    t = 0.0
    for vid in DEFAULT_VECTOR_IDS:
        vector = by_id[vid]
        direction = _DIR_MAP.get(vector.get("dir"))
        if direction is None:
            continue
        records.append({"t": round(t, 3), "dir": direction, "hex": vector["hex"].upper()})
        t += interval
        if direction != "rx":
            continue

        header = vector["header"]
        response: bytes | None = None
        if vector["kind"] == "REQ_SET_CONNECTION":
            body = bytes([wire.RSC_SUCCESS]) + wire.encode_np(wire.WireNP(
                sw_version=1, gcg_id=header["GCG ID"], node_id=header["Node ID"],
                status=wire.STATUS_NORMAL, num_devices=0,
            ))
            response = wire.encode_header(wire.WireHeader(
                version=0x12, msg_type=wire.MT_RES_SET_CONNECTION,
                trans_type=header["Transmission Type"],
                msg_id=header["Message Identifier"], payload_len=len(body),
                gcg_id=header["GCG ID"], node_id=header["Node ID"],
            )) + body
        elif vector["kind"].startswith("NOTI_"):
            response = wire.encode_header(wire.WireHeader(
                version=0x12, msg_type=wire.MT_ACK,
                trans_type=header["Transmission Type"],
                msg_id=header["Message Identifier"], payload_len=0,
                gcg_id=header["GCG ID"], node_id=header["Node ID"],
            ))
        if response is not None:
            records.append({"t": round(t, 3), "dir": "tx", "hex": response.hex().upper()})
            t += interval
    return records


def build(vector_ids: list[str] | None = DEFAULT_VECTOR_IDS, interval: float = 1.0) -> list[dict]:
    """judgement=normal/alert 골든 벡터를 세션 로그 레코드 목록으로
    변환한다. `vector_ids=None` 이면 대상 전체(위반 8종 제외)를 쓴다."""
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        vectors = [json.loads(line) for line in f if line.strip()]
    by_id = {v["id"]: v for v in vectors}
    if vector_ids == DEFAULT_VECTOR_IDS:
        return _default_session(by_id, interval)
    if vector_ids is not None:
        vectors = [by_id[vid] for vid in vector_ids if vid in by_id]

    records: list[dict] = []
    t = 0.0
    for v in vectors:
        if v.get("judgement") not in ("normal", "alert"):
            continue
        d = _DIR_MAP.get(v.get("dir"))
        if d is None:
            continue
        records.append({"t": round(t, 3), "dir": d, "hex": v["hex"].upper()})
        t += interval
    return records


def write(out_path: Path = DEFAULT_OUT, vector_ids: list[str] | None = DEFAULT_VECTOR_IDS,
          interval: float = 1.0) -> Path:
    records = build(vector_ids, interval)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return out_path


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="sim/golden_log.py")
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--interval", type=float, default=1.0)
    p.add_argument("--all", action="store_true", help="curated 8건 대신 normal/alert 전량을 담는다")
    args = p.parse_args(argv)
    out = write(Path(args.out), vector_ids=None if args.all else DEFAULT_VECTOR_IDS,
                interval=args.interval)
    print(f"[golden_log] {out} 생성 완료")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
