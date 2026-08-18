"""siap/codec.py 검증 — 골든 벡터 53건 왕복 + Value 범위 검사.

C 호스트 테스트
(`firmware/tests/test_golden.c`)와 같은 골든 파일을 읽어, 같은 판정을
Python 쪽에서도 내리는지 확인한다 — 같은 명세서를 두 번 타이핑해 같은
결과가 나오는지가 교차 검증이다.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from contracts.frame import Frame, Header, MsgKind, RSC
from siap import codec

GOLDEN_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "contracts" / "vectors" / "golden.jsonl"


def _load_golden() -> list[dict]:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


GOLDEN = _load_golden()


def test_golden_count_53():
    assert len(GOLDEN) == 53


@pytest.mark.parametrize("vec", GOLDEN, ids=lambda v: v["id"])
def test_golden_vector(vec):
    data = bytes.fromhex(vec["hex"])

    node_known = None
    if vec.get("inject") == "unregistered_node":
        node_known = lambda nid: False           # noqa: E731 — 위반 케이스 2 재현
    elif vec["category"] == "위반":
        node_known = lambda nid: True             # 다른 위반 축을 node_known 이 가리지 않게

    frame = codec.decode_frame(data, "strict", node_known=node_known)

    if vec["judgement"] in ("normal", "alert"):
        assert not frame.violations, f"{vec['id']}: 예상치 못한 위반 {frame.violations}"
        assert frame.kind is not None and frame.kind.name == vec["kind"]
        reenc = codec.encode_frame(frame, "strict")
        assert reenc == data, f"{vec['id']}: 재인코딩이 원본과 다르다"
    elif vec["judgement"] == "violation":
        assert frame.violations, f"{vec['id']}: 위반이 검출되지 않았다"
        v = frame.violations[0]
        expect = vec["violations"][0]
        assert v.code == expect["code"]
        assert v.code_name == expect["code_name"]
        assert v.clause == expect["clause"]
    else:
        pytest.fail(f"{vec['id']}: 알 수 없는 judgement {vec['judgement']!r}")


def test_incomplete_header_returns_violation_frame_f215():
    data = b"\x12\x00"
    frame = codec.decode_frame(data, "strict")
    assert frame.header is None
    assert frame.kind is None
    assert frame.raw == data
    assert not frame.is_valid
    assert [v.code_name for v in frame.violations] == ["INVALID_FORMAT"]
    assert frame.violations[0].clause == "7.3.1"


def test_incomplete_payload_returns_violation_frame_f215():
    """완전한 헤더는 원본 의미값을 보존하되 없는 payload는 만들지 않는다."""
    # RES_SET_CONNECTION, N=1(payload_len=9+30=39, 유효한 N) 로 선언했지만
    # 실제로는 헤더 12byte 뿐이다 — element_count() 는 통과하지만 공개
    # 단발 디코드는 누락된 payload를 INVALID_FORMAT Frame으로 반환해야 한다.
    header = codec.encode_header(
        Header(version=0x12, msg_type=0x0400, trans_type=0, msg_id=1,
               payload_len=39, gcg_id=1, node_id=3)
    )
    frame = codec.decode_frame(header, "strict")
    assert frame.header is not None and frame.header.payload_len == 39
    assert frame.kind is MsgKind.RES_SET_CONNECTION
    assert frame.raw == header
    assert [v.code_name for v in frame.violations] == ["INVALID_FORMAT"]


def test_streaming_decoder_waits_for_incomplete_frame_f215():
    header = Header(version=0x12, msg_type=0x0C00, trans_type=0, msg_id=1,
                    payload_len=0, gcg_id=1, node_id=3)
    wire = codec.encode_header(header)
    decoder = codec.Decoder("strict")
    assert list(decoder.feed(wire[:2])) == []
    frames = list(decoder.feed(wire[2:]))
    assert len(frames) == 1
    assert frames[0].header == header
    assert frames[0].kind is MsgKind.ACK
    assert frames[0].is_valid


def test_encode_rejects_headerless_frame_f215():
    frame = Frame(header=None, kind=MsgKind.ACK, raw=b"\x12")
    with pytest.raises(codec.ValueRangeError):
        codec.encode_frame(frame)


# ── pack_value / unpack_value 경계값 ───────────────

def test_pack_int_boundaries():
    assert codec.pack_int(-(2 ** 31)) == 0x80000000
    assert codec.pack_int(-1) == 0xFFFFFFFF
    assert codec.pack_int(2 ** 31 - 1) == 0x7FFFFFFF
    with pytest.raises(codec.ValueRangeError):
        codec.pack_int(2 ** 31)
    with pytest.raises(codec.ValueRangeError):
        codec.pack_int(-(2 ** 31) - 1)


def test_pack_uint_boundaries():
    assert codec.pack_uint(0) == 0
    assert codec.pack_uint(2 ** 32 - 1) == 0xFFFFFFFF
    with pytest.raises(codec.ValueRangeError):
        codec.pack_uint(-1)
    with pytest.raises(codec.ValueRangeError):
        codec.pack_uint(2 ** 32)


def test_pack_integer_rejects_fractional_values_f214():
    for value in (1.5, -1.5):
        with pytest.raises(codec.ValueRangeError):
            codec.pack_int(value)
    with pytest.raises(codec.ValueRangeError):
        codec.pack_uint(1.5)


def test_pack_float_boundaries():
    assert codec.pack_float(25.3) == 0x41CA6666
    assert codec.pack_float(codec.FLOAT32_MAX) == 0x7F7FFFFF
    for bad in (float("inf"), float("-inf"), float("nan"), 1e39, -1e39, 10 ** 400):
        with pytest.raises(codec.ValueRangeError):
            codec.pack_float(bad)


def test_pack_value_conversion_failures_normalize_to_value_range_error():
    """OverflowError/ValueError/TypeError 가 전부 ValueRangeError 로
    정규화돼야 decode_frame() 이 예외 종류를 하나만 잡으면 된다."""
    for bad in ("abc", None):
        with pytest.raises(codec.ValueRangeError):
            codec.pack_float(bad)
        with pytest.raises(codec.ValueRangeError):
            codec.pack_int(bad if bad is not None else object())
    with pytest.raises(codec.ValueRangeError):
        codec.pack_int(float("inf"))


def test_unpack_type_separation():
    """동일 비트열이 타입에 따라 다른 값으로 해석돼야 한다."""
    assert codec.unpack_int(0xFFFFFFFF) == -1
    assert codec.unpack_uint(0xFFFFFFFF) == 4294967295


def test_bitwriter_rejects_out_of_range_without_partial_write():
    """범위 초과 시 아무것도 기록하지 않는다(마스킹 래핑 금지).
    bitpack.c 의 "실패 시 buf 도 *bitpos 도 바뀌지 않는다" 계약의 Python 대응."""
    w = codec.BitWriter(4)
    assert w.write(0xFF, 4) is False               # 4bit 에 0xFF 는 못 들어간다
    assert w.bitpos == 0
    assert bytes(w.buf) == b"\x00\x00\x00\x00"


def test_bitwriter_capacity_guard():
    w = codec.BitWriter(1)
    assert w.write(1, 8) is True
    assert w.write(1, 8) is False                   # 용량 초과 — 두 번째 바이트가 없다


# ── Decoder 재동기 ────────────────────────────────────────

def test_decoder_resync_preserves_trailing_valid_frame_after_header_violation_f140():
    """Version 위반처럼 payload_len 자체가 검증되지 않은 위반은
    그 값을 신뢰해 버퍼를 지우면 안 된다. Version=0x99·payload_len=0xFFFF
    인 위반 헤더 뒤에 정상 프레임이 바로 이어 붙어 있어도, 정상 프레임은
    살아남아야 한다(예전에는 위반 프레임의 payload_len 만큼 지워 24byte
    버퍼 전체가 삭제되고 정상 프레임이 사라졌다)."""
    from contracts.frame import Header

    bad = codec.encode_header(Header(version=0x99, msg_type=0x0803, trans_type=0,
                                      msg_id=1, payload_len=0xFFFF, gcg_id=1, node_id=3))
    good = codec.encode_header(Header(version=0x12, msg_type=0x0803, trans_type=0,
                                       msg_id=2, payload_len=0, gcg_id=1, node_id=3))

    dec = codec.Decoder("strict", node_known=lambda n: True)
    frames = list(dec.feed(bad + good))

    assert len(frames) == 2, f"위반 프레임 뒤 정상 프레임이 사라졌다: {len(frames)}건만 나옴"
    assert frames[0].violations and frames[0].violations[0].code_name == "INVALID_VERSION"
    assert not frames[1].violations
    assert frames[1].header.msg_id == 2


def _golden_bytes(vector_id: str) -> bytes:
    v = next(g for g in GOLDEN if g["id"] == vector_id)
    return bytes.fromhex(v["hex"])


def test_decoder_classifies_sequential_injected_violations_f146():
    """S4-b 순서(X01→X03→X05)를 한 스트림에
    이어 붙여 먹여도 셋 다 개별적으로 분류돼야 한다. 이전에는 X01 위반
    직후 재동기 모드에 들어간 뒤, X03·X05 자신의 헤더가 (각자의 위반
    때문에) 4조건 재동기 게이트를 통과하지 못해 노이즈로 오인되어
    1byte 씩 삼켜졌다(실측: msg_id [50]만 나오고 [52,54] 소실)."""
    stream = _golden_bytes("X01") + _golden_bytes("X03") + _golden_bytes("X05")

    dec = codec.Decoder("strict", node_known=lambda n: True)
    frames = list(dec.feed(stream))

    msg_ids = [f.header.msg_id for f in frames]
    assert 50 in msg_ids and 52 in msg_ids and 54 in msg_ids, (
        f"연속 주입 프레임이 소실됐다( 재발): msg_id={msg_ids}"
    )
    by_id = {f.header.msg_id: f for f in frames}
    assert [v.code_name for v in by_id[50].violations] == ["INVALID_VERSION"]
    assert [v.code_name for v in by_id[52].violations] == ["INVALID_FORMAT"]
    assert [v.code_name for v in by_id[54].violations] == ["INVALID_TRANSMISSION_TYPE"]


def test_decoder_resync_does_not_mistake_stray_version_byte_for_new_header_f151():
    """ 이 재동기 게이트를 Version 단독으로 완화한 뒤 생긴
    회귀. 위반 헤더( 에 따라 payload_len 을 신뢰하지 않고 헤더
    12byte 만 지운다)가 남긴 잔여 payload 바이트가 우연히 `0x12`
    (Version)이면, Version 단독 게이트가 그 지점을 새 헤더로 오인해
    뒤따르는 진짜 정상 프레임을 삼켰다(실측: msg_id 91 유실, 대신
    msg_id=3072 인 가짜 위반 프레임 발생). Node ID 조건을 더해 등록된
    노드가 아니면(그리고 나머지 구조도 유효하지 않으면) 후보를 거절하게
    고쳤다 — 오탐률이 1/256 에서 4조건 수준(약 2⁻²²)으로 돌아간다."""
    from contracts.frame import Header

    bad = codec.encode_header(Header(version=0x99, msg_type=0x0803, trans_type=0,
                                      msg_id=90, payload_len=1, gcg_id=1, node_id=3)) + b"\x12"
    good = codec.encode_header(Header(version=0x12, msg_type=0x0803, trans_type=0,
                                       msg_id=91, payload_len=0, gcg_id=1, node_id=3))

    dec = codec.Decoder("strict", node_known=lambda n: n == 3)
    frames = list(dec.feed(bad + good))

    msg_ids = [f.header.msg_id for f in frames]
    assert 91 in msg_ids, f"정상 프레임이 유실됐다( 재발): msg_id={msg_ids}"
    by_id = {f.header.msg_id: f for f in frames}
    assert by_id[90].violations[0].code_name == "INVALID_VERSION"
    assert not by_id[91].violations


def test_decoder_resync_still_classifies_unregistered_node_after_violation_f151():
    """ 수정이 X02(Node ID 만 미등록, 나머지 구조는 전부 정상)를
    다시 삼키지 않는지 확인한다 — Node ID 조건을 무조건 거부로 쓰면
    몽타주(X02 가 다른 위반 직후 연쇄 주입될 때)에서
    INVALID_NODE_ID 자체가 재동기 노이즈로 오인돼 사라진다. Node ID 만
    미등록이고 resolve_kind·Transmission Type·element_count 가 전부
    자기충족적으로 유효하면 후보로 인정해야 한다."""
    stream = _golden_bytes("X07") + _golden_bytes("X02")

    dec = codec.Decoder("strict", node_known=lambda n: n == 3)
    frames = list(dec.feed(stream))

    by_id = {f.header.msg_id: f for f in frames}
    assert 56 in by_id and 51 in by_id, (
        f"X02(Node ID 미등록)가 위반 직후 연쇄 주입될 때 유실됐다: {sorted(by_id)}"
    )
    assert [v.code_name for v in by_id[56].violations] == ["INVALID_DATA_SUBTYPE"]
    assert [v.code_name for v in by_id[51].violations] == ["INVALID_NODE_ID"]


def test_decoder_resync_recovers_frame_split_across_multiple_feeds_after_violation_f140():
    """같은 시나리오를 두 번의 feed() 호출로 나눠 넣어도(스트리밍 경계가
    프레임 중간에 걸려도) 정상 프레임을 잃지 않아야 한다."""
    from contracts.frame import Header

    bad = codec.encode_header(Header(version=0x99, msg_type=0x0803, trans_type=0,
                                      msg_id=1, payload_len=0xFFFF, gcg_id=1, node_id=3))
    good = codec.encode_header(Header(version=0x12, msg_type=0x0803, trans_type=0,
                                       msg_id=2, payload_len=0, gcg_id=1, node_id=3))
    stream = bad + good

    dec = codec.Decoder("strict", node_known=lambda n: True)
    frames = list(dec.feed(stream[:16])) + list(dec.feed(stream[16:]))

    assert len(frames) == 2
    assert frames[1].header.msg_id == 2
